"""Token 记账：deepmemory 自身 LLM 调用的用量统计（供陪伴插件 Token 页经桥接读取展示）。

设计要点（独立实现，不与外部插件雷同）：
- 每次 LLM 调用后记一笔（任务 + 模型 + 输入/输出 token + 调用次数）；
- 提供方返回真实 usage 时优先真实值；不返回时按文本估算（汉字每字约 1 token、
  其余字符约 4 字符 1 token，纯本地规则，不额外调 LLM）；
- 持久化到数据目录 token.json，按日期聚合，滚动保留最近 90 天；
- 最近调用明细保留 200 笔，供页面分页展示；
- 对外只暴露只读 stats()，由桥接接口转发给其他插件。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_TOKEN_FILE = "token.json"
_RETAIN_DAYS = 90
_RECENT_LIMIT = 200
_SAVE_INTERVAL = 3.0  # 写盘节流（秒）：高频记账不每笔都全量写文件


def estimate_tokens(text: str | Any) -> int:
    """按文本字符估算 token 数（零依赖、不调 LLM）。

    规则：CJK 字符（汉字 + 中日韩标点）约每字 1 token；其余字符约 4 字符 1 token。
    仅用于提供方没返回 usage 时的兜底。
    """
    raw = str(text or "")
    if not raw:
        return 0
    cjk = 0
    for ch in raw:
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F:
            cjk += 1
    others = max(0, len(raw) - cjk)
    return max(0, cjk + int(others / 4.0 + 0.5))


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _month() -> str:
    return time.strftime("%Y-%m", time.localtime())


def _now_clock() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


class DeepMemoryTokenStore:
    """deepmemory 自己的 token 用量记账与统计。"""

    def __init__(self, data_dir: Path):
        self._file = Path(data_dir) / _TOKEN_FILE
        self._data: dict[str, Any] = {}
        self._load()
        self._last_save = 0.0

    def _load(self) -> None:
        try:
            if self._file.exists():
                raw = json.loads(self._file.read_text(encoding="utf-8-sig"))
                if isinstance(raw, dict) and isinstance(raw.get("daily"), dict):
                    self._data = raw
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._last_save = time.monotonic()
        except Exception:
            pass

    def _maybe_save(self) -> None:
        if time.monotonic() - self._last_save >= _SAVE_INTERVAL:
            self._save()

    def record(
        self,
        *,
        task: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """记一笔 token（按任务 + 模型累积）。"""
        inp = max(0, int(input_tokens or 0))
        out = max(0, int(output_tokens or 0))
        if inp == 0 and out == 0:
            return
        day = _today()
        daily = self._data.setdefault("daily", {})
        day_data = daily.setdefault(day, {"total": {}, "by_task": {}, "by_model": {}})
        total = day_data.setdefault("total", {})
        total["input"] = int(total.get("input", 0) or 0) + inp
        total["output"] = int(total.get("output", 0) or 0) + out
        total["calls"] = int(total.get("calls", 0) or 0) + 1
        task_data = day_data.setdefault("by_task", {}).setdefault(str(task or "chat")[:40], {"input": 0, "output": 0, "calls": 0})
        task_data["input"] = int(task_data.get("input", 0) or 0) + inp
        task_data["output"] = int(task_data.get("output", 0) or 0) + out
        task_data["calls"] = int(task_data.get("calls", 0) or 0) + 1
        model_data = day_data.setdefault("by_model", {}).setdefault(str(model or "default")[:80], {"input": 0, "output": 0})
        model_data["input"] = int(model_data.get("input", 0) or 0) + inp
        model_data["output"] = int(model_data.get("output", 0) or 0) + out
        recent = self._data.setdefault("recent", [])
        recent.insert(0, {
            "time": _now_clock(),
            "source": "memory",
            "task": str(task or "chat")[:40],
            "model": str(model or "default")[:80],
            "input": inp,
            "output": out,
        })
        del recent[_RECENT_LIMIT:]
        keys = sorted(daily.keys())
        if len(keys) > _RETAIN_DAYS:
            for old in keys[: len(keys) - _RETAIN_DAYS]:
                daily.pop(old, None)
        self._maybe_save()

    def stats(self) -> dict[str, Any]:
        """只读统计：总 / 当天 / 当月 / 每任务 / 每模型 / 最近调用（与陪伴插件 Token 页约定一致）。"""
        daily = self._data.get("daily", {})
        today = _today()
        month = _month()
        month_days = [d for d in daily if d.startswith(month)]
        all_days = list(daily.keys())

        def totals(days: list[str]) -> dict[str, int]:
            inp = out = calls = 0
            for day in days:
                total = daily.get(day, {}).get("total", {}) or {}
                inp += int(total.get("input", 0) or 0)
                out += int(total.get("output", 0) or 0)
                calls += int(total.get("calls", 0) or 0)
            return {"input": inp, "output": out, "calls": calls}

        def agg(days: list[str], key: str) -> list[dict[str, Any]]:
            buckets: dict[str, dict[str, int]] = {}
            for day in days:
                section = daily.get(day, {}).get(key, {}) or {}
                for name, v in section.items():
                    if not isinstance(v, dict):
                        continue
                    b = buckets.setdefault(str(name), {"input": 0, "output": 0, "calls": 0})
                    b["input"] += int(v.get("input", 0) or 0)
                    b["output"] += int(v.get("output", 0) or 0)
                    b["calls"] += int(v.get("calls", 0) or 0)
            result = [
                {"source": "memory", "name": str(name), "input": b["input"], "output": b["output"],
                 "calls": b["calls"], "total": b["input"] + b["output"]}
                for name, b in buckets.items()
            ]
            result.sort(key=lambda x: -x["total"])
            return result

        def pack(t: dict[str, int]) -> dict[str, Any]:
            return {"input": t["input"], "output": t["output"], "sum": t["input"] + t["output"], "calls": t["calls"]}

        return {
            "source": "memory",
            "total": pack(totals(all_days)),
            "today": pack(totals([today])),
            "month": pack(totals(month_days)),
            "by_task": agg(month_days, "by_task"),
            "by_model": agg(month_days, "by_model"),
            "recent": [r for r in self._data.get("recent", []) if isinstance(r, dict)][:_RECENT_LIMIT],
        }

    def flush(self) -> None:
        self._save()