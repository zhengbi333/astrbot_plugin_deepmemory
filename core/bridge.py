from __future__ import annotations

from typing import Any

from .models import SessionContext


class DeepMemoryBridge:
    """面向其他插件（如陪伴插件）的公开桥接接口。

    通过 astrbot_plugin_deepmemory.core.bridge.get_deepmemory_bridge()
    获取全局实例；桥接开关与外部写入权限可在设置页「插件协同桥接」中配置。
    """

    def __init__(self, service: Any):
        self._service = service

    # ------------------------------------------------------------- 写入

    async def add_memory(
        self,
        *,
        content: str,
        memory_type: str = "fact",
        summary: str = "",
        tags: list[str] | None = None,
        importance: float | None = None,
        confidence: float | None = None,
        session_context: SessionContext | dict[str, Any] | None = None,
        persona_id: str = "",
        scope: str = "",
        visibility: str = "",
        subject: dict[str, Any] | None = None,
        object: dict[str, Any] | None = None,
        source_plugin: str = "external",
        metadata: dict[str, Any] | None = None,
        occurred_at: str = "",
    ) -> str:
        """写入一条长期记忆，返回 memory_id。"""
        return await self._service.record_external_event(
            content=content,
            memory_type=memory_type,
            summary=summary,
            tags=tags,
            importance=importance,
            confidence=confidence,
            ctx=session_context,
            persona_id=persona_id,
            scope=scope,
            visibility=visibility,
            subject=subject,
            object=object,
            source_plugin=source_plugin,
            metadata=metadata,
            occurred_at=occurred_at,
        )

    async def record_visible_turn(
        self,
        *,
        role: str,
        content: str,
        session_context: SessionContext | dict[str, Any] | None = None,
    ) -> str:
        """把一条可见对话记录进短期时间线（供阶段总结使用），返回事件 ID。"""
        ctx = session_context if isinstance(session_context, SessionContext) else SessionContext.from_dict(session_context)
        if ctx is None:
            raise ValueError("session_context is required")
        await self._service.resolve_persona(ctx)
        from .models import TimelineEvent

        event = TimelineEvent(
            session_id=ctx.session_id,
            scope=ctx.scope,
            platform=ctx.platform,
            user_id=ctx.user_id,
            user_name=ctx.user_name,
            group_id=ctx.group_id,
            group_name=ctx.group_name,
            bot_id=ctx.bot_id,
            persona_id=ctx.persona_id,
            role=clean_role(role),
            content=content[:2000],
        )
        self._service.store.add_timeline_event(event)
        await self._service.maybe_summarize_session(ctx)
        return event.id

    async def record_bot_action(
        self,
        *,
        content: str,
        session_context: SessionContext | dict[str, Any] | None = None,
        source_plugin: str = "external",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """记录一条「Bot 自己做了什么」的记忆（自我时间线/日程/行动）。"""
        return await self.add_memory(
            content=content,
            memory_type="self_action",
            session_context=session_context,
            source_plugin=source_plugin,
            metadata=metadata,
        )

    async def record_persona_life(
        self,
        *,
        content: str,
        session_context: SessionContext | dict[str, Any] | None = None,
        source_plugin: str = "external",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """记录一条 Bot 拟人生活的记忆（心情、日常、经历，间接表述）。"""
        return await self.add_memory(
            content=content,
            memory_type="persona_life",
            session_context=session_context,
            source_plugin=source_plugin,
            metadata=metadata,
        )

    # ------------------------------------------------------------- 读取

    async def search(
        self,
        query: str,
        *,
        session_context: SessionContext | dict[str, Any] | None = None,
        top_k: int = 6,
    ) -> list[dict[str, Any]]:
        """按当前会话可见性检索记忆。"""
        return await self._service.bridge_search(
            query, session_context=session_context, top_k=top_k
        )

    async def recall(
        self,
        query: str,
        *,
        session_context: SessionContext | dict[str, Any] | None = None,
        top_k: int = 6,
    ) -> list[dict[str, Any]]:
        """search 的别名，语义更贴近陪伴场景。"""
        return await self.search(query, session_context=session_context, top_k=top_k)

    async def compose_injection(
        self,
        query: str,
        *,
        session_context: SessionContext | dict[str, Any] | None = None,
        top_k: int | None = None,
        max_chars: int | None = None,
    ) -> str:
        """生成一段可直接注入提示词的记忆包。"""
        return await self._service.bridge_compose_injection(
            query, session_context=session_context, top_k=top_k, max_chars=max_chars
        )

    def set_injection_managed(self, enabled: bool) -> None:
        """由外部插件（如陪伴插件）托管记忆注入。

        True 时本插件不再在 on_llm_request 自动注入记忆（捕获与总结不受影响），
        改由调用方通过 inject_for_event 注入。
        """
        self._service.external_injection_managed = bool(enabled)

    async def inject_for_event(self, req: Any, event: Any) -> bool:
        """由外部插件（如陪伴插件）托管注入：解析事件上下文并注入记忆到请求。"""
        return await self._service.bridge_inject_for_event(req, event)

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        record = self._service.store.get_memory(memory_id)
        return record.to_dict() if record else None

    def list_recent_memories(
        self,
        *,
        session_context: SessionContext | dict[str, Any] | None = None,
        limit: int = 10,
        memory_type: str = "",
        lifecycle: str = "active",
    ) -> list[dict[str, Any]]:
        """按会话/用户返回最近记忆（不带检索词）。"""
        ctx = session_context if isinstance(session_context, SessionContext) else SessionContext.from_dict(session_context)
        records = self._service.store.list_memories(
            limit=limit,
            session_id=(ctx.session_id if ctx else "") or "",
            user_id=(ctx.user_id if ctx else "") or "",
            scope=(ctx.scope if ctx and ctx.scope != "unknown" else "") or "",
            memory_type=memory_type,
            lifecycle=lifecycle,
            order_by="occurred_at DESC",
        )
        return [record.to_dict() for record in records]

    async def resolve_persona_for(self, session_context: SessionContext | dict[str, Any]) -> str:
        """查询某会话当前使用的人格 ID（与 AstrBot 一致：会话绑定 → 全局默认 → default）。"""
        ctx = session_context if isinstance(session_context, SessionContext) else SessionContext.from_dict(session_context)
        await self._service.resolve_persona(ctx)
        return ctx.persona_id

    def get_timeline(
        self,
        *,
        session_context: SessionContext | dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """返回最近时间线事件（供陪伴插件读取会话上下文）。"""
        ctx = session_context if isinstance(session_context, SessionContext) else SessionContext.from_dict(session_context)
        events = self._service.store.recent_timeline(
            limit=limit,
            session_id=(ctx.session_id if ctx else "") or "",
            persona_id=(ctx.persona_id if ctx else "") or "",
        )
        return [event.to_dict() for event in events]

    # ------------------------------------------------------------- 管理

    async def update_importance(self, memory_id: str, importance: float) -> bool:
        return await self._service.update_importance(memory_id, importance)

    def delete_memory(self, memory_id: str) -> bool:
        return self._service.store.delete_memory(memory_id)

    def list_personas(self) -> list[dict[str, Any]]:
        return [persona.to_dict() for persona in self._service.store.list_personas()]

    def get_persona(self, persona_id: str) -> dict[str, Any] | None:
        persona = self._service.store.get_persona(persona_id)
        return persona.to_dict() if persona else None

    def create_persona(self, persona_id: str, name: str = "", description: str = "") -> dict[str, Any]:
        from .models import Persona

        persona = self._service.store.upsert_persona(
            Persona(persona_id=persona_id, name=name or persona_id, description=description)
        )
        return persona.to_dict()

    def set_user_persona(self, user_key: str, persona_id: str) -> bool:
        if self._service.store.get_persona(persona_id) is None:
            return False
        self._service.store.set_user_persona(user_key, persona_id)
        return True

    def list_users(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._service.store.list_users(limit=limit)

    def get_user(self, user_key: str) -> dict[str, Any] | None:
        return self._service.store.get_user(user_key)

    def delete_user_memories(self, user_key: str) -> int:
        """删除某用户的全部私聊记忆，返回删除条数。"""
        return self._service.store.delete_user(user_key)

    async def summarize_now(self, session_context: SessionContext | dict[str, Any]) -> dict[str, Any]:
        ctx = session_context if isinstance(session_context, SessionContext) else SessionContext.from_dict(session_context)
        if ctx is None:
            return {"ok": False, "reason": "no_session"}
        await self._service.resolve_persona(ctx)
        return await self._service._summarize_session_inner(ctx)

    async def run_maintenance(self) -> dict[str, Any]:
        return await self._service.run_maintenance()

    def run_retention(self) -> dict[str, Any]:
        return self._service.run_retention()

    def export(self, *, format: str = "jsonl", scope: str = "", persona_id: str = "") -> dict[str, Any]:
        return self._service.export_data(format=format, scope=scope, persona_id=persona_id)

    def preview_import(self, path: str, *, limit: int = 5) -> dict[str, Any]:
        return self._service.preview_import(path, limit=limit)

    async def import_data(self, path: str, *, persona_mapping: dict[str, str] | None = None) -> dict[str, Any]:
        return await self._service.import_data(path, persona_mapping=persona_mapping)

    def health(self) -> dict[str, Any]:
        return self._service.health()

    def stats(self) -> dict[str, Any]:
        return self._service.store.stats()

    def coordination_status(self) -> dict[str, Any]:
        """供陪伴插件询问协同状态。"""
        return {
            "available": True,
            "persona_isolation": self._service.config.bool("isolation.persona_isolation_enabled", True),
            "user_isolation": self._service.config.bool("isolation.user_isolation_enabled", True),
            "accept_external_records": self._service.config.bool("bridge.accept_external_records", True),
            "injection_enabled": self._service.config.bool("injection.enabled", True),
        }

    def token_stats(self) -> dict[str, Any]:
        """只读 token 统计（陪伴插件 Token 页读取记忆插件单独调用；零副作用）。"""
        getter = getattr(self._service, "token_stats", None)
        if not callable(getter):
            return {}
        return getter() or {}


def clean_role(role: str) -> str:
    value = str(role or "user").strip().lower()
    return "user" if value in {"user", "member", "sender", "group_member"} else ("bot" if value in {"bot", "assistant"} else "user")


def get_deepmemory_bridge() -> "DeepMemoryBridge | None":
    """从插件主模块取当前对外暴露的记忆桥实例。

    延迟导入 main 以避免 main ↔ bridge 的循环依赖；
    插件卸载或桥接开关关闭时返回 None。
    """
    from ..main import get_deepmemory_bridge as _fetch

    return _fetch()


def bridge_status() -> dict:
    """识别接口：供其他插件（如陪伴插件）探测本插件的联动可用性。

    只读、零副作用；返回 availability、版本号、桥接与协同配置摘要。
    未安装/未加载时调用方拿不到本函数（import 失败），此函数只回答
    「已加载后桥接是否可用」。
    """
    from .service import PLUGIN_VERSION

    status: dict = {
        "available": False,
        "name": "为你篆刻的历史",
        "version": PLUGIN_VERSION,
        "reason": "",
    }
    bridge = get_deepmemory_bridge()
    if bridge is None:
        status["reason"] = "插件已加载但桥接对象未就绪（可能已停用，或设置页「插件协同桥接 → 启用桥接 API」被关闭）"
        return status
    status["available"] = True
    status["reason"] = "正常"
    try:
        info = bridge.coordination_status() or {}
        status["reason"] = "正常"
        if not info.get("accept_external_records", True):
            status["reason"] = "已联动，但「接受外部写入」被关闭，外部写入会被拒绝"
        for key in ("persona_isolation", "user_isolation", "accept_external_records", "injection_enabled"):
            if key in info:
                status[f"dm_{key}"] = info[key]
    except Exception as exc:
        status["reason"] = f"已联动（协同状态查询失败: {exc}）"
    return status
