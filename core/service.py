from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .log import logger

from .config import ConfigView
from .identity import IdentityResolver, entity_for_current_target, entity_for_user, maybe_await
from .log import (
    clear_log_files,
    log_files,
    read_tail,
    reset_file_handler,
    setup_plugin_logging,
)
from .models import (
    EntityRef,
    MemoryRecord,
    Persona,
    SearchResult,
    SessionContext,
    TimelineEvent,
    clean_text,
    clamp_float,
    json_loads,
    new_id,
    utc_now,
)
from .retrieval import RetrievalEngine
from .store import MemoryStore
from .token_usage import DeepMemoryTokenStore, estimate_tokens

try:
    from astrbot.core.agent.message import TextPart
except Exception:  # pragma: no cover
    try:
        from astrbot.api.message import TextPart  # type: ignore
    except Exception:
        TextPart = None  # type: ignore

INJECTION_HEADER = "<DeepMemory-Context>"
INJECTION_FOOTER = "</DeepMemory-Context>"

# 模块级全局总结去重集合：插件可能被 AstrBot 重载出多个实例，
# 用全局集合避免多实例对同一会话并发触发重复总结
# 集合值为触发时间戳，超时自动失效，防止异常挂起的任务永久阻塞该会话
_GLOBAL_SUMMARY_INFLIGHT: dict[str, float] = {}

# 总结任务的最长执行时间（秒），超过视为异常挂起
_SUMMARY_INFLIGHT_TTL = 300.0

# 常见 AstrBot 清空上下文指令（/reset 及其常见别名）
RESET_COMMAND_RE = re.compile(
    r"^\s*(?:/|／|!|！)?\s*(?:reset|清空|重置|清除上下文|清空上下文|重置上下文)\s*$",
    re.IGNORECASE,
)

# 轮次计算：相邻事件间隔超过该分钟数视为新会话片段（新轮起点）
_ROUND_GAP_MINUTES = 30

# 群聊系统/状态通知（退群、入群、撤回等），不进入时间线
_SYSTEM_NOTICE_RE = re.compile(
    r"(退出了群聊|退出群聊|加入群聊|退群|入群|被移出群聊|撤回了一条消息|拍了拍|"
    r"已成为管理员|被取消管理员|群聊名称已修改|开启了全员禁言|关闭了全员禁言|"
    r"解散了群聊|开启了禁止加群|关闭了禁止加群)",
    re.IGNORECASE,
)

PLUGIN_VERSION = "alpha-0.81"
PLUGIN_DISPLAY_NAME = "为你篆刻的历史"

INJECTION_BLOCK_RE = re.compile(
    r"\n*\s*<DeepMemory-Context>.*?</DeepMemory-Context>\s*", re.DOTALL
)

CONFIG_FILE_NAME = "astrbot_plugin_deepmemory_config.json"


def _coerce_config_dict(config: Any) -> dict[str, Any]:
    """把 AstrBot 传入的配置（dict 或 AstrBotConfig 等对象）安全转为 dict。"""
    if isinstance(config, dict):
        return dict(config)
    if config is None:
        return {}
    for getter in ("dict", "to_dict", "get_data", "get_config"):
        fn = getattr(config, getter, None)
        if callable(fn):
            try:
                value = fn()
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
    try:
        return dict(config)
    except Exception:
        return {}

SUMMARY_PROMPT_TEMPLATE = (
    "你是记忆整理助手。请把下面最近几轮对话总结为一条长期记忆。\n"
    "要求：\n"
    "1. 输出严格的 JSON 对象（不要数组），包含 content（综合总结正文，2-5 句话，保留有价值的事实、"
    "偏好、关系信息与承诺）、summary（一句话摘要）、memory_type（fact/preference/event/relationship/promise）、"
    "importance（0.0-1.0）、tags（字符串数组）。\n"
    "2. 称呼规则：用户称呼为「{user_name}」，机器人自称「{bot_name}」。"
    "总结正文中必须使用这些称呼来描述双方，禁止使用「用户」「机器人」「对方」等通称。\n"
    "3. 对话可能包含多位不同的人（群聊）：每行发言前标有说话人姓名，"
    "总结时必须严格按说话人区分内容，绝对禁止把一个人的发言归到另一个人名下。\n"
    "4. 不要编造对话中不存在的信息；寒暄、无信息量内容忽略。\n"
    "5. 去重规则：本轮对话若没有产生新事实、新偏好、新关系变化或新承诺（比如只是寒暄、重复打招呼、"
    "或关系信息与已总结过的内容相同），就不要再输出 relationship 型记忆；"
    "同一个人物之间的同一条关系信息在记忆库里只应存在一次。\n"
    "{persona_hint}"
    "{group_rules}"
    "媒体说明：对话中的 [图片]/[表情]/[文件]/[链接]/[视频]/[语音] 等标记代表对方发送了多媒体内容；"
    "其中出现的重要事实（文档里的关键内容、链接指向的重要内容、图片展示的关键事物）应纳入总结；"
    "纯表情互动、无信息量的图可以不用特意记录。\n"
    "对话：\n{events}"
)

# 群聊总结附加规则：他人互相讨论是旁观背景，禁止写成「对我说」，且只提炼与机器人相关的信息
GROUP_SUMMARY_RULES = (
    "\n6. 群聊规则：以下对话来自群聊，其中大部分内容是成员之间的相互讨论，属于旁观背景。"
    "禁止把成员之间的互相讨论写成「问我/对我说/向我提问/让我」。"
    "只有直接与机器人对话的内容（提及机器人、回复机器人、机器人参与的互动）才允许使用「对我说/问我」。"
    "总结时只提炼与机器人相关的信息（机器人被委托的事、做出的承诺、日程安排、与成员的直接互动）；"
    "成员之间的纯闲聊不写入记忆。\n"
)

# 群聊总结附加规则（all 全员捕获）：旁观视角提炼成员间有价值信息
GROUP_SUMMARY_RULES_ALL = (
    "\n6. 群聊规则（全员捕获）：本会话开启了全员捕获，以下对话包含成员之间的讨论。"
    "总结时以旁观者视角提炼有价值的信息：成员之间新出现的约定、事件、事实、关系变化、"
    "日程安排、时间地点等公共信息都可以写入记忆；"
    "禁止把成员之间的互相讨论写成「问我/对我说/向我提问/让我」；"
    "机器人直接参与的互动正常记录。\n"
)

# 无信息总结识别：LLM 判定本轮无值得保留内容时，不写入垃圾记忆
_NO_INFO_SUMMARY_RE = re.compile(
    r"(没有(值得|可)?(保留|记录|存储|写入)?的?(长期)?(信息|内容|记忆|互动|对话)"
    r"|没有新(信息|内容)|无(新)?(信息|内容)"
    r"|未(获取|获得|参与)(新)?(信息|内容|互动)"
    r"|没有(参与|进行)(任何)?(群聊|对话|互动))",
    re.IGNORECASE,
)

# 总结时可参考的人格/用户设定前缀（空时整段省略）
PERSONA_HINT_RULE = (
    "\n7. 参考设定：下面是本会话配置的人格提示词与用户提示词，"
    "仅用于帮助你正确理解机器人的身份、称呼习惯与用户背景；"
    "仍然只允许总结对话中真实发生的内容，禁止把设定里没有发生的事写成记忆。\n"
    "{persona}\n"
)

DECAY_PROMPT_TEMPLATE = (
    "你是记忆整理助手。请把下面一组长期记忆碎片压缩为一条更精炼的高层记忆，丢弃重复与过时细节，保留仍然重要的信息。\n"
    "输出严格的 JSON 对象，包含 content、summary、memory_type（fact/summary/relationship）、"
    "importance（0.0-1.0）、tags（数组）字段。只用 JSON 输出。\n\n"
    "碎片：\n{items}"
)


