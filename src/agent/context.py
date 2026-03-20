"""上下文构建器 - 管理传递给 LLM 的上下文"""
import platform
from pathlib import Path
from typing import Dict, List, Optional
import distro

from src.agent.session import Session
from src.config import ConfigManager
from src.agent.skills import SkillLoader

class ContextBuilder:
    SYSTEM_ROLE = "system"

    def __init__(self, config: Optional[ConfigManager] = None, workspace: Optional[Path] = None):
        self.config = config or ConfigManager()
        self.max_history_messages = 50
        self._system_prompt_cache: Optional[str] = None
        self._workspace = Path(workspace) if workspace else None
        bot_dir = self._workspace / ".bot" if self._workspace else None
        self._prompt_file: Optional[Path] = bot_dir / "prompts" / "AGENT.md" if bot_dir else None
        self._skill_loader = SkillLoader(bot_dir / "skills") if bot_dir else SkillLoader(Path())

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
        """获取系统提示词（从 workspace/.bot/prompts/AGENT.md 加载，带缓存）"""
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache

        if self._prompt_file and self._prompt_file.exists():
            base_prompt = self._prompt_file.read_text(encoding="utf-8").strip()
        else:
            base_prompt = ""

        os_info = self._get_os_info()
        workspace_info = f"- 工作目录: {self._workspace}" if self._workspace else ""
        env_section = f"{os_info}\n{workspace_info}".strip()
        self._system_prompt_cache = f"{base_prompt}\n\n## 运行环境\n\n{env_section}"
        return self._system_prompt_cache

    def _get_os_info(self) -> str:
        system = platform.system()
        release = platform.release()

        if system == "Windows":
            return f"- 操作系统: Windows {release}"
        elif system == "Darwin":
            return f"- 操作系统: macOS {release}"
        elif system == "Linux":
            distro_info = self._get_linux_distro()
            return f"- 操作系统: Linux ({distro_info})"
        else:
            return f"- 操作系统: {system} {release}"

    @staticmethod
    def _get_linux_distro() -> str:
        try:
            return f"{distro.name()} {distro.version()}"
        except ImportError:
            return "Unknown"

    def reload_system_prompt(self) -> str:
        self._system_prompt_cache = None
        return self._get_system_prompt()
