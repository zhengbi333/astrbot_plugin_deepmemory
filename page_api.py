from __future__ import annotations

import functools
import inspect
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .core.log import logger

from .core.models import SessionContext, clean_text
from .core.service import CONFIG_FILE_NAME, DeepMemoryService

try:
    from astrbot.api.web import error_response, file_response, json_response, request
    _MODERN_WEB = True
except Exception:  # pragma: no cover - 兼容旧版 AstrBot（无 astrbot.api.web）
    from quart import jsonify, request, send_file  # type: ignore

    _MODERN_WEB = False


async def _ok(data: Any) -> Any:
    """统一成功响应：新 API 返回 Response；旧版返回 quart jsonify。"""
    if _MODERN_WEB:
        return json_response(data)
    return jsonify({} if data is None else data)


async def _err(message: str, status_code: int = 400) -> Any:
    if _MODERN_WEB:
        return error_response(message, status_code=status_code)
    return jsonify({"status": "error", "message": message}), status_code


async def _file(path: str | Path, filename: str, content_type: str) -> Any:
    if _MODERN_WEB:
        return file_response(path, filename=filename, content_type=content_type)
    return await send_file(path, as_attachment=True, download_name=filename, mimetype=content_type)


def _query_get(key: str, default: Any = None, *, type_fn: Any = None) -> Any:
    if _MODERN_WEB:
        try:
            if type_fn:
                return request.query.get(key, default, type=type_fn)
            return request.query.get(key, default)
        except Exception:
            return default
    try:
        if type_fn:
            return request.args.get(key, default, type=type_fn)
        return request.args.get(key, default)
    except Exception:
        return default


def _query_int(key: str, default: int) -> int:
    try:
        return int(_query_get(key, default))
    except Exception:
        return default


async def _json_body(default: Any = None) -> Any:
    if _MODERN_WEB:
        try:
            return await request.json(default=default)
        except Exception:
            return default
    try:
        get_json = getattr(request, "get_json", None)
        if callable(get_json):
            value = get_json(silent=True)
            if inspect.isawaitable(value):
                value = await value
            return value if value is not None else default
    except Exception:
        pass
    return default


async def _request_files() -> Any:
    """读取上传文件，兼容新 API 的 awaitable 与旧版 Quart 的同步属性。"""
    files = getattr(request, "files", None)
    if callable(files):
        files = files()
    if inspect.isawaitable(files):
        files = await files
    return files or {}


async def _save_upload(upload: Any, target: Path) -> None:
    save = getattr(upload, "save", None)
    if not callable(save):
        return
    result = save(target)
    if inspect.isawaitable(result):
        await result


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "开", "开启"}
    return bool(value)


