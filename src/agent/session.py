"""会话管理模块"""
import json
from typing import Any, Dict, List, Optional

from src.config.globle_define import *
from src.utils import get_logger

logger = get_logger(__name__)


class Session:
    def __init__(self, workspace: Optional[Path] = None):
        self.messages: List[Dict[str, str]] = []

    async def add_user_input(self, content: str) -> None:
        """添加用户输入"""
        print(f"{USER} {content}")
        self.messages.append({"role": USER, "content": content})

    async def add_agent_response(self, content: str) -> None:
        """添加 Agent 响应"""
        self.messages.append({"role": ASSISTANT, "content": content})
        print(f"{ASSISTANT} {content}")

    async def add_tool_result(self, tool_name: str, result: Dict[str, Any]) -> None:
        """添加工具执行结果"""
        self.messages.append({
            "role": USER,  # GLM 使用 user 角色传递工具结果
            "content": f"Tool [{tool_name}] result:\n{json.dumps(result, ensure_ascii=False, indent=2)}"
        })
        print(f"{ASSISTANT} {json.dumps(result, ensure_ascii=False, indent=2)}")

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