"""上下文构建器 - 管理传递给 LLM 的上下文"""
import platform
from pathlib import Path
from typing import Dict, List, Optional
import distro

from src.agent.session import Session
from src.config import ConfigManager
from src.agent.skills import SkillLoader

class ContextBuilder:
    TEMPLATE_DIR = Path(__file__).parent / "prompts"
    SKILLS_DIR   = Path(__file__).parent / "prompts" / "skills"
    DEFAULT_PROMPT_FILE = "AGENTS.md"
    SYSTEM_ROLE = "system"

    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config or ConfigManager()
        self.max_history_messages = 50
        self._system_prompt_cache: Optional[str] = None
        self._skill_loader = SkillLoader(self.SKILLS_DIR)

    def build(self, session: Session) -> List[Dict[str, str]]:
        # 1. 基础系统提示词（缓存）
        system_prompt = self._get_system_prompt()

        # 2. 动态注入 skills：取最新一条用户消息作为匹配文本
        last_user_input = self._get_last_user_input(session)
        skill_text = self._skill_loader.get_prompt(last_user_input)
        if skill_text:
            system_prompt = system_prompt + "\n\n" + skill_text

        messages = [{"role": self.SYSTEM_ROLE, "content": system_prompt}]
        messages.extend(session.get_messages())
        return messages

    def _get_last_user_input(self, session: Session) -> str:
        """从 session 消息中取最后一条 user 消息内容"""
        for msg in reversed(session.get_messages()):
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                return msg["content"]
        return ""

    def _get_system_prompt(self) -> str:
        """获取系统提示词 (优先从配置读取，其次从文件加载)"""
        # 1. 从缓存读取
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache

        # 2. 从模板文件加载
        prompt_file = self.TEMPLATE_DIR / self.DEFAULT_PROMPT_FILE
        if prompt_file.exists():
            base_prompt = prompt_file.read_text(encoding="utf-8").strip()
        else:
            base_prompt = ""

        # 3. 追加运行系统信息
        os_info = self._get_os_info()
        self._system_prompt_cache = f"{base_prompt}\n\n## 运行环境\n\n{os_info}"
        return self._system_prompt_cache

    def _get_os_info(self) -> str:
        system = platform.system()
        release = platform.release()

        if system == "Windows":
            return f"- 操作系统: Windows {release}"
        elif system == "Darwin":
            return f"- 操作系统: macOS {release}"
        elif system == "Linux":
            distro = self._get_linux_distro()
            return f"- 操作系统: Linux ({distro})"
        else:
            return f"- 操作系统: {system} {release}"

    @staticmethod
    def _get_linux_distro() -> str:
        """获取 Linux 发行版信息"""
        try:

            return f"{distro.name()} {distro.version()}"
        except ImportError:
            return "Unknown"

    def _truncate_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        截断消息列表，保持系统提示词和最近的消息

        策略: 保留 system prompt + 最近 N 条消息
        """
        if len(messages) <= self.max_history_messages:
            return messages

        # 保留系统提示词
        system_msg = messages[:1]
        # 保留最近的消息
        recent = messages[-(self.max_history_messages - 1):]

        return system_msg + recent

    def set_system_prompt(self, prompt: str) -> None:
        """设置自定义系统提示词"""
        self.config.set("agent.system_prompt", prompt)
        self._system_prompt_cache = None  # 清除缓存

    def reset_system_prompt(self) -> None:
        """重置为默认系统提示词 (从文件加载)"""
        self.config.set("agent.system_prompt", None)
        self._system_prompt_cache = None  # 清除缓存，下次将从文件加载

    def reload_system_prompt(self) -> str:
        """强制重新加载系统提示词"""
        self._system_prompt_cache = None
        return self._get_system_prompt()
