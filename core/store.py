from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .log import logger
from .models import (
    MemoryRecord,
    Persona,
    TimelineEvent,
    clean_text,
    json_dumps,
    json_loads,
    new_id,
    utc_now,
)

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoryStore:
    """SQLite 存储层：记忆、人格、用户、时间线、向量、导入批次、注入日志。"""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.RLock()
        self._fts_trigram = False
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ------------------------------------------------------------------ schema

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT, content TEXT, summary TEXT, tags TEXT,
                    importance REAL, base_importance REAL, weight_factors TEXT, confidence REAL,
                    subject_kind TEXT, subject_id TEXT, subject_name TEXT, subject_role TEXT,
                    subject_verified INTEGER, subject_verified_by TEXT, subject_verified_at TEXT,
                    object_kind TEXT, object_id TEXT, object_name TEXT, object_role TEXT,
                    object_verified INTEGER, object_verified_by TEXT, object_verified_at TEXT,
                    scope TEXT, persona_id TEXT, platform TEXT, session_id TEXT,
                    user_id TEXT, user_name TEXT, group_id TEXT, group_name TEXT, bot_id TEXT,
                    lifecycle TEXT, visibility TEXT, source TEXT, source_plugin TEXT, message_id TEXT,
                    created_at TEXT, updated_at TEXT, occurred_at TEXT,
                    last_accessed_at TEXT, access_count INTEGER,
                    import_batch_id TEXT, supersedes_id TEXT, merged_count INTEGER,
                    content_fingerprint TEXT, metadata TEXT
                )
                """
            )
            for sql in (
                "CREATE INDEX IF NOT EXISTS idx_mem_persona ON memories(persona_id)",
                "CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(scope)",
                "CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_mem_group ON memories(group_id)",
                "CREATE INDEX IF NOT EXISTS idx_mem_lifecycle ON memories(lifecycle)",
                "CREATE INDEX IF NOT EXISTS idx_mem_fingerprint ON memories(content_fingerprint)",
                "CREATE INDEX IF NOT EXISTS idx_mem_updated ON memories(updated_at)",
                "CREATE INDEX IF NOT EXISTS idx_mem_occurred ON memories(occurred_at)",
            ):
                cur.execute(sql)
            try:
                cur.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5("
                    "memory_id UNINDEXED, content, summary, tags, tokenize='trigram'"
                    ")"
                )
                self._fts_trigram = True
            except Exception:
                cur.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5("
                    "memory_id UNINDEXED, content, summary, tags, tokenize='unicode61'"
                    ")"
                )
                self._fts_trigram = False
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS personas (
                    persona_id TEXT PRIMARY KEY,
                    name TEXT, description TEXT, enabled INTEGER, is_default INTEGER,
                    created_at TEXT, updated_at TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_key TEXT PRIMARY KEY,
                    user_id TEXT, name TEXT, platform TEXT, persona_id TEXT,
                    extra TEXT, first_seen TEXT, last_seen TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS timeline (
                    id TEXT PRIMARY KEY,
                    session_id TEXT, scope TEXT, platform TEXT,
                    user_id TEXT, user_name TEXT, group_id TEXT, group_name TEXT,
                    bot_id TEXT, persona_id TEXT, role TEXT, content TEXT,
                    occurred_at TEXT, message_id TEXT, summarized INTEGER,
                    summary_memory_id TEXT, import_batch_id TEXT, is_system INTEGER DEFAULT 0,
                    kind TEXT DEFAULT ''
                )
                """
            )
            for sql in (
                "CREATE INDEX IF NOT EXISTS idx_tl_session ON timeline(session_id, summarized)",
                "CREATE INDEX IF NOT EXISTS idx_tl_persona ON timeline(persona_id)",
            ):
                cur.execute(sql)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    memory_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    dim INTEGER,
                    vector TEXT,
                    text_hash TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (memory_id, provider_id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS import_batches (
                    batch_id TEXT PRIMARY KEY,
                    filename TEXT, status TEXT, total INTEGER, imported INTEGER,
                    skipped INTEGER, params TEXT, created_at TEXT, completed_at TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS injection_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT, session_id TEXT, scope TEXT, query TEXT,
                    selected_memory_ids TEXT, blocked TEXT, injection_chars INTEGER
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT
                )
                """
            )
            version = self.get_setting("schema_version")
            if version is None:
                self.set_setting("schema_version", str(SCHEMA_VERSION))
            self._conn.commit()
        self._migrate_timeline_system_column()

    def _migrate_timeline_system_column(self) -> None:
        """旧库补充 is_system / kind 列。"""
        try:
            with self._lock:
                cols = [row[1] for row in self._conn.execute("PRAGMA table_info(timeline)")]
                if "is_system" not in cols:
                    self._conn.execute("ALTER TABLE timeline ADD COLUMN is_system INTEGER DEFAULT 0")
                if "kind" not in cols:
                    self._conn.execute("ALTER TABLE timeline ADD COLUMN kind TEXT DEFAULT ''")
                self._conn.commit()
        except Exception as exc:
            logger.warning("[DeepMemory] 迁移时间线列失败: %s", exc)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def backup(self, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._conn.commit()
            backup = self._conn.cursor()
            backup.execute(f"VACUUM INTO ?", (str(dest),))
        return dest

    # ------------------------------------------------------------------ settings

    def get_setting(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()

    # ------------------------------------------------------------------ personas

    def list_personas(self) -> list[Persona]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM personas ORDER BY is_default DESC, created_at ASC").fetchall()
        return [self._persona_from_row(row) for row in rows]

    def get_persona(self, persona_id: str) -> Persona | None:
        persona_id = clean_text(persona_id, 80)
        if not persona_id:
            return None
        with self._lock:
            row = self._conn.execute("SELECT * FROM personas WHERE persona_id=?", (persona_id,)).fetchone()
        return self._persona_from_row(row) if row else None

    def upsert_persona(self, persona: Persona) -> Persona:
        persona.persona_id = clean_text(persona.persona_id, 80) or new_id("persona")
        persona.name = clean_text(persona.name, 80) or persona.persona_id
        persona.description = clean_text(persona.description, 2000)
        now = _now()
        persona.updated_at = now
        if not persona.created_at:
            persona.created_at = now
        with self._lock:
            self._conn.execute(
                "INSERT INTO personas(persona_id, name, description, enabled, is_default, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(persona_id) DO UPDATE SET name=excluded.name, description=excluded.description, "
                "enabled=excluded.enabled, is_default=excluded.is_default, updated_at=excluded.updated_at",
                (
                    persona.persona_id, persona.name, persona.description,
                    int(persona.enabled), int(persona.is_default),
                    persona.created_at, persona.updated_at,
                ),
            )
            self._conn.commit()
        return persona

    def ensure_default_persona(self, persona_id: str, name: str = "") -> Persona:
        existing = self.get_persona(persona_id)
        if existing:
            return existing
        return self.upsert_persona(
            Persona(
                persona_id=persona_id,
                name=clean_text(name, 80) or persona_id,
                description="默认人格",
                enabled=True,
                is_default=True,
            )
        )

    def set_default_persona(self, persona_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE personas SET is_default=0")
            self._conn.execute("UPDATE personas SET is_default=1 WHERE persona_id=?", (persona_id,))
            self._conn.commit()

    def delete_persona(self, persona_id: str) -> int:
        """删除人格及其全部记忆。返回删除的记忆条数。"""
        persona_id = clean_text(persona_id, 80)
        if not persona_id:
            return 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM memories WHERE persona_id=?", (persona_id,)
            ).fetchall()
            ids = [row["id"] for row in rows]
            count = len(ids)
            if ids:
                placeholders = ", ".join("?" for _ in ids)
                self._conn.execute(
                    f"DELETE FROM memories_fts WHERE memory_id IN ({placeholders})", ids
                )
                self._conn.execute(
                    f"DELETE FROM memories WHERE id IN ({placeholders})", ids
                )
                self._conn.execute(
                    f"DELETE FROM embeddings WHERE memory_id IN ({placeholders})", ids
                )
            self._conn.execute("DELETE FROM personas WHERE persona_id=?", (persona_id,))
            self._conn.commit()
        return count

    @staticmethod
    def _persona_from_row(row: Any) -> Persona:
        return Persona(
            persona_id=row["persona_id"],
            name=row["name"],
            description=row["description"],
            enabled=bool(row["enabled"]),
            is_default=bool(row["is_default"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------------ users

    def upsert_user(
        self,
        *,
        user_key: str,
        user_id: str,
        name: str = "",
        platform: str = "",
        persona_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        user_key = clean_text(user_key, 200)
        if not user_key:
            return
        now = _now()
        with self._lock:
            existing = self._conn.execute("SELECT * FROM users WHERE user_key=?", (user_key,)).fetchone()
            if existing:
                self._conn.execute(
                    "UPDATE users SET user_id=?, name=COALESCE(NULLIF(?, ''), name), platform=COALESCE(NULLIF(?, ''), platform), "
                    "persona_id=COALESCE(NULLIF(?, ''), persona_id), extra=?, last_seen=? WHERE user_key=?",
                    (
                        clean_text(user_id, 120), clean_text(name, 80), clean_text(platform, 80),
                        clean_text(persona_id, 80), json_dumps(extra or {}), now, user_key,
                    ),
                )
            else:
                self._conn.execute(
                    "INSERT INTO users(user_key, user_id, name, platform, persona_id, extra, first_seen, last_seen) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (
                        user_key, clean_text(user_id, 120), clean_text(name, 80),
                        clean_text(platform, 80), clean_text(persona_id, 80),
                        json_dumps(extra or {}), now, now,
                    ),
                )
            self._conn.commit()

    def list_users(self, limit: int = 200, offset: int = 0, query: str = "") -> list[dict[str, Any]]:
        with self._lock:
            if query:
                like = f"%{clean_text(query, 100)}%"
                rows = self._conn.execute(
                    "SELECT * FROM users WHERE user_id LIKE ? OR name LIKE ? OR user_key LIKE ? "
                    "ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                    (like, like, like, limit, offset),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM users ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [self._user_to_dict(row) for row in rows]

    def get_user(self, user_key: str) -> dict[str, Any] | None:
        user_key = clean_text(user_key, 200)
        if not user_key:
            return None
        with self._lock:
            row = self._conn.execute("SELECT * FROM users WHERE user_key=?", (user_key,)).fetchone()
        return self._user_to_dict(row) if row else None

    def delete_user(self, user_key: str) -> int:
        """删除用户及其归属的私聊记忆。返回删除的记忆条数。"""
        user_key = clean_text(user_key, 200)
        if not user_key:
            return 0
        with self._lock:
            user = self._conn.execute("SELECT * FROM users WHERE user_key=?", (user_key,)).fetchone()
            count = 0
            if user:
                count = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM memories WHERE user_id=? AND scope='private'",
                    (user["user_id"],),
                ).fetchone()["c"]
                self._conn.execute(
                    "DELETE FROM memories WHERE user_id=? AND scope='private'", (user["user_id"],)
                )
            self._conn.execute("DELETE FROM users WHERE user_key=?", (user_key,))
            self._conn.execute("DELETE FROM memories_fts WHERE memory_id NOT IN (SELECT id FROM memories)")
            self._conn.execute("DELETE FROM embeddings WHERE memory_id NOT IN (SELECT id FROM memories)")
            self._conn.commit()
        return int(count or 0)

    def set_user_persona(self, user_key: str, persona_id: str) -> None:
        """为用户绑定人格（不存在则创建用户记录）。"""
        user_key = clean_text(user_key, 200)
        persona_id = clean_text(persona_id, 80)
        if not user_key:
            return
        user_id = user_key.split(":", 1)[-1] if ":" in user_key else user_key
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO users(user_key, user_id, name, platform, persona_id, extra, first_seen, last_seen) "
                "VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(user_key) DO UPDATE SET persona_id=excluded.persona_id, last_seen=excluded.last_seen",
                (user_key, user_id, "", "", persona_id, "{}", now, now),
            )
            self._conn.commit()

    @staticmethod
    def _user_to_dict(row: Any) -> dict[str, Any]:
        return {
            "user_key": row["user_key"],
            "user_id": row["user_id"],
            "name": row["name"],
            "platform": row["platform"],
            "persona_id": row["persona_id"],
            "extra": json_loads(row["extra"], {}),
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
        }

    # ------------------------------------------------------------------ memories

    def upsert_memory(self, record: MemoryRecord) -> MemoryRecord:
        record.ensure_defaults()
        data = record.to_db()
        columns = list(data.keys())
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{col}=excluded.{col}" for col in columns if col != "id")
        with self._lock:
            self._conn.execute(
                f"INSERT INTO memories({', '.join(columns)}) VALUES({placeholders}) "
                f"ON CONFLICT(id) DO UPDATE SET {updates}",
                [data[col] for col in columns],
            )
            self._conn.execute("DELETE FROM memories_fts WHERE memory_id=?", (record.id,))
            self._conn.execute(
                "INSERT INTO memories_fts(memory_id, content, summary, tags) VALUES(?,?,?,?)",
                (record.id, record.content, record.summary, " ".join(record.tags)),
            )
            self._conn.commit()
        return record

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        memory_id = clean_text(memory_id, 120)
        if not memory_id:
            return None
        with self._lock:
            row = self._conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return MemoryRecord.from_row(row) if row else None

    def get_memories_by_ids(self, memory_ids: Iterable[str]) -> dict[str, MemoryRecord]:
        ids = [clean_text(mid, 120) for mid in memory_ids if clean_text(mid, 120)]
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})", ids
            ).fetchall()
        return {row["id"]: MemoryRecord.from_row(row) for row in rows}

    def list_memories(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        query: str = "",
        memory_type: str = "",
        scope: str = "",
        persona_id: str = "",
        user_id: str = "",
        group_id: str = "",
        lifecycle: str = "",
        visibility: str = "",
        session_id: str = "",
        source: str = "",
        order_by: str = "updated_at DESC",
    ) -> list[MemoryRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if query:
            clauses.append("(content LIKE ? OR summary LIKE ? OR tags LIKE ?)")
            like = f"%{clean_text(query, 200)}%"
            params.extend([like, like, like])
        for column, value in (
            ("memory_type", memory_type), ("scope", scope), ("persona_id", persona_id),
            ("user_id", user_id), ("group_id", group_id), ("lifecycle", lifecycle),
            ("visibility", visibility), ("session_id", session_id), ("source", source),
        ):
            if value:
                clauses.append(f"{column}=?")
                params.append(clean_text(value, 200))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = clean_text(order_by, 80) or "updated_at DESC"
        if not re_safe_order(order):
            order = "updated_at DESC"
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM memories {where} ORDER BY {order} LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
        return [MemoryRecord.from_row(row) for row in rows]

    def count_memories_filtered(
        self,
        *,
        query: str = "",
        memory_type: str = "",
        scope: str = "",
        persona_id: str = "",
        user_id: str = "",
        group_id: str = "",
        lifecycle: str = "",
        visibility: str = "",
        session_id: str = "",
        source: str = "",
    ) -> int:
        """与 list_memories 相同过滤条件下的总数（分页用）。"""
        clauses: list[str] = []
        params: list[Any] = []
        if query:
            clauses.append("(content LIKE ? OR summary LIKE ? OR tags LIKE ?)")
            like = f"%{clean_text(query, 200)}%"
            params.extend([like, like, like])
        for column, value in (
            ("memory_type", memory_type), ("scope", scope), ("persona_id", persona_id),
            ("user_id", user_id), ("group_id", group_id), ("lifecycle", lifecycle),
            ("visibility", visibility), ("session_id", session_id), ("source", source),
        ):
            if value:
                clauses.append(f"{column}=?")
                params.append(clean_text(value, 200))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) AS c FROM memories {where}", params
            ).fetchone()
        return int(row["c"] or 0)

    def count_memories(self, *, lifecycle: str = "") -> int:
        with self._lock:
            if lifecycle:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM memories WHERE lifecycle=?", (lifecycle,)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
        return int(row["c"] or 0)

    def find_duplicate(self, record: MemoryRecord) -> MemoryRecord | None:
        """按内容指纹查找同人格、同用户下的已有记忆。"""
        record.ensure_defaults()
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memories WHERE content_fingerprint=? AND persona_id=? AND lifecycle='active' "
                "ORDER BY updated_at DESC LIMIT 1",
                (record.content_fingerprint, record.persona_id),
            ).fetchone()
        return MemoryRecord.from_row(row) if row else None

    def delete_memory(self, memory_id: str) -> bool:
        memory_id = clean_text(memory_id, 120)
        if not memory_id:
            return False
        with self._lock:
            cur = self._conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            self._conn.execute("DELETE FROM memories_fts WHERE memory_id=?", (memory_id,))
            self._conn.execute("DELETE FROM embeddings WHERE memory_id=?", (memory_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def update_memory_fields(self, memory_id: str, **fields: Any) -> bool:
        """按白名单更新记忆字段。"""
        memory_id = clean_text(memory_id, 120)
        if not memory_id:
            return False
        allowed = {
            "memory_type", "content", "summary", "tags", "importance", "base_importance",
            "confidence", "scope", "persona_id", "lifecycle", "visibility", "metadata",
            "weight_factors", "user_id", "user_name", "group_id", "group_name",
            "occurred_at",
        }
        updates: dict[str, Any] = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if not updates:
            return False
        record = self.get_memory(memory_id)
        if not record:
            return False
        for key, value in updates.items():
            if key == "tags":
                record.tags = [clean_text(tag, 80) for tag in value]
            elif key == "metadata":
                # 整体替换语义：调用方负责基于旧值组装完整 metadata
                record.metadata = value if isinstance(value, dict) else {}
            elif key == "weight_factors":
                record.weight_factors = value if isinstance(value, dict) else {}
            elif key in ("importance", "base_importance", "confidence"):
                try:
                    setattr(record, key, max(0.0, min(1.0, float(value))))
                except Exception:
                    pass
            else:
                setattr(record, key, clean_text(value, 2000) if isinstance(getattr(record, key), str) else value)
        record.updated_at = _now()
        self.upsert_memory(record)
        return True

    def touch_memory(self, memory_id: str) -> None:
        """召回后更新访问时间与次数。"""
        memory_id = clean_text(memory_id, 120)
        if not memory_id:
            return
        with self._lock:
            self._conn.execute(
                "UPDATE memories SET last_accessed_at=?, access_count=access_count+1 WHERE id=?",
                (_now(), memory_id),
            )
            self._conn.commit()

    def batch_touch_memories(self, memory_ids: Iterable[str]) -> None:
        ids = [clean_text(mid, 120) for mid in memory_ids if clean_text(mid, 120)]
        if not ids:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE memories SET last_accessed_at=?, access_count=access_count+1 WHERE id=?",
                [(_now(), mid) for mid in ids],
            )
            self._conn.commit()

    def mark_superseded(self, old_ids: Iterable[str], new_id: str) -> None:
        ids = [clean_text(mid, 120) for mid in old_ids if clean_text(mid, 120)]
        if not ids:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE memories SET lifecycle='archived', supersedes_id=?, updated_at=? WHERE id=?",
                [(new_id, _now(), mid) for mid in ids],
            )
            self._conn.commit()

    def list_decay_candidates(
        self,
        *,
        after_days: int,
        idle_days: int,
        max_importance: float,
        max_access_count: int,
        limit: int,
    ) -> list[MemoryRecord]:
        import time
        now = time.time()
        cutoff_age = now - after_days * 86400
        cutoff_idle = now - idle_days * 86400
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE lifecycle='active'
                  AND importance <= ?
                  AND access_count <= ?
                  AND CAST(strftime('%s', created_at) AS INTEGER) <= ?
                  AND (last_accessed_at = '' OR CAST(strftime('%s', last_accessed_at) AS INTEGER) <= ?)
                ORDER BY importance ASC, created_at ASC
                LIMIT ?
                """,
                (max_importance, max_access_count, cutoff_age, cutoff_idle, limit),
            ).fetchall()
        return [MemoryRecord.from_row(row) for row in rows]

    def decay_records(
        self,
        *,
        mode: str,
        memory_ids: Iterable[str],
        summary_memory_id: str = "",
    ) -> int:
        ids = [clean_text(mid, 120) for mid in memory_ids if clean_text(mid, 120)]
        if not ids:
            return 0
        with self._lock:
            if mode == "delete":
                placeholders = ", ".join("?" for _ in ids)
                self._conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)
                self._conn.execute(f"DELETE FROM memories_fts WHERE memory_id IN ({placeholders})", ids)
                self._conn.execute(f"DELETE FROM embeddings WHERE memory_id IN ({placeholders})", ids)
            else:
                self._conn.executemany(
                    "UPDATE memories SET lifecycle='decayed', supersedes_id=?, updated_at=? WHERE id=?",
                    [(summary_memory_id, _now(), mid) for mid in ids],
                )
            self._conn.commit()
        return len(ids)

    # ------------------------------------------------------------------ FTS

    def fts_search(self, query: str, *, limit: int = 50) -> list[tuple[MemoryRecord, float]]:
        """FTS5 关键词检索，返回 (记录, bm25 得分) 列表。"""
        query = clean_text(query, 500)
        if not query:
            return []
        tokens = [token for token in query.split() if token]
        if not tokens:
            return []
        # trigram 分词器要求每个词至少 3 个字符；短词交给 LIKE 兜底。
        # CJK 连续串按 3 字滑动窗口拆分为多个短语做 OR，实现子串召回。
        def _has_cjk(value: str) -> bool:
            return any("\u4e00" <= ch <= "\u9fff" for ch in value)

        parts: list[str] = []
        for token in tokens:
            if self._fts_trigram and _has_cjk(token) and len(token) >= 3:
                parts.extend(f'"{token[i:i + 3]}"' for i in range(len(token) - 2))
            else:
                parts.append(f'"{token}"')
        if not parts:
            return []
        fts_query = " OR ".join(parts)
        try:
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT m.*, bm25(memories_fts) AS rank_score
                    FROM memories_fts
                    JOIN memories m ON m.id = memories_fts.memory_id
                    WHERE memories_fts MATCH ?
                    ORDER BY rank_score
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
        except Exception:
            return []
        results: list[tuple[MemoryRecord, float]] = []
        for row in rows:
            record = MemoryRecord.from_row(row)
            score = 1.0 / (1.0 + abs(float(row["rank_score"] or 0.0)))
            results.append((record, score))
        return results

    def like_search(self, query: str, *, limit: int = 50) -> list[MemoryRecord]:
        """多列 LIKE 兜底检索。"""
        query = clean_text(query, 200)
        if not query:
            return []
        like = f"%{query}%"
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE content LIKE ? OR summary LIKE ? OR tags LIKE ?
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        return [MemoryRecord.from_row(row) for row in rows]

    # ------------------------------------------------------------------ embeddings

    def upsert_embedding(self, memory_id: str, provider_id: str, vector: list[float], text_hash: str) -> None:
        memory_id = clean_text(memory_id, 120)
        provider_id = clean_text(provider_id, 120)
        if not memory_id or not provider_id or not vector:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO embeddings(memory_id, provider_id, dim, vector, text_hash, updated_at) "
                "VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(memory_id, provider_id) DO UPDATE SET "
                "dim=excluded.dim, vector=excluded.vector, text_hash=excluded.text_hash, updated_at=excluded.updated_at",
                (memory_id, provider_id, len(vector), json_dumps(vector), text_hash, _now()),
            )
            self._conn.commit()

    def get_embedding(self, memory_id: str, provider_id: str) -> list[float] | None:
        memory_id = clean_text(memory_id, 120)
        provider_id = clean_text(provider_id, 120)
        if not memory_id or not provider_id:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT vector FROM embeddings WHERE memory_id=? AND provider_id=?", (memory_id, provider_id)
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["vector"])
            return [float(item) for item in data] if isinstance(data, list) else None
        except Exception:
            return None

    def list_memories_without_embedding(self, provider_id: str, limit: int = 50) -> list[MemoryRecord]:
        provider_id = clean_text(provider_id, 120)
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE lifecycle='active'
                  AND id NOT IN (
                      SELECT memory_id FROM embeddings WHERE provider_id=?
                  )
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (provider_id, limit),
            ).fetchall()
        return [MemoryRecord.from_row(row) for row in rows]

    def iter_memory_embeddings(
        self, provider_id: str, *, limit: int = 0, pool_first: bool = True
    ) -> list[tuple[MemoryRecord, list[float]]]:
        """按候选池读取记忆向量（0.79 性能修复）。

        - pool_first=True（默认）：按 重要度 DESC, 创建时间 DESC 有序截断（预池），
          避免「读取全量向量再机械截断」——记忆 5 万条时读取行数恒定在候选池规模，
          延迟不再随记忆总量线性增长；低重要度旧记忆仍由 FTS 关键词通道兜底召回；
        - limit=0 表示全量（导入/导出等管理路径使用）。
        """
        provider_id = clean_text(provider_id, 120)
        sql = """
            SELECT m.*, e.vector
            FROM memories m
            JOIN embeddings e ON e.memory_id = m.id
            WHERE e.provider_id=? AND m.lifecycle='active'
            """
        params: list[Any] = [provider_id]
        if pool_first and limit > 0:
            sql += " ORDER BY m.importance DESC, m.created_at DESC LIMIT ?"
            params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        results: list[tuple[MemoryRecord, list[float]]] = []
        for row in rows:
            try:
                vector = json.loads(row["vector"])
            except Exception:
                continue
            if isinstance(vector, list) and vector:
                results.append((MemoryRecord.from_row(row), [float(item) for item in vector]))
        return results

    def embedding_memory_ids_count(self, provider_id: str) -> int:
        provider_id = clean_text(provider_id, 120)
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM embeddings WHERE provider_id=?", (provider_id,)
            ).fetchone()
        return int(row["c"] or 0)

    # ------------------------------------------------------------------ timeline

    def add_timeline_event(self, event: TimelineEvent) -> TimelineEvent:
        event.id = clean_text(event.id, 120) or new_id("tl")
        event.occurred_at = event.occurred_at or _now()
        event.content = clean_text(event.content, 4000)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO timeline("
                "id, session_id, scope, platform, user_id, user_name, group_id, group_name, "
                "bot_id, persona_id, role, content, occurred_at, message_id, summarized, "
                "summary_memory_id, import_batch_id, is_system, kind) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event.id, event.session_id, event.scope, event.platform,
                    event.user_id, event.user_name, event.group_id, event.group_name,
                    event.bot_id, event.persona_id, event.role, event.content,
                    event.occurred_at, event.message_id, int(event.summarized),
                    event.summary_memory_id, event.import_batch_id, int(event.is_system),
                    event.kind or "",
                ),
            )
            self._conn.commit()
        return event

    def timeline_duplicate(self, session_id: str, message_id: str) -> bool:
        """同一会话同一消息 ID 是否已记录（群聊捕获与主链捕获去重用）。"""
        session_id = clean_text(session_id, 200)
        message_id = clean_text(message_id, 120)
        if not session_id or not message_id:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM timeline WHERE session_id=? AND message_id=? LIMIT 1",
                (session_id, message_id),
            ).fetchone()
        return row is not None

    def delete_timeline_events(self, ids: list[str]) -> int:
        """删除指定时间线事件。返回删除条数。"""
        ids = [clean_text(eid, 120) for eid in ids if clean_text(eid, 120)]
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM timeline WHERE id IN ({placeholders})", ids
            )
            self._conn.commit()
        return cur.rowcount

    def delete_timeline_by_message_id(self, message_id: str, *, summarized_only: bool = False) -> int:
        """按消息 ID 删除时间线事件（消息撤回用）。

        默认只删除未总结的事件（已总结进记忆的无法回滚）；bot 回复事件与
        对应用户消息共用同一 message_id，会一并删除。
        """
        message_id = clean_text(message_id, 120)
        if not message_id:
            return 0
        clause = "message_id=?"
        if summarized_only:
            clause += " AND summarized=1"
        else:
            clause += " AND summarized=0"
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM timeline WHERE {clause}", (message_id,)
            )
            self._conn.commit()
        return cur.rowcount

    def recent_timeline(self, *, limit: int = 30, offset: int = 0, session_id: str = "", scope: str = "", persona_id: str = "") -> list[TimelineEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id=?")
            params.append(clean_text(session_id, 200))
        if scope:
            clauses.append("scope=?")
            params.append(clean_text(scope, 40))
        if persona_id:
            clauses.append("persona_id=?")
            params.append(clean_text(persona_id, 80))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM timeline {where} ORDER BY occurred_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
        return [TimelineEvent.from_row(row) for row in rows]

    def unsummarized_timeline(
        self,
        *,
        session_id: str = "",
        persona_id: str = "",
        limit: int = 50,
    ) -> list[TimelineEvent]:
        clauses: list[str] = ["summarized=0", "is_system=0"]
        params: list[Any] = []
        if session_id:
            clauses.append("session_id=?")
            params.append(clean_text(session_id, 200))
        if persona_id:
            clauses.append("persona_id=?")
            params.append(clean_text(persona_id, 80))
        where = " AND ".join(clauses)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM timeline WHERE {where} ORDER BY occurred_at ASC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [TimelineEvent.from_row(row) for row in rows]

    def count_unsummarized(self, *, session_id: str = "", persona_id: str = "") -> int:
        clauses: list[str] = ["summarized=0", "is_system=0"]
        params: list[Any] = []
        if session_id:
            clauses.append("session_id=?")
            params.append(clean_text(session_id, 200))
        if persona_id:
            clauses.append("persona_id=?")
            params.append(clean_text(persona_id, 80))
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) AS c FROM timeline WHERE {' AND '.join(clauses)}", params
            ).fetchone()
        return int(row["c"] or 0)

    def earliest_unsummarized_at(self, *, session_id: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(occurred_at) AS m FROM timeline WHERE summarized=0 AND is_system=0 AND session_id=?",
                (clean_text(session_id, 200),),
            ).fetchone()
        return row["m"] or ""

    def mark_timeline_summarized(self, event_ids: Iterable[str], summary_memory_id: str) -> int:
        ids = [clean_text(eid, 120) for eid in event_ids if clean_text(eid, 120)]
        if not ids:
            return 0
        with self._lock:
            self._conn.executemany(
                "UPDATE timeline SET summarized=1, summary_memory_id=? WHERE id=?",
                [(summary_memory_id, eid) for eid in ids],
            )
            self._conn.commit()
        return len(ids)

    def delete_timeline_by_keywords(self, keywords: list[str]) -> int:
        """删除时间线中匹配关键词的系统/状态通知类事件（退群、入群、撤回等）。"""
        keywords = [clean_text(kw, 40) for kw in keywords if clean_text(kw, 40)]
        if not keywords:
            return 0
        removed = 0
        with self._lock:
            for keyword in keywords:
                cur = self._conn.execute(
                    "DELETE FROM timeline WHERE content LIKE ?", (f"%{keyword}%",)
                )
                removed += cur.rowcount
            self._conn.commit()
        return removed

    def delete_unsummarized_timeline(self, *, session_id: str = "", persona_id: str = "") -> int:
        """删除指定会话的未总结时间线事件（/reset 等清空上下文时调用，保留系统通知）。"""
        clauses: list[str] = ["summarized=0", "is_system=0"]
        params: list[Any] = []
        if session_id:
            clauses.append("session_id=?")
            params.append(clean_text(session_id, 200))
        if persona_id:
            clauses.append("persona_id=?")
            params.append(clean_text(persona_id, 80))
        with self._lock:
            cur = self._conn.execute(
                f"DELETE FROM timeline WHERE {' AND '.join(clauses)}", params
            )
            self._conn.commit()
        return cur.rowcount

    def mark_system_timeline(self, keywords: list[str]) -> int:
        """把时间线中匹配关键词的系统/状态通知事件标记为 is_system=1（可见但不参与总结）。"""
        keywords = [clean_text(kw, 40) for kw in keywords if clean_text(kw, 40)]
        if not keywords:
            return 0
        marked = 0
        with self._lock:
            for keyword in keywords:
                cur = self._conn.execute(
                    "UPDATE timeline SET is_system=1 WHERE is_system=0 AND content LIKE ?",
                    (f"%{keyword}%",),
                )
                marked += cur.rowcount
            self._conn.commit()
        return marked

    def delete_timeline_older_than(self, days: int) -> int:
        """删除已总结且超过保留天数的时间线事件。"""
        if days <= 0:
            return 0
        with self._lock:
            cur = self._conn.execute(
                # 0.89 修复：两侧都必须 CAST 成 INTEGER。
                # strftime() 返回 **TEXT**，而 `strftime('%s','now') - ?` 是**数字**；
                # SQLite 的类型排序里数字恒小于文本 → `TEXT <= INTEGER` **永远为假**，
                # 于是这条"保留策略"从未删掉任何一行（实测：90 天前的已总结记录删不掉）。
                "DELETE FROM timeline WHERE summarized=1 "
                "AND CAST(strftime('%s', occurred_at) AS INTEGER) "
                "<= CAST(strftime('%s', 'now') AS INTEGER) - ?",
                (days * 86400,),
            )
            self._conn.commit()
        return cur.rowcount

    def count_timeline(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM timeline").fetchone()
        return int(row["c"] or 0)

    def count_timeline_filtered(self, *, session_id: str = "", persona_id: str = "") -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id=?")
            params.append(clean_text(session_id, 200))
        if persona_id:
            clauses.append("persona_id=?")
            params.append(clean_text(persona_id, 80))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) AS c FROM timeline {where}", params
            ).fetchone()
        return int(row["c"] or 0)

    def count_users(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return int(row["c"] or 0)

    # ------------------------------------------------------------------ import batches

    def create_import_batch(self, *, filename: str, status: str = "pending", total: int = 0, params: dict[str, Any] | None = None) -> str:
        batch_id = new_id("batch")
        with self._lock:
            self._conn.execute(
                "INSERT INTO import_batches(batch_id, filename, status, total, imported, skipped, params, created_at) "
                "VALUES(?,?,?,?,0,0,?,?)",
                (batch_id, clean_text(filename, 240), status, total, json_dumps(params or {}), _now()),
            )
            self._conn.commit()
        return batch_id

    def update_import_batch(
        self,
        batch_id: str,
        *,
        status: str = "",
        total: int | None = None,
        imported: int | None = None,
        skipped: int | None = None,
    ) -> None:
        batch_id = clean_text(batch_id, 120)
        updates: list[str] = []
        params: list[Any] = []
        if status:
            updates.append("status=?")
            params.append(clean_text(status, 40))
        if total is not None:
            updates.append("total=?")
            params.append(int(total))
        if imported is not None:
            updates.append("imported=?")
            params.append(int(imported))
        if skipped is not None:
            updates.append("skipped=?")
            params.append(int(skipped))
        if not updates:
            return
        updates.append("completed_at=?")
        params.append(_now() if status in ("done", "failed") else "")
        params.append(batch_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE import_batches SET {', '.join(updates)} WHERE batch_id=?", params
            )
            self._conn.commit()

    def list_import_batches(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM import_batches ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "batch_id": row["batch_id"],
                "filename": row["filename"],
                "status": row["status"],
                "total": row["total"],
                "imported": row["imported"],
                "skipped": row["skipped"],
                "params": json_loads(row["params"], {}),
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------ injection logs

    def add_injection_log(
        self,
        *,
        session_id: str,
        scope: str,
        query: str,
        selected_memory_ids: list[str],
        blocked: list[dict[str, Any]],
        injection_chars: int,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO injection_logs(created_at, session_id, scope, query, selected_memory_ids, blocked, injection_chars) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    _now(), clean_text(session_id, 200), clean_text(scope, 40),
                    clean_text(query, 1000), json_dumps(selected_memory_ids[:20]),
                    json_dumps(blocked[:20]), int(injection_chars),
                ),
            )
            self._conn.commit()

    def recent_injection_logs(self, limit: int = 20, session_id: str = "") -> list[dict[str, Any]]:
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    "SELECT * FROM injection_logs WHERE session_id=? ORDER BY id DESC LIMIT ?",
                    (clean_text(session_id, 200), limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM injection_logs ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "session_id": row["session_id"],
                "scope": row["scope"],
                "query": row["query"],
                "selected_memory_ids": json_loads(row["selected_memory_ids"], []),
                "blocked": json_loads(row["blocked"], []),
                "injection_chars": row["injection_chars"],
            }
            for row in rows
        ]

    def delete_injection_logs_older_than(self, days: int) -> int:
        if days <= 0:
            return 0
        with self._lock:
            cur = self._conn.execute(
                # 0.89 修复：同上——两侧 CAST 成 INTEGER，否则 TEXT <= INTEGER 恒为假，日志永不清理。
            "DELETE FROM injection_logs WHERE CAST(strftime('%s', created_at) AS INTEGER) "
            "<= CAST(strftime('%s', 'now') AS INTEGER) - ?",
                (days * 86400,),
            )
            self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------ stats

    def update_identity_legacy_meta(self) -> int:
        """0.79 迁移：旧版身份标识记忆（含"旨在说明/给我发了消息"特征）→ 新文案 + 轻重要性。返回更新条数。"""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT id, user_name FROM memories "
                    "WHERE memory_type='identity' AND (content LIKE '%旨在说明%' OR content LIKE '%给我发了消息%')"
                ).fetchall()
                if not rows:
                    return 0
                now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                count = 0
                for row in rows:
                    user_name = row["user_name"] or "对方"
                    new_content = f"我记得{user_name}这个名字，用于确认我认识{user_name}，与亲密度、互动等无关。"
                    new_summary = f"我记得{user_name}"
                    cur = self._conn.execute(
                        "UPDATE memories SET content=?, summary=?, importance=?, confidence=?, updated_at=? "
                        "WHERE id=?",
                        (new_content, new_summary, 0.3, 0.95, now, row["id"]),
                    )
                    count += max(0, cur.rowcount)
                self._conn.commit()
                return count
        except Exception:
            return 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
            active = self._conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE lifecycle='active'"
            ).fetchone()["c"]
            archived = self._conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE lifecycle IN ('archived','decayed')"
            ).fetchone()["c"]
            by_type = self._conn.execute(
                "SELECT memory_type, COUNT(*) AS c FROM memories GROUP BY memory_type"
            ).fetchall()
            by_scope = self._conn.execute(
                "SELECT scope, COUNT(*) AS c FROM memories GROUP BY scope"
            ).fetchall()
            timeline = self._conn.execute("SELECT COUNT(*) AS c FROM timeline").fetchone()["c"]
            unsummarized = self._conn.execute(
                "SELECT COUNT(*) AS c FROM timeline WHERE summarized=0 AND is_system=0"
            ).fetchone()["c"]
            personas = self._conn.execute("SELECT COUNT(*) AS c FROM personas").fetchone()["c"]
            users = self._conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            embedded = self._conn.execute("SELECT COUNT(*) AS c FROM embeddings").fetchone()["c"]
            batches = self._conn.execute("SELECT COUNT(*) AS c FROM import_batches").fetchone()["c"]
        return {
            "total_memories": int(total),
            "active_memories": int(active),
            "archived_memories": int(archived),
            "memory_types": {row["memory_type"]: int(row["c"]) for row in by_type},
            "scopes": {row["scope"]: int(row["c"]) for row in by_scope},
            "timeline_events": int(timeline),
            "unsummarized_events": int(unsummarized),
            "personas": int(personas),
            "users": int(users),
            "embedded_vectors": int(embedded),
            "import_batches": int(batches),
        }


def re_safe_order(order: str) -> bool:
    """只允许「字段名 + ASC/DESC」的简单排序表达式。"""
    import re

    if not order:
        return False
    return bool(
        re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\s+(ASC|DESC)", order.strip(), re.IGNORECASE)
    )
