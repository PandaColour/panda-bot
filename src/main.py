"""
Panda Bot - 通用智能体

入口文件
"""
import asyncio
import sys

# Windows 控制台 UTF-8 编码支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from aioconsole import ainput

from src.agent import AgentLoop
from src.agent.session import Session
from src.utils import get_logger, setup_logging

logger = get_logger(__name__)


async def run_main_loop():
    """
    主循环：使用 aioconsole.ainput() 实现异步输入

    aioconsole 在独立线程中处理输入，不会阻塞事件循环，
    也不会和 subprocess 产生 Windows 控制台冲突。
    """
    main_session = Session()

    while True:
        # 使用 aioconsole 异步获取输入
        try:
            user_input = await ainput("You: ")
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
