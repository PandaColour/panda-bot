"""
Panda Bot - 通用智能体

入口文件
"""
import asyncio
import json

from src.agent import AgentLoop
from src.agent.session import Session
from src.utils import get_logger, setup_logging



async def run_main_loop():
    main_session = Session()
    while True:
        user_input = input("You：")
        await main_session.add_user_input(user_input)
        agent_loop = AgentLoop()
        await agent_loop.runloop(main_session)

def main():
    setup_logging("DEBUG")
    logger = get_logger(__name__)
    logger.info("Panda Bot 启动中...")
    asyncio.run(run_main_loop())

    # user_input = "在我的桌面上建立一个helloworld.txt 文件，内容写入helloworld"
    # main_session = Session()
    # main_session.add_user_input(user_input)
    # agent_loop = AgentLoop()
    # agent_loop.runloop(main_session)

if __name__ == "__main__":
    main()
