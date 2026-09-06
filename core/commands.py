from __future__ import annotations

from typing import Any

from .models import clean_text
from .service import DeepMemoryService


class DeepMemoryCommandHandler:
    def __init__(self, service: DeepMemoryService, version: str):
        self.service = service
        self.version = version

    async def status(self) -> str:
        health = self.service.health()
        stats = health["stats"]
        lines = [
            f"为你篆刻的历史 v{self.version}",
            f"数据目录：{health['data_dir']}",
            f"记忆总数：{stats['total_memories']}（活跃 {stats['active_memories']}）",
            f"时间线事件：{stats['timeline_events']}（未总结 {stats['unsummarized_events']}）",
            f"用户数：{stats['users']} | 向量数：{stats['embedded_vectors']}",
            f"注入：{'开' if health['injection_enabled'] else '关'} | 嵌入：{'开' if health['embedding_enabled'] else '关'}",
            f"隔离：按 AstrBot 人格隔离 | 上次维护：{health['last_maintenance_at'] or '从未'}",
        ]
        return "\n".join(lines)

    async def search(self, event: Any, query: str = "", k: int = 6) -> str:
        from .identity import IdentityResolver

        ctx = await IdentityResolver().resolve_event_context(event)
        await self.service.resolve_persona(ctx)
        if not query:
            query = ctx.message_text
        results = await self.service.search(query, ctx, k)
        if not results:
            return "没有找到相关记忆。"
        lines = [f"共召回 {len(results)} 条："]
        for index, item in enumerate(results, start=1):
            record = item.memory
            created = record.created_at[:16]
            lines.append(
                f"{index}. [{record.memory_type}|{record.persona_id}] {created} "
                f"(重要度 {record.importance:.2f}，相关度 {item.score:.2f})"
            )
            content = record.content if len(record.content) <= 120 else record.content[:117] + "…"
            lines.append(f"   {content}")
        return "\n".join(lines)

    async def add(self, event: Any, content: str = "") -> str:
        if not content:
            return "用法：/deepmem add <内容>"
        record = await self.service.add_memory(
            ctx=await self._ctx(event),
            content=content,
            memory_type="fact",
            source="manual",
        )
        return f"已记住（{record.id}）记忆分区：{record.persona_id}"

    async def recent(self, limit: int = 10) -> str:
        records = self.service.store.list_memories(limit=limit, lifecycle="active")
        if not records:
            return "记忆库为空。"
        lines = [f"最近 {len(records)} 条记忆："]
        for record in records:
            content = record.content if len(record.content) <= 100 else record.content[:97] + "…"
            lines.append(f"- [{record.memory_type}] {record.persona_id} | {record.created_at[:16]} | {content}")
        return "\n".join(lines)

    async def summarize(self, event: Any) -> str:
        ctx = await self._ctx(event)
        await self.service.resolve_persona(ctx)
        result = await self.service._summarize_session_inner(ctx)
        if result.get("ok"):
            return f"总结完成：生成 {result['created']} 条记忆（基于 {result['events']} 条时间线）。"
        return f"总结未生成：{result.get('reason', 'unknown')}"

    async def delete(self, memory_id: str) -> str:
        if not memory_id:
            return "用法：/deepmem delete <memory_id>"
        return "已删除。" if self.service.store.delete_memory(memory_id) else "记忆不存在。"

    async def maintenance(self) -> str:
        report = await self.service.run_maintenance()
        decay = report["decay"]
        retention = report["retention"]
        decay_line = "未启用"
        if decay.get("ok"):
            decay_line = f'处理 {decay["processed"]} 条（{decay.get("mode", "compress")}）'
        return (
            "维护完成。\n"
            f"衰减：{decay_line}\n"
            f"保留清理：时间线 {retention['timeline_removed']} 条，注入日志 {retention['injection_log_removed']} 条"
        )

    async def export(self) -> str:
        result = self.service.export_data()
        return f"已导出 {result['count']} 条记忆到：{result['path']}"

    async def help(self) -> str:
        return (
            "为你篆刻的历史 命令：\n"
            "/deepmem status - 查看状态\n"
            "/deepmem search <关键词> [k] - 检索记忆\n"
            "/deepmem add <内容> - 手动添加记忆\n"
            "/deepmem recent [n] - 最近记忆\n"
            "/deepmem summarize - 立即总结当前会话时间线\n"
            "/deepmem delete <memory_id> - 删除记忆\n"
            "/deepmem maintenance - 运行维护（衰减+清理）\n"
            "/deepmem export - 导出全部记忆\n"
            "完整管理功能请使用 WebUI 仪表盘。"
        )

    async def _ctx(self, event: Any):
        from .identity import IdentityResolver

        ctx = await IdentityResolver().resolve_event_context(event)
        await self.service.resolve_persona(ctx)
        return ctx