def _split_list(value: Any) -> list[str]:
    """把数组或逗号/顿号分隔的字符串拆成去重后的标签/人物列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        items = list(value)
    else:
        items = str(value).replace("、", ",").split(",")
    seen: list[str] = []
    for item in items:
        text = clean_text(item, 80)
        if text and text not in seen:
            seen.append(text)
    return seen


def _coerce_occurred_at(value: Any) -> str:
    """把各种时间输入统一转换为 UTC ISO；无时区输入按配置时区（默认 Asia/Shanghai）解释。"""
    if value is None:
        return ""
    text = clean_text(value, 40)
    if not text:
        return ""
    try:
        number = float(text)
        return datetime.fromtimestamp(number, tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        pass
    normalized = text.strip().replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except Exception:
        try:
            dt = datetime.fromisoformat(normalized + "T00:00:00")
        except Exception:
            return text
    if dt.tzinfo is None:
        try:
            tz = ZoneInfo("Asia/Shanghai")
        except Exception:
            tz = timezone(timedelta(hours=8))
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _page_payload() -> dict[str, Any]:
    """从查询参数构造用于检索测试的会话上下文。"""
    scope = clean_text(_query_get("scope", ""), 40).lower() or "private"
    return {
        "session_id": clean_text(_query_get("session_id", ""), 200),
        "scope": scope,
        "platform": clean_text(_query_get("platform", ""), 80),
        "user_id": clean_text(_query_get("user_id", ""), 120),
        "user_name": clean_text(_query_get("user_name", ""), 80),
        "group_id": clean_text(_query_get("group_id", ""), 120),
        "group_name": clean_text(_query_get("group_name", ""), 80),
        "bot_id": clean_text(_query_get("bot_id", ""), 120),
        "persona_id": clean_text(_query_get("persona_id", ""), 80),
        "message_text": clean_text(_query_get("q", ""), 2000),
    }


class DeepMemoryPageApi:
    def __init__(self, plugin: Any):
        self.plugin = plugin

    @property
    def service(self) -> DeepMemoryService:
        return self.plugin.service

    def _guard(self, handler: Any) -> Any:
        """异常守护：任何处理器异常都记录日志并返回 500 错误体，避免空转。"""

        @functools.wraps(handler)
        async def wrapper(*args: Any, **kwargs: Any):
            try:
                return await handler(*args, **kwargs)
            except Exception as exc:
                logger.error(
                    "[DeepMemory] 页面 API 异常: handler=%s error=%s",
                    getattr(handler, "__name__", handler),
                    exc,
                    exc_info=True,
                )
                return await _err(f"{getattr(handler, '__name__', 'handler')}: {exc}", 500)

        return wrapper

    def register_routes(self) -> None:
        register = self.plugin.context.register_web_api
        prefix = "/astrbot_plugin_deepmemory"
        routes = [
            (f"{prefix}/health", self.health, ["GET"], "DeepMemory health"),
            (f"{prefix}/stats", self.stats, ["GET"], "DeepMemory stats"),
            (f"{prefix}/memories", self.memories, ["GET"], "DeepMemory memories list"),
            (f"{prefix}/memory", self.memory_detail, ["GET"], "DeepMemory memory detail"),
            (f"{prefix}/memory/create", self.memory_create, ["POST"], "DeepMemory memory create"),
            (f"{prefix}/memory/update", self.memory_update, ["POST"], "DeepMemory memory update"),
            (f"{prefix}/memory/delete", self.memory_delete, ["POST"], "DeepMemory memory delete"),
            (f"{prefix}/memory/batch_delete", self.memory_batch_delete, ["POST"], "DeepMemory memory batch delete"),
            (f"{prefix}/personas", self.personas, ["GET"], "DeepMemory astr personas"),
            (f"{prefix}/users", self.users, ["GET"], "DeepMemory users"),
            (f"{prefix}/user/delete", self.user_delete, ["POST"], "DeepMemory user delete"),
            (f"{prefix}/search", self.search, ["GET"], "DeepMemory search test"),
            (f"{prefix}/timeline", self.timeline, ["GET"], "DeepMemory timeline"),
            (f"{prefix}/timeline/delete", self.timeline_delete, ["POST"], "DeepMemory timeline delete"),
            (f"{prefix}/export", self.export, ["GET", "POST"], "DeepMemory export download"),
            (f"{prefix}/export/archive", self.export_archive, ["POST"], "DeepMemory export archive (returns path)"),
            (f"{prefix}/import/preview", self.import_preview, ["POST"], "DeepMemory import upload preview"),
            (f"{prefix}/import/run", self.import_run, ["POST"], "DeepMemory import run"),
            (f"{prefix}/import/batches", self.import_batches, ["GET"], "DeepMemory import batches"),
            (f"{prefix}/config/schema", self.config_schema, ["GET"], "DeepMemory config schema"),
            (f"{prefix}/config/module/update", self.config_module_update, ["POST"], "DeepMemory config module update"),
            (f"{prefix}/config/module/reset", self.config_module_reset, ["POST"], "DeepMemory config module reset"),
            (f"{prefix}/maintenance/run", self.maintenance_run, ["POST"], "DeepMemory maintenance run"),
            (f"{prefix}/maintenance/decay", self.maintenance_decay, ["POST"], "DeepMemory daily decay run"),
            (f"{prefix}/backup", self.backup, ["POST"], "DeepMemory backup database"),
            (f"{prefix}/summary/test", self.summary_test, ["POST"], "DeepMemory summary provider test"),
            (f"{prefix}/debug/last_prompt", self.debug_last_prompt, ["GET"], "DeepMemory last LLM prompt"),
            (f"{prefix}/debug/main_prompt", self.debug_main_prompt, ["GET"], "DeepMemory last main chain prompt"),
            (f"{prefix}/debug/persona", self.debug_persona, ["GET"], "DeepMemory last persona resolve"),
            (f"{prefix}/thanks/images", self.thanks_images, ["GET"], "DeepMemory thanks avatars"),
            (f"{prefix}/author/talk", self.author_talk, ["GET"], "DeepMemory author talk"),
            (f"{prefix}/logs", self.logs, ["GET"], "DeepMemory injection logs"),
            (f"{prefix}/bridge/status", self.bridge_status, ["GET"], "DeepMemory bridge status"),
            (f"{prefix}/appearance", self.appearance_get, ["GET"], "DeepMemory appearance get"),
            (f"{prefix}/appearance/update", self.appearance_update, ["POST"], "DeepMemory appearance update"),
            (f"{prefix}/appearance/reset", self.appearance_reset, ["POST"], "DeepMemory appearance reset"),
            (f"{prefix}/appearance/background", self.appearance_background, ["POST"], "DeepMemory background upload"),
            (f"{prefix}/appearance/background/clear", self.appearance_background_clear, ["POST"], "DeepMemory background clear"),
            (f"{prefix}/runtime/logs", self.runtime_logs_get, ["GET"], "DeepMemory runtime logs"),
            (f"{prefix}/runtime/logs/clear", self.runtime_logs_clear, ["POST"], "DeepMemory runtime logs clear"),
        ]
        for route, handler, methods, desc in routes:
            register(route, self._guard(handler), methods, desc)

    # ------------------------------------------------------------------ helpers

    def _load_config_schema(self) -> dict[str, Any]:
        path = Path(__file__).with_name("_conf_schema.json")
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _provider_options(self, context: Any) -> list[dict[str, str]]:
        options = [{"id": "", "label": "留空（自动/当前会话）"}]
        getter = getattr(context, "get_all_providers", None)
        if not callable(getter):
            return options
        try:
            providers = getter()
            if inspect.isawaitable(providers):
                providers = []
        except Exception:
            return options
        for provider in providers or []:
            try:
                meta = provider.meta()
                provider_id = str(getattr(meta, "id", "") or "")
            except Exception:
                provider_id = ""
            if not provider_id:
                continue
            provider_type = ""
            model_name = ""
            try:
                provider_type = str(getattr(meta, "type", "") or "").strip()
                model_name = str(getattr(meta, "model", "") or "").strip()
            except Exception:
                pass
            label = provider_id
            if provider_type:
                label = f"{provider_type} ({provider_id})"
            if model_name and model_name not in label:
                label = f"{label} - {model_name}"
            options.append({"id": provider_id, "label": label})
        return options

    async def _embedding_provider_options(self) -> list[dict[str, str]]:
        options = [{"id": "", "label": "自动探测"}]
        context = self.plugin.context
        getter = getattr(context, "get_all_embedding_providers", None) or getattr(context, "get_all_providers", None)
        candidates: list[Any] = []
        if callable(getter):
            try:
                result = getter()
                if inspect.isawaitable(result):
                    result = await result
                candidates = list(result or [])
            except Exception:
                candidates = []
        for provider in candidates or []:
            if not hasattr(provider, "get_embedding") and not hasattr(provider, "get_embeddings"):
                continue
            try:
                meta = provider.meta()
                provider_id = str(getattr(meta, "id", "") or "")
            except Exception:
                provider_id = ""
            if not provider_id:
                continue
            options.append({"id": provider_id, "label": provider_id})
        return options

    async def _rerank_provider_options(self) -> list[dict[str, str]]:
        options = [{"id": "", "label": "自动探测"}]
        context = self.plugin.context
        # AstrBot v4.27 无 get_all_rerank_providers context 接口：专用接口 → provider_manager.rerank_provider_insts → inst_map 按类型兜底
        candidates: list[Any] = []
        getter = getattr(context, "get_all_rerank_providers", None)
        if callable(getter):
            try:
                result = getter()
                if inspect.isawaitable(result):
                    result = await result
                candidates = list(result or [])
            except Exception:
                candidates = []
        manager = getattr(context, "provider_manager", None) if context is not None else None
        if not candidates and manager is not None:
            candidates = list(getattr(manager, "rerank_provider_insts", None) or [])
        if not candidates and manager is not None:
            inst_map = getattr(manager, "inst_map", None) or {}
            candidates = [
                inst for inst in inst_map.values()
                if str((getattr(inst, "provider_config", None) or {}).get("provider_type") or "").find("rerank") >= 0
            ]
        for provider in candidates or []:
            if not hasattr(provider, "rerank"):
                continue
            try:
                meta = provider.meta()
                provider_id = str(getattr(meta, "id", "") or "")
            except Exception:
                provider_id = ""
            if not provider_id:
                continue
            options.append({"id": provider_id, "label": provider_id})
        return options

    # ------------------------------------------------------------------ endpoints

    async def health(self):
        return await _ok(self.service.health())

    async def stats(self):
        return await _ok({"stats": self.service.stats_full()})

    async def memories(self):
        limit = min(200, max(1, _query_int("limit", 50)))
        offset = max(0, _query_int("offset", 0))
        memory_type = clean_text(_query_get("memory_type", ""), 60)
        scope = clean_text(_query_get("scope", ""), 40)
        persona_id = clean_text(_query_get("persona_id", ""), 80)
        user_id = clean_text(_query_get("user_id", ""), 120)
        group_id = clean_text(_query_get("group_id", ""), 120)
        lifecycle = clean_text(_query_get("lifecycle", ""), 40)
        visibility = clean_text(_query_get("visibility", ""), 40)
        session_id = clean_text(_query_get("session_id", ""), 200)
        source = clean_text(_query_get("source", ""), 60)
        q = clean_text(_query_get("q", ""), 200)
        records = self.service.store.list_memories(
            limit=limit,
            offset=offset,
            query=q,
            memory_type=memory_type,
            scope=scope,
            persona_id=persona_id,
            user_id=user_id,
            group_id=group_id,
            lifecycle=lifecycle,
            visibility=visibility,
            session_id=session_id,
            source=source,
                order_by=clean_text(_query_get("order_by", "occurred_at DESC"), 60),
        )
        total = self.service.store.count_memories_filtered(
            query=q,
            memory_type=memory_type,
            scope=scope,
            persona_id=persona_id,
            user_id=user_id,
            group_id=group_id,
            lifecycle=lifecycle,
            visibility=visibility,
            session_id=session_id,
            source=source,
        )
        return await _ok({"memories": [record.to_dict() for record in records], "total": total, "limit": limit, "offset": offset})

    async def memory_detail(self):
        memory_id = clean_text(_query_get("id", ""), 120)
        if not memory_id:
            return await _err("missing id")
        record = self.service.store.get_memory(memory_id)
        if not record:
            return await _err("memory not found", 404)
        return await _ok({"memory": record.to_dict()})

    async def memory_create(self):
        """手动新增一条记忆：支持时间、地点、人物、总结等字段。"""
        payload = await _json_body({})
        content = clean_text(payload.get("content"), self.service.config.int("general.max_content_chars", 4000))
        if not content:
            return await _err("content 不能为空")
        from .core.models import EntityRef

        participants = _split_list(payload.get("participants"))
        location = clean_text(payload.get("location"), 300)
        metadata: dict[str, Any] = {}
        if location:
            metadata["location"] = location
        if participants:
            metadata["participants"] = participants
        metadata.setdefault("source", "manual_page")
        user_id = clean_text(payload.get("user_id"), 120)
        user_name = clean_text(payload.get("user_name"), 80)
        group_id = clean_text(payload.get("group_id"), 120)
        group_name = clean_text(payload.get("group_name"), 80)
        scope = clean_text(payload.get("scope"), 40).lower() or "private"
        subject = EntityRef(
            kind="user",
            id=user_id,
            name=user_name,
            role="manual_owner",
            verified=True,
            verified_by="admin",
        )
        object_ref = EntityRef(
            kind="group" if scope == "group" else "user",
            id=group_id if scope == "group" else user_id,
            name=group_name if scope == "group" else user_name,
            role="manual_target",
        )
        try:
            record = await self.service.add_memory(
                ctx=None,
                content=content,
                memory_type=clean_text(payload.get("memory_type"), 60) or "fact",
                summary=clean_text(payload.get("summary"), 2000),
                tags=_split_list(payload.get("tags")),
                importance=payload.get("importance"),
                base_importance=payload.get("importance"),
                confidence=payload.get("confidence"),
                subject=subject,
                object=object_ref,
                scope=scope,
                persona_id=clean_text(payload.get("persona_id"), 80),
                visibility=clean_text(payload.get("visibility"), 40),
                source="manual_page",
                metadata=metadata,
                occurred_at=_coerce_occurred_at(payload.get("occurred_at")),
                merge_duplicates=False,
            )
        except ValueError as exc:
            return await _err(str(exc))
        self.service._log_op(f"手动新增记忆 {record.id}")
        return await _ok({"created": True, "memory": record.to_dict()})

    async def memory_update(self):
        payload = await _json_body({})
        memory_id = clean_text(payload.get("id"), 120)
        if not memory_id:
            return await _err("missing id")
        fields: dict[str, Any] = {}
        for key in (
            "memory_type", "content", "summary", "tags", "importance", "base_importance",
            "confidence", "scope", "persona_id", "lifecycle", "visibility", "metadata",
            "user_id", "user_name", "group_id", "group_name",
        ):
            if key in payload and payload.get(key) is not None:
                fields[key] = payload.get(key)
        if payload.get("occurred_at") is not None:
            occurred_at = _coerce_occurred_at(payload.get("occurred_at"))
            if occurred_at:
                fields["occurred_at"] = occurred_at
        existing = self.service.store.get_memory(memory_id)
        if not existing:
            return await _err("memory not found", 404)
        metadata = dict(existing.metadata or {})
        if "location" in payload:
            location = clean_text(payload.get("location"), 300)
            if location:
                metadata["location"] = location
            else:
                metadata.pop("location", None)
        if "participants" in payload:
            participants = _split_list(payload.get("participants"))
            if participants:
                metadata["participants"] = participants
            else:
                metadata.pop("participants", None)
        if metadata != (existing.metadata or {}):
            fields["metadata"] = metadata
        ok = self.service.store.update_memory_fields(memory_id, **fields)
        if not ok:
            return await _err("memory not found", 404)
        self.service._log_op(f"修改记忆 {memory_id}")
        record = self.service.store.get_memory(memory_id)
        return await _ok({"updated": ok, "memory": record.to_dict() if record else None})

    async def memory_delete(self):
        payload = await _json_body({})
        memory_id = clean_text(payload.get("id"), 120)
        ok = self.service.store.delete_memory(memory_id)
        if ok:
            self.service._log_op(f"删除记忆 {memory_id}")
        return await _ok({"deleted": ok})

    async def memory_batch_delete(self):
        payload = await _json_body({})
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids:
            return await _err("ids 不能为空")
        ids = [clean_text(mid, 120) for mid in ids if clean_text(mid, 120)]
        removed = self.service.batch_delete_memories(ids)
        return await _ok({"deleted": removed})

    async def personas(self):
        """返回 AstrBot 已配置的人格列表（隔离键来源）。"""
        personas: list[dict[str, Any]] = []
        try:
            db = self.plugin.context.get_db()
            rows = await db.get_personas()
            for row in rows or []:
                persona_id = clean_text(getattr(row, "persona_id", "") or "", 120)
                if not persona_id:
                    continue
                personas.append(
                    {
                        "persona_id": persona_id,
                        "name": persona_id,
                        "description": clean_text(getattr(row, "system_prompt", "") or "", 2000)[:300],
                        "is_default": False,
                        "enabled": True,
                    }
                )
        except Exception as exc:
            logger.warning("[DeepMemory] 读取 AstrBot 人格列表失败: %s", exc)
        return await _ok({"personas": personas, "source": "astrbot"})

    async def users(self):
        limit = min(100, max(1, _query_int("limit", 10)))
        offset = max(0, _query_int("offset", 0))
        users = self.service.store.list_users(limit=limit, offset=offset)
        total = self.service.store.count_users()
        return await _ok({"users": users, "total": total, "limit": limit, "offset": offset})

    async def user_delete(self):
        payload = await _json_body({})
        user_key = clean_text(payload.get("user_key"), 200)
        if not user_key:
            return await _err("user_key is required")
        removed = self.service.store.delete_user(user_key)
        return await _ok({"deleted": True, "removed_memories": removed})

    async def search(self):
        query = clean_text(_query_get("q", ""), 500)
        if not query:
            return await _err("q is required")
        top_k = min(50, max(1, _query_int("top_k", 8)))
        admin_read_all = _bool(_query_get("admin", ""), False)
        ctx = SessionContext.from_dict(_page_payload())
        ctx.persona_id = clean_text(_query_get("persona_id", ""), 80)
        if not ctx.persona_id:
            await self.service.resolve_persona(ctx)
        results = await self.service.search(query, ctx, top_k, admin_read_all=admin_read_all)
        return await _ok(
            {
                "results": [
                    {
                        **item.memory.to_dict(),
                        "score": round(item.score, 4),
                        "reason": item.reason,
                    }
                    for item in results
                ],
                "context": ctx.to_dict(),
            }
        )

    async def timeline(self):
        limit = min(100, max(1, _query_int("limit", 10)))
        offset = max(0, _query_int("offset", 0))
        session_id = clean_text(_query_get("session_id", ""), 200)
        persona_id = clean_text(_query_get("persona_id", ""), 80)
        events = self.service.store.recent_timeline(
            limit=limit,
            offset=offset,
            session_id=session_id,
            persona_id=persona_id,
        )
        total = self.service.store.count_timeline_filtered(session_id=session_id, persona_id=persona_id)
        return await _ok({"items": [event.to_dict() for event in events], "total": total, "limit": limit, "offset": offset})

    async def timeline_delete(self):
        """删除时间线事件（单个或多个）。"""
        payload = await _json_body({})
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids:
            return await _err("ids 不能为空")
        ids = [clean_text(eid, 120) for eid in ids if clean_text(eid, 120)]
        removed = self.service.store.delete_timeline_events(ids)
        if removed:
            logger.info("[DeepMemory] 删除时间线事件: count=%s", removed)
        return await _ok({"deleted": removed})

    async def export(self):
        """导出记忆档案。兼容 POST（JSON body）与 GET（query 参数，bridge.download 用）。"""
        payload = await _json_body({})
        payload = payload if isinstance(payload, dict) else {}
        export_format = clean_text(
            _query_get("format", "") or payload.get("format") or "jsonl", 10
        )
        scope = clean_text(_query_get("scope", "") or payload.get("scope") or "", 40)
        persona_id = clean_text(
            _query_get("persona_id", "") or payload.get("persona_id") or "", 80
        )
        try:
            result = self.service.export_data(
                format=export_format,
                scope=scope,
                persona_id=persona_id,
            )
        except Exception as exc:
            return await _err(f"导出失败: {exc}")
        path = Path(result["path"])
        return await _file(
            path,
            result["filename"],
            "application/json" if result["format"] == "json" else "application/x-ndjson",
        )

    async def export_archive(self):
        """生成导出档案并返回文件路径（不触发下载）。

        兼容 AstrBot Launcher 内置浏览器无法触发文件下载的场景：
        前端展示路径，用户可直接从文件管理器取用。
        """
        payload = await _json_body({})
        payload = payload if isinstance(payload, dict) else {}
        export_format = clean_text(payload.get("format") or "jsonl", 10)
        try:
            result = self.service.export_data(
                format=export_format,
                scope=clean_text(payload.get("scope") or "", 40),
                persona_id=clean_text(payload.get("persona_id") or "", 80),
            )
        except Exception as exc:
            return await _err(f"导出失败: {exc}")
        return await _ok(
            {
                "ok": True,
                "path": result["path"],
                "filename": result["filename"],
                "count": result["count"],
            }
        )

    async def import_preview(self):
        """上传导入文件并返回预览。字段名固定为 file。"""
        try:
            files = await _request_files()
        except Exception as exc:
            return await _err(f"读取上传文件失败: {exc}")
        upload = files.get("file") if files else None
        if upload is None:
            return await _err("missing file")
        import_dir = self.service.data_dir / "imports"
        import_dir.mkdir(parents=True, exist_ok=True)
        filename = clean_text(getattr(upload, "filename", "") or "import.jsonl", 240)
        safe_name = Path(filename).name
        target = import_dir / f"{int(time.time())}_{safe_name}"
        try:
            await _save_upload(upload, target)
        except Exception as exc:
            return await _err(f"保存文件失败: {exc}")
        try:
            preview = self.service.preview_import(str(target))
        except Exception as exc:
            return await _err(f"预览失败: {exc}")
        return await _ok({"preview": preview, "path": str(target)})

    async def import_run(self):
        payload = await _json_body({})
        path = clean_text(payload.get("path"), 2000)
        if not path:
            return await _err("path is required")
        persona_mapping = payload.get("persona_mapping")
        if not isinstance(persona_mapping, dict):
            persona_mapping = {}
        user_mapping = payload.get("user_mapping")
        if not isinstance(user_mapping, dict):
            user_mapping = {}
        try:
            result = await self.service.import_data(
                path,
                persona_mapping=persona_mapping,
                user_mapping=user_mapping,
                merge_duplicates=_bool(payload.get("merge_duplicates"), True),
            )
        except Exception as exc:
            return await _err(f"导入失败: {exc}", 500)
        return await _ok({"result": result})

    async def import_batches(self):
        return await _ok({"batches": self.service.store.list_import_batches(limit=30)})

    async def config_schema(self):
        schema = self._load_config_schema()
        config_file = self.service._config_file_path()
        values = self.service.config_values(schema)
        disk_snapshot: dict[str, Any] = {}
        try:
            if config_file.exists():
                raw = json.loads(config_file.read_text(encoding="utf-8-sig"))
                if isinstance(raw, dict):
                    disk_snapshot = raw
        except Exception:
            disk_snapshot = {}
        return await _ok(
            {
                "schema": schema,
                "values": values,
                "provider_options": self._provider_options(self.plugin.context),
                "embedding_provider_options": await self._embedding_provider_options(),
                "rerank_provider_options": await self._rerank_provider_options(),
                "config_file": CONFIG_FILE_NAME,
                "config_file_path": str(config_file),
                "config_file_exists": config_file.exists(),
                "disk_snapshot": disk_snapshot,
                "runtime_embedding_enabled": (values.get("retrieval") or {}).get("embedding_enabled"),
            }
        )

    async def config_module_update(self):
        payload = await _json_body({})
        module = clean_text(payload.get("module"), 80)
        values = payload.get("values")
        if not isinstance(values, dict):
            return await _err("values must be an object")
        schema = self._load_config_schema()
        ok, message = self.service.update_config_module(module, values, schema)
        if not ok:
            return await _err(message)
        return await _ok(
            {
                "updated": True,
                "message": message,
                "values": self.service.config_values(schema).get(module, {}),
            }
        )

    async def config_module_reset(self):
        payload = await _json_body({})
        module = clean_text(payload.get("module"), 80)
        ok, message = self.service.reset_config_module(module, self._load_config_schema())
        if not ok:
            return await _err(message)
        return await _ok({"updated": True, "message": message})

    async def maintenance_run(self):
        try:
            report = await self.service.run_maintenance()
        except Exception as exc:
            return await _err(f"维护失败: {exc}", 500)
        return await _ok({"report": report})

    async def maintenance_decay(self):
        """立即执行一次每日减权衰减检测。"""
        try:
            report = await self.service.run_daily_decay()
        except Exception as exc:
            return await _err(f"衰减失败: {exc}", 500)
        return await _ok({"report": report})

    async def debug_last_prompt(self):
        """返回最近一次总结/衰减发送给 LLM 的完整 prompt（调试用，不截断）。"""
        return await _ok(self.service._last_llm_prompt or {"ok": False, "reason": "尚无 LLM 调用记录"})

    async def debug_main_prompt(self):
        """返回最近一次主链对话实际发送给 LLM 的完整内容（注入前，调试用）。"""
        return await _ok(self.service._last_main_prompt or {"ok": False, "reason": "尚无主链对话记录"})

    async def debug_persona(self):
        """返回最近一次人格解析链路结果（调试用）。"""
        return await _ok(self.service._last_persona_resolve or {"ok": False, "reason": "尚无解析记录"})

    async def thanks_images(self):
        """返回特别鸣谢头像图片（data URL，避免受限 iframe 静态资源加载问题）。"""
        import base64
        import mimetypes

        images: dict[str, str] = {}
        root = Path(__file__).resolve().parent / "Special_Thanks"
        try:
            for name in ("DS", "QED", "SO2"):
                for ext in ("png", "jpg", "jpeg", "gif", "webp"):
                    path = root / f"{name}.{ext}"
                    if path.exists():
                        raw = path.read_bytes()
                        mime = mimetypes.guess_type(path.name)[0] or "image/png"
                        images[name] = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                        break
        except Exception as exc:
            logger.warning("[DeepMemory] 读取特别鸣谢头像失败: %s", exc)
        return await _ok({"images": images})

    async def author_talk(self):
        """读取「作者的话」文档（插件目录 Special_Thanks 下的 .md 文件，改文件即更新页面）。"""
        root = Path(__file__).resolve().parent / "Special_Thanks"
        content = ""
        filename = ""
        updated_at = ""
        try:
            for md in sorted(root.glob("*.md")):
                content = md.read_text(encoding="utf-8")
                filename = md.name
                import time as _time

                updated_at = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(md.stat().st_mtime))
                break
        except Exception as exc:
            logger.warning("[DeepMemory] 读取作者的话失败: %s", exc)
        return await _ok({"content": content, "filename": filename, "updated_at": updated_at})

    async def backup(self):
        try:
            result = self.service.export_backup()
        except Exception as exc:
            return await _err(f"备份失败: {exc}", 500)
        return await _ok({"result": result})

    async def summary_test(self):
        """测试总结模型调用链（流式优先），用于排查总结超时/失败。"""
        try:
            result = await self.service.test_summary_provider()
        except Exception as exc:
            return await _err(f"总结模型测试失败: {exc}", 500)
        return await _ok(result)

    async def logs(self):
        logs = self.service.store.recent_injection_logs(
            limit=min(100, max(1, _query_int("limit", 30))),
            session_id=clean_text(_query_get("session_id", ""), 200),
        )
        return await _ok({"items": logs})

    async def bridge_status(self):
        from .core.bridge import get_deepmemory_bridge

        bridge = get_deepmemory_bridge()
        return await _ok(
            {
                "available": bridge is not None,
                "enabled": self.service.config.bool("bridge.enabled", True),
                "accept_external_records": self.service.config.bool("bridge.accept_external_records", True),
                "allowed_source_plugins": clean_text(self.service.config.get("bridge.allowed_source_plugins", ""), 500),
            }
        )

    # ------------------------------------------------------------------ 外观

    async def appearance_get(self):
        appearance = self.service.get_appearance()
        appearance["bg_data_url"] = self.service.background_data_url()
        return await _ok({"appearance": appearance})

    async def appearance_update(self):
        payload = await _json_body({})
        fields = payload.get("appearance")
        if not isinstance(fields, dict):
            fields = payload
        appearance = self.service.set_appearance(fields)
        appearance["bg_data_url"] = self.service.background_data_url()
        return await _ok({"appearance": appearance})

    async def appearance_reset(self):
        appearance = self.service.reset_appearance()
        appearance["bg_data_url"] = self.service.background_data_url()
        return await _ok({"appearance": appearance})

    async def appearance_background(self):
        """上传背景图片。字段名固定为 file。"""
        try:
            files = await _request_files()
        except Exception as exc:
            return await _err(f"读取上传文件失败: {exc}")
        upload = files.get("file") if files else None
        if upload is None:
            return await _err("missing file")
        import_dir = self.service.data_dir / "backgrounds"
        import_dir.mkdir(parents=True, exist_ok=True)
        filename = clean_text(getattr(upload, "filename", "") or "bg.png", 240)
        ext = Path(filename).suffix or "png"
        target = import_dir / f"bg{ext}"
        try:
            await _save_upload(upload, target)
        except Exception as exc:
            return await _err(f"保存背景图片失败: {exc}")
        try:
            result = self.service.save_background_image(target.read_bytes(), ext)
        except ValueError as exc:
            return await _err(str(exc))
        except Exception as exc:
            return await _err(f"背景图片处理失败: {exc}")
        result["appearance"] = self.service.get_appearance()
        return await _ok(result)

    async def appearance_background_clear(self):
        result = self.service.clear_background_image()
        result["appearance"] = result.pop("appearance", {})
        result["bg_data_url"] = ""
        return await _ok(result)

    # ------------------------------------------------------------------ 运行时日志

    async def runtime_logs_get(self):
        lines = min(2000, max(50, _query_int("lines", 300)))
        level = clean_text(_query_get("level", ""), 10)
        return await _ok(self.service.runtime_logs(lines=lines, level=level))

    async def runtime_logs_clear(self):
        result = self.service.clear_runtime_logs()
        return await _ok(result)
