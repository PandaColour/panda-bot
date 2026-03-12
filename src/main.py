"""
Panda Bot - 通用智能体

入口文件
"""
import asyncio
import json
import sys
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
    """独立协程：持续监听用户输入"""

    def __init__(self):
        self._input_queue: asyncio.Queue = asyncio.Queue()

    async def start(self):
        """启动监听协程"""
        asyncio.create_task(self._listen_loop())

    async def _listen_loop(self):
        """监听循环：持续读取用户输入并放入队列"""
        while True:
            try:
                # 使用 asyncio.to_thread 在线程中执行阻塞的 input
                user_input = await asyncio.to_thread(input, "You: ")
                if user_input.strip():
                    await self._input_queue.put(user_input.strip())
                    logger.debug(f"用户输入已入队: {user_input.strip()[:50]}...")
            except EOFError:
                # 处理 Ctrl+D
                logger.info("检测到 EOF，停止监听")
                await self._input_queue.put("exit")
                break
            except KeyboardInterrupt:
                # 处理 Ctrl+C
                logger.info("检测到中断信号，停止监听")
                await self._input_queue.put("exit")
                break

    async def get_input(self) -> Optional[str]:
        """阻塞等待用户输入"""
        try:
            return await self._input_queue.get()
        except Exception:
            return None

    def get_input_nowait(self) -> Optional[str]:
        """非阻塞获取用户输入，没有则返回 None"""
        try:
            return self._input_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

async def run_main_loop():
    listener = InputListener()
    await listener.start()
    main_session = Session()
    while True:
        # 等待用户输入
        user_input = await listener.get_input()
        if user_input is None:
            await asyncio.sleep(0.5)
            break
        await main_session.add_user_input(user_input)
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
