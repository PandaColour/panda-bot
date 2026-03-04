"""模型提供商基类"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseProvider(ABC):
    """LLM 提供商基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def call(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        调用 LLM 生成响应

        Args:
            messages: 消息列表，格式为 [{"role": "user/assistant/system", "content": "..."}]

        Returns:
            必须返回 JSON 格式:
            {
              "type": "tool|final|think",
              "tool": "bash|python",  # 仅 type=tool 时需要
              "input": "...",         # 仅 type=tool 时需要
              "content": "最终回答"    # 仅 type=final 时需要
            }
        """
        pass
