"""模型提供商基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config.config_manager import globe_config_manager

@dataclass
class ToolCallRequest:
    """A tool call request from the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None  # Kimi, DeepSeek-R1 etc.

    @property
    def has_tool_calls(self) -> bool:
        """Check if the response contains tool calls."""
        return len(self.tool_calls) > 0


class BaseProvider(ABC):
    """LLM 提供商基类"""

    def __init__(self):
        self.config = globe_config_manager

    @abstractmethod
    def chat(self,
             messages: List[Dict[str, str]],
             tools: Optional[List[Dict[str, Any]]] = None,
             temperature: Optional[float] = None,
             **kwargs) -> LLMResponse:
        """调用模型 API"""
        pass
