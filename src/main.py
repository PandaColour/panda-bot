"""
Panda Bot - 通用智能体

入口文件
"""
import asyncio
import sys
from pathlib import Path

# Windows 控制台 UTF-8 编码支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from src.agent.session import Session
from src.config.config_manager import globe_config_manager
from src.utils import get_logger, setup_logging

logger = get_logger(__name__)

# 项目根目录（main.py 在 src/ 下，上一级即根目录）
_PROJECT_ROOT = Path(__file__).parent.parent


async def run_main_loop():
    workspace_str = globe_config_manager.get("main-agent.workspace")
    if workspace_str:
        workspace = Path(workspace_str)
        if not workspace.is_absolute():
            workspace = (_PROJECT_ROOT / workspace).resolve()
    else:
        workspace = None

    session = Session(workspace=workspace)
    await asyncio.gather(session.start_input_loop(),
                         session.start_agent_loop())

def main():
    setup_logging("DEBUG")
    logger = get_logger(__name__)
    logger.info("Panda Bot 启动中...")
    asyncio.run(run_main_loop())


if __name__ == "__main__":
    main()
