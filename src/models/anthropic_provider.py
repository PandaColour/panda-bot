"""Anthropic Claude API Provider"""
import json
from typing import Any, Dict, List, Optional

import requests

from src.utils import get_logger
from .base_provider import BaseProvider, LLMResponse, ToolCallRequest

logger = get_logger(__name__)


class AnthropicProvider(BaseProvider):
    """标准 Anthropic Claude API Provider"""

    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        super().__init__()
        if config_dict:
            self.base_url = config_dict.get("base_url", "https://api.anthropic.com")
            self.api_key = config_dict.get("api_key", "")
            self.model = config_dict.get("model", "claude-sonnet-4-6")
            self.temperature = config_dict.get("temperature", 0.7)
            self.max_tokens = config_dict.get("max_tokens", 8192)

    def chat(self,
             messages: List[Dict[str, str]],
             tools: Optional[List[Dict[str, Any]]] = None,
             temperature: Optional[float] = None,
             **kwargs) -> LLMResponse:
        """调用 Anthropic Claude API"""
        logger.debug(f"调用 Anthropic API, 消息数: {len(messages)}")

        # 转换消息格式：OpenAI → Anthropic
        system_prompt = None
        anthropic_messages = []

        for message in messages:
            role = message.get("role")

            if role == "system":
                system_prompt = message.get("content", "")
            elif role == "assistant":
                content_blocks = []
                if message.get("content"):
                    content_blocks.append({"type": "text", "text": message["content"]})
                if "tool_calls" in message:
                    for tc in message["tool_calls"]:
                        func = tc.get("function", {})
                        arguments = func.get("arguments", "{}")
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments)
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "input": arguments
                        })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content_blocks if content_blocks else ""
                })

            elif role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": message.get("tool_call_id", ""),
                        "content": message.get("content", "")
                    }]
                })

            elif role == "user":
                anthropic_messages.append({
                    "role": "user",
                    "content": message.get("content", "")
                })

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if tools is not None:
            # 转换 OpenAI 格式到 Anthropic 格式
            payload["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "input_schema": t["function"]["parameters"]
                }
                for t in tools if t.get("type") == "function"
            ]
            payload["tool_choice"] = {"type": "auto"}

        payload.update(kwargs)

        try:
            response = requests.post(
                url=f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            logger.debug("Anthropic API 调用成功")
        except requests.RequestException as e:
            logger.error(f"Anthropic API RequestException: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Anthropic API 返回结果解析失败: {str(e)}")
            raise

        return self._convert_response(result)

    @staticmethod
    def _convert_response(response: dict) -> LLMResponse:
        """将 Anthropic API 响应转换为 LLMResponse"""
        content_blocks = response.get("content", [])

        text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
        content = "\n".join(text_parts) if text_parts else None

        tool_calls = [
            ToolCallRequest(
                id=b.get("id", ""),
                name=b.get("name", ""),
                arguments=b.get("input", {})
            )
            for b in content_blocks if b.get("type") == "tool_use"
        ]

        usage = {}
        if "usage" in response:
            u = response["usage"]
            usage = {
                "prompt_tokens": u.get("input_tokens", 0),
                "completion_tokens": u.get("output_tokens", 0),
                "total_tokens": u.get("input_tokens", 0) + u.get("output_tokens", 0)
            }

        stop_reason = response.get("stop_reason", "end_turn")
        finish_reason = {"end_turn": "stop", "tool_use": "tool_calls"}.get(stop_reason, stop_reason)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=None
        )
