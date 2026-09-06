from __future__ import annotations

import inspect
import re
from typing import Any

from .models import EntityRef, SessionContext, clean_text


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def parse_scope_from_session(session_id: str) -> tuple[str, str]:
    """从 AstrBot 会话键解析作用域与目标 ID，如 aiocqhttp:GroupMessage:123456。"""
    normalized = session_id.lower()
    if ":groupmessage:" in normalized:
        return "group", _tail_after_token(session_id, normalized, ":groupmessage:")
    if ":group:" in normalized:
        return "group", session_id.rsplit(":", 1)[-1]
    if ":friendmessage:" in normalized:
        return "private", _tail_after_token(session_id, normalized, ":friendmessage:")
    if ":privatemessage:" in normalized:
        return "private", _tail_after_token(session_id, normalized, ":privatemessage:")
    if ":friend:" in normalized or ":private:" in normalized:
        return "private", session_id.rsplit(":", 1)[-1]
    return "unknown", ""


def _tail_after_token(original: str, normalized: str, token: str) -> str:
    index = normalized.rfind(token)
    if index < 0:
        return ""
    return original[index + len(token):]


def normalize_session_fields(
    *,
    session_id: str = "",
    scope: str = "",
    platform: str = "",
    user_id: str = "",
    group_id: str = "",
) -> dict[str, str]:
    session_id = clean_text(session_id, 200)
    scope = clean_text(scope, 40) or "unknown"
    platform = clean_text(platform, 80)
    user_id = clean_text(user_id, 120)
    group_id = clean_text(group_id, 120)
    parsed_scope, parsed_target = parse_scope_from_session(session_id)
    if scope == "unknown" and parsed_scope != "unknown":
        scope = parsed_scope
    if not platform and session_id and ":" in session_id:
        platform = session_id.split(":", 1)[0]
    if scope == "private" and not user_id and parsed_target:
        user_id = parsed_target
    if scope == "group" and not group_id and parsed_target:
        group_id = parsed_target
    return {
        "session_id": session_id,
        "scope": scope,
        "platform": platform,
        "user_id": user_id,
        "group_id": group_id,
    }


