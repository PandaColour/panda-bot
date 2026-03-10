"""
Panda Bot - 通用智能体

入口文件
"""
from requests import session

from src.agent import AgentLoop
from src.agent.session import Session
from src.utils import get_logger, setup_logging


def main():
    setup_logging("DEBUG")
    logger = get_logger(__name__)
    logger.info("Panda Bot 启动中...")

    user_input = "在我的桌面上建立一个helloworld.txt 文件，内容写入helloworld"
    main_session = Session()
    main_session.add_user_input(user_input)
    agent_loop = AgentLoop()
    agent_loop.runloop(main_session)

if __name__ == "__main__":
    main()
