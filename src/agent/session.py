"""会话管理模块"""
import asyncio
import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from aioconsole import ainput

from src.config.globle_define import *
from src.utils import get_logger

if TYPE_CHECKING:
    from src.agent.agent import AgentLoop

logger = get_logger(__name__)


class Session:
    def __init__(self, workspace: Optional[Path] = None):
        self.user_inputs: asyncio.Queue[str] = asyncio.Queue()
        self.messages: List[Dict[str, str]] = []
        self.workspace = workspace
        self._agent_loop: Optional["AgentLoop"] = None

    @property
    def agent_loop(self) -> "AgentLoop":
        """延迟初始化 AgentLoop，避免循环导入"""
        if self._agent_loop is None:
            from src.agent.agent import AgentLoop
            self._agent_loop = AgentLoop(self)
        return self._agent_loop

    async def start_agent_loop(self):
        """启动会话"""
        await self.agent_loop.run()

    async def start_input_loop(self):
        """启动输入循环"""
        while True:
            # 使用 aioconsole 异步获取输入
            try:
                user_input = await ainput("You: ")
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input.strip():
                continue

            await self.push_user_input(user_input.strip())

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
        return "".join(items)

    async def add_user_input(self, content: str) -> None:
        """添加用户输入"""
        print(f"{USER} {content}")
        self.messages.append({"role": USER, "content": content})

    async def add_agent_response(self, content: str) -> None:
        """添加 Agent 响应"""
        self.messages.append({"role": ASSISTANT, "content": content})
        print(f"{ASSISTANT} {content}")

    async def add_assistant_tool_calls(self, content: Optional[str], tool_calls: list) -> None:
        """添加 assistant 的 tool_calls 消息（必须在 tool result 之前）"""
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

    async def add_tool_result(self, tool_call_id: str, result: Dict[str, Any]) -> None:
        """添加工具执行结果"""
        content = result.get("result", "") if isinstance(result, dict) else str(result)
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content
        })
        print(f"[tool] {content}")

    async def add_error(self, error_msg: str) -> None:
        """添加错误信息"""
        self.messages.append({
            "role": USER,
            "content": f"Error: {error_msg}"
        })
        print(f"{ASSISTANT} {error_msg}")

    def get_messages(self) -> List[Dict[str, str]]:
        """获取所有消息"""
        return self.messages.copy()