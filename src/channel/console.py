"""命令行 Channel"""
from aioconsole import ainput

from src.utils import get_logger
from .base import BaseChannel

logger = get_logger(__name__)


class ConsoleChannel(BaseChannel):
    """通过命令行标准输入输出与 Agent 交互。"""

    channel_id = "console"

    def __init__(self, config: dict = None):
        self._config = config or {}
        self._running = False

    async def start(self, session) -> None:
        # 注册回调
        session._reply_callback    = self.send_reply
        session._progress_callback = self.on_progress
        self._running = True
        logger.info("ConsoleChannel 已启动，等待输入...")

        while self._running:
            try:
                user_input = await ainput("You: ")
            except (EOFError, KeyboardInterrupt):
                logger.info("ConsoleChannel 收到退出信号")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            await session.push_user_input(user_input)

    async def stop(self) -> None:
        self._running = False

    async def send_reply(self, content: str) -> None:
        """打印 Agent 最终回复"""
        print(f"\nAgent: {content}\n")

    async def on_progress(self, event: str, data: str) -> None:
        """打印工具执行过程（仅命令行可见）"""
        if event == "tool_call":
            print(f"  [工具] {data}")
        elif event == "tool_result":
            # 结果可能很长，截断显示
            preview = data[:200] + "…" if len(data) > 200 else data
            print(f"  [结果] {preview}")
        elif event == "error":
            print(f"  [错误] {data}")
