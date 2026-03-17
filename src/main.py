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

from src.agent.session import Session
from src.utils import get_logger, setup_logging

logger = get_logger(__name__)


async def run_main_loop():
    session = Session()
    await asyncio.gather(session.start_input_loop(),
                         session.start_agent_loop())

def main():
    setup_logging("DEBUG")
    logger = get_logger(__name__)
    logger.info("Panda Bot 启动中...")
    asyncio.run(run_main_loop())


if __name__ == "__main__":
    main()
