try:
    from .main import DeepMemoryPlugin
except ModuleNotFoundError as exc:
    if exc.name != "astrbot":
        raise
    DeepMemoryPlugin = None

__all__ = ["DeepMemoryPlugin"]
