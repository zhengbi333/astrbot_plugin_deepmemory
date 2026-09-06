from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from .core.log import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.event.filter import PermissionType, permission_type
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register

from .core.bridge import DeepMemoryBridge
from .core.commands import DeepMemoryCommandHandler
from .core.models import json_dumps
from .core.service import PLUGIN_VERSION, DeepMemoryService

PLUGIN_NAME = "astrbot_plugin_deepmemory"


def _ensure_plugin_data_dir() -> Path:
    directory = Path(StarTools.get_data_dir(PLUGIN_NAME))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@register(
    "为你篆刻的历史",
    "deepmemory",
    "为你篆刻的历史：记忆分区与用户双层隔离的长期记忆中枢，支持权重、衰减、混合检索、手动记忆管理与批量迁移。",
    PLUGIN_VERSION,
    "https://github.com/example/astrbot_plugin_deepmemory",
)
class DeepMemoryPlugin(Star):
    # 对外暴露的记忆桥实例：由 __init__ 注入、terminate 置空，供其他插件跨模块取用
    _public_memory_handle: "DeepMemoryBridge | None" = None

    def __init__(self, context: Context, config: dict[str, Any]):
        super().__init__(context)
        self.context = context
        data_dir = _ensure_plugin_data_dir()
        self.service = DeepMemoryService(
            context=context,
            config=config or {},
            plugin_root=Path(__file__).resolve().parent,
            data_dir=data_dir,
        )
        self.commands = DeepMemoryCommandHandler(self.service, PLUGIN_VERSION)
        self.page_api = None

        if self.service.config.bool("bridge.enabled", True):
            DeepMemoryPlugin._public_memory_handle = DeepMemoryBridge(self.service)
        self._register_page_api_if_available()
        logger.info("[DeepMemory] 为你篆刻的历史已加载，数据目录=%s", data_dir)

    def _register_page_api_if_available(self) -> None:
        if not hasattr(self.context, "register_web_api"):
            return
        try:
            from .page_api import DeepMemoryPageApi

            self.page_api = DeepMemoryPageApi(self)
            self.page_api.register_routes()
        except Exception as exc:
            self.page_api = None
            logger.warning("[DeepMemory] 拓展页 API 注册失败: %s", exc, exc_info=True)

    # ------------------------------------------------------------ 事件入口

    @filter.on_llm_request(priority=10001)
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        # 0.80：priority 提升到 10001——必须早于陪伴插件接管（on_llm_request priority=10000，
        # 接管时会 stop_event 终止传播），否则接管模式下本钩子永远收不到，
        # 身份标识沉淀 / 主链捕获 / prompt 记录全部失效（用户实测"删了身份标识记忆后不再产生"）。
        # 注入部分仍由托管管理跳过（external_injection_managed），不受影响。
        await self.service.handle_llm_request(event, req)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=1000)
    async def on_group_message(self, event: AstrMessageEvent):
        await self.service.handle_group_message(event)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1500)
    async def on_all_capture(self, event: AstrMessageEvent):
        await self.service.handle_message_capture(event)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=500)
    async def on_all_message(self, event: AstrMessageEvent):
        await self.service.handle_reset_detection(event)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        await self.service.handle_llm_response(event, resp)

    # ------------------------------------------------------------ LLM 工具

    @filter.llm_tool(name="deepmem_recall")
    async def deepmem_recall_tool(self, event: AstrMessageEvent, **kwargs: Any) -> str:
        """从为你篆刻的历史记忆库中主动回忆当前会话可见的长期记忆。

        返回内容只是与当前问题相关的候选，不代表必须提及；与用户当前说法冲突时以用户为准。

        Args:
            query(string): 要回忆的关键词或自然语言问题。
            top_k(number): 最多返回几条，默认 5，最多 10。
        """
        if not self.service.config.bool("tools.enable_recall_tool", True):
            return json_dumps({"ok": False, "error": "recall tool disabled"})
        try:
            top_k = int(kwargs.get("top_k") or 5)
        except (TypeError, ValueError):
            top_k = 5
        result = await self.service.tool_recall(
            event,
            str(kwargs.get("query") or ""),
            max(1, min(10, top_k)),
        )
        return json_dumps(result)

    @filter.llm_tool(name="deepmem_remember")
    async def deepmem_remember_tool(self, event: AstrMessageEvent, **kwargs: Any) -> str:
        """把值得长期保留的信息交予记忆库归档。

        仅在用户明确要求「记住某事」、或当前信息对后续相处确有长期价值时使用；
        玩笑、注入话术与临时情绪不属于归档对象。只有本工具返回 ok=true 才算真正落库，
        其余情况应如实告知尚未保存，不可口头承诺「已记住」。

        Args:
            content(string): 需要归档的记忆内容。
            note_type(string): 归档类别，如 fact/preference/relationship/promise。
        """
        if not self.service.config.bool("tools.enable_remember_tool", True):
            return json_dumps({"ok": False, "error": "remember tool disabled"})
        try:
            result = await self.service.tool_remember(
                event,
                str(kwargs.get("content") or ""),
                note_type=str(kwargs.get("note_type") or "memory"),
            )
        except Exception as exc:
            logger.warning("[DeepMemory] 主动记忆工具异常: %s", exc, exc_info=True)
            result = {"ok": False, "error": "memory write failed"}
        return json_dumps(result)

    # ------------------------------------------------------------ 聊天命令

    @filter.command_group("deepmem")
    def deepmem(self):
        """为你篆刻的历史记忆管理命令组。"""
        pass

    @permission_type(PermissionType.ADMIN)
    @deepmem.command("status", priority=10)
    async def cmd_deepmem_status(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        yield event.plain_result(await self.commands.status())

    @permission_type(PermissionType.ADMIN)
    @deepmem.command("search", priority=10)
    async def cmd_deepmem_search(
        self, event: AstrMessageEvent, query: str = "", k: int = 6
    ) -> AsyncGenerator[MessageEventResult, None]:
        yield event.plain_result(await self.commands.search(event, query, k))

    @permission_type(PermissionType.ADMIN)
    @deepmem.command("add", priority=10)
    async def cmd_deepmem_add(
        self, event: AstrMessageEvent, content: str = ""
    ) -> AsyncGenerator[MessageEventResult, None]:
        yield event.plain_result(await self.commands.add(event, content))

    @permission_type(PermissionType.ADMIN)
    @deepmem.command("recent", priority=10)
    async def cmd_deepmem_recent(
        self, event: AstrMessageEvent, limit: int = 10
    ) -> AsyncGenerator[MessageEventResult, None]:
        yield event.plain_result(await self.commands.recent(limit))

    @permission_type(PermissionType.ADMIN)
    @deepmem.command("summarize", priority=10)
    async def cmd_deepmem_summarize(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[MessageEventResult, None]:
        yield event.plain_result(await self.commands.summarize(event))

    @permission_type(PermissionType.ADMIN)
    @deepmem.command("delete", priority=10)
    async def cmd_deepmem_delete(
        self, event: AstrMessageEvent, memory_id: str = ""
    ) -> AsyncGenerator[MessageEventResult, None]:
        yield event.plain_result(await self.commands.delete(memory_id))

    @permission_type(PermissionType.ADMIN)
    @deepmem.command("maintenance", priority=10)
    async def cmd_deepmem_maintenance(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        yield event.plain_result(await self.commands.maintenance())

    @permission_type(PermissionType.ADMIN)
    @deepmem.command("export", priority=10)
    async def cmd_deepmem_export(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        yield event.plain_result(await self.commands.export())

    @permission_type(PermissionType.ADMIN)
    @deepmem.command("help", priority=10)
    async def cmd_deepmem_help(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        yield event.plain_result(self.commands.help())

    # ------------------------------------------------------------ 生命周期

    async def initialize(self):
        await self.service.start()

    async def terminate(self):
        if DeepMemoryPlugin._public_memory_handle is not None and DeepMemoryPlugin._public_memory_handle._service is self.service:
            DeepMemoryPlugin._public_memory_handle = None
        await self.service.aclose()
        logger.info("[DeepMemory] 为你篆刻的历史已停止")


def get_deepmemory_bridge() -> DeepMemoryBridge | None:
    """获取「为你篆刻的历史」当前对外提供的记忆读写接口。

    其他插件（如陪伴插件）调用此函数拿到的实例可直接读写记忆库；
    插件卸载或桥接开关关闭时返回 None。
    """
    return DeepMemoryPlugin._public_memory_handle
