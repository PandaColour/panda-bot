"""OpenAI API Provider"""
import json
from typing import Any, Dict, List, Optional

import requests

from src.utils import get_logger
from .base_provider import BaseProvider, LLMResponse, ToolCallRequest

logger = get_logger(__name__)


class OpenAIProvider(BaseProvider):
    """标准 OpenAI API Provider"""

    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        super().__init__()
        if config_dict:
            # 使用传入的配置字典
            self.base_url = config_dict.get("base_url", "https://api.openai.com")
            self.api_key = config_dict.get("api_key", "")
            self.model = config_dict.get("model", "gpt-4")
            self.temperature = config_dict.get("temperature", 0.7)
            self.max_tokens = config_dict.get("max_tokens", 4096)

    def chat(self,
             messages: List[Dict[str, str]],
             tools: Optional[List[Dict[str, Any]]] = None,
             temperature: Optional[float] = None,
             **kwargs) -> LLMResponse:
        """调用 OpenAI API"""
        logger.debug(f"调用 OpenAI API, 消息数: {len(messages)}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": self.max_tokens,
        }

        if tools is not None:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        payload.update(kwargs)

        try:
            response = requests.post(
                url=f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            logger.debug(f"OpenAI API 调用成功 {result}")
        except requests.RequestException as e:
            logger.error(f"OpenAI API RequestException: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"OpenAI API 返回结果解析失败: {str(e)}")
            raise

        return self._convert_response(result)

    @staticmethod
    def _convert_response(response: dict) -> LLMResponse:
        """将 OpenAI API 响应转换为 LLMResponse"""
        choice = response["choices"][0]
        message = choice["message"]

        # 提取 tool_calls
        tool_calls = []
        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                arguments = tc["function"]["arguments"]
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                tool_calls.append(ToolCallRequest(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=arguments
                ))

        # 构建 usage 字典
        usage = {}
        if "usage" in response:
            usage_data = response["usage"]
            usage = {
                "prompt_tokens": usage_data.get("prompt_tokens", 0),
                "completion_tokens": usage_data.get("completion_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0)
            }

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=usage,
            reasoning_content=None
        )
