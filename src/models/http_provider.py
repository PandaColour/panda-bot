"""GLM-5 模型提供商"""
import json
from typing import Any, Dict, List, Optional

import requests

from src.utils import get_logger
from .base_provider import BaseProvider, LLMResponse, ToolCallRequest

logger = get_logger(__name__)


class HttpProvider(BaseProvider):
    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        super().__init__()
        if config_dict:
            # 使用传入的配置字典
            self.base_url = config_dict.get("base_url")
            self.api_key = config_dict.get("api_key", "")
            self.model = config_dict.get("model", "glm-5")
            self.temperature = config_dict.get("temperature", 0.7)
            self.max_tokens = config_dict.get("max_tokens", 102400)

    def chat(self,
             messages: List[Dict[str, str]],
             tools: Optional[List[Dict[str, Any]]] = None,
             temperature: Optional[float] = None,
             **kwargs) -> LLMResponse:
        """调用 Anthropic Claude API"""
        logger.debug(f"调用 LLM API, 消息数: {len(messages)}")

        # 转换消息格式：OpenAI → Anthropic
        system_prompt = None
        anthropic_messages = []

        for message in messages:
            role = message.get("role")

            if role == "system":
                system_prompt = message.get("content", "")

            elif role == "assistant":
                # assistant 消息可能包含 tool_calls
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
                # tool result 转换为 user 消息
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
            "stream": False,
            "messages": anthropic_messages
        }

        if system_prompt:
            payload["system"] = system_prompt

        if temperature is not None:
            payload["temperature"] = temperature
        else:
            payload["temperature"] = self.temperature

        if tools is not None:
            # 转换 OpenAI 格式到 Anthropic 格式
            anthropic_tools = []
            for tool in tools:
                if tool.get("type") == "function" and "function" in tool:
                    func = tool["function"]
                    anthropic_tools.append({
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {})
                    })
            payload["tools"] = anthropic_tools
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
            logger.debug("LLM API 调用成功")
        except requests.RequestException as e:
            logger.error(f"LLM API RequestException: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"LLM API 返回结果解析失败: {str(e)}")
            raise

        return self._convert_response(result)

    @staticmethod
    def _convert_response(response: dict) -> LLMResponse:
        """将 Anthropic Claude API 响应转换为 LLMResponse"""
        content_blocks = response.get('content', [])

        # 提取文本内容
        text_parts = []
        for block in content_blocks:
            if block.get('type') == 'text':
                text_parts.append(block.get('text', ''))
        content = '\n'.join(text_parts) if text_parts else None

        # 提取 tool_use
        tool_calls = []
        for block in content_blocks:
            if block.get('type') == 'tool_use':
                tool_calls.append(ToolCallRequest(
                    id=block.get('id', ''),
                    name=block.get('name', ''),
                    arguments=block.get('input', {})
                ))

        # 构建 usage 字典
        usage = {}
        if 'usage' in response:
            usage_data = response['usage']
            usage = {
                "prompt_tokens": usage_data.get('input_tokens', 0),
                "completion_tokens": usage_data.get('output_tokens', 0),
                "total_tokens": usage_data.get('input_tokens', 0) + usage_data.get('output_tokens', 0)
            }

        # stop_reason 映射到 finish_reason
        stop_reason = response.get('stop_reason', 'stop')
        finish_reason_map = {
            'end_turn': 'stop',
            'tool_use': 'tool_calls',
            'max_tokens': 'length',
            'stop_sequence': 'stop'
        }
        finish_reason = finish_reason_map.get(stop_reason, stop_reason)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=None
        )