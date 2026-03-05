"""会话管理模块"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils import get_logger

logger = get_logger(__name__)


class Session:
    """管理对话历史和记忆"""

    # 默认工作目录: 项目根目录/workspace
    DEFAULT_WORKSPACE = Path(__file__).parent.parent.parent / "workspace"
    USER = "user"
    ASSISTANT = "assistant"

    def __init__(self, workspace: Optional[Path] = None):
        self.messages: List[Dict[str, str]] = []
        self.memory: List[Dict[str, Any]] = []

        # 设置工作目录
        self.workspace = Path(workspace) if workspace else self.DEFAULT_WORKSPACE
        self.workspace.mkdir(parents=True, exist_ok=True)

        # 创建会话目录: workspace/session-{{YYYYmmDDHHMMSS}}
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.session_dir = self.workspace / f"session-{timestamp}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 文件路径
        self.history_file = self.session_dir / "history.md"
        self.memory_file = self.session_dir / "memory.md"

        logger.info(f"创建新会话: {self.session_dir}")

    @property
    def work_dir(self) -> Path:
        """获取当前会话工作目录"""
        return self.session_dir

    def add_user_input(self, content: str) -> None:
        """添加用户输入"""
        self.messages.append({"role": "user", "content": content})
        self._save_history()

    def add_agent_response(self, content: str) -> None:
        """添加 Agent 响应"""
        self.messages.append({"role": self.ASSISTANT, "content": content})
        self._save_history()

    def add_message(self, role: str, content: str) -> None:
        """添加消息到对话历史"""
        self.messages.append({"role": role, "content": content})
        self._save_history()

    def add_tool_result(self, tool_name: str, result: Dict[str, Any]) -> None:
        """添加工具执行结果"""
        self.messages.append({
            "role": self.USER,  # GLM 使用 user 角色传递工具结果
            "content": f"Tool [{tool_name}] result:\n{json.dumps(result, ensure_ascii=False, indent=2)}"
        })
        self._save_history()

    def add_error(self, error_msg: str) -> None:
        """添加错误信息"""
        self.messages.append({
            "role": self.USER,
            "content": f"Error: {error_msg}"
        })
        self._save_history()

    def get_messages(self) -> List[Dict[str, str]]:
        """获取所有消息"""
        return self.messages.copy()

    def get_last_message(self) -> Optional[Dict[str, str]]:
        """获取最后一条消息"""
        return self.messages[-1] if self.messages else None

    def add_memory(self, key: str, value: Any) -> None:
        """添加记忆项"""
        self.memory.append({"key": key, "value": value})
        self._save_memory()

    def get_memory(self, key: str) -> Optional[Any]:
        """获取记忆项"""
        for item in self.memory:
            if item["key"] == key:
                return item["value"]
        return None

    def get_memory_context(self) -> str:
        """获取记忆上下文"""
        if not self.memory:
            return ""
        return "\n".join([
            f"- {item['key']}: {item['value']}"
            for item in self.memory
        ])

    def clear_messages(self) -> None:
        """清空消息历史"""
        self.messages = []
        self._save_history()

    def summary(self) -> Dict[str, Any]:
        """获取会话摘要"""
        return {
            "session_dir": str(self.session_dir),
            "message_count": len(self.messages),
            "memory_count": len(self.memory),
        }

    def _save_history(self) -> None:
        """保存对话历史到 history.md"""
        lines = ["# 对话历史\n"]
        for msg in self.messages:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                lines.append(f"## 用户\n\n{content}\n")
            elif role == "assistant":
                lines.append(f"## 助手\n\n{content}\n")
            else:
                lines.append(f"## {role}\n\n{content}\n")

        self.history_file.write_text("\n".join(lines), encoding="utf-8")

    def _save_memory(self) -> None:
        """保存记忆到 memory.md"""
        lines = ["# 会话记忆\n"]
        for item in self.memory:
            lines.append(f"- **{item['key']}**: {item['value']}")

        self.memory_file.write_text("\n".join(lines), encoding="utf-8")
