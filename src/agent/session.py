"""会话管理模块"""
import asyncio
import json
import shutil
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING

from src.config.globle_define import *
from src.utils import get_logger

if TYPE_CHECKING:
    from src.agent.agent import AgentLoop

logger = get_logger(__name__)

# Channel 回调类型
ReplyCallback    = Callable[[str], Awaitable[None]]          # Agent 最终回复
ProgressCallback = Callable[[str, str], Awaitable[None]]     # (event, data) 过程事件


class Session:
    def __init__(self, workspace: Optional[Path] = None,
                 reply_callback: Optional[ReplyCallback] = None):
        self.session_id = uuid.uuid4().hex[:8]
        self.workspace: Path = Path(workspace) if workspace else DEFAULT_WORKSPACE / self.session_id
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._init_bot_dir()
        self.user_inputs: asyncio.Queue[str] = asyncio.Queue()
        self.messages: List[Dict[str, str]] = []
        self._agent_loop: Optional["AgentLoop"] = None
        self._reply_callback:    Optional[ReplyCallback]    = reply_callback
        self._progress_callback: Optional[ProgressCallback] = None
        logger.info(f"Session [{self.session_id}] workspace: {self.workspace}")

    def _init_bot_dir(self) -> None:
        """若 workspace/.bot 不存在，从 template 目录复制初始内容"""
        bot_dir = self.workspace / ".bot"
        if not bot_dir.exists():
            shutil.copytree(TEMPLATE_DIR, bot_dir)
            logger.info(f"已初始化 .bot 目录: {bot_dir}")

    @property
    def agent_loop(self) -> "AgentLoop":
        """延迟初始化 AgentLoop，避免循环导入"""
        if self._agent_loop is None:
            from src.agent.agent import AgentLoop
            self._agent_loop = AgentLoop(self)
        return self._agent_loop

    async def start_agent_loop(self):
        await self.agent_loop.run()

    async def push_user_input(self, content: str) -> None:
        await self.user_inputs.put(content)

    async def take_all_inputs_nowait(self) -> str:
        items = []
        while True:
            try:
                item = self.user_inputs.get_nowait()
                items.append(item)
            except asyncio.QueueEmpty:
                break
        return "\n".join(items)

    # ------------------------------------------------------------------ #
    # 消息历史维护（不做任何输出，输出由 Channel 负责）
    # ------------------------------------------------------------------ #

    async def add_user_input(self, content: str) -> None:
        self.messages.append({"role": USER, "content": content})

    async def add_agent_response(self, content: str) -> None:
        """Agent 产生最终文字回复 → 写历史 + 触发 reply_callback"""
        self.messages.append({"role": ASSISTANT, "content": content})
        if self._reply_callback:
            await self._reply_callback(content)

    async def add_assistant_tool_calls(self, content: Optional[str], tool_calls: list) -> None:
        """写工具调用消息 → 写历史 + 触发 progress_callback"""
        msg: Dict[str, Any] = {"role": "assistant", "content": content or ""}
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}
            }
            for tc in tool_calls
        ]
        self.messages.append(msg)
        if self._progress_callback:
            names = ", ".join(tc.name for tc in tool_calls)
            await self._progress_callback("tool_call", names)

    async def add_tool_result(self, tool_call_id: str, result: Dict[str, Any]) -> None:
        """写工具结果 → 写历史 + 触发 progress_callback"""
        content = result.get("result", "") if isinstance(result, dict) else str(result)
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content
        })
        if self._progress_callback:
            await self._progress_callback("tool_result", content)

    async def add_error(self, error_msg: str) -> None:
        """写错误消息 → 写历史 + 触发 progress_callback"""
        self.messages.append({"role": ASSISTANT, "content": f"Error: {error_msg}"})
        if self._progress_callback:
            await self._progress_callback("error", error_msg)

    def get_messages(self) -> List[Dict[str, str]]:
        return self.messages.copy()
