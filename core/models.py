from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def clean_text(value: Any, limit: int = 2000) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()
    if len(text) > limit:
        return text[: max(0, limit - 1)].rstrip() + "…"
    return text


def clamp_float(value: Any, low: float = 0.0, high: float = 1.0, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        number = default
    return max(low, min(high, number))


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def stable_fingerprint(*parts: Any) -> str:
    raw = "|".join(clean_text(part, 1000).lower() for part in parts if part is not None)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


@dataclass(slots=True)
class EntityRef:
    """身份引用：记忆主体或客体，含身份验证信息。"""

    kind: str = "user"          # user / bot / session / group / unknown
    id: str = ""
    name: str = ""
    role: str = "unknown"       # owner / target / bot_self / member / shared_experience_partner ...
    verified: bool = False      # 是否经过身份验证
    verified_by: str = ""       # system / user / admin / llm / platform
    verified_at: str = ""       # 验证时间戳

    @classmethod
    def bot_self(cls, bot_id: str = "", bot_name: str = "", verified: bool = True) -> "EntityRef":
        return cls(
            kind="bot",
            id=clean_text(bot_id, 120) or "self",
            name=clean_text(bot_name, 80) or "Bot",
            role="bot_self",
            verified=verified,
            verified_by="system",
            verified_at=utc_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "verified": self.verified,
            "verified_by": self.verified_by,
            "verified_at": self.verified_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "EntityRef":
        payload = payload or {}
        return cls(
            kind=clean_text(payload.get("kind"), 40) or "unknown",
            id=clean_text(payload.get("id"), 160),
            name=clean_text(payload.get("name"), 80),
            role=clean_text(payload.get("role"), 60) or "unknown",
            verified=bool(payload.get("verified", False)),
            verified_by=clean_text(payload.get("verified_by"), 40),
            verified_at=clean_text(payload.get("verified_at"), 80),
        )


@dataclass(slots=True)
class SessionContext:
    """一次消息事件解析出的会话上下文。"""

    session_id: str = ""
    scope: str = "unknown"          # private / group / public
    platform: str = ""
    user_id: str = ""
    user_name: str = ""
    group_id: str = ""
    group_name: str = ""
    bot_id: str = ""
    bot_name: str = ""
    message_id: str = ""
    message_text: str = ""
    is_command: bool = False
    persona_id: str = ""            # 会话当前人格

    @property
    def current_target_id(self) -> str:
        return self.group_id if self.scope == "group" else self.user_id

    @property
    def label(self) -> str:
        if self.scope == "group":
            return f"群聊 {self.group_name or self.group_id or 'unknown'} / 发言人 {self.user_name or self.user_id or 'unknown'}"
        if self.scope == "private":
            return f"私聊 {self.user_name or self.user_id or 'unknown'}"
        return self.session_id or "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "scope": self.scope,
            "platform": self.platform,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "bot_id": self.bot_id,
            "bot_name": self.bot_name,
            "message_id": self.message_id,
            "message_text": self.message_text,
            "persona_id": self.persona_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "SessionContext":
        payload = payload or {}
        return cls(
            session_id=clean_text(payload.get("session_id"), 200),
            scope=clean_text(payload.get("scope"), 40).lower() or "unknown",
            platform=clean_text(payload.get("platform"), 80),
            user_id=clean_text(payload.get("user_id"), 120),
            user_name=clean_text(payload.get("user_name"), 80),
            group_id=clean_text(payload.get("group_id"), 120),
            group_name=clean_text(payload.get("group_name"), 80),
            bot_id=clean_text(payload.get("bot_id"), 120),
            bot_name=clean_text(payload.get("bot_name"), 80),
            message_id=clean_text(payload.get("message_id"), 120),
            message_text=clean_text(payload.get("message_text"), 2000),
            persona_id=clean_text(payload.get("persona_id"), 80),
        )


@dataclass(slots=True)
class MemoryRecord:
    """一条长期记忆，字段尽量完整：身份、时间、来源、权重、生命周期等。"""

    id: str = ""
    memory_type: str = "fact"           # fact/preference/event/relationship/promise/summary/note/other
    content: str = ""                   # 正文
    summary: str = ""                   # 摘要
    tags: list[str] = field(default_factory=list)

    importance: float = 0.45            # 复合重要度（最终排序用）
    base_importance: float = 0.45       # 基础重要度（写入方指定）
    weight_factors: dict[str, float] = field(default_factory=dict)  # 权重因子分解
    confidence: float = 0.7             # 置信度

    subject: EntityRef = field(default_factory=EntityRef)
    object: EntityRef = field(default_factory=EntityRef)

    scope: str = "private"              # private/group/public
    persona_id: str = ""                # 人格隔离键
    platform: str = ""
    session_id: str = ""                # 来源会话
    user_id: str = ""                   # 归属用户（私聊）
    user_name: str = ""
    group_id: str = ""                  # 归属群（群聊）
    group_name: str = ""
    bot_id: str = ""

    lifecycle: str = "active"           # active/archived/decayed
    visibility: str = "private"         # private/shared/public
    source: str = "capture"             # capture/llm_tool/manual/import/bridge/summary/decay
    source_plugin: str = "deepmemory"
    message_id: str = ""                # 来源消息 ID

    created_at: str = ""
    updated_at: str = ""
    occurred_at: str = ""               # 事件实际发生时间
    last_accessed_at: str = ""
    access_count: int = 0

    import_batch_id: str = ""
    supersedes_id: str = ""             # 被谁取代（合并/压缩）
    merged_count: int = 1
    content_fingerprint: str = ""

    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展字段

    def ensure_defaults(self) -> "MemoryRecord":
        now = utc_now()
        if not self.id:
            self.id = new_id("mem")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.occurred_at:
            self.occurred_at = self.created_at
        if not self.persona_id:
            self.persona_id = "first"
        self.content = clean_text(self.content, 4000)
        self.summary = clean_text(self.summary, 2000)
        self.confidence = clamp_float(self.confidence, default=0.7)
        self.importance = clamp_float(self.importance, default=0.45)
        self.base_importance = clamp_float(self.base_importance, default=0.45)
        self.tags = [clean_text(tag, 80) for tag in self.tags if clean_text(tag, 80)]
        if not self.content_fingerprint:
            self.content_fingerprint = stable_fingerprint(
                self.memory_type,
                self.persona_id,
                self.scope,
                self.user_id,
                self.group_id,
                self.subject.kind,
                self.subject.id,
                self.object.kind,
                self.object.id,
                self.content,
            )
        self.merged_count = max(1, int(self.merged_count or 1))
        return self

    def to_db(self) -> dict[str, Any]:
        self.ensure_defaults()
        return {
            "id": self.id,
            "memory_type": self.memory_type,
            "content": self.content,
            "summary": self.summary,
            "tags": json_dumps(self.tags),
            "importance": self.importance,
            "base_importance": self.base_importance,
            "weight_factors": json_dumps(self.weight_factors),
            "confidence": self.confidence,
            "subject_kind": self.subject.kind,
            "subject_id": self.subject.id,
            "subject_name": self.subject.name,
            "subject_role": self.subject.role,
            "subject_verified": int(self.subject.verified),
            "subject_verified_by": self.subject.verified_by,
            "subject_verified_at": self.subject.verified_at,
            "object_kind": self.object.kind,
            "object_id": self.object.id,
            "object_name": self.object.name,
            "object_role": self.object.role,
            "object_verified": int(self.object.verified),
            "object_verified_by": self.object.verified_by,
            "object_verified_at": self.object.verified_at,
            "scope": self.scope,
            "persona_id": self.persona_id,
            "platform": self.platform,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "bot_id": self.bot_id,
            "lifecycle": self.lifecycle,
            "visibility": self.visibility,
            "source": self.source,
            "source_plugin": self.source_plugin,
            "message_id": self.message_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "occurred_at": self.occurred_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": int(self.access_count or 0),
            "import_batch_id": self.import_batch_id,
            "supersedes_id": self.supersedes_id,
            "merged_count": self.merged_count,
            "content_fingerprint": self.content_fingerprint,
            "metadata": json_dumps(self.metadata),
        }

    @classmethod
    def from_row(cls, row: Any) -> "MemoryRecord":
        get = row.__getitem__
        return cls(
            id=get("id"),
            memory_type=get("memory_type"),
            content=get("content"),
            summary=get("summary"),
            tags=json_loads(get("tags"), []),
            importance=float(get("importance") or 0.0),
            base_importance=float(get("base_importance") or 0.0),
            weight_factors=json_loads(get("weight_factors"), {}),
            confidence=float(get("confidence") or 0.0),
            subject=EntityRef(
                get("subject_kind"), get("subject_id"), get("subject_name"), get("subject_role"),
                bool(get("subject_verified")), get("subject_verified_by"), get("subject_verified_at"),
            ),
            object=EntityRef(
                get("object_kind"), get("object_id"), get("object_name"), get("object_role"),
                bool(get("object_verified")), get("object_verified_by"), get("object_verified_at"),
            ),
            scope=get("scope"),
            persona_id=get("persona_id"),
            platform=get("platform"),
            session_id=get("session_id"),
            user_id=get("user_id"),
            user_name=get("user_name"),
            group_id=get("group_id"),
            group_name=get("group_name"),
            bot_id=get("bot_id"),
            lifecycle=get("lifecycle"),
            visibility=get("visibility"),
            source=get("source"),
            source_plugin=get("source_plugin"),
            message_id=get("message_id"),
            created_at=get("created_at"),
            updated_at=get("updated_at"),
            occurred_at=get("occurred_at"),
            last_accessed_at=get("last_accessed_at"),
            access_count=int(get("access_count") or 0),
            import_batch_id=get("import_batch_id"),
            supersedes_id=get("supersedes_id"),
            merged_count=int(get("merged_count") or 1),
            content_fingerprint=get("content_fingerprint"),
            metadata=json_loads(get("metadata"), {}),
        )

    def to_dict(self) -> dict[str, Any]:
        self.ensure_defaults()
        return {
            "id": self.id,
            "memory_type": self.memory_type,
            "content": self.content,
            "summary": self.summary,
            "tags": list(self.tags),
            "importance": self.importance,
            "base_importance": self.base_importance,
            "weight_factors": dict(self.weight_factors),
            "confidence": self.confidence,
            "subject": self.subject.to_dict(),
            "object": self.object.to_dict(),
            "scope": self.scope,
            "persona_id": self.persona_id,
            "platform": self.platform,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "bot_id": self.bot_id,
            "lifecycle": self.lifecycle,
            "visibility": self.visibility,
            "source": self.source,
            "source_plugin": self.source_plugin,
            "message_id": self.message_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "occurred_at": self.occurred_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
            "import_batch_id": self.import_batch_id,
            "supersedes_id": self.supersedes_id,
            "merged_count": self.merged_count,
            "content_fingerprint": self.content_fingerprint,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "MemoryRecord":
        payload = payload or {}
        return cls(
            id=clean_text(payload.get("id"), 120),
            memory_type=clean_text(payload.get("memory_type"), 60) or "fact",
            content=clean_text(payload.get("content"), 4000),
            summary=clean_text(payload.get("summary"), 2000),
            tags=[clean_text(tag, 80) for tag in (payload.get("tags") or [])],
            importance=clamp_float(payload.get("importance"), default=0.45),
            base_importance=clamp_float(payload.get("base_importance"), default=0.45),
            weight_factors=payload.get("weight_factors") if isinstance(payload.get("weight_factors"), dict) else {},
            confidence=clamp_float(payload.get("confidence"), default=0.7),
            subject=EntityRef.from_dict(payload.get("subject")),
            object=EntityRef.from_dict(payload.get("object")),
            scope=clean_text(payload.get("scope"), 40).lower() or "private",
            persona_id=clean_text(payload.get("persona_id"), 80) or "first",
            platform=clean_text(payload.get("platform"), 80),
            session_id=clean_text(payload.get("session_id"), 200),
            user_id=clean_text(payload.get("user_id"), 120),
            user_name=clean_text(payload.get("user_name"), 80),
            group_id=clean_text(payload.get("group_id"), 120),
            group_name=clean_text(payload.get("group_name"), 80),
            bot_id=clean_text(payload.get("bot_id"), 120),
            lifecycle=clean_text(payload.get("lifecycle"), 40) or "active",
            visibility=clean_text(payload.get("visibility"), 40) or "private",
            source=clean_text(payload.get("source"), 60) or "import",
            source_plugin=clean_text(payload.get("source_plugin"), 80) or "deepmemory",
            message_id=clean_text(payload.get("message_id"), 120),
            created_at=clean_text(payload.get("created_at"), 80),
            updated_at=clean_text(payload.get("updated_at"), 80),
            occurred_at=clean_text(payload.get("occurred_at"), 80),
            last_accessed_at=clean_text(payload.get("last_accessed_at"), 80),
            access_count=int(payload.get("access_count") or 0),
            import_batch_id=clean_text(payload.get("import_batch_id"), 120),
            supersedes_id=clean_text(payload.get("supersedes_id"), 120),
            merged_count=int(payload.get("merged_count") or 1),
            content_fingerprint=clean_text(payload.get("content_fingerprint"), 80),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )


@dataclass(slots=True)
class SearchResult:
    memory: MemoryRecord
    score: float
    reason: str = ""


@dataclass(slots=True)
class Persona:
    persona_id: str = ""
    name: str = ""
    description: str = ""
    enabled: bool = True
    is_default: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class TimelineEvent:
    id: str = ""
    session_id: str = ""
    scope: str = "unknown"
    platform: str = ""
    user_id: str = ""
    user_name: str = ""
    group_id: str = ""
    group_name: str = ""
    bot_id: str = ""
    persona_id: str = ""
    role: str = "user"          # user / bot / group_member
    content: str = ""
    occurred_at: str = ""
    message_id: str = ""
    summarized: bool = False
    summary_memory_id: str = ""
    import_batch_id: str = ""
    is_system: bool = False     # 系统/状态通知（退群等）：时间线可见但不参与总结
    kind: str = ""              # "" 普通对话 / "system" 系统通知 / "op" 记忆库操作（红字）

    def to_db(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "scope": self.scope,
            "platform": self.platform,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "bot_id": self.bot_id,
            "persona_id": self.persona_id,
            "role": self.role,
            "content": self.content,
            "occurred_at": self.occurred_at,
            "message_id": self.message_id,
            "summarized": int(self.summarized),
            "summary_memory_id": self.summary_memory_id,
            "import_batch_id": self.import_batch_id,
            "is_system": int(self.is_system),
            "kind": self.kind,
        }

    @classmethod
    def from_row(cls, row: Any) -> "TimelineEvent":
        get = row.__getitem__
        return cls(
            id=get("id"),
            session_id=get("session_id"),
            scope=get("scope"),
            platform=get("platform"),
            user_id=get("user_id"),
            user_name=get("user_name"),
            group_id=get("group_id"),
            group_name=get("group_name"),
            bot_id=get("bot_id"),
            persona_id=get("persona_id"),
            role=get("role"),
            content=get("content"),
            occurred_at=get("occurred_at"),
            message_id=get("message_id"),
            summarized=bool(get("summarized")),
            summary_memory_id=get("summary_memory_id"),
            import_batch_id=get("import_batch_id"),
            is_system=bool(get("is_system") if "is_system" in row.keys() else False),
            kind=get("kind") if "kind" in row.keys() else "",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "scope": self.scope,
            "platform": self.platform,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "bot_id": self.bot_id,
            "persona_id": self.persona_id,
            "role": self.role,
            "content": self.content,
            "occurred_at": self.occurred_at,
            "message_id": self.message_id,
            "summarized": self.summarized,
            "summary_memory_id": self.summary_memory_id,
            "import_batch_id": self.import_batch_id,
            "is_system": self.is_system,
            "kind": self.kind,
        }
