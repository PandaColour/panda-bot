"""
Panda Bot - 通用智能体

入口文件
"""
import asyncio
import json
import sys
import threading
from typing import Optional

# Windows 控制台 UTF-8 编码支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from src.agent import AgentLoop
from src.agent.session import Session
from src.utils import get_logger, setup_logging

logger = get_logger(__name__)


class InputListener:
    """独立线程：持续监听用户输入

    注意：使用 threading.Thread 而不是 asyncio.to_thread，
    因为在 Windows 上 to_thread(input) 和 asyncio 子进程存在冲突。

    支持 pause/resume，在执行命令时完全停止线程避免死锁。
    """

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = True
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self):
        """启动监听线程"""
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def pause(self):
        """暂停输入监听（执行命令前调用）

        在 Windows 上，input() 无法被中断，所以需要完全停止线程。
        """
        self._running = False  # 让线程退出

    def resume(self):
        """恢复输入监听（执行命令后调用）"""
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def _listen_loop(self):
        """监听循环（在独立线程中运行）"""
        while self._running:
            try:
                user_input = input("You: ")
                if user_input.strip():
                    if self._loop and not self._loop.is_closed():
                        self._loop.call_soon_threadsafe(
                            lambda: self._queue.put_nowait(user_input.strip())
                        )
            except EOFError:
                logger.info("检测到 EOF，停止监听")
                break
            except KeyboardInterrupt:
                logger.info("检测到中断信号，停止监听")
                break

    async def get_input(self) -> Optional[str]:
        """从队列获取用户输入"""
        try:
            return await self._queue.get()
        except Exception:
            return None

    def get_input_nowait(self) -> Optional[str]:
        """非阻塞获取用户输入"""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def stop(self):
        """停止监听"""
        self._running = False


# 全局 InputListener 实例，供 shell 工具使用
_input_listener: Optional[InputListener] = None


def get_input_listener() -> Optional[InputListener]:
    """获取全局 InputListener 实例"""
    return _input_listener


def set_input_listener(listener: InputListener):
    """设置全局 InputListener 实例"""
    global _input_listener
    _input_listener = listener


async def run_main_loop():
    """
    主循环：简单的阻塞式输入 + Agent 执行

    在 Windows 上，input() 和 subprocess 无法真正并发（控制台 stdin 冲突）。
    所以采用简单的顺序执行模式：输入 → 执行 → 输入 → 执行...
    """
    main_session = Session()

    while True:
        # 阻塞等待用户输入
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input.strip():
            continue

        await main_session.add_user_input(user_input.strip())

        # 创建 Agent 任务
        agent_loop = AgentLoop()
        await agent_loop.runloop(main_session)


def main():
    setup_logging("DEBUG")
    logger = get_logger(__name__)
    logger.info("Panda Bot 启动中...")
    asyncio.run(run_main_loop())

if __name__ == "__main__":
    main()
