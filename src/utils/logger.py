"""
异步日志系统模块

自动配置:
- 异步非阻塞 (QueueHandler + 后台线程)
- 500MB 自动切片滚动
- 保留 10 个历史文件
- 控制台彩色输出 + 文件日志
- 程序退出自动刷新

使用示例:
    from src.utils import get_logger, setup_logging

    # 初始化 (程序入口调用一次)
    setup_logging()  # 使用默认配置
    # 或
    setup_logging(level="DEBUG")  # 只配置级别

    # 获取 logger
    logger = get_logger(__name__)
    logger.info("这条日志不会阻塞主线程")
"""
import atexit
import logging
import sys
import queue
from datetime import datetime
from logging.handlers import (
    RotatingFileHandler,
    TimedRotatingFileHandler,
    QueueHandler,
    QueueListener,
)
from pathlib import Path
from typing import Optional, Union, List

# ============================================================================
# 默认配置 (可根据需要修改)
# ============================================================================
DEFAULT_CONFIG = {
    "level": "INFO",
    "log_dir": "logs",
    "max_bytes": 500 * 1024 * 1024,  # 500MB
    "backup_count": 10,
    "queue_size": 10000,
    "console_output": True,  # False 关闭控制台输出
    "file_output": True,
    "rotation": "size",  # "size" 或 "time"
    "when": "midnight",
    "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    "date_format": "%Y-%m-%d %H:%M:%S",
}


# ============================================================================
# 颜色支持
# ============================================================================
class Colors:
    """控制台颜色"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    BRIGHT_RED = "\033[91m"


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""

    LEVEL_COLORS = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BRIGHT_RED + Colors.BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
        record.levelname = f"{color}{record.levelname}{Colors.RESET}"
        result = super().format(record)
        record.levelname = original_levelname
        return result


# ============================================================================
# 日志管理器
# ============================================================================
class LoggerManager:
    """
    异步日志管理器 (单例)

    特性:
    - 异步非阻塞: 主线程只放队列，后台线程写文件
    - 自动切片: 超过 500MB 自动滚动
    - 自动清理: 保留最近 10 个文件
    - 自动刷新: 程序退出时自动 flush
    """

    _instance: Optional["LoggerManager"] = None
    _initialized: bool = False

    def __new__(cls) -> "LoggerManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._loggers: dict[str, logging.Logger] = {}
        self._root_logger = logging.getLogger()
        self._log_dir: Optional[Path] = None
        self._queue: Optional[queue.Queue] = None
        self._listener: Optional[QueueListener] = None
        self._handlers: List[logging.Handler] = []

    def setup(self, level: Optional[str] = None, **overrides) -> None:
        """
        配置日志系统

        Args:
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                   不传则使用默认 INFO
            **overrides: 覆盖默认配置 (一般不需要)
        """
        # 合并配置
        config = {**DEFAULT_CONFIG}
        if level:
            config["level"] = level.upper()
        config.update(overrides)

        log_level = getattr(logging, config["level"], logging.INFO)

        # 清理旧配置
        self._root_logger.handlers.clear()
        self._handlers.clear()

        # 设置根 logger
        self._root_logger.setLevel(log_level)

        # 创建队列
        self._queue = queue.Queue(maxsize=config["queue_size"])

        # 控制台 handler
        if config["console_output"]:
            console = logging.StreamHandler(sys.stdout)
            console.setLevel(log_level)
            console.setFormatter(ColoredFormatter(config["format"], datefmt=config["date_format"]))
            self._handlers.append(console)

        # 文件 handler
        if config["file_output"]:
            self._log_dir = Path(config["log_dir"])
            self._log_dir.mkdir(parents=True, exist_ok=True)

            log_file = self._log_dir / f"panda-bot_{datetime.now().strftime('%Y%m%d')}.log"

            if config["rotation"] == "time":
                file_handler = TimedRotatingFileHandler(
                    log_file,
                    when=config["when"],
                    backupCount=config["backup_count"],
                    encoding="utf-8",
                )
            else:
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=config["max_bytes"],
                    backupCount=config["backup_count"],
                    encoding="utf-8",
                )

            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(config["format"], datefmt=config["date_format"]))
            self._handlers.append(file_handler)

        # 启动异步监听器
        self._listener = QueueListener(self._queue, *self._handlers, respect_handler_level=True)
        self._listener.start()

        # 主线程使用 QueueHandler
        self._root_logger.addHandler(QueueHandler(self._queue))

        # 注册退出清理
        atexit.register(self.shutdown)

    def get_logger(self, name: str) -> logging.Logger:
        """获取 logger"""
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        return self._loggers[name]

    def set_level(self, level: str) -> None:
        """动态修改日志级别"""
        log_level = getattr(logging, level.upper(), logging.INFO)
        self._root_logger.setLevel(log_level)
        for h in self._handlers:
            h.setLevel(log_level)

    def shutdown(self) -> None:
        """关闭日志系统，刷新剩余日志"""
        if self._listener:
            self._listener.stop()
            self._listener = None

    @property
    def queue_size(self) -> int:
        """队列中待处理的日志数量"""
        return self._queue.qsize() if self._queue else 0


# ============================================================================
# 全局实例 & 公开 API
# ============================================================================
_manager = LoggerManager()


def setup_logging(level: Optional[str] = None) -> None:
    """
    初始化日志系统 (程序入口调用一次)

    Args:
        level: 日志级别，可选值: DEBUG, INFO, WARNING, ERROR, CRITICAL
               默认 INFO

    使用示例:
        setup_logging()           # 默认 INFO 级别
        setup_logging("DEBUG")    # DEBUG 级别
    """
    _manager.setup(level=level)


def get_logger(name: str) -> logging.Logger:
    """
    获取 logger 实例

    Args:
        name: 通常使用 __name__

    Returns:
        配置好的 logger

    示例:
        logger = get_logger(__name__)
        logger.info("操作成功")
    """
    return _manager.get_logger(name)


def set_log_level(level: str) -> None:
    """动态修改日志级别"""
    _manager.set_level(level)


def shutdown_logging() -> None:
    """关闭日志系统 (可选，程序退出时会自动调用)"""
    _manager.shutdown()
