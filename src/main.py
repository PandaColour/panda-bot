"""
Panda Bot - 通用智能体

入口文件
"""
from src.agent import AgentLoop
from src.utils import get_logger, setup_logging


def main():
    setup_logging("DEBUG")
    logger = get_logger(__name__)
    logger.info("Panda Bot 启动中...")

    agent_loop = AgentLoop()
    agent_loop.runloop()

if __name__ == "__main__":
    main()
