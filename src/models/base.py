"""模型提供商基类"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from src.config.config_manager import globe_config_manager


class BaseProvider(ABC):
    """LLM 提供商基类"""

    def __init__(self):
        self.config = globe_config_manager

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """调用模型 API"""
        pass
