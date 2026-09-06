from __future__ import annotations

from typing import Any


class ConfigView:
    """Dot-path config accessor over the raw plugin config dict."""

    def __init__(self, raw: Any):
        self.raw = raw if isinstance(raw, dict) else {}

    def get(self, dotted: str, default: Any = None) -> Any:
        value = self._get_exact(dotted)
        return default if value is None else value

    def _get_exact(self, dotted: str) -> Any:
        cur: Any = self.raw
        for part in dotted.split("."):
            if isinstance(cur, dict):
                if part not in cur or cur.get(part) is None:
                    return None
                cur = cur.get(part)
            else:
                getter = getattr(cur, "get", None)
                if not callable(getter):
                    return None
                value = getter(part)
                if value is None:
                    return None
                cur = value
            if cur is None:
                return None
        return cur

    def bool(self, dotted: str, default: bool) -> bool:
        value = self.get(dotted, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "开", "开启"}
        return bool(value)

    def int(self, dotted: str, default: int) -> int:
        try:
            return int(self.get(dotted, default))
        except Exception:
            return default

    def float(self, dotted: str, default: float) -> float:
        try:
            return float(self.get(dotted, default))
        except Exception:
            return default

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        cur = self.raw
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = value

    def module_values(self, module: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, default in (defaults or {}).items():
            result[key] = self.get(f"{module}.{key}", default)
        return result
