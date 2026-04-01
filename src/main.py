"""
Panda Bot - 通用智能体

入口文件
"""
import sys
from pathlib import Path

# Windows 控制台 UTF-8 编码支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from src.agent.session import Session
from src.channel.chat_window import ChatWindow
from src.config.config_manager import globe_config_manager
from src.utils import get_logger, setup_logging

logger = get_logger(__name__)

# 项目根目录
_PROJECT_ROOT = Path(__file__).parent.parent


def main():
    setup_logging("DEBUG")
    logger.info("Panda Bot 启动中...")

    # 获取 workspace 配置
    workspace_str = globe_config_manager.get("main-agent.workspace")
    if workspace_str:
        workspace = Path(workspace_str)
        if not workspace.is_absolute():
            workspace = (_PROJECT_ROOT / workspace).resolve()
    else:
        workspace = None

    # 创建 session
    session = Session(workspace=workspace)

    # 启动 Qt 应用
    app = QApplication(sys.argv)

    # 用 qasync 让 Qt 和 asyncio 共享事件循环
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = ChatWindow(session)
    window.show()

    with loop:
        loop.run_until_complete(window.start_agent())


if __name__ == "__main__":
    import asyncio
    main()
