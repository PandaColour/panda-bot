"""上下文构建器 - 管理传递给 LLM 的上下文"""
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import ConfigManager
from src.session import Session


class ContextBuilder:
    """
    构建 LLM 调用所需的上下文

    职责:
    1. 加载和管理系统提示词
    2. 构建消息历史
    3. 控制上下文长度
    """

    # 模板文件路径
    TEMPLATE_DIR = Path(__file__).parent.parent / "template"
    DEFAULT_PROMPT_FILE = "AGENTS.md"
    SYSTEM_ROLE = "assistant"

    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config or ConfigManager()
        self.max_history_messages = 50  # 最大历史消息数
        self._system_prompt_cache: Optional[str] = None

    def build(self, session: Session) -> List[Dict[str, str]]:
        """
        构建完整的消息上下文

        Args:
            session: 会话对象

        Returns:
            构建好的消息列表，可直接传给 LLM
        """
        messages = []

        # 1. 添加系统提示词
        system_prompt = self._get_system_prompt()
        messages.append({"role": self.SYSTEM_ROLE, "content": system_prompt})

        # 2. 添加对话历史 (session 中已维护所有历史)
        messages.extend(session.get_messages())

        # 3. 控制上下文长度
        messages = self._truncate_messages(messages)

        return messages

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
        """获取操作系统信息"""
        system = platform.system()
        release = platform.release()
        version = platform.version()

        if system == "Windows":
            return f"- 操作系统: Windows {release}"
        elif system == "Darwin":
            return f"- 操作系统: macOS {release}"
        elif system == "Linux":
            distro = self._get_linux_distro()
            return f"- 操作系统: Linux ({distro})"
        else:
            return f"- 操作系统: {system} {release}"

    def _get_linux_distro(self) -> str:
        """获取 Linux 发行版信息"""
        try:
            import distro
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