class IdentityResolver:
    async def resolve_event_context(self, event: Any) -> SessionContext:
        session_id = clean_text(getattr(event, "unified_msg_origin", "") or "", 200)
        platform = await self._call(event, "get_platform_name")
        if not platform and session_id and ":" in session_id:
            platform = session_id.split(":", 1)[0]

        scope, parsed_target = parse_scope_from_session(session_id)
        group_id = await self._call(event, "get_group_id")
        if group_id:
            scope = "group"
        elif scope == "group" and parsed_target:
            group_id = parsed_target
        group_name = await self._call(event, "get_group_name")
        if not group_name:
            message_obj = getattr(event, "message_obj", None)
            for source in (event, message_obj):
                if source is None:
                    continue
                for attr in ("group_name", "groupname", "group"):
                    value = getattr(source, attr, "")
                    if value:
                        group_name = clean_text(value, 80)
                        break
                if group_name:
                    break
            raw = getattr(message_obj, "raw_message", None)
            if not group_name and isinstance(raw, dict):
                group_name = clean_text(raw.get("group_name") or raw.get("group") or "", 80)

        user_id = await self._call(event, "get_sender_id")
        if not user_id and scope == "private" and parsed_target:
            user_id = parsed_target
        user_name = await self._call(event, "get_sender_name")
        bot_id = await self._call(event, "get_self_id")
        bot_name = await self._call(event, "get_self_name")
        text = await self._message_text(event)
        message_id = self._message_id(event)

        if not session_id:
            if scope == "group" and group_id:
                session_id = f"{platform or 'unknown'}:GroupMessage:{group_id}"
            elif user_id:
                session_id = f"{platform or 'unknown'}:FriendMessage:{user_id}"

        if scope == "unknown" and user_id:
            scope = "private"

        return SessionContext(
            session_id=session_id,
            scope=scope,
            platform=clean_text(platform, 80),
            user_id=clean_text(user_id, 120),
            user_name=clean_text(user_name, 80),
            group_id=clean_text(group_id, 120),
            group_name=clean_text(group_name, 80),
            bot_id=clean_text(bot_id, 120),
            bot_name=clean_text(bot_name, 80),
            message_id=clean_text(message_id, 120),
            message_text=clean_text(text, 2000),
        )

    async def _call(self, event: Any, name: str) -> str:
        func = getattr(event, name, None)
        if not callable(func):
            return ""
        try:
            value = await maybe_await(func())
        except Exception:
            return ""
        return "" if value is None else str(value)

    async def _message_text(self, event: Any) -> str:
        getter = getattr(event, "get_message_str", None)
        if callable(getter):
            try:
                value = await maybe_await(getter())
                if isinstance(value, str):
                    return value
            except Exception:
                pass
        value = getattr(event, "message_str", "")
        return value if isinstance(value, str) else ""

    def _message_id(self, event: Any) -> str:
        message_obj = getattr(event, "message_obj", None)
        for source in (message_obj, event):
            if source is None:
                continue
            for attr in ("message_id", "id"):
                value = getattr(source, attr, None)
                if value:
                    return str(value)
        raw = getattr(message_obj, "raw_message", None)
        if isinstance(raw, dict):
            for key in ("message_id", "id"):
                if raw.get(key):
                    return str(raw.get(key))
        return ""

    def extract_media_descriptors(self, event: Any) -> dict[str, list]:
        """提取事件中的多模态内容：图片/表情、文件、视频、语音、网址。

        返回结构：
        {
            "images": [url...],        # 图片与表情（含 url 或 file 引用）
            "files":  [{"name","path","url"}...],
            "videos": [{"name","url"}...],
            "records":[{"name","url","text"}...],
            "urls":   [完整网址...],
        }
        """
        images: list[str] = []
        files: list[dict] = []
        videos: list[dict] = []
        records: list[dict] = []
        urls: list[str] = []
        for comp in self._message_components(event):
            cls = type(comp).__name__
            if cls in ("Image", "Face"):
                url = str(getattr(comp, "url", "") or getattr(comp, "file", "") or "")
                if url:
                    images.append(clean_text(url, 500))
            elif cls == "File":
                files.append(
                    {
                        "name": clean_text(getattr(comp, "name", "") or "", 200),
                        "path": clean_text(getattr(comp, "file_", "") or "", 500),
                        "url": clean_text(getattr(comp, "url", "") or "", 500),
                    }
                )
            elif cls == "Video":
                videos.append(
                    {
                        "name": clean_text(getattr(comp, "file", "") or "", 200),
                        "url": clean_text(getattr(comp, "url", "") or "", 500),
                    }
                )
            elif cls == "Record":
                records.append(
                    {
                        "name": clean_text(getattr(comp, "file", "") or "", 200),
                        "url": clean_text(getattr(comp, "url", "") or "", 500),
                        "text": clean_text(getattr(comp, "text", "") or "", 300),
                    }
                )
            elif cls == "Share":
                url = clean_text(getattr(comp, "url", "") or "", 500)
                if url:
                    urls.append(url)
            elif cls == "Plain":
                text = str(getattr(comp, "text", "") or "")
                urls.extend(re.findall(r"https?://[^\s<>\"']+", text))
        return {
            "images": images,
            "files": files,
            "videos": videos,
            "records": records,
            "urls": urls,
        }

    def _message_components(self, event: Any) -> list[Any]:
        getter = getattr(event, "get_messages", None)
        if callable(getter):
            try:
                chain = getter()
                return chain if isinstance(chain, list) else []
            except Exception:
                pass
        message_obj = getattr(event, "message_obj", None)
        chain = getattr(message_obj, "message", None)
        return chain if isinstance(chain, list) else []


def entity_for_user(ctx: SessionContext, verified: bool = True) -> EntityRef:
    return EntityRef(
        kind="user",
        id=ctx.user_id,
        name=ctx.user_name,
        role="current_sender",
        verified=verified,
        verified_by="platform",
    )


def entity_for_current_target(ctx: SessionContext) -> EntityRef:
    if ctx.scope == "group":
        return EntityRef(kind="group", id=ctx.group_id, name=ctx.group_name, role="current_group")
    return EntityRef(kind="user", id=ctx.user_id, name=ctx.user_name, role="current_private_user")


def looks_like_command(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        # 空文本不是命令：可能是图片/表情/文件等媒体消息，不应被命令过滤跳过
        return False

    def _strip_decorations(value: str) -> str:
        current = value.strip()
        for _ in range(8):
            previous = current
            current = re.sub(
                r"^(?:\[CQ:at,[^\]]+\]|\[At:[^\]]+\]|\[at:[^\]]+\])\s*", "", current, flags=re.I
            )
            current = re.sub(
                r"^(?:\[Reply:[^\]]+\]|\[reply:[^\]]+\]|\[引用消息[^\]]*\])\s*", "", current, flags=re.I
            )
            current = re.sub(r"^(?:<at\b[^>]*>|<reply\b[^>]*>)\s*", "", current, flags=re.I)
            current = re.sub(r"^@\S{1,64}\s+", "", current)
            if current == previous:
                break
        return current.strip()

    command_prefixes = ("/", "／", "!", "！", "#", "＃", "﹟")
    candidates = (stripped, _strip_decorations(stripped))
    if any(candidate.startswith(command_prefixes) for candidate in candidates):
        return True
    if re.fullmatch(r"[\W_]+", stripped):
        return True
    return False
