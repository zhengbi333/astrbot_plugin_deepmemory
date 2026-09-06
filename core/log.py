"""插件专用日志：按大小轮转，定期清理过期备份，控制磁盘占用。

使用 astrbot 命名空间下的子 logger：日志同时进入 AstrBot 日志体系
（控制台 / Dashboard 日志页可见），并由本插件的文件 handler 单独落盘。
"""
from __future__ import annotations

import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_NAME = "astrbot.plugin_deepmemory"
_LOG_FILE = "deepmemory.log"
_MAX_BYTES = 5 * 1024 * 1024  # 单文件 5 MiB
_BACKUP_COUNT = 5             # 最多保留 5 个滚动备份（约 30 MiB 上限）
_RETENTION_DAYS = 30          # 超过该天数的日志备份文件启动时删除

_LEVEL_TAG = {
    "DEBUG": "DBUG",
    "INFO": "INFO",
    "WARNING": "WARN",
    "ERROR": "ERRO",
    "CRITICAL": "CRIT",
}

_LEVEL_ANSI = {
    "DEBUG": "\x1b[1;34m",
    "INFO": "\x1b[1;36m",
    "WARNING": "\x1b[1;33m",
    "ERROR": "\x1b[31m",
    "CRITICAL": "\x1b[1;31m",
}


class _PluginEnricherFilter(logging.Filter):
    """为日志记录注入 AstrBot 日志体系期望的字段。

    插件日志沿 logger 链传播到 AstrBot 的 handler 时，不会执行挂载在
    AstrBot 自身 logger 上的 enricher filter，因此必须由本插件自己补齐
    plugin_tag / short_levelname 等字段，否则 AstrBot 的日志格式化会报错
    （Formatting field not found in record: 'plugin_tag'）。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.plugin_tag = "[Plug]"
        record.short_levelname = _LEVEL_TAG.get(record.levelname, record.levelname[:4].upper())
        record.astrbot_version_tag = ""
        record.source_file = (
            os.path.basename(os.path.dirname(record.pathname)) + "." +
            os.path.basename(record.pathname).replace(".py", "")
        )
        record.source_line = record.lineno
        record.is_trace = False
        record.ansi_prefix = _LEVEL_ANSI.get(record.levelname, "\x1b[0m")
        record.ansi_reset = "\x1b[0m"
        return True


logger = logging.getLogger(_LOG_NAME)
logger.setLevel(logging.INFO)
logger.addFilter(_PluginEnricherFilter())
# propagate 保持默认 True：插件日志会进入 astrbot 日志体系，控制台可见

_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

_file_handler: RotatingFileHandler | None = None


def setup_plugin_logging(data_dir: Path) -> None:
    """挂载文件输出（控制台由 astrbot 日志体系处理）。可重复调用（幂等）。"""
    global _file_handler

    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    _prune_old_logs(log_dir)

    target = log_dir / _LOG_FILE
    if _file_handler is not None:
        if _file_handler.baseFilename == str(target):
            return
        logger.removeHandler(_file_handler)
        try:
            _file_handler.close()
        except Exception:
            pass
        _file_handler = None
    _file_handler = RotatingFileHandler(
        target,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    _file_handler.setFormatter(_formatter)
    logger.addHandler(_file_handler)


def _prune_old_logs(log_dir: Path) -> None:
    """删除超过保留天数的滚动备份文件。"""
    cutoff = time.time() - _RETENTION_DAYS * 86400
    try:
        for path in log_dir.glob("deepmemory.log*"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass
    except Exception:
        pass


def log_files(log_dir: Path) -> list[dict]:
    """列出日志目录下的日志文件（含大小与修改时间）。"""
    files: list[dict] = []
    try:
        for path in sorted(log_dir.glob("deepmemory.log*")):
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                }
            )
    except Exception:
        pass
    return files


def read_tail(path: Path, lines: int = 300) -> list[str]:
    """从文件尾部读取指定行数（高效）。"""
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            block_size = 4096
            f.seek(0, 2)
            size = f.tell()
            chunks: list[str] = []
            pos = size
            while pos > 0 and len(chunks) < lines * 8:
                read_size = min(block_size, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size)
                chunks.append(chunk)
                if pos <= 0:
                    break
            text = "".join(reversed(chunks))
            result = [line for line in text.splitlines() if line.strip()][-lines:]
            return result
    except Exception:
        return []


def reset_file_handler() -> None:
    """关闭并移除文件输出（清空日志前调用，避免 Windows 文件占用）。"""
    global _file_handler
    if _file_handler is not None:
        try:
            logger.removeHandler(_file_handler)
            _file_handler.close()
        except Exception:
            pass
        _file_handler = None


def clear_log_files(log_dir: Path) -> int:
    """清空日志目录，返回删除的文件数。"""
    removed = 0
    try:
        for path in list(log_dir.glob("deepmemory.log*")):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    except Exception:
        pass
    return removed