class DeepMemoryService:
    def __init__(
        self,
        *,
        context: Any,
        config: dict[str, Any] | None,
        plugin_root: Path,
        data_dir: Path,
    ):
        self.context = context
        self.plugin_root = plugin_root
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self._raw_config: dict[str, Any] = _coerce_config_dict(config)
        self._config_mtime: float = 0.0
        self._config_loaded = False
        self._load_runtime_overrides(force=True)
        self.config = ConfigView(self._raw_config)
        self.identity = IdentityResolver()
        self.store = MemoryStore(data_dir / "deepmemory.db")
        self.token_store = DeepMemoryTokenStore(data_dir)
        self.retrieval = RetrievalEngine(
            self.store, self.config, context, note_usage=self._note_token_usage
        )

        self._summary_inflight: dict[str, float] = _GLOBAL_SUMMARY_INFLIGHT
        self._embed_backfill_task: asyncio.Task | None = None
        self._maintenance_task: asyncio.Task | None = None
        self._summary_scan_task: asyncio.Task | None = None
        self._bg_tasks: set[asyncio.Task] = set()
        self._embedding_provider_cache: tuple[Any, str] | None = None
        self._last_maintenance_at = ""
        self._last_llm_prompt: dict[str, Any] = {}   # 最近一次发给 LLM 的 prompt（调试用）
        self._last_main_prompt: dict[str, Any] = {}  # 最近一次主链对话的完整请求内容（调试用）
        self._last_persona_resolve: dict[str, Any] = {}  # 最近一次人格解析结果（调试用）
        self.external_injection_managed: bool = False  # 由外部插件（如陪伴插件）托管记忆注入时置 True


    def _inflight_has(self, session_key: str) -> bool:
        """检查会话是否在总结中；超过 TTL 视为异常挂起并自动清除。"""
        stamp = self._summary_inflight.get(session_key)
        if stamp is None:
            return False
        if time.monotonic() - stamp > _SUMMARY_INFLIGHT_TTL:
            self._summary_inflight.pop(session_key, None)
            logger.warning("[DeepMemory] 总结任务疑似挂起，已解除防重: session=%s", session_key)
            return False
        return True

    def _inflight_add(self, session_key: str) -> None:
        self._summary_inflight[session_key] = time.monotonic()

    def _inflight_discard(self, session_key: str) -> None:
        self._summary_inflight.pop(session_key, None)

    def _spawn(self, coro: Any, label: str) -> asyncio.Task:
        task = asyncio.create_task(coro, name=f"deepmemory:{label}")
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    # ================================================================== config

    def _config_file_path(self) -> Path:
        """AstrBot 插件配置文件路径（与 AstrBot 配置系统一致）。

        数据目录形如 <data>/plugin_data/<plugin_name>，配置文件在 <data>/config/<plugin_name>_config.json，
        因此需要向上两级（parent.parent）——此前写错为 parent 导致配置写入 plugin_data/config/ 错误位置。
        """
        parent = self.data_dir.parent
        if parent.name == "plugin_data":
            parent = parent.parent
        return parent / "config" / CONFIG_FILE_NAME

    def _load_runtime_overrides(self, *, force: bool = False) -> None:
        """从磁盘读取运行时配置覆盖（主配置文件为唯一权威来源）。带 mtime 检测。"""
        try:
            main = self._config_file_path()
            try:
                mtime = main.stat().st_mtime if main.exists() else 0.0
            except OSError:
                mtime = 0.0
            if not force and self._config_loaded and mtime == self._config_mtime:
                return
            if main.exists():
                data = json.loads(main.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    merged = dict(self._raw_config)
                    for key, value in data.items():
                        if isinstance(value, dict) and isinstance(merged.get(key), dict):
                            merged[key] = {**merged[key], **value}
                        else:
                            merged[key] = value
                    self._raw_config = merged
            self._config_mtime = mtime
            self._config_loaded = True
            loaded_value = self._raw_config.get("retrieval", {}).get("embedding_enabled", None)
            logger.info(
                "[DeepMemory] 运行时配置已加载: source=%s embedding_enabled=%s",
                main.name if main.exists() else "none",
                loaded_value,
            )
        except Exception as exc:
            logger.warning("[DeepMemory] 读取运行时配置失败: %s", exc, exc_info=True)

    def save_config(self) -> bool:
        """保存运行时配置到磁盘（主配置文件）。返回是否写入成功（失败不静默）。"""
        try:
            path = self._config_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._raw_config, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
            try:
                self._config_mtime = path.stat().st_mtime
            except OSError:
                pass
            return True
        except Exception as exc:
            logger.warning("[DeepMemory] 保存主配置文件失败: %s", exc, exc_info=True)
            return False

    def update_config_module(self, module: str, values: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, str]:
        module_schema = schema.get(module)
        if not isinstance(module_schema, dict):
            return False, "未知配置模块"
        items = module_schema.get("items")
        if not isinstance(items, dict):
            return False, "配置模块格式错误"
        target = self._raw_config.setdefault(module, {})
        if not isinstance(target, dict):
            target = {}
            self._raw_config[module] = target
        for key, item_schema in items.items():
            if key not in values or not isinstance(item_schema, dict):
                continue
            target[key] = self._coerce_config_value(values.get(key), item_schema)
        self.config = ConfigView(self._raw_config)
        self.retrieval.config = self.config
        if not self.save_config():
            return False, "配置已更新内存，但写入磁盘失败（请检查数据目录权限或 AstrBot 是否占用配置文件）"
        return True, "已保存"

    def reset_config_module(self, module: str, schema: dict[str, Any]) -> tuple[bool, str]:
        module_schema = schema.get(module)
        items = module_schema.get("items") if isinstance(module_schema, dict) else None
        if not isinstance(items, dict):
            return False, "未知配置模块"
        self._raw_config[module] = {
            key: item_schema.get("default")
            for key, item_schema in items.items()
            if isinstance(item_schema, dict) and "default" in item_schema
        }
        self.config = ConfigView(self._raw_config)
        self.retrieval.config = self.config
        if not self.save_config():
            return False, "配置已重置内存，但写入磁盘失败（请检查数据目录权限或 AstrBot 是否占用配置文件）"
        return True, "已重置为默认"

    @staticmethod
    def _coerce_config_value(value: Any, item_schema: dict[str, Any]) -> Any:
        value_type = clean_text(item_schema.get("type"), 40)
        if value_type == "bool":
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on", "开", "开启"}
            return bool(value)
        if value_type == "int":
            try:
                return int(value)
            except Exception:
                return int(item_schema.get("default", 0) or 0)
        if value_type == "float":
            try:
                return float(value)
            except Exception:
                return float(item_schema.get("default", 0.0) or 0.0)
        text = clean_text(value, 2000)
        options = item_schema.get("options")
        if isinstance(options, list) and options and text and text not in {str(option) for option in options}:
            return clean_text(item_schema.get("default", ""), 2000)
        return text

    def config_values(self, schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """读取当前配置值（供设置页渲染）。

        每次读取前强制从磁盘刷新运行时配置：AstrBot 重载插件时可能出现
        多个插件实例并存，Web API 请求可能命中内存配置为旧值的实例；
        磁盘文件是实例间共享的，从磁盘刷新可保证「保存后刷新页面仍显示新值」。
        """
        self._load_runtime_overrides()
        self.config = ConfigView(self._raw_config)
        result: dict[str, dict[str, Any]] = {}
        for module, module_schema in schema.items():
            items = module_schema.get("items") if isinstance(module_schema, dict) else None
            if not isinstance(items, dict):
                continue
            result[module] = {}
            for key, item_schema in items.items():
                if not isinstance(item_schema, dict):
                    continue
                result[module][key] = self.config.get(f"{module}.{key}", item_schema.get("default"))
        return result

    # ================================================================== lifecycle

    def cleanup_system_timeline(self) -> int:
        """标记时间线中的系统/状态通知事件（退群、入群、撤回等）为 is_system。

        此类事件在时间线中可见，但不参与未总结轮数、总结与 /reset 清理。
        """
        keywords = [
            "退群", "退出群聊", "加入群聊", "撤回了一条消息", "拍了拍",
            "已成为管理员", "被取消管理员", "被移出群聊", "解散了群聊",
            "群聊名称已修改", "开启了全员禁言", "关闭了全员禁言",
        ]
        marked = self.store.mark_system_timeline(keywords)
        if marked:
            logger.info("[DeepMemory] 已标记时间线系统通知: marked=%s", marked)
        return marked

    async def start(self) -> None:
        setup_plugin_logging(self.data_dir)
        self.cleanup_system_timeline()
        self._migrate_identity_meta()
        default_persona = "default"
        self.store.ensure_default_persona(default_persona, "默认人格")
        self.store.set_default_persona(default_persona)
        if self.config.bool("maintenance.auto_maintenance_enabled", True):
            self._maintenance_task = self._spawn(self._auto_maintenance_loop(), "maintenance")
        if self.config.bool("retrieval.embedding_enabled", False):
            self._embed_backfill_task = self._spawn(self._embed_backfill_loop(), "embed_backfill")
        if (
            self.config.bool("summary.auto_scan_enabled", True)
            and self.config.bool("summary.enabled", True)
        ):
            self._summary_scan_task = self._spawn(self._summary_scan_loop(), "summary_scan")
        logger.info(
            "[DeepMemory] 为你篆刻的历史已启动: db=%s personas=%s memories=%s",
            self.store.db_path,
            len(self.store.list_personas()),
            self.store.count_memories(),
        )

    async def aclose(self) -> None:
        tasks = [task for task in self._bg_tasks]
        if self._embed_backfill_task is not None:
            tasks.append(self._embed_backfill_task)
        if self._maintenance_task is not None:
            tasks.append(self._maintenance_task)
        if self._summary_scan_task is not None:
            tasks.append(self._summary_scan_task)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._bg_tasks.clear()
        self.store.close()

    async def _summary_scan_loop(self) -> None:
        """后台扫描：达标的未总结会话即使没有新消息也会被触发总结。"""
        while True:
            interval = max(15, self.config.int("summary.scan_interval_seconds", 60))
            await asyncio.sleep(interval)
            if not self.config.bool("general.enabled", True) or not self.config.bool("summary.enabled", True):
                continue
            try:
                await self._scan_ready_sessions()
            except Exception as exc:
                logger.debug("[DeepMemory] 总结扫描异常: %s", exc)

    async def _scan_ready_sessions(self) -> None:
        """按会话分组检查未总结进度，达标会话触发后台总结（与消息路径共用 inflight 防重）。"""
        events = self.store.unsummarized_timeline(limit=3000)
        by_session: dict[tuple[str, str, str], list] = {}
        for item in events:
            by_session.setdefault((item.persona_id, item.scope, item.session_id), []).append(item)
        trigger = self.config.int("summary.trigger_event_count", 8)
        group_trigger = self.config.int("summary.group_trigger_events", 15)
        min_events = self.config.int("summary.min_events", 4)
        group_min_events = self.config.int("summary.group_min_events", 6)
        interval_minutes = self.config.int("summary.trigger_interval_minutes", 90)
        for (persona_id, scope, session_id), session_events in by_session.items():
            is_group = scope == "group"
            count = len(session_events) if is_group else self._count_rounds(session_events)
            threshold = group_trigger if is_group else trigger
            # 0.81 轮完整性守卫（仅私聊）：不拆半轮（最后一段必须 bot 且距最后事件 ≥2 秒）
            if count >= threshold:
                if is_group or self._session_rounds_ready(session_events):
                    self._spawn_summary_if_free(session_id, scope, persona_id)
                continue
            needed = group_min_events if is_group else min_events
            if interval_minutes > 0 and count >= needed:
                earliest = session_events[0].occurred_at
                try:
                    earliest_dt = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - earliest_dt).total_seconds() >= interval_minutes * 60 and (is_group or self._session_rounds_ready(session_events)):
                        self._spawn_summary_if_free(session_id, scope, persona_id)
                except Exception:
                    pass

    def _spawn_summary_if_free(self, session_id: str, scope: str, persona_id: str) -> None:
        session_key = f"{persona_id}|{scope}|{session_id}"
        if self._inflight_has(session_key):
            return
        ctx = SessionContext(
            session_id=session_id,
            scope=scope,
            persona_id=persona_id,
        )
        self._inflight_add(session_key)
        self._spawn(self._summarize_task(ctx, session_key), "summary")

    # ================================================================== persona / session

    async def resolve_persona(self, ctx: SessionContext) -> str:
        """解析会话使用的记忆隔离键：严格跟随 AstrBot 当前人格。

        不再使用可配置的默认分区：直接读取 AstrBot 会话人格 ID 作为隔离键；
        会话未配置人格（persona_id 为空）时统一使用固定兜底 "default"。
        """
        if not self.config.bool("isolation.persona_isolation_enabled", True):
            ctx.persona_id = "default"
            return "default"
        persona_id = await self._astr_persona_id(ctx)
        if not persona_id:
            persona_id = "default"
        ctx.persona_id = persona_id
        return persona_id

    async def _astr_persona_id(self, ctx: SessionContext) -> str:
        """从 AstrBot 解析当前会话实际使用的人格 ID。

        与 AstrBot 主链一致：优先会话绑定人格；会话未绑定时回退
        全局默认人格（provider_settings.default_personality）。
        """
        result = ""
        error = ""
        cid = ""
        if self.context is None or not ctx.session_id:
            error = "no_context_or_session"
        else:
            try:
                manager = getattr(self.context, "conversation_manager", None)
                if manager is None:
                    error = "no_conversation_manager"
                else:
                    cid = await maybe_await(manager.get_curr_conversation_id(ctx.session_id))
                    if not cid:
                        error = "no_current_conversation"
                    else:
                        conv = await maybe_await(manager.get_conversation(ctx.session_id, cid))
                        if conv is None:
                            error = "conversation_not_found"
                        else:
                            result = clean_text(getattr(conv, "persona_id", "") or "", 120)
                            if not result:
                                error = "conversation_persona_empty"
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "[DeepMemory] 获取 AstrBot 会话人格失败: session=%s error=%s",
                    ctx.session_id, exc,
                )
        if not result and self.context is not None:
            # 会话未绑定时回退 AstrBot 全局默认人格（与主链行为一致）
            try:
                persona_mgr = getattr(self.context, "persona_manager", None)
                if persona_mgr is not None:
                    getter = getattr(persona_mgr, "get_default_persona_v3", None)
                    if callable(getter):
                        personality = await maybe_await(getter(ctx.session_id))
                        if isinstance(personality, dict):
                            name = clean_text(personality.get("name") or "", 120)
                        else:
                            name = clean_text(getattr(personality, "name", "") or "", 120)
                        if name and name != "default":
                            result = name
                            if not error:
                                error = "default_persona_fallback"
                        elif not error:
                            error = "no_persona_configured"
                elif not error:
                    error = "no_persona_manager"
            except Exception as exc:
                if not error:
                    error = f"default_persona_error: {exc}"
                logger.warning(
                    "[DeepMemory] 读取 AstrBot 默认人格失败: session=%s error=%s",
                    ctx.session_id, exc,
                )
        self._last_persona_resolve = {
            "time": utc_now(),
            "session_id": ctx.session_id,
            "persona_id": result or "",
            "conversation_id": cid or "",
            "error": error or "",
            "note": (
                "会话未绑定人格，已回退 AstrBot 全局默认人格。"
                "如需会话级绑定：AstrBot WebUI → 会话管理 → 打开该会话详情 → 设置人格。"
                if result and "persona" in error
                else ""
            ),
        }
        return result

    def touch_user(self, ctx: SessionContext) -> None:
        if not ctx.user_id:
            return
        self.store.upsert_user(
            user_key=f"{ctx.platform}:{ctx.user_id}",
            user_id=ctx.user_id,
            name=ctx.user_name,
            platform=ctx.platform,
            persona_id=ctx.persona_id,
            extra={"last_scope": ctx.scope, "last_session": ctx.session_id},
        )

    async def handle_reset_detection(self, event: Any) -> bool:
        """检测 AstrBot 清空上下文指令（/reset 等），同步清空当前会话的未总结缓存。

        返回是否命中指令。
        """
        if not self.config.bool("general.enabled", True):
            return False
        ctx = await self.identity.resolve_event_context(event)
        text = (ctx.message_text or "").strip()
        if not text or not RESET_COMMAND_RE.match(text):
            return False
        await self.resolve_persona(ctx)
        removed = self.store.delete_unsummarized_timeline(session_id=ctx.session_id)
        logger.info(
            "[DeepMemory] 检测到清空上下文指令，已清空未总结缓存: session=%s removed=%s",
            ctx.session_id, removed,
        )
        return True

    # ================================================================== capture

    async def handle_llm_request(self, event: Any, req: Any) -> None:
        if not self.config.bool("general.enabled", True):
            return
        if self._is_self_message(event):
            return
        if self._is_synthetic_event(event):
            return
        ctx = await self.identity.resolve_event_context(event)
        ctx.is_command = self._event_looks_command(event, ctx.message_text)
        await self.resolve_persona(ctx)
        self.touch_user(ctx)
        if self.config.bool("capture.enabled", True) and not ctx.is_command:
            # 主链请求前只捕获、不触发总结：
            # 总结与主链并发调用同一 API 时，免费/中转接口可能限流排队导致超时
            if self._group_capture_allowed(ctx):
                await self.capture_timeline(ctx, role="user", trigger_summary=False, event=event, req=req)
        if self.config.bool("capture.enabled", True) and self._group_capture_allowed(ctx):
            await self.ensure_identity_memory(ctx)
        self._record_main_prompt(ctx, req)
        if not self.config.bool("injection.enabled", True):
            return
        if self.external_injection_managed:
            # 注入已由外部插件（如陪伴插件）托管，本插件跳过自动注入（捕获不受影响）
            return
        await self.inject_memories(ctx, req)
        # 记录注入后的最终请求（调试页展示实际发送给 LLM 的内容，含记忆注入块）
        self._record_main_prompt(ctx, req)

    @staticmethod
    def _is_synthetic_event(event: Any) -> bool:
        """识别合成/主动消息事件（如陪伴插件主动问候），不作为真实用户消息捕获。

        仅使用确定性特征：消息 ID 带合成前缀、或 sender 与会话键相同
        （合成事件常把会话键当用户 ID）。
        注意：不能使用 is_wake / is_at_or_wake_command——AstrBot 对
        「@机器人 / 私聊 / 唤醒词」的真实消息也会置 True，误判会导致全部消息被跳过。
        """
        try:
            message_obj = getattr(event, "message_obj", None)
            if message_obj is None:
                return False
            message_id = str(getattr(message_obj, "message_id", "") or "")
            if message_id.startswith(("private_companion_", "companion_", "synthetic_")):
                return True
            session_id = str(getattr(event, "unified_msg_origin", "") or "")
            sender = getattr(message_obj, "sender", None)
            user_id = str(getattr(sender, "user_id", "") or "") if sender is not None else ""
            if user_id and session_id and user_id == session_id:
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _is_self_message(event: Any) -> bool:
        """识别平台回显的「机器人自己发出的消息」（sender == 自身 ID）。

        部分 OneBot 实现会把 Bot 发出的消息作为 message 事件回传；若不识别，
        会被当成用户消息捕获进时间线（角色错位）。默认平台不上报，此为双保险。
        """
        try:
            self_id = getattr(event, "get_self_id", None)
            sender_id = getattr(event, "get_sender_id", None)
            if callable(self_id) and callable(sender_id):
                sid = str(self_id() or "")
                uid = str(sender_id() or "")
                if sid and uid:
                    return sid == uid
            message_obj = getattr(event, "message_obj", None)
            if message_obj is not None:
                obj_self = str(getattr(message_obj, "self_id", "") or "")
                sender = getattr(message_obj, "sender", None)
                obj_sender = str(getattr(sender, "user_id", "") or "") if sender is not None else ""
                if obj_self and obj_sender:
                    return obj_self == obj_sender
        except Exception:
            pass
        return False

    def _migrate_identity_meta(self) -> None:
        """0.79 存量迁移：旧版身份标识记忆（"在{time}给我发了消息…旨在说明…"）改为新文案并把重要性降到轻标记。

        幂等；只更新含旧模板特征的 identity 记忆。
        """
        try:
            fixed = self.store.update_identity_legacy_meta()
            if fixed:
                logger.info("[DeepMemory] 已迁移旧版身份标识记忆 %s 条", fixed)
        except Exception as exc:
            logger.warning("[DeepMemory] 身份标识记忆迁移失败: %s", exc)

    def _group_capture_allowed(self, ctx: SessionContext) -> bool:
        """群聊捕获开关：off 时群聊完全不捕获、不沉淀身份记忆（私聊不受影响）。"""
        if ctx.scope != "group":
            return True
        mode = clean_text(self.config.get("capture.group_capture_mode", "off"), 20) or "off"
        return mode != "off"

    def _record_main_prompt(self, ctx: SessionContext, req: Any) -> None:
        """记录最近一次主链对话实际发送给 LLM 的完整内容（含记忆注入，调试用）。"""
        try:
            def part_text(part: Any) -> str:
                if isinstance(part, str):
                    return part
                text = getattr(part, "text", None)
                return text if isinstance(text, str) else str(part)

            prompt = getattr(req, "prompt", "") or ""
            system = getattr(req, "system_prompt", "") or ""
            contexts = getattr(req, "contexts", None) or []
            extra = getattr(req, "extra_user_content_parts", None) or []
            context_lines: list[str] = []
            for item in contexts:
                if isinstance(item, dict):
                    context_lines.append(f"[{item.get('role', '?')}] {item.get('content', '')}")
                else:
                    role = getattr(item, "role", "?")
                    content = getattr(item, "content", None)
                    if content is None:
                        content = part_text(item)
                    context_lines.append(f"[{role}] {content}")
            self._last_main_prompt = {
                "time": utc_now(),
                "session_id": ctx.session_id,
                "is_command": bool(ctx.is_command),
                "system_prompt": system,
                "prompt": prompt,
                "contexts": context_lines,
                "extra_parts": [part_text(p) for p in extra],
            }
        except Exception as exc:
            logger.debug("[DeepMemory] 记录主链 prompt 失败: %s", exc)

    async def ensure_identity_memory(self, ctx: SessionContext) -> None:
        """为当前用户沉淀身份记忆（按 人格+用户+作用域 幂等）。

        私聊与群聊各自沉淀一条：私聊记忆只对私聊会话可见，群聊记忆只对
        归属群可见；隔离开启时同一用户在私聊/群聊都能被正确识别。
        群聊捕获关闭时跳过。
        """
        if not self._group_capture_allowed(ctx):
            return
        if not ctx.user_id or not ctx.user_name:
            return
        existing = self.store.list_memories(
            memory_type="identity",
            persona_id=ctx.persona_id,
            user_id=ctx.user_id,
            scope=ctx.scope,
            group_id=ctx.group_id if ctx.scope == "group" else "",
            limit=5,
        )
        if existing:
            return
        try:
            template = self.config.get("capture.identity_prompt_template", "") or ""
            # 0.79：旧版模板（0.42 的"在{time}给我发了消息…旨在说明…"）会让记忆库出现
            # "旨在说明你知道对方叫…"这类元信息文案（用户反感），且同样内容会被注入侧清洗——
            # 识别旧模板特征后忽略，改用新默认（用户自己后续改的自定义值不含这些特征则保留）
            if "旨在说明" in template or "给我发了消息" in template:
                template = ""
            if not template:
                template = "我记得{user_name}这个名字，用于确认我认识{user_name}，与亲密度、互动等无关。"
            now_local = self._local_now_str()
            try:
                content = template.format(
                    user_name=ctx.user_name,
                    time=now_local,
                    user_id=ctx.user_id,
                    platform=ctx.platform or "",
                )
            except Exception:
                content = f"我记得{ctx.user_name}这个名字"
            await self.add_memory(
                ctx=ctx,
                content=content,
                memory_type="identity",
                summary=f"我记得{ctx.user_name}",
                tags=["认识的人", "称呼"],
                importance=0.3,   # 0.79：身份标识是轻标记（旧 0.85 会压过真实记忆排在检索最前）
                confidence=0.95,
                source="capture",
                metadata={
                    "identity_scope": "user_name",
                    "platform_user_id": ctx.user_id,
                    "platform": ctx.platform,
                    "first_seen_at": now_local,
                },
            )
            logger.info(
                "[DeepMemory] 已沉淀用户身份记忆: user=%s id=%s persona=%s",
                ctx.user_name, ctx.user_id, ctx.persona_id,
            )
        except Exception as exc:
            logger.warning("[DeepMemory] 写入用户身份记忆失败: %s", exc)

    def _log_op(self, content: str) -> None:
        """把记忆库管理操作写入时间线（红色标记，不参与未总结、不影响轮数）。"""
        try:
            event = TimelineEvent(
                scope="public",
                role="system",
                content=f"[记忆库操作] {content}",
                is_system=True,
                kind="op",
            )
            self.store.add_timeline_event(event)
        except Exception as exc:
            logger.warning("[DeepMemory] 记录操作日志失败: %s", exc)

    def _local_now_str(self) -> str:
        tz_name = self.config.get("general.timezone", "Asia/Shanghai") or "Asia/Shanghai"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone(timedelta(hours=8))
        return datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    async def handle_group_message(self, event: Any) -> None:
        if not self.config.bool("general.enabled", True) or not self.config.bool("capture.enabled", True):
            return
        if self._is_self_message(event):
            return
        if self._is_synthetic_event(event):
            return
        ctx = await self.identity.resolve_event_context(event)
        if not ctx.user_id:
            return
        if self._event_looks_command(event, ctx.message_text):
            return
        # 群聊捕获模式：off 不捕获 / related 只捕获与机器人相关 / all 全部
        mode = clean_text(self.config.get("capture.group_capture_mode", "off"), 20) or "off"
        if mode == "off":
            return
        if mode == "related" and not self._is_bot_related(ctx):
            return
        # 与主链捕获去重（同一 message_id 只记录一次）
        if ctx.message_id and self.store.timeline_duplicate(ctx.session_id, ctx.message_id):
            return
        await self.resolve_persona(ctx)
        self.touch_user(ctx)
        if not self.config.bool("capture.capture_group_when_not_mentioned", True):
            return
        await self.capture_timeline(ctx, role="group_member", event=event)

    async def handle_llm_response(self, event: Any, resp: Any) -> None:
        if not self.config.bool("general.enabled", True) or not self.config.bool("capture.enabled", True):
            return
        if not self.config.bool("capture.capture_bot_responses", True):
            return
        if self._is_self_message(event):
            return
        if self._is_synthetic_event(event):
            return
        ctx = await self.identity.resolve_event_context(event)
        if not self._group_capture_allowed(ctx):
            return
        await self.resolve_persona(ctx)
        completion = getattr(resp, "completion_text", "") or ""
        bot_min = max(1, self.config.int("capture.bot_min_chars", 1))
        if not isinstance(completion, str) or len(completion.strip()) < bot_min:
            return
        logger.info(
            "[DeepMemory] 捕获 Bot 回复: session=%s persona=%s chars=%s",
            ctx.session_id, ctx.persona_id, len(completion),
        )
        await self._append_timeline(
            ctx=ctx,
            role="bot",
            content=clean_text(completion, self.config.int("capture.capture_max_chars", 1200)),
        )

    async def capture_timeline(
        self,
        ctx: SessionContext,
        *,
        role: str = "user",
        trigger_summary: bool = True,
        event: Any = None,
        req: Any = None,
    ) -> None:
        if not self.config.bool("capture.capture_user_messages", True):
            return
        # 统一去重：同一会话同一消息 ID 只记录一次（群聊捕获 / 主链捕获 / ALL 捕获可能重复触发）
        if ctx.message_id and self.store.timeline_duplicate(ctx.session_id, ctx.message_id):
            return
        text = ctx.message_text or ""
        media_note = ""
        if event is not None and self._has_media_content(event):
            media_note = await self._describe_event_media(ctx, event, req)
        # capture_min_chars 仅作用于「用户消息」：过滤无意义短文本，防噪音
        if len(text.strip()) < self.config.int("capture.capture_min_chars", 1) and not media_note:
            return
        content = text.strip()
        if media_note:
            content = f"{content}\n{media_note}" if content else media_note
        await self._append_timeline(
            ctx=ctx,
            role=role,
            content=clean_text(content, self.config.int("capture.capture_max_chars", 1200)),
            trigger_summary=trigger_summary,
        )

    async def handle_message_capture(self, event: Any) -> None:
        """通用消息捕获（私聊入口）：覆盖不触发主链的消息（如纯图片/表情）。

        群聊仍由 handle_group_message 按模式处理；私聊在此统一捕获，
        与主链捕获通过 message_id 去重。同时处理消息撤回通知。
        """
        if not self.config.bool("general.enabled", True) or not self.config.bool("capture.enabled", True):
            return
        if self._is_self_message(event):
            return
        if self._is_synthetic_event(event):
            return
        # 撤回通知：从时间线移除被撤回的消息（未总结部分），不依赖用户身份
        recalled_message_id = self._extract_recall_message_id(event)
        if recalled_message_id:
            removed = self.store.delete_timeline_by_message_id(recalled_message_id)
            if removed:
                logger.info(
                    "[DeepMemory] 检测到消息撤回，已从时间线移除: message_id=%s removed=%s",
                    recalled_message_id, removed,
                )
            return
        ctx = await self.identity.resolve_event_context(event)
        if not ctx.user_id:
            return
        if ctx.scope == "group":
            return
        # 通知类/空消息（无文本且无媒体，如群系统通知、戳一戳等）：不沉淀用户、不捕获
        if not ctx.message_text and not self._has_media_content(event):
            return
        if self._event_looks_command(event, ctx.message_text):
            return
        if ctx.message_id and self.store.timeline_duplicate(ctx.session_id, ctx.message_id):
            return
        await self.resolve_persona(ctx)
        self.touch_user(ctx)
        await self.capture_timeline(ctx, role="user", trigger_summary=False, event=event)

    @staticmethod
    def _extract_recall_message_id(event: Any) -> str:
        """从 OneBot 通知类事件提取被撤回的消息 ID（group_recall / friend_recall）。"""
        try:
            message_obj = getattr(event, "message_obj", None)
            if message_obj is None:
                return ""
            raw = getattr(message_obj, "raw_message", None)
            if not isinstance(raw, dict):
                return ""
            if raw.get("post_type") != "notice":
                return ""
            if raw.get("notice_type") not in ("group_recall", "friend_recall"):
                return ""
            return clean_text(raw.get("message_id") or "", 120)
        except Exception:
            return ""

    def _has_media_content(self, event: Any) -> bool:
        try:
            descriptors = self.identity.extract_media_descriptors(event)
            return bool(
                descriptors["images"] or descriptors["files"]
                or descriptors["videos"] or descriptors["records"]
            )
        except Exception:
            return False

    async def _describe_event_media(self, ctx: SessionContext, event: Any, req: Any = None) -> str:
        """生成多模态内容描述文本（优先复用 AstrBot 已理解结果，避免重复调用 LLM）。

        即使关闭模型理解，也返回基础类型标记（[图片]/[文件] 等），保证媒体消息可入时间线。
        """
        try:
            descriptors = self.identity.extract_media_descriptors(event)
        except Exception as exc:
            logger.debug("[DeepMemory] 提取多模态内容失败: %s", exc)
            return ""
        if not self.config.bool("capture.media_describe", True):
            # 仅基础标记，不做模型理解
            lines: list[str] = []
            for _ in descriptors["images"][:3]:
                lines.append("[图片]")
            for item in descriptors["files"]:
                lines.append(f"[文件] {item.get('name') or '文件'}")
            for item in descriptors["videos"]:
                lines.append(f"[视频] {item.get('name') or '视频'}")
            for item in descriptors["records"]:
                lines.append("[语音]")
            if descriptors["urls"]:
                lines.append(f"[链接] {' '.join(descriptors['urls'][:5])}")
            return "；".join(lines)
        lines: list[str] = []
        existing_captions = self._extract_existing_image_captions(req) if req is not None else []
        caption_index = 0
        for image_url in descriptors["images"][:3]:
            caption = ""
            if caption_index < len(existing_captions):
                caption = existing_captions[caption_index]
                caption_index += 1
            if not caption:
                caption = await self._caption_image(image_url, ctx)
            lines.append(f"[图片] {caption}" if caption else "[图片]")
        for item in descriptors["files"]:
            name = item.get("name") or "文件"
            summary = await self._summarize_document(item, ctx)
            lines.append(f"[文件] {name}" + (f"：{summary}" if summary else ""))
        for item in descriptors["videos"]:
            name = item.get("name") or "视频"
            lines.append(f"[视频] {name}")
        for item in descriptors["records"]:
            if item.get("text"):
                lines.append(f"[语音] {item['text']}")
            else:
                lines.append("[语音]")
        if descriptors["urls"]:
            links_line = await self._describe_links(ctx, descriptors["urls"])
            if links_line:
                lines.append(links_line)
            else:
                lines.append(f"[链接] {' '.join(descriptors['urls'][:5])}")
        return "；".join(lines)

    async def _fetch_page_context(self, url: str, *, timeout: float = 6.0) -> str:
        """拉取网页标题/描述/开头文字（链接记忆用；失败返回空串）。"""
        raw = ""
        try:
            import aiohttp

            headers = {"User-Agent": "AstrBot DeepMemory Media Reader"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status != 200:
                        return ""
                    raw = (await resp.content.read(65536)).decode("utf-8", errors="replace")
        except Exception:
            return ""
        title = ""
        desc = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
        for pattern in (
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        ):
            m = re.search(pattern, raw, re.S | re.I)
            if m:
                desc = re.sub(r"\s+", " ", m.group(1)).strip()[:400]
                if desc:
                    break
        body = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
        body = re.sub(r"<style.*?</style>", " ", body, flags=re.S | re.I)
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body).strip()
        return " | ".join(p for p in (title, desc, body[:500]) if p)[:1000]

    async def _describe_links(self, ctx: SessionContext, urls: list[str]) -> str:
        """链接记忆：标题（零 Token 抓取）+ 可选 LLM 要点（capture.link_summary）。"""
        if not urls:
            return ""
        detail_enabled = bool(self.config.bool("capture.link_summary", True))
        parts: list[str] = []
        for url in urls[:3]:
            context = await self._fetch_page_context(url)
            title = ""
            if context:
                title = re.split(r" \| ", context, maxsplit=1)[0].strip()
            if detail_enabled and title and len(context) > len(title):
                point = await self._link_point(context, title, ctx)
                if point:
                    parts.append(f"[链接] {title}：{point}")
                    continue
            if title:
                parts.append(f"[链接] {title}")
            else:
                parts.append(f"[链接] {url[:120]}")
        return "；".join(parts)

    async def _link_point(self, context: str, title: str, ctx: SessionContext) -> str:
        """基于网页上下文生成一句要点（不编造；失败空串）。"""
        attempts = await self._media_provider_attempts(ctx)
        if not attempts:
            return ""
        prompt = (
            "这是用户刚发来的一个链接的网页信息（标题/描述/开头文字），请用一句话说出"
            "「这条链接大致是什么」（用于记忆时间线记录；拿不准只给标题，不要编造）：\n\n"
            f"{context}"
        )
        for attempt in attempts:
            provider = attempt["provider"]
            try:
                result = await self._call_provider_text(provider, prompt, ctx, timeout=15, task="link_point")
                text = getattr(result, "completion_text", "") or ""
                if isinstance(text, str) and text.strip():
                    return clean_text(text, 200)
            except Exception as exc:
                logger.debug("[DeepMemory] 链接要点失败: source=%s error=%s", attempt["source"], exc)
        return ""

    @staticmethod
    def _extract_existing_image_captions(req: Any) -> list[str]:
        """从主链请求中提取已生成的图片描述：

        - AstrBot 群聊上下文注入的 [Image: xxx]；
        - 陪伴插件（为你续写的故事）注入的「（图片转述：xxx / 对方发来的图片：xxx）」，
          复用其识图结果，避免两张图被两个插件各调一次模型。
        """
        found: list[str] = []
        patterns = [
            re.compile(r"\[Image:\s*(.*?)\]"),
            re.compile(r"[（(](?:图片转述|对方发来的图片|对方发了个表情包)[：:]\s*(.*?)[。．.！!？?）)]"),
        ]

        def scan(value: Any) -> None:
            if not isinstance(value, str):
                return
            for pattern in patterns:
                found.extend(match.group(1).strip() for match in pattern.finditer(value))
            # 去重
            seen: list[str] = []
            for item in found:
                if item and item not in seen:
                    seen.append(item)
            found[:] = seen

        for part in getattr(req, "extra_user_content_parts", None) or []:
            scan(getattr(part, "text", None))
        for item in getattr(req, "contexts", None) or []:
            if isinstance(item, dict):
                scan(item.get("content"))
            else:
                scan(getattr(item, "content", None))
        scan(getattr(req, "prompt", "") or "")
        return [caption for caption in found if caption]

    async def _caption_image(self, image_url: str, ctx: SessionContext) -> str:
        """用视觉模型为图片/动图生成一句话描述（供时间线记录）。

        动图（GIF）：PIL 均匀抽 N 帧（默认 3）同一次请求传入，做连贯理解。
        """
        if not image_url or image_url.startswith("base64://"):
            return ""
        attempts = await self._media_provider_attempts(ctx)
        if not attempts:
            return ""
        prompt = self.config.get("capture.media_describe_prompt", "") or (
            "请用一句简洁中文描述这张图片的内容（用于记忆时间线记录，不要编造）。"
        )
        send_urls = [image_url]
        if self._looks_like_gif(image_url):
            frames = self._extract_gif_frames(image_url)
            if frames:
                send_urls = frames
                prompt = (
                    "这是同一张动态表情包/动图的 N 帧（按时间顺序）。请连贯理解它整体在表达什么"
                    "（情绪或梗），用一句简洁中文描述（用于记忆时间线记录，不要编造）。"
                )
        for attempt in attempts:
            provider = attempt["provider"]
            try:
                result = await self._call_provider_vision_multi(
                    provider, prompt, ctx, send_urls, timeout=20
                )
                text = getattr(result, "completion_text", "") or ""
                if isinstance(text, str) and text.strip():
                    return clean_text(text, 300)
            except Exception as exc:
                logger.debug("[DeepMemory] 图片描述失败: source=%s error=%s", attempt["source"], exc)
        return ""

    @staticmethod
    def _looks_like_gif(url: str) -> bool:
        low = str(url or "").lower()
        return low.endswith(".gif") or "gif" in low[:80]

    def _extract_gif_frames(self, image_url: str) -> list[str] | None:
        """本地抽 GIF 的 N 帧 → PNG 临时文件列表（动图连贯理解用）；失败 None。"""
        try:
            from PIL import Image as PILImage

            local = ""
            if str(image_url).startswith(("http://", "https://")):
                raw = None
                try:
                    raw = self._http_get_sync(image_url, timeout=10)
                except Exception:
                    raw = None
                if raw is None:
                    return None
                tmp = Path(self.data_dir) / f"dm_gif_{abs(hash(image_url))}.gif"
                tmp.write_bytes(raw)
                local = str(tmp)
            else:
                local = image_url
                if not Path(local).exists():
                    return None
            frames_n = max(1, min(9, int(self.config.int("capture.gif_frames", 3) or 3)))
            with PILImage.open(local) as img:
                if img.format != "GIF" and not getattr(img, "is_animated", False):
                    return None
                total = getattr(img, "n_frames", 1)
                if total <= 1:
                    indexes = [0]
                else:
                    indexes = sorted({round(i * (total - 1) / max(1, frames_n - 1)) for i in range(frames_n)})
                outs: list[str] = []
                for i in indexes:
                    img.seek(i)
                    frame = img.convert("RGB")
                    path = Path(self.data_dir) / f"dm_gif_{abs(hash(image_url))}_f{i}.png"
                    frame.save(path, "PNG")
                    outs.append(str(path))
                return outs
        except Exception as exc:
            logger.debug("[DeepMemory] 动图抽帧失败: %s", exc)
            return None

    async def _http_get(self, url: str, timeout: float = 8.0) -> bytes | None:
        import aiohttp

        headers = {"User-Agent": "AstrBot DeepMemory Media Reader"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.read()
        except Exception:
            return None

    @staticmethod
    def _http_get_sync(url: str, timeout: float = 10.0) -> bytes | None:
        """同步拉取（抽帧等非协程路径用；stdlib，1MB 上限）。"""
        import urllib.request

        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "AstrBot DeepMemory Media Reader"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(1 << 20)
        except Exception:
            return None

    async def _call_provider_vision_multi(
        self, provider: Any, prompt: str, ctx: SessionContext, image_urls: list[str], *, timeout: int = 45
    ) -> Any:
        """调用 Provider 的图片理解接口（多图同传，先记 token 后返回）。"""
        result = await self._call_provider_vision_multi_inner(provider, prompt, ctx, image_urls, timeout=timeout)
        self._note_token_usage("vision", provider, prompt, result)
        return result

    async def _call_provider_vision_multi_inner(
        self, provider: Any, prompt: str, ctx: SessionContext, image_urls: list[str], *, timeout: int = 45
    ) -> Any:
        """调用 Provider 的图片理解接口（多图同传）。"""
        text_chat = getattr(provider, "text_chat", None)
        if not callable(text_chat):
            raise TypeError(f"{type(provider).__name__} 不支持图片理解（缺少 text_chat）")
        if timeout > 0:
            return await asyncio.wait_for(
                text_chat(
                    prompt=prompt,
                    session_id=ctx.session_id,
                    image_urls=list(image_urls),
                    persist=False,
                ),
                timeout=timeout,
            )
        return await text_chat(
            prompt=prompt,
            session_id=ctx.session_id,
            image_urls=list(image_urls),
            persist=False,
        )

    async def _call_provider_vision(
        self, provider: Any, prompt: str, ctx: SessionContext, image_url: str, *, timeout: int = 45
    ) -> Any:
        """调用 Provider 的图片理解接口（text_chat + image_urls，先记 token 后返回）。"""
        result = await self._call_provider_vision_inner(provider, prompt, ctx, image_url, timeout=timeout)
        self._note_token_usage("vision", provider, prompt, result)
        return result

    async def _call_provider_vision_inner(
        self, provider: Any, prompt: str, ctx: SessionContext, image_url: str, *, timeout: int = 45
    ) -> Any:
        """调用 Provider 的图片理解接口（text_chat + image_urls）。"""
        text_chat = getattr(provider, "text_chat", None)
        if not callable(text_chat):
            raise TypeError(f"{type(provider).__name__} 不支持图片理解（缺少 text_chat）")
        if timeout > 0:
            return await asyncio.wait_for(
                text_chat(
                    prompt=prompt,
                    session_id=ctx.session_id,
                    image_urls=[image_url],
                    persist=False,
                ),
                timeout=timeout,
            )
        return await text_chat(
            prompt=prompt,
            session_id=ctx.session_id,
            image_urls=[image_url],
            persist=False,
        )

    _DOCUMENT_EXTENSIONS = {
        ".txt", ".md", ".json", ".yaml", ".yml", ".log", ".csv",
        ".py", ".js", ".ts", ".html", ".xml", ".ini", ".cfg", ".conf", ".toml",
    }

    async def _summarize_document(self, item: dict, ctx: SessionContext) -> str:
        """读取文本类文档并交给 LLM 生成摘要（供时间线记录）。"""
        path = str(item.get("path") or "") or str(item.get("url") or "")
        if not path:
            return ""
        try:
            doc_path = Path(path)
            if doc_path.suffix.lower() not in self._DOCUMENT_EXTENSIONS:
                return ""
            if not doc_path.exists():
                return ""
            limit = self.config.int("capture.media_document_max_chars", 20000)
            content = doc_path.read_text(encoding="utf-8", errors="replace")[:limit]
            if len(content.strip()) < 20:
                return ""
        except Exception:
            return ""
        attempts = await self._media_provider_attempts(ctx)
        if not attempts:
            return ""
        prompt = (
            "请用 2-3 句话概括以下文档内容（用于记忆时间线记录）：\n\n"
            f"{content}"
        )
        for attempt in attempts:
            provider = attempt["provider"]
            try:
                result = await self._call_provider_text(provider, prompt, ctx, timeout=20, task="document")
                text = getattr(result, "completion_text", "") or ""
                if isinstance(text, str) and text.strip():
                    return clean_text(text, 400)
            except Exception as exc:
                logger.debug("[DeepMemory] 文档摘要失败: source=%s error=%s", attempt["source"], exc)
        return ""

    async def _media_provider_attempts(self, ctx: SessionContext) -> list[dict[str, Any]]:
        """多模态理解用的 Provider 尝试列表：

        专用配置（capture.media_describe_provider_id）→ AstrBot 配置的默认图片理解模型
        （provider_settings.default_image_caption_provider_id）→ 总结主备链 → 当前会话。
        """
        custom = clean_text(self.config.get("capture.media_describe_provider_id", ""), 120)
        if custom:
            provider = await self._provider_by_id(custom, ctx)
            if provider is not None:
                return [{"source": "media_describe", "provider": provider}]
        astrbot_default = self._astrbot_default_image_provider()
        if astrbot_default:
            provider = await self._provider_by_id(astrbot_default, ctx)
            if provider is not None:
                return [{"source": "astrbot_image_caption", "provider": provider}]
        return await self._provider_attempts(
            ctx,
            prefix="summary",
            provider_key="provider_id",
            fallback_provider_key="fallback_provider_id",
            include_current=True,
        )

    def _astrbot_default_image_provider(self) -> str:
        """读取 AstrBot 配置的默认图片理解模型 ID（provider_settings.default_image_caption_provider_id）。"""
        try:
            data_root = self.data_dir.parent.parent
            config_dir = data_root / "config"
            if not config_dir.exists():
                return ""
            for path in sorted(config_dir.glob("abconf_*.json")):
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(raw, dict):
                    continue
                provider_settings = raw.get("provider_settings")
                if not isinstance(provider_settings, dict):
                    continue
                value = provider_settings.get("default_image_caption_provider_id") or ""
                if value:
                    return clean_text(value, 120)
        except Exception as exc:
            logger.debug("[DeepMemory] 读取 AstrBot 图片理解模型配置失败: %s", exc)
        return ""

    async def _append_timeline(self, ctx: SessionContext, *, role: str, content: str, trigger_summary: bool = True) -> None:
        if not content:
            return
        event = TimelineEvent(
            session_id=ctx.session_id,
            is_system=self._is_system_notice(content),
            scope=ctx.scope,
            platform=ctx.platform,
            user_id=ctx.user_id,
            user_name=ctx.user_name,
            group_id=ctx.group_id,
            group_name=ctx.group_name,
            bot_id=ctx.bot_id,
            persona_id=ctx.persona_id,
            role=role,
            content=content,
            message_id=ctx.message_id,
        )
        self.store.add_timeline_event(event)
        if trigger_summary:
            await self.maybe_summarize_session(ctx)

    def _looks_command(self, text: str) -> bool:
        from .identity import looks_like_command

        return looks_like_command(text)

    def _event_looks_command(self, event: Any, text: str) -> bool:
        """命令判定：解析后文本可能已被 AstrBot 剥离命令前缀（/reset -> reset），
        因此同时用原始消息文本（raw_message）判断。"""
        from .identity import looks_like_command

        if looks_like_command(text):
            return True
        raw_text = self._raw_event_text(event)
        return bool(raw_text and looks_like_command(raw_text))

    @staticmethod
    def _raw_event_text(event: Any) -> str:
        """从 raw_message 提取未剥离前缀的原始文本（OneBot raw_message/raw_text）。"""
        try:
            message_obj = getattr(event, "message_obj", None)
            if message_obj is None:
                return ""
            raw = getattr(message_obj, "raw_message", None)
            if isinstance(raw, dict):
                value = raw.get("raw_message") or raw.get("raw_text")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        except Exception:
            pass
        return ""

    # ================================================================== summary

    def _session_rounds_ready(self, events: list[Any]) -> bool:
        """0.81 轮完整性守卫：最后一段必须是 bot（本轮有回应）且距最后事件 ≥2 秒。

        后台扫描拍点可能在"用户刚说完、bot 回复还没进来"的瞬间触发总结，
        把半轮（只剩 user）当成完整轮总结掉——随后 bot 回复就成了没被总结的尾巴
        （用户实测:第三轮 user 被总结但 bot 两条待总结，且计数变成 bot-only 的 1/3）。
        缓冲拆条发送的 bot 尾巴间隔 0.8~4s，2 秒守卫可收齐大部分；剩下的由"最后一段必须
        是 bot"兜底（下一拍若最后事件仍是 user 则不触发，不会把半轮拆掉）。
        """
        if not events:
            return False
        last = events[-1]
        if getattr(last, "role", "") != "bot":
            return False
        try:
            ts = getattr(last, "occurred_at", "") or ""
            if ts:
                t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - t).total_seconds() < 2.0:
                    return False
        except Exception:
            pass
        return True

    async def maybe_summarize_session(self, ctx: SessionContext, *, force: bool = False) -> bool:
        """检查并触发阶段总结（后台执行，不阻塞回复）。

        以「对话轮数」计数：用户连续发言段（可多条消息）+ 随后机器人连续回复段算一轮；
        群聊消息彼此之间不区分轮次，因此群聊按「事件条数」计数触发。
        """
        if not self.config.bool("summary.enabled", True) and not force:
            return False
        if ctx.scope == "group" and not force and not self.config.bool("summary.group_enabled", False):
            return False
        session_key = f"{ctx.persona_id}|{ctx.scope}|{ctx.session_id}"
        if self._inflight_has(session_key):
            return False
        events = self.store.unsummarized_timeline(
            session_id=ctx.session_id,
            persona_id=ctx.persona_id,
            limit=300,
        )
        rounds = self._count_rounds(events)
        is_group = ctx.scope == "group"
        if is_group:
            count = len(events)
            trigger_rounds = self.config.int("summary.group_trigger_events", 15)
            min_rounds = self.config.int("summary.group_min_events", 6)
        else:
            count = rounds
            trigger_rounds = self.config.int("summary.trigger_event_count", 8)
            min_rounds = self.config.int("summary.min_events", 4)
        interval_minutes = self.config.int("summary.trigger_interval_minutes", 90)
        triggered = force or count >= trigger_rounds
        if not triggered and interval_minutes > 0 and count >= min_rounds:
            earliest = self.store.earliest_unsummarized_at(session_id=ctx.session_id)
            if earliest:
                try:
                    earliest_dt = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - earliest_dt).total_seconds() >= interval_minutes * 60:
                        triggered = True
                except Exception:
                    triggered = False
        # 0.81 轮完整性（仅私聊）：不拆半轮（最后一段必须是 bot 且距最后事件 ≥2 秒）；
        # 群聊按事件数触发、没有 user/bot 配对概念，不套守卫
        if triggered and not force and not is_group and not self._session_rounds_ready(events):
            return False
        if not triggered:
            return False
        self._inflight_add(session_key)
        logger.info(
            "[DeepMemory] 触发阶段总结: session=%s persona=%s rounds=%s events=%s trigger=%s",
            ctx.session_id, ctx.persona_id, rounds, len(events), "force" if force else "auto",
        )
        self._spawn(self._summarize_task(ctx, session_key), "summary")
        return True

    @staticmethod
    def _is_system_notice(text: str) -> bool:
        return bool(_SYSTEM_NOTICE_RE.search(text or ""))

    def _is_bot_related(self, ctx: SessionContext) -> bool:
        """判断群聊消息是否与机器人相关（提及/回复/直接对话）。"""
        text = ctx.message_text or ""
        if not text:
            return False
        bot_id = ctx.bot_id or ""
        bot_name = ctx.bot_name or ""
        if bot_id and f"[CQ:at,qq={bot_id}" in text:
            return True
        if bot_id and f"@{bot_id}" in text:
            return True
        if bot_name and len(bot_name) > 1 and bot_name in text:
            return True
        if bot_id and bot_id in text:
            return True
        return False

    @staticmethod
    def _count_rounds(events: list[Any]) -> int:
        """按轮计数：同侧连续发言为一段，用户每发起一段新对话计一轮。

        相邻事件间隔超过 _ROUND_GAP_MINUTES 视为新的会话片段，
        避免时间线上残留的旧未总结段与新对话粘合成一轮导致轮数不涨。
        """
        rounds = 0
        prev_side: str | None = None
        prev_time: str | None = None
        for event in events:
            side = "bot" if event.role == "bot" else "user"
            gap = False
            if prev_time and event.occurred_at:
                try:
                    t0 = datetime.fromisoformat(prev_time.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
                    gap = (t1 - t0).total_seconds() > _ROUND_GAP_MINUTES * 60
                except Exception:
                    gap = False
            if gap or side != prev_side:
                if side == "user":
                    rounds += 1
                prev_side = side
            prev_time = event.occurred_at or prev_time
        if events and events[0].role == "bot":
            rounds += 1
        return rounds

    def _group_summary_rules(self, ctx: SessionContext) -> str:
        """按群聊捕获模式选择总结附加规则：all 全员捕获提炼公共信息，related 只提炼与机器人相关。"""
        if ctx.scope != "group":
            return ""
        mode = clean_text(self.config.get("capture.group_capture_mode", "off"), 20) or "off"
        return GROUP_SUMMARY_RULES_ALL if mode == "all" else GROUP_SUMMARY_RULES

    async def _summarize_task(self, ctx: SessionContext, session_key: str) -> None:
        try:
            await self._summarize_session_inner(ctx)
        except Exception as exc:
            logger.warning("[DeepMemory] 阶段总结失败: session=%s error=%s", ctx.session_id, exc, exc_info=True)
        finally:
            self._inflight_discard(session_key)

    async def _conversation_prompt_text(self, ctx: SessionContext) -> str:
        """读取当前会话配置的人格/用户提示词，供总结时参考（取不到返回空串，不影响总结）。"""
        if self.context is None or not ctx.session_id:
            return ""
        try:
            manager = getattr(self.context, "conversation_manager", None)
            if manager is None:
                return ""
            cid = await maybe_await(manager.get_curr_conversation_id(ctx.session_id))
            if not cid:
                return ""
            conv = await maybe_await(manager.get_conversation(ctx.session_id, cid))
            if conv is None:
                return ""
            parts: list[str] = []
            persona = getattr(conv, "persona", None)
            if isinstance(persona, dict):
                name = clean_text(persona.get("name") or "", 120)
                prompt = clean_text(persona.get("prompt") or persona.get("content") or "", 3000)
            else:
                name = clean_text(getattr(persona, "name", "") or "", 120)
                prompt = clean_text(getattr(persona, "prompt", "") or "", 3000)
            if name:
                parts.append(f"人格：{name}")
            if prompt:
                parts.append(f"人格设定：{prompt}")
            user_prompt = clean_text(getattr(conv, "prompt", "") or "", 3000)
            system_prompt = clean_text(getattr(conv, "system_prompt", "") or "", 3000)
            if user_prompt:
                parts.append(f"用户提示词：{user_prompt}")
            if system_prompt:
                parts.append(f"系统提示词：{system_prompt}")
            return "\n".join(parts)[:4000]
        except Exception as exc:
            logger.debug("[DeepMemory] 读取会话提示词失败: %s", exc)
            return ""

    async def _summarize_session_inner(self, ctx: SessionContext) -> dict[str, Any]:
        events = self.store.unsummarized_timeline(
            session_id=ctx.session_id,
            persona_id=ctx.persona_id,
            limit=max(1, self.config.int("summary.max_events_per_summary", 30)),
        )
        if not events:
            return {"ok": False, "reason": "no_events"}
        user_name = ctx.user_name or "对方"
        bot_name = ctx.bot_name or "我"
        lines: list[str] = []
        prev_side: str | None = None
        round_no = 0
        for event in events:
            side = "bot" if event.role == "bot" else "user"
            if side == "user" and side != prev_side:
                round_no += 1
            prev_side = side
            if side == "bot":
                speaker = bot_name
            else:
                # 群聊多人：优先使用事件记录的具体发言人（昵称或 ID），避免混淆
                speaker = event.user_name or event.user_id or user_name
            lines.append(f"[第{round_no}轮] {speaker}: {event.content}")
        text = "\n".join(lines)
        max_input = self.config.int("summary.max_input_chars", 6000)
        if len(text) > max_input:
            text = text[:max_input] + "\n…(截断)"
        persona_text = await self._conversation_prompt_text(ctx)
        persona_hint = PERSONA_HINT_RULE.format(persona=persona_text) if persona_text else ""
        payload = await self._llm_json(
            SUMMARY_PROMPT_TEMPLATE.format(
                events=text,
                user_name=user_name,
                bot_name=bot_name,
                persona_hint=persona_hint,
                group_rules=self._group_summary_rules(ctx),
            ),
            ctx=ctx,
            prefix="summary",
        )
        if not payload:
            logger.info(
                "[DeepMemory] 阶段总结失败: session=%s rounds=%s reason=provider_no_output",
                ctx.session_id, round_no,
            )
            return {"ok": False, "reason": "provider_no_output"}
        item: dict[str, Any] | None = None
        if isinstance(payload, dict):
            item = payload
        elif isinstance(payload, list):
            # 兼容旧版数组输出：取第一条有效记忆
            for entry in payload:
                if isinstance(entry, dict) and clean_text(entry.get("content"), 120):
                    item = entry
                    break
        if item is None:
            return {"ok": False, "reason": "bad_llm_output"}
        max_chars = self.config.int("summary.max_summary_chars", 1200)
        # 无信息总结过滤：LLM 判定本轮无可保留内容时，不写入垃圾记忆，仅标记时间线已总结
        content_text = clean_text(item.get("content"), max_chars)
        summary_text = clean_text(item.get("summary"), 400)
        if _NO_INFO_SUMMARY_RE.search(content_text) or _NO_INFO_SUMMARY_RE.search(summary_text):
            self.store.mark_timeline_summarized(
                [event.id for event in events], ""
            )
            logger.info(
                "[DeepMemory] 阶段总结判定无新信息，跳过写入: session=%s events=%s",
                ctx.session_id, len(events),
            )
            return {"ok": True, "created": 0, "events": len(events), "skipped": True}
        created: list[str] = []
        # 群聊总结是群公共记忆，不归属触发总结的单个用户
        is_group = ctx.scope == "group"
        record_user_id = "" if is_group else ctx.user_id
        record_user_name = "" if is_group else ctx.user_name
        record = MemoryRecord(
            memory_type=clean_text(item.get("memory_type"), 60) or "summary",
            content=content_text,
            summary=summary_text,
            tags=[clean_text(tag, 80) for tag in (item.get("tags") or []) if clean_text(tag, 80)],
            importance=clamp_float(item.get("importance"), default=0.5),
            base_importance=clamp_float(item.get("importance"), default=0.5),
            confidence=0.7,
            subject=entity_for_current_target(ctx),
            object=EntityRef(kind="bot", id=ctx.bot_id or "self", name=ctx.bot_name or "我", role="bot_self", verified=True, verified_by="system"),
            scope=ctx.scope,
            persona_id=ctx.persona_id,
            platform=ctx.platform,
            session_id=ctx.session_id,
            user_id=record_user_id,
            user_name=record_user_name,
            group_id=ctx.group_id,
            group_name=ctx.group_name,
            bot_id=ctx.bot_id,
            lifecycle="active",
            visibility="private" if ctx.scope == "private" else "shared",
            source="summary",
            metadata={"source_session": ctx.session_id, "trigger": "timeline_summary", "event_count": len(events), "rounds": round_no},
        )
        created.append(record.id)
        # 指纹去重：与库内同人格、同指纹记忆合并，避免每次总结都堆积重复关系
        duplicate = self.store.find_duplicate(record)
        if duplicate is not None:
            self.store.mark_timeline_summarized([event.id for event in events], duplicate.id)
            logger.info(
                "[DeepMemory] 阶段总结内容与已有记忆重复，已合并: session=%s existing=%s",
                ctx.session_id, duplicate.id,
            )
            return {"ok": True, "created": 0, "events": len(events), "merged": True}
        self.store.upsert_memory(record)
        if created:
            self.store.mark_timeline_summarized(
                [event.id for event in events], created[0]
            )
            await self._background_embed_records([self.store.get_memory(mid) for mid in created])
            logger.info(
                "[DeepMemory] 阶段总结完成: session=%s events=%s rounds=%s created=%s",
                ctx.session_id, len(events), round_no, len(created),
            )
        return {"ok": bool(created), "created": len(created), "events": len(events)}

    # ================================================================== LLM

    async def _llm_json(
        self,
        prompt: str,
        *,
        ctx: SessionContext,
        prefix: str,
        fallback_prefix: str = "",
    ) -> Any:
        """调用 LLM 并解析 JSON 输出。

        按 主模型 → 备用模型 → 当前会话模型 的顺序逐个尝试；
        单个超时/失败会自动尝试下一个，全部失败后返回 None 并记录日志。
        """
        fallback_key = f"{fallback_prefix}.provider_id" if fallback_prefix else ""
        attempts = await self._provider_attempts(
            ctx,
            prefix=prefix,
            provider_key="provider_id",
            fallback_provider_key=fallback_key,
            include_current=True,
        )
        if not attempts:
            logger.warning("[DeepMemory] LLM 无可用 Provider: prefix=%s", prefix)
            return None
        timeout = self.config.int(f"{prefix}.provider_timeout_seconds", 60)
        started = time.monotonic()
        last_error = ""
        for attempt in attempts:
            source = attempt["source"]
            provider = attempt["provider"]
            try:
                result = await self._call_provider_text(provider, prompt, ctx, timeout=timeout, task=prefix)
                completion = getattr(result, "completion_text", "") or ""
            except asyncio.TimeoutError:
                last_error = "provider_timeout"
                logger.warning(
                    "[DeepMemory] LLM 调用超时(%ss): source=%s provider=%s prefix=%s",
                    timeout, source, type(provider).__name__, prefix,
                )
                continue
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "[DeepMemory] LLM 调用失败: source=%s provider=%s prefix=%s error=%s",
                    source, type(provider).__name__, prefix, exc,
                )
                continue
            if not completion:
                last_error = "provider_no_output"
                logger.warning(
                    "[DeepMemory] LLM 无输出: source=%s prefix=%s",
                    source, prefix,
                )
                continue
            logger.debug(
                "[DeepMemory] LLM 调用: prefix=%s source=%s elapsed_ms=%s",
                prefix, source, int((time.monotonic() - started) * 1000),
            )
            self._last_llm_prompt = {
                "time": utc_now(),
                "prefix": prefix,
                "source": source,
                "provider": type(provider).__name__,
                "prompt": prompt,
            }
            return self._extract_json(completion)
        logger.warning(
            "[DeepMemory] LLM 全部尝试失败: prefix=%s attempts=%s last_error=%s",
            prefix, [attempt["source"] for attempt in attempts], last_error,
        )
        return None

    def _note_token_usage(self, task: str, provider: Any, prompt: Any, result: Any) -> None:
        """LLM 调用成功后记一笔 token（真实 usage 优先，缺失时字符估算）。"""
        store = getattr(self, "token_store", None)
        if store is None:
            return
        try:
            usage = getattr(result, "usage", None)
            inp_real = out_real = None
            if usage is not None:
                try:
                    inp_real = int(getattr(usage, "input_other", 0) or 0) + int(getattr(usage, "input_cached", 0) or 0)
                    out_real = int(getattr(usage, "output", 0) or 0)
                except Exception:
                    inp_real = out_real = None
            inp = inp_real if (inp_real or 0) > 0 else estimate_tokens(prompt)
            text = str(getattr(result, "completion_text", "") or "")
            text += str(getattr(result, "reasoning_content", "") or "")
            out = out_real if (out_real or 0) > 0 else estimate_tokens(text)
            if inp == 0 and out == 0:
                return
            model = ""
            get_model = getattr(provider, "get_model", None)
            if callable(get_model):
                try:
                    model = str(get_model() or "")
                except Exception:
                    model = ""
            store.record(task=task, model=model or "default", input_tokens=inp, output_tokens=out)
        except Exception:
            pass

    def token_stats(self) -> dict:
        """只读 token 统计（供桥接接口转发给陪伴插件 Token 页）。"""
        store = getattr(self, "token_store", None)
        if store is None:
            return {"source": "memory", "total": {"input": 0, "output": 0, "sum": 0, "calls": 0},
                    "today": {"input": 0, "output": 0, "sum": 0, "calls": 0},
                    "month": {"input": 0, "output": 0, "sum": 0, "calls": 0},
                    "by_task": [], "by_model": [], "recent": []}
        try:
            return store.stats()
        except Exception:
            return {}

    async def _call_provider_text(
        self, provider: Any, prompt: str, ctx: SessionContext, *, timeout: int = 0, task: str = "chat"
    ) -> Any:
        """调用 Provider 文本对话接口（先记 token 后返回：真实 usage 或字符估算）。"""
        result = await self._call_provider_text_inner(provider, prompt, ctx, timeout=timeout)
        self._note_token_usage(task, provider, prompt, result)
        return result

    async def _call_provider_text_inner(self, provider: Any, prompt: str, ctx: SessionContext, *, timeout: int = 0) -> Any:
        """调用 Provider 文本对话接口。

        优先使用流式接口（text_chat_stream）：对话等慢速/拥挤 API 对非流式
        请求需等待完整生成，容易触发 SDK 超时，而流式请求持续返回数据；
        流式不可用或失败时回退非流式 text_chat，最后回退旧版 text。
        """

        async def wait_result(value: Any) -> Any:
            if not inspect.isawaitable(value):
                return value
            if timeout > 0:
                return await asyncio.wait_for(value, timeout=timeout)
            return await value

        text_chat_stream = getattr(provider, "text_chat_stream", None)
        if callable(text_chat_stream):
            try:
                return await self._collect_stream(
                    provider, text_chat_stream, prompt, ctx, timeout=timeout
                )
            except (asyncio.TimeoutError, Exception):
                # 流式失败/超时，回退非流式
                text_chat = getattr(provider, "text_chat", None)
                if callable(text_chat):
                    return await wait_result(text_chat(prompt=prompt, session_id=ctx.session_id))
        text_chat = getattr(provider, "text_chat", None)
        if callable(text_chat):
            return await wait_result(text_chat(prompt=prompt, session_id=ctx.session_id))
        text = getattr(provider, "text", None)
        if callable(text):
            return await wait_result(text(prompt, session_id=ctx.session_id))
        raise TypeError(
            f"{type(provider).__name__} 不支持 text_chat_stream/text_chat/text 接口，"
            "请确认 summary.provider_id 配置的是可对话的 LLM Provider"
        )

    @staticmethod
    async def _collect_stream(
        provider: Any,
        stream_method: Any,
        prompt: str,
        ctx: SessionContext,
        *,
        timeout: int = 0,
    ) -> Any:
        """聚合流式响应：优先取最后一个完整 chunk，否则拼接所有分片。"""

        async def consume() -> Any:
            full: Any = None
            parts: list[str] = []
            generator = stream_method(prompt=prompt, session_id=ctx.session_id)
            if inspect.isasyncgen(generator):
                async for chunk in generator:
                    full = chunk
                    text = getattr(chunk, "completion_text", "") or ""
                    if text:
                        parts.append(text)
            elif inspect.isawaitable(generator):
                generator = await generator
                async for chunk in generator:
                    full = chunk
                    text = getattr(chunk, "completion_text", "") or ""
                    if text:
                        parts.append(text)
            if full is not None and getattr(full, "completion_text", ""):
                return full
            combined = "".join(parts)
            if combined:
                return type("_StreamResult", (), {"completion_text": combined})()
            return full

        if timeout > 0:
            return await asyncio.wait_for(consume(), timeout=timeout)
        return await consume()

    async def test_summary_provider(self, *, mode: str = "auto") -> dict[str, Any]:
        """诊断总结模型：按 主模型 → 备用模型 → 当前会话模型 顺序测试调用。

        用于 UI 排查总结超时/失败问题（对话走流式很快，非流式总结可能被慢 API 拖垮）。
        """
        ctx = SessionContext(session_id="", scope="private")
        attempts = await self._provider_attempts(
            ctx,
            prefix="summary",
            provider_key="provider_id",
            fallback_provider_key="fallback_provider_id",
            include_current=True,
        )
        prompt = "请只回复四个字：测试成功。"
        timeout = self.config.int("summary.provider_timeout_seconds", 120)
        results: list[dict[str, Any]] = []
        for attempt in attempts:
            provider = attempt["provider"]
            info: dict[str, Any] = {
                "source": attempt["source"],
                "provider": type(provider).__name__,
            }
            provider_config = getattr(provider, "provider_config", None)
            if isinstance(provider_config, dict):
                info["sdk_timeout"] = provider_config.get("timeout", "默认 120")
            try:
                started = time.monotonic()
                result = await self._call_provider_text(provider, prompt, ctx, timeout=timeout, task="test")
                text = getattr(result, "completion_text", "") or ""
                info.update(
                    {
                        "ok": bool(text),
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                        "output": clean_text(text, 200),
                    }
                )
                if not text:
                    info["error"] = "无输出"
            except asyncio.TimeoutError:
                info.update({"ok": False, "error": f"调用超时（{timeout}s）"})
            except Exception as exc:
                info.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            results.append(info)
            if info.get("ok"):
                break
        return {
            "ok": bool(results) and bool(results[0].get("ok")),
            "config": {
                "provider_id": clean_text(self.config.get("summary.provider_id", ""), 120),
                "fallback_provider_id": clean_text(self.config.get("summary.fallback_provider_id", ""), 120),
                "timeout_seconds": timeout,
            },
            "results": results,
        }

    async def _provider_attempts(
        self,
        ctx: SessionContext,
        *,
        prefix: str,
        provider_key: str,
        fallback_provider_key: str,
        include_current: bool,
    ) -> list[dict[str, Any]]:
        """按配置顺序收集可用的 LLM Provider 尝试列表（去重）。

        顺序：主模型 → 备用模型 → 当前会话模型。
        """
        attempts: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_objects: set[int] = set()
        configured = [
            ("primary", clean_text(self.config.get(f"{prefix}.{provider_key}", ""), 120)),
            ("fallback", clean_text(self.config.get(f"{prefix}.{fallback_provider_key}", ""), 120)),
        ]
        for source, provider_id in configured:
            if not provider_id or provider_id in seen_ids:
                continue
            provider = await self._provider_by_id(provider_id, ctx)
            if provider is None or id(provider) in seen_objects:
                continue
            seen_ids.add(provider_id)
            seen_objects.add(id(provider))
            attempts.append({"source": source, "provider": provider})
        if include_current:
            current = await self._current_provider(ctx)
            if current is not None and id(current) not in seen_objects:
                attempts.append({"source": "current_session", "provider": current})
        return attempts

    async def _provider_by_id(self, provider_id: str, ctx: SessionContext) -> Any | None:
        if not provider_id or self.context is None:
            return None
        getter = getattr(self.context, "get_provider_by_id", None)
        if not callable(getter):
            return None
        try:
            return await maybe_await(getter(provider_id))
        except Exception as exc:
            logger.warning("[DeepMemory] 获取 Provider 失败: id=%s error=%s", provider_id, exc)
            return None

    async def _current_provider(self, ctx: SessionContext) -> Any | None:
        if self.context is None:
            return None
        getter = getattr(self.context, "get_using_provider", None)
        if not callable(getter):
            return None
        try:
            return await maybe_await(getter(ctx.session_id))
        except Exception:
            return None

    @staticmethod
    def _extract_json(completion: str) -> Any:
        if not completion:
            return None
        text = completion.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except Exception:
            pass
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        return None

    # ================================================================== memory write

    async def add_memory(
        self,
        *,
        ctx: SessionContext | None = None,
        content: str,
        memory_type: str = "fact",
        summary: str = "",
        tags: list[str] | None = None,
        importance: float | None = None,
        base_importance: float | None = None,
        confidence: float | None = None,
        subject: EntityRef | None = None,
        object: EntityRef | None = None,
        scope: str = "",
        persona_id: str = "",
        visibility: str = "",
        source: str = "manual",
        source_plugin: str = "deepmemory",
        metadata: dict[str, Any] | None = None,
        occurred_at: str = "",
        merge_duplicates: bool = True,
    ) -> MemoryRecord:
        content = clean_text(content, self.config.int("general.max_content_chars", 4000))
        if not content:
            raise ValueError("记忆内容不能为空")
        if ctx is not None:
            await self.resolve_persona(ctx)
        effective_persona = persona_id or (ctx.persona_id if ctx else "") or (
            clean_text(self.config.get("general.default_persona_id", ""), 80) or "first"
        )
        effective_scope = scope or (ctx.scope if ctx and ctx.scope != "unknown" else "private")
        effective_visibility = visibility or ("private" if effective_scope == "private" else "shared")
        if importance is None:
            importance = clamp_float(base_importance, default=self.config.float("weights.default_importance", 0.45))
        if base_importance is None:
            base_importance = importance
        manual_boost = 0.0
        if source in {"manual", "llm_tool", "bridge"} and self.config.float("weights.manual_importance_boost", 0.2) > 0:
            manual_boost = min(0.3, self.config.float("weights.manual_importance_boost", 0.2))
            importance = min(1.0, clamp_float(importance, default=0.45) + manual_boost)
        record = MemoryRecord(
            memory_type=clean_text(memory_type, 60) or "fact",
            content=content,
            summary=clean_text(summary, 2000),
            tags=[clean_text(tag, 80) for tag in (tags or []) if clean_text(tag, 80)],
            importance=clamp_float(importance, default=0.45),
            base_importance=clamp_float(base_importance, default=0.45),
            weight_factors={"manual_boost": manual_boost, "evaluated": "rule"},
            confidence=clamp_float(confidence, default=0.7),
            subject=subject or (entity_for_user(ctx) if ctx else EntityRef()),
            object=object or (entity_for_current_target(ctx) if ctx else EntityRef()),
            scope=effective_scope,
            persona_id=effective_persona,
            platform=ctx.platform if ctx else "",
            session_id=ctx.session_id if ctx else "",
            user_id=ctx.user_id if ctx else "",
            user_name=ctx.user_name if ctx else "",
            group_id=ctx.group_id if ctx else "",
            group_name=ctx.group_name if ctx else "",
            bot_id=ctx.bot_id if ctx else "",
            lifecycle="active",
            visibility=effective_visibility,
            source=source,
            source_plugin=source_plugin,
            message_id=ctx.message_id if ctx else "",
            occurred_at=occurred_at or utc_now(),
            metadata=dict(metadata or {}),
        )
        if merge_duplicates:
            existing = self.store.find_duplicate(record)
            if existing is not None and existing.source not in {"summary"}:
                existing.merged_count = (existing.merged_count or 1) + 1
                existing.updated_at = utc_now()
                existing.confidence = max(existing.confidence, record.confidence)
                self.store.upsert_memory(existing)
                return existing
        self.store.upsert_memory(record)
        await self._background_embed_records([record])
        return record

    async def update_importance(self, memory_id: str, importance: float) -> bool:
        importance = clamp_float(importance, default=0.45)
        ok = self.store.update_memory_fields(memory_id, importance=importance, base_importance=importance)
        if ok:
            record = self.store.get_memory(memory_id)
            if record:
                factors = dict(record.weight_factors)
                factors["manual_adjust"] = importance
                self.store.update_memory_fields(memory_id, weight_factors=factors)
        return ok

    # ================================================================== retrieval

    async def search(
        self,
        query: str,
        ctx: SessionContext,
        top_k: int = 6,
        *,
        admin_read_all: bool = False,
    ) -> list[SearchResult]:
        results = await self.retrieval.search(query, ctx, top_k, admin_read_all=admin_read_all)
        if results and not admin_read_all:
            self.store.batch_touch_memories([item.memory.id for item in results])
        return results

    async def search_with_diagnostics(
        self,
        query: str,
        ctx: SessionContext,
        top_k: int = 6,
    ) -> tuple[list[SearchResult], list[dict[str, Any]]]:
        results = await self.retrieval.search(query, ctx, top_k)
        self.store.batch_touch_memories([item.memory.id for item in results])
        return results, []

    def compose_injection(self, ctx: SessionContext, results: list[SearchResult], max_chars: int = 1800) -> str:
        """把召回记忆组装为注入文本块。"""
        if not results:
            return ""
        if ctx.scope == "group":
            speaker_line = (
                f"当前群聊：{ctx.group_name or ctx.group_id or '未知群'}；"
                f"当前发言者：{ctx.user_name or '未知'}（ID {ctx.user_id or '未知'}）"
            )
        else:
            speaker_line = (
                f"当前对话者：{ctx.user_name or '未知'}（ID {ctx.user_id or '未知'}）"
            )
        lines = [
            INJECTION_HEADER,
            speaker_line,
            "说明：以下是来自长期记忆库的资料，不是新的用户消息。请优先回应当前用户消息；",
            "只有与当前话题直接相关时才自然引用这些记忆；与用户当前说法冲突时以用户为准。",
            "不得向当前会话之外的窗口泄露私密内容。",
        ]
        budget = max(200, max_chars)
        used = 0
        for index, item in enumerate(results, start=1):
            record = item.memory
            entry_lines = []
            if record.summary:
                entry_lines.append(f"内容：{record.summary}")
            entry_lines.append(f"内容：{record.content}")
            if record.tags:
                entry_lines.append(f"标签：{'、'.join(record.tags[:6])}")
            created = record.created_at[:10]
            type_label = self._type_label(record.memory_type)
            entry_lines.insert(0, f"[记忆 {index}/{len(results)} | {type_label} | {created} | 相关度 {item.score:.2f}]")
            block = "\n".join(entry_lines)
            if used + len(block) > budget and used > 0:
                break
            used += len(block)
            lines.append(block)
        lines.append(INJECTION_FOOTER)
        return "\n".join(lines)

    @staticmethod
    def _type_label(memory_type: str) -> str:
        return {
            "fact": "事实", "preference": "偏好", "event": "事件", "relationship": "关系",
            "promise": "承诺", "summary": "总结", "note": "笔记", "other": "其他",
        }.get(memory_type, memory_type)

    async def inject_memories(self, ctx: SessionContext, req: Any) -> None:
        self._remove_old_injection(req)
        text = ctx.message_text or ""
        if self.config.bool("injection.skip_on_short_reply", True) and len(text.strip()) <= 2:
            return
        top_k = max(1, self.config.int("injection.top_k", 6))
        max_chars = self.config.int("injection.max_chars", 1800)
        results = await self.retrieval.search(text, ctx, top_k)
        if self.config.bool("injection.include_summaries", True):
            pass
        else:
            results = [item for item in results if item.memory.memory_type != "summary"]
        min_importance = self.config.float("weights.min_importance_for_injection", 0.2)
        results = [item for item in results if item.memory.importance >= min_importance]
        if not results:
            self._log_injection(ctx, text, [], max_chars)
            logger.info(
                "[DeepMemory] 记忆注入: session=%s 无相关记忆可注入",
                ctx.session_id,
            )
            return
        injection = self.compose_injection(ctx, results, max_chars)
        if not injection:
            return
        appended = self._append_temp_text(req, injection)
        if appended:
            self._log_injection(
                ctx,
                text,
                [item.memory.id for item in results],
                len(injection),
                injection if self.config.bool("injection.debug_log_injection_enabled", False) else "",
            )
            logger.info(
                "[DeepMemory] 记忆注入成功: session=%s 命中=%s 字数=%s",
                ctx.session_id, len(results), len(injection),
            )
        self.store.batch_touch_memories([item.memory.id for item in results])

    def _remove_old_injection(self, req: Any) -> None:
        parts = getattr(req, "extra_user_content_parts", None)
        if isinstance(parts, list):
            kept = []
            for part in parts:
                text = getattr(part, "text", "")
                if isinstance(text, str) and INJECTION_HEADER in text:
                    continue
                kept.append(part)
            req.extra_user_content_parts = kept
        prompt = getattr(req, "prompt", None)
        if isinstance(prompt, str) and INJECTION_HEADER in prompt:
            req.prompt = INJECTION_BLOCK_RE.sub("", prompt).strip()
        contexts = getattr(req, "contexts", None)
        if isinstance(contexts, list):
            kept = []
            for item in contexts:
                text = item.text if hasattr(item, "text") else (str(item) if isinstance(item, str) else "")
                if isinstance(text, str) and INJECTION_HEADER in text:
                    continue
                kept.append(item)
            if len(kept) != len(contexts):
                req.contexts = kept

    def _append_temp_text(self, req: Any, text: str) -> bool:
        if TextPart is None:
            return False
        if getattr(req, "extra_user_content_parts", None) is None:
            req.extra_user_content_parts = []
        part = TextPart(text=text)
        mark_as_temp = getattr(part, "mark_as_temp", None)
        if callable(mark_as_temp):
            part = mark_as_temp()
        req.extra_user_content_parts.append(part)
        return True

    def _log_injection(
        self,
        ctx: SessionContext,
        query: str,
        selected_ids: list[str],
        chars: int,
        debug_text: str = "",
    ) -> None:
        if self.config.bool("injection.enable_injection_logs", True):
            self.store.add_injection_log(
                session_id=ctx.session_id,
                scope=ctx.scope,
                query=query,
                selected_memory_ids=selected_ids,
                blocked=[],
                injection_chars=chars,
            )
        if debug_text:
            logger.info(
                "========== DeepMemory 注入调试 ==========\nsession=%s\nquery=%s\nselected=%s\n%s\n========== DeepMemory 注入调试结束 ==========",
                ctx.session_id, query, selected_ids, debug_text,
            )

    # ================================================================== LLM tools

    async def tool_recall(self, event: Any, query: str, top_k: int = 5) -> dict[str, Any]:
        if not self.config.bool("tools.enable_recall_tool", True):
            return {"ok": False, "error": "recall tool disabled"}
        ctx = await self.identity.resolve_event_context(event)
        await self.resolve_persona(ctx)
        results = await self.search(query, ctx, top_k)
        return {
            "ok": True,
            "count": len(results),
            "results": [self._serialize_result(item) for item in results],
        }

    async def tool_remember(self, event: Any, content: str, note_type: str = "memory") -> dict[str, Any]:
        if not self.config.bool("tools.enable_remember_tool", True):
            return {"ok": False, "error": "remember tool disabled"}
        ctx = await self.identity.resolve_event_context(event)
        await self.resolve_persona(ctx)
        type_map = {
            "memory": "fact", "preference": "preference", "relationship": "relationship",
            "promise": "promise", "note": "note",
        }
        try:
            record = await self.add_memory(
                ctx=ctx,
                content=content,
                memory_type=type_map.get(clean_text(note_type, 40), "fact"),
                source="llm_tool",
                metadata={"trigger": "llm_tool"},
            )
            return {"ok": True, "memory_id": record.id, "persona_id": record.persona_id}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    # ================================================================== 外观（UI 主题/背景）

    APPEARANCE_DEFAULTS: dict[str, Any] = {
        "theme": "default",      # 配色主题 key
        "scheme": "auto",        # 明暗模式：auto / light / dark
        "primary": "",           # 自定义主色（覆盖主题）
        "accent": "",            # 自定义辅色（覆盖主题）
        "bg_color": "",          # 背景板（页面底色），空 = 跟随主题
        "bg_enabled": False,
        "bg_opacity": 0.8,
        "bg_blur": 0,
        "bg_hash": "",
    }

    def _appearance_path(self) -> Path:
        return self.data_dir / "appearance.json"

    def _write_appearance(self, appearance: dict[str, Any]) -> None:
        path = self._appearance_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(appearance, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def get_appearance(self) -> dict[str, Any]:
        appearance = dict(self.APPEARANCE_DEFAULTS)
        try:
            path = self._appearance_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    for key in self.APPEARANCE_DEFAULTS:
                        if key in data and data.get(key) is not None:
                            appearance[key] = data[key]
        except Exception as exc:
            logger.warning("[DeepMemory] 读取外观配置失败: %s", exc)
        return appearance

    def set_appearance(self, fields: dict[str, Any]) -> dict[str, Any]:
        appearance = self.get_appearance()
        allowed = {"theme", "scheme", "primary", "accent", "bg_color", "bg_enabled", "bg_opacity", "bg_blur"}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "bg_enabled":
                appearance[key] = bool(value)
            elif key == "bg_opacity":
                try:
                    appearance[key] = max(0.0, min(1.0, float(value)))
                except Exception:
                    pass
            elif key == "bg_blur":
                try:
                    appearance[key] = max(0, min(60, int(value)))
                except Exception:
                    pass
            else:
                appearance[key] = clean_text(value, 40)
        self._write_appearance(appearance)
        return appearance

    def reset_appearance(self) -> dict[str, Any]:
        self._write_appearance(dict(self.APPEARANCE_DEFAULTS))
        return dict(self.APPEARANCE_DEFAULTS)

    def _background_file(self) -> Path | None:
        bg_dir = self.data_dir / "backgrounds"
        if not bg_dir.exists():
            return None
        candidates = sorted(bg_dir.glob("bg.*"))
        return candidates[0] if candidates else None

    def background_data_url(self) -> str:
        cached = getattr(self, "_bg_data_url_cache", None)
        if cached is not None:
            return cached
        bg = self._background_file()
        if bg is None:
            return ""
        import base64
        import mimetypes

        try:
            raw = bg.read_bytes()
            mime = mimetypes.guess_type(bg.name)[0] or "image/png"
            data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
            self._bg_data_url_cache = data_url
            return data_url
        except Exception as exc:
            logger.warning("[DeepMemory] 读取背景图片失败: %s", exc)
            return ""

    def save_background_image(self, content: bytes, ext: str = "") -> dict[str, Any]:
        if not content:
            raise ValueError("图片内容为空")
        if len(content) > 8 * 1024 * 1024:
            raise ValueError("图片超过 8 MiB 限制")
        ext = clean_text(ext, 10).lower().lstrip(".")
        if ext not in {"png", "jpg", "jpeg", "gif", "webp", "bmp"}:
            ext = "png"
        bg_dir = self.data_dir / "backgrounds"
        bg_dir.mkdir(parents=True, exist_ok=True)
        for old in bg_dir.glob("bg.*"):
            try:
                old.unlink()
            except OSError:
                pass
        path = bg_dir / f"bg.{ext}"
        path.write_bytes(content)
        import hashlib

        appearance = self.get_appearance()
        appearance["bg_hash"] = hashlib.md5(content).hexdigest()[:12]
        self._write_appearance(appearance)
        self._bg_data_url_cache = None
        return {"ok": True, "bg_hash": appearance["bg_hash"], "data_url": self.background_data_url()}

    def clear_background_image(self) -> dict[str, Any]:
        bg = self._background_file()
        if bg is not None:
            try:
                bg.unlink()
            except OSError:
                pass
        self._bg_data_url_cache = None
        appearance = self.get_appearance()
        appearance["bg_hash"] = ""
        self._write_appearance(appearance)
        return {"ok": True, "appearance": appearance}

    # ================================================================== 桥接支持

    async def record_external_event(self, **kwargs: Any) -> str:
        if not self.config.bool("bridge.accept_external_records", True):
            raise PermissionError("external records disabled")
        source_plugin = clean_text(kwargs.get("source_plugin"), 80) or "external"
        allowed = clean_text(self.config.get("bridge.allowed_source_plugins", ""), 500)
        if allowed:
            whitelist = {item.strip() for item in allowed.split(",") if item.strip()}
            if whitelist and source_plugin not in whitelist:
                raise PermissionError(f"plugin {source_plugin} not allowed")
        ctx_payload = kwargs.get("ctx") or kwargs.get("session_context")
        ctx = SessionContext.from_dict(ctx_payload) if isinstance(ctx_payload, dict) else None
        record = await self.add_memory(
            ctx=ctx,
            content=clean_text(kwargs.get("content"), self.config.int("general.max_content_chars", 4000)),
            memory_type=clean_text(kwargs.get("memory_type"), 60) or "fact",
            summary=clean_text(kwargs.get("summary"), 2000),
            tags=kwargs.get("tags"),
            importance=kwargs.get("importance"),
            base_importance=kwargs.get("base_importance"),
            confidence=kwargs.get("confidence"),
            subject=EntityRef.from_dict(kwargs.get("subject")),
            object=EntityRef.from_dict(kwargs.get("object")),
            scope=clean_text(kwargs.get("scope"), 40) or (ctx.scope if ctx else "private"),
            persona_id=clean_text(kwargs.get("persona_id"), 80),
            visibility=clean_text(kwargs.get("visibility"), 40),
            source="bridge",
            source_plugin=source_plugin,
            metadata=kwargs.get("metadata") if isinstance(kwargs.get("metadata"), dict) else {},
            occurred_at=clean_text(kwargs.get("occurred_at"), 80),
        )
        return record.id

    async def bridge_search(
        self,
        query: str,
        *,
        session_context: SessionContext | dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        ctx = session_context if isinstance(session_context, SessionContext) else SessionContext.from_dict(session_context)
        await self.resolve_persona(ctx)
        results = await self.search(query, ctx, top_k or 6)
        return [self._serialize_result(item) for item in results]

    async def bridge_compose_injection(
        self,
        query: str,
        *,
        session_context: SessionContext | dict[str, Any] | None = None,
        top_k: int | None = None,
        max_chars: int | None = None,
    ) -> str:
        ctx = session_context if isinstance(session_context, SessionContext) else SessionContext.from_dict(session_context)
        await self.resolve_persona(ctx)
        results = await self.search(query, ctx, top_k or 6)
        return self.compose_injection(ctx, results, max_chars or self.config.int("injection.max_chars", 1800))

    async def bridge_inject_for_event(self, req: Any, event: Any) -> bool:
        """由外部插件（如陪伴插件）托管注入：解析事件上下文并注入记忆到请求。

        返回是否实际注入了记忆（True 表示 req 已被修改）。此方法复用本插件自身的
        检索与注入格式，保证与自动注入一致；调用前应由外部插件设置
        external_injection_managed 以避免本插件重复注入。
        """
        if self._is_synthetic_event(event):
            return False
        ctx = await self.identity.resolve_event_context(event)
        ctx.is_command = self._event_looks_command(event, ctx.message_text)
        await self.resolve_persona(ctx)
        self.touch_user(ctx)
        before = len(getattr(req, "extra_user_content_parts", None) or [])
        await self.inject_memories(ctx, req)
        after = len(getattr(req, "extra_user_content_parts", None) or [])
        return after > before

    @staticmethod
    def _serialize_result(item: SearchResult) -> dict[str, Any]:
        data = item.memory.to_dict()
        data["score"] = round(item.score, 4)
        data["reason"] = item.reason
        return data

    # ================================================================== export / import

    def export_data(self, *, format: str = "jsonl", scope: str = "", persona_id: str = "") -> dict[str, Any]:
        format = clean_text(format, 10).lower() or "jsonl"
        exports_dir = self.data_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        records = self.store.list_memories(limit=100000, scope=scope, persona_id=persona_id, lifecycle="")
        users = self.store.list_users(limit=10000)
        user_payload = [dict(item) for item in users]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "jsonl" if format == "jsonl" else "json"
        path = exports_dir / f"deepmemory_export_{stamp}.{ext}"
        payload: Any
        if format == "jsonl":
            meta_line = json.dumps(
                {"__deepmemory_meta__": {"version": 2, "users": user_payload}},
                ensure_ascii=False,
            )
            payload = "\n".join(
                [meta_line]
                + [
                    json.dumps(record.to_dict(), ensure_ascii=False)
                    for record in records
                ]
            )
        else:
            payload = json.dumps(
                {
                    "plugin": "astrbot_plugin_deepmemory",
                    "version": 2,
                    "memories": [r.to_dict() for r in records],
                    "users": user_payload,
                },
                ensure_ascii=False,
                indent=2,
            )
        path.write_text(payload, encoding="utf-8")
        if not self.config.bool("maintenance.keep_export_history", True):
            for old in exports_dir.glob("deepmemory_export_*.jsonl"):
                if old != path:
                    try:
                        old.unlink()
                    except OSError:
                        pass
            for old in exports_dir.glob("deepmemory_export_*.json"):
                if old != path:
                    try:
                        old.unlink()
                    except OSError:
                        pass
        self._log_op(f"导出记忆档案 {len(records)} 条（{format}）")
        return {
            "ok": True,
            "path": str(path),
            "filename": path.name,
            "count": len(records),
            "format": format,
        }

    def preview_import(self, path: str, *, limit: int = 5) -> dict[str, Any]:
        path = clean_text(path, 2000)
        import_file = Path(path)
        if not import_file.exists():
            raise FileNotFoundError("文件不存在")
        if import_file.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("文件超过 64 MiB 限制")
        raw = import_file.read_text(encoding="utf-8", errors="replace")
        records: list[MemoryRecord] = []
        errors: list[str] = []
        if path.endswith(".jsonl"):
            for line_no, line in enumerate(raw.splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict) and "__deepmemory_meta__" in parsed:
                        continue
                    records.append(MemoryRecord.from_dict(parsed))
                except Exception as exc:
                    errors.append(f"第 {line_no} 行解析失败: {exc}")
        else:
            try:
                data = json.loads(raw)
                if isinstance(data, dict) and isinstance(data.get("memories"), list):
                    for item in data["memories"]:
                        records.append(MemoryRecord.from_dict(item))
                elif isinstance(data, list):
                    for item in data:
                        records.append(MemoryRecord.from_dict(item))
                else:
                    raise ValueError("JSON 顶层结构无法识别")
            except ValueError as exc:
                errors.append(str(exc))
        personas: set[str] = set()
        for record in records:
            personas.add(record.persona_id)
        return {
            "ok": True,
            "path": path,
            "total": len(records),
            "errors": errors[:20],
            "error_count": len(errors),
            "personas": sorted(personas),
            "samples": [record.to_dict() for record in records[:limit]],
        }

    async def import_data(
        self,
        path: str,
        *,
        persona_mapping: dict[str, str] | None = None,
        user_mapping: dict[str, str] | None = None,
        merge_duplicates: bool = True,
        batch_id: str = "",
    ) -> dict[str, Any]:
        preview = self.preview_import(path, limit=0)
        if preview["error_count"] and not preview["total"]:
            return {"ok": False, "error": preview["errors"][0] if preview["errors"] else "解析失败"}
        if self.config.bool("maintenance.backup_before_import", True):
            self._create_backup("import")
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        records: list[MemoryRecord] = []
        imported_users: list[dict] = []
        if path.endswith(".jsonl"):
            lines = raw.splitlines()
            # 首行可能是导出元数据（含用户列表）
            if lines:
                try:
                    head = json.loads(lines[0])
                    if isinstance(head, dict) and "__deepmemory_meta__" in head:
                        meta = head.get("__deepmemory_meta__") or {}
                        user_list = meta.get("users")
                        if isinstance(user_list, list):
                            imported_users = [u for u in user_list if isinstance(u, dict)]
                        lines = lines[1:]
                except Exception:
                    pass
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                records.append(MemoryRecord.from_dict(json.loads(line)))
        else:
            data = json.loads(raw)
            if isinstance(data, dict):
                user_list = data.get("users")
                if isinstance(user_list, list):
                    imported_users = [u for u in user_list if isinstance(u, dict)]
                data = data.get("memories", [])
            for item in data:
                records.append(MemoryRecord.from_dict(item))
        # 恢复用户列表（防止导入后第一轮认错人）
        restored_users = 0
        for user in imported_users:
            try:
                user_key = clean_text(user.get("user_key") or "", 200)
                user_id = clean_text(user.get("user_id") or "", 120)
                if not user_key or not user_id:
                    continue
                self.store.upsert_user(
                    user_key=user_key,
                    user_id=user_id,
                    name=clean_text(user.get("name") or "", 80),
                    platform=clean_text(user.get("platform") or "", 80),
                    persona_id=clean_text(user.get("persona_id") or "", 80),
                    extra=user.get("extra") if isinstance(user.get("extra"), dict) else None,
                )
                restored_users += 1
            except Exception:
                continue
        if restored_users:
            logger.info("[DeepMemory] 导入恢复用户列表: %s", restored_users)
        persona_mapping = persona_mapping or {}
        user_mapping = user_mapping or {}
        if not batch_id:
            batch_id = self.store.create_import_batch(filename=Path(path).name, status="running", total=len(records))
        imported = 0
        skipped = 0
        for item in records:
            try:
                if item.persona_id in persona_mapping:
                    item.persona_id = persona_mapping[item.persona_id] or item.persona_id
                if item.user_id in user_mapping:
                    item.user_id = user_mapping[item.user_id]
                item.source = "import"
                item.import_batch_id = batch_id
                if merge_duplicates:
                    existing = self.store.find_duplicate(item)
                    if existing is None and item.id:
                        # 回退：同 id 且内容一致视为同一条（覆盖旧记录指纹缺失/不一致的情况）
                        by_id = self.store.get_memory(item.id)
                        if by_id is not None and by_id.content == item.content:
                            existing = by_id
                        elif by_id is not None:
                            # 同 id 不同内容：换新 id，避免覆盖既有记忆
                            item.id = ""
                    if existing is not None:
                        skipped += 1
                        continue
                self.store.upsert_memory(item)
                imported += 1
            except Exception as exc:
                logger.warning("[DeepMemory] 导入单条失败: %s", exc)
                skipped += 1
        self.store.update_import_batch(batch_id, status="done", imported=imported, skipped=skipped)
        await self._background_embed_records(
            [self.store.get_memory(item.id) for item in records if item.import_batch_id == batch_id]
        )
        self._log_op(f"导入记忆档案：成功 {imported} 条，跳过 {skipped} 条")
        return {"ok": True, "batch_id": batch_id, "imported": imported, "skipped": skipped}

    def export_backup(self) -> dict[str, Any]:
        backup_path = self.data_dir / "backups" / f"deepmemory_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        path = self.store.backup(backup_path)
        return {"ok": True, "path": str(path), "filename": path.name}

    def _create_backup(self, reason: str) -> str:
        backup_path = self.data_dir / "backups" / f"deepmemory_{reason}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        self.store.backup(backup_path)
        return str(backup_path)

    # ================================================================== maintenance

    async def run_maintenance(self) -> dict[str, Any]:
        self.cleanup_system_timeline()
        daily_decay_report = await self.run_daily_decay()
        decay_report = await self.run_decay()
        retention_report = self.run_retention()
        self._last_maintenance_at = utc_now()
        self.store.set_setting("last_maintenance_at", self._last_maintenance_at)
        return {
            "ok": True,
            "daily_decay": daily_decay_report,
            "decay": decay_report,
            "retention": retention_report,
        }

    async def run_daily_decay(self) -> dict[str, Any]:
        """每日按百分比降低记忆重要度；低于阈值的记忆进入归档判定。

        可开关（decay.daily_decay_enabled）；每条记忆按距上次衰减的天数计算
        （importance *= (1 - rate) ** days），并记录 last_decay_at。
        """
        if not self.config.bool("decay.daily_decay_enabled", True):
            return {"ok": False, "reason": "daily decay disabled", "processed": 0}
        rate = self.config.float("decay.daily_decay_rate_percent", 0.5) / 100.0
        threshold = self.config.float("decay.decay_importance_threshold", 0.2)
        if rate <= 0:
            return {"ok": False, "reason": "decay rate is 0", "processed": 0}
        records = self.store.list_memories(limit=20000, lifecycle="active")
        today = datetime.now(timezone.utc).date().isoformat()
        processed = 0
        candidates: list[MemoryRecord] = []
        examples: list[str] = []
        for record in records:
            last = (record.metadata or {}).get("last_decay_at", "")
            try:
                last_date = datetime.fromisoformat(last).date() if last else None
                days = (datetime.now(timezone.utc).date() - last_date).days if last_date else 1
            except Exception:
                days = 1
            if days <= 0:
                continue
            old_importance = record.importance
            new_importance = max(0.0, record.importance * ((1.0 - rate) ** days))
            metadata = dict(record.metadata or {})
            metadata["last_decay_at"] = today
            processed += 1
            if len(examples) < 5:
                examples.append(f"{record.id}: {old_importance:.4f} → {new_importance:.4f}（{days}天）")
            if new_importance < threshold:
                candidates.append(record)
                continue
            self.store.update_memory_fields(
                record.id,
                importance=new_importance,
                base_importance=record.base_importance,
                metadata=metadata,
            )
        mode = clean_text(self.config.get("decay.decay_mode", "archive"), 20) or "archive"
        if mode == "delete":
            self.store.decay_records(mode="delete", memory_ids=[c.id for c in candidates])
        else:
            # compress 模式简化为归档（深层压缩由 run_decay 的候选流程处理）
            self.store.decay_records(
                mode="archive",
                memory_ids=[c.id for c in candidates],
                summary_memory_id="",
            )
        logger.info(
            "[DeepMemory] 每日减权完成: rate=%s%%/天 处理=%s 归档判定=%s mode=%s 示例=%s",
            round(rate * 100, 2), processed, len(candidates), mode,
            " | ".join(examples) if examples else "无（无活跃记忆或均已衰减）",
        )
        return {
            "ok": True,
            "processed": processed,
            "archived": len(candidates),
            "mode": mode,
            "rate_percent": round(rate * 100, 2),
            "threshold": threshold,
        }

    async def run_decay(self) -> dict[str, Any]:
        if not self.config.bool("decay.enabled", True):
            return {"ok": False, "reason": "decay disabled", "processed": 0}
        candidates = self.store.list_decay_candidates(
            after_days=max(1, self.config.int("decay.decay_after_days", 120)),
            idle_days=max(1, self.config.int("decay.decay_idle_days", 60)),
            max_importance=self.config.float("decay.decay_max_importance", 0.7),
            max_access_count=max(0, self.config.int("decay.decay_max_access_count", 3)),
            limit=max(1, self.config.int("decay.decay_batch_size", 80)),
        )
        if not candidates:
            return {"ok": True, "processed": 0}
        mode = clean_text(self.config.get("decay.decay_mode", "compress"), 20) or "compress"
        if mode == "delete":
            self.store.decay_records(mode="delete", memory_ids=[c.id for c in candidates])
            return {"ok": True, "processed": len(candidates), "mode": "delete"}
        if mode == "archive":
            self.store.decay_records(mode="archive", memory_ids=[c.id for c in candidates])
            return {"ok": True, "processed": len(candidates), "mode": "archive"}
        groups: dict[str, list[MemoryRecord]] = {}
        for record in candidates:
            key = f"{record.persona_id}|{record.scope}|{record.user_id}|{record.group_id}"
            groups.setdefault(key, []).append(record)
        processed = 0
        for group in groups.values():
            summary_text = "\n".join(f"- {record.content[:300]}" for record in group[:12])
            prompt = DECAY_PROMPT_TEMPLATE.format(items=summary_text)
            ctx = SessionContext(
                session_id=group[0].session_id,
                scope=group[0].scope,
                persona_id=group[0].persona_id,
                platform=group[0].platform,
                user_id=group[0].user_id,
                user_name=group[0].user_name,
                group_id=group[0].group_id,
                bot_id=group[0].bot_id,
            )
            payload = await self._llm_json(prompt, ctx=ctx, prefix="decay", fallback_prefix="summary")
            new_memory_id = ""
            if isinstance(payload, dict):
                record = MemoryRecord(
                    memory_type=clean_text(payload.get("memory_type"), 60) or "summary",
                    content=clean_text(payload.get("content"), self.config.int("decay.decay_summary_chars", 800)),
                    summary=clean_text(payload.get("summary"), 400),
                    tags=[clean_text(tag, 80) for tag in (payload.get("tags") or []) if clean_text(tag, 80)],
                    importance=clamp_float(payload.get("importance"), default=0.5),
                    base_importance=clamp_float(payload.get("importance"), default=0.5),
                    confidence=0.7,
                    scope=group[0].scope,
                    persona_id=group[0].persona_id,
                    platform=group[0].platform,
                    session_id=group[0].session_id,
                    user_id=group[0].user_id,
                    user_name=group[0].user_name,
                    group_id=group[0].group_id,
                    bot_id=group[0].bot_id,
                    lifecycle="active",
                    visibility=group[0].visibility,
                    source="decay",
                    metadata={"decayed_from": [r.id for r in group], "trigger": "memory_decay"},
                )
                self.store.upsert_memory(record)
                new_memory_id = record.id
            self.store.decay_records(
                mode="archive",
                memory_ids=[r.id for r in group],
                summary_memory_id=new_memory_id,
            )
            processed += len(group)
        return {"ok": True, "processed": processed, "mode": "compress"}

    def run_retention(self) -> dict[str, Any]:
        timeline_removed = self.store.delete_timeline_older_than(
            max(0, self.config.int("maintenance.retention_timeline_days", 30))
        )
        log_removed = self.store.delete_injection_logs_older_than(14)
        return {
            "ok": True,
            "timeline_removed": timeline_removed,
            "injection_log_removed": log_removed,
        }

    async def _auto_maintenance_loop(self) -> None:
        interval_hours = max(1, self.config.int("maintenance.auto_maintenance_interval_hours", 12))
        while True:
            await asyncio.sleep(interval_hours * 3600)
            try:
                if self.config.bool("general.enabled", True) and self.config.bool("maintenance.auto_maintenance_enabled", True):
                    await self.run_maintenance()
            except Exception as exc:
                logger.warning("[DeepMemory] 自动维护失败: %s", exc, exc_info=True)

    # ================================================================== embeddings

    async def _background_embed_records(self, records: Iterable[MemoryRecord | None]) -> None:
        if not self.config.bool("retrieval.embedding_enabled", False):
            return
        records = [record for record in records if record is not None]
        if not records:
            return
        self._spawn(self._embed_records_worker(list(records)), "embed_worker")

    async def _embed_records_worker(self, records: list[MemoryRecord]) -> None:
        try:
            provider, provider_id = await self.retrieval.embedding.resolve_provider()
            if provider is None:
                return
            for record in records:
                text = self._embedding_text(record)
                if not text:
                    continue
                vector = await self.retrieval.embedding.embed(text, provider=provider, provider_id=provider_id)
                if vector:
                    import hashlib
                    self.store.upsert_embedding(
                        record.id, provider_id, vector,
                        hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    )
        except Exception as exc:
            logger.warning("[DeepMemory] 记忆向量化失败: %s", exc)

    @staticmethod
    def _embedding_text(record: MemoryRecord) -> str:
        parts = [
            record.memory_type,
            record.scope,
            record.persona_id,
            record.tags and " ".join(record.tags),
            record.content,
            record.summary,
            record.user_name,
            record.group_name,
        ]
        return " ".join(part for part in parts if part)[:1200]

    async def _embed_backfill_loop(self) -> None:
        while True:
            await asyncio.sleep(300)
            try:
                if not self.config.bool("general.enabled", True) or not self.config.bool("retrieval.embedding_enabled", False):
                    continue
                provider, provider_id = await self.retrieval.embedding.resolve_provider()
                if provider is None:
                    continue
                batch = self.store.list_memories_without_embedding(
                    provider_id,
                    limit=max(1, self.config.int("retrieval.embedding_backfill_batch_size", 50)),
                )
                if not batch:
                    continue
                for record in batch:
                    text = self._embedding_text(record)
                    if not text:
                        continue
                    vector = await self.retrieval.embedding.embed(text, provider=provider, provider_id=provider_id)
                    if vector:
                        import hashlib
                        self.store.upsert_embedding(
                            record.id, provider_id, vector,
                            hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        )
                    await asyncio.sleep(0.05)
            except Exception as exc:
                logger.warning("[DeepMemory] 向量补索引失败: %s", exc)

    # ================================================================== status

    def health(self) -> dict[str, Any]:
        stats = self.stats_full()
        return {
            "ok": True,
            "plugin": "astrbot_plugin_deepmemory",
            "plugin_name": PLUGIN_DISPLAY_NAME,
            "version": PLUGIN_VERSION,
            "data_dir": str(self.data_dir),
            "db_path": str(self.store.db_path),
            "stats": stats,
            "config_modules": sorted(self.config.raw.keys()) if isinstance(self.config.raw, dict) else [],
            "last_maintenance_at": self._last_maintenance_at or self.store.get_setting("last_maintenance_at") or "",
            "embedding_enabled": self.config.bool("retrieval.embedding_enabled", False),
            "injection_enabled": self.config.bool("injection.enabled", True),
        }

    def stats_full(self) -> dict[str, Any]:
        """统计信息（含未总结进度与触发阈值，供面板展示）。

        每个会话独立计算未总结量：
        - 私聊按「对话轮」（每会话独立计轮），合计为 unsummarized_rounds；
        - 群聊按「事件条数」（每会话独立计数），合计为 unsummarized_group_events；
        - 同时给出已达触发阈值的会话数（private_ready_sessions / group_ready_sessions）。
        """
        stats = self.store.stats()
        try:
            events = self.store.unsummarized_timeline(limit=2000)
            trigger = self.config.int("summary.trigger_event_count", 8)
            group_trigger = self.config.int("summary.group_trigger_events", 15)
            by_session: dict[tuple[str, str], list] = {}
            for item in events:
                by_session.setdefault((item.scope, item.session_id), []).append(item)
            private_rounds = 0
            group_events = 0
            private_ready = 0
            group_ready = 0
            for (scope, _session_id), session_events in by_session.items():
                if scope == "group":
                    count = len(session_events)
                    group_events += count
                    if count >= group_trigger:
                        group_ready += 1
                else:
                    round_count = self._count_rounds(session_events)
                    private_rounds += round_count
                    if round_count >= trigger:
                        private_ready += 1
            stats["unsummarized_rounds"] = private_rounds
            stats["unsummarized_group_events"] = group_events
            stats["private_ready_sessions"] = private_ready
            stats["group_ready_sessions"] = group_ready
            stats["unsummarized_sessions"] = len(by_session)
        except Exception:
            stats["unsummarized_rounds"] = 0
            stats["unsummarized_group_events"] = 0
            stats["private_ready_sessions"] = 0
            stats["group_ready_sessions"] = 0
            stats["unsummarized_sessions"] = 0
        stats["summary_trigger_rounds"] = self.config.int("summary.trigger_event_count", 8)
        stats["group_trigger_events"] = self.config.int("summary.group_trigger_events", 15)
        return stats

    def batch_delete_memories(self, memory_ids: list[str]) -> int:
        """批量删除记忆，返回删除条数。"""
        removed = 0
        for memory_id in memory_ids:
            if self.store.delete_memory(memory_id):
                removed += 1
        if removed:
            logger.info("[DeepMemory] 批量删除记忆: count=%s", removed)
            self._log_op(f"批量删除记忆 {removed} 条")
        return removed

    def clear_all_data(self) -> dict[str, Any]:
        """清空全部记忆数据（备份后）。"""
        backup = self._create_backup("clear_all")
        with self.store._lock:
            for table in ("memories", "memories_fts", "embeddings", "timeline", "injection_logs"):
                self.store._conn.execute(f"DELETE FROM {table}")
            self.store._conn.commit()
        return {"ok": True, "backup": backup}

    # ================================================================== 运行时日志

    def runtime_logs(self, *, lines: int = 300, level: str = "") -> dict[str, Any]:
        """读取插件运行时日志（含文件列表与按级别过滤）。"""
        log_dir = self.data_dir / "logs"
        main_file = log_dir / "deepmemory.log"
        raw_lines = read_tail(main_file, max(1, min(2000, lines)))
        level = clean_text(level, 10).upper()
        level_order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        if level in level_order:
            threshold = level_order[level]
            filtered: list[str] = []
            for line in raw_lines:
                match = re.search(r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]", line)
                match_level = match.group(1) if match else "INFO"
                if level_order.get(match_level, 20) >= threshold:
                    filtered.append(line)
            raw_lines = filtered
        return {
            "ok": True,
            "files": log_files(log_dir),
            "current_file": "deepmemory.log",
            "lines": raw_lines,
            "total": len(raw_lines),
        }

    def clear_runtime_logs(self) -> dict[str, Any]:
        log_dir = self.data_dir / "logs"
        reset_file_handler()
        removed = clear_log_files(log_dir)
        setup_plugin_logging(self.data_dir)
        return {"ok": True, "removed_files": removed, "files": log_files(log_dir)}
