"""GLM-5 模型提供商"""
import json
import re
from typing import Any, Dict, List, Optional

import requests
from zai import ZhipuAiClient
from zai.types.chat import Completion

from src.utils import get_logger
from .base_provider import BaseProvider, LLMResponse, ToolCallRequest

logger = get_logger(__name__)


class GLMProvider(BaseProvider):
    """智谱 GLM-5 模型提供商"""
    def __init__(self, ):
        super().__init__()
        self.base_url = self.config.get("llm.base_url")
        self.api_key = self.config.get("llm.api_key", "")
        self.model = self.config.get("llm.model", "glm-5")
        self.temperature = self.config.get("llm.temperature", 0.7)
        self.max_tokens = self.config.get("llm.max_tokens", 102400)
        self.client = ZhipuAiClient(api_key=self.api_key)

    def chat(self,
             messages: List[Dict[str, str]],
             tools: Optional[List[Dict[str, Any]]] = None,
             temperature: Optional[float] = None,
             **kwargs) -> LLMResponse:
        """调用智谱 API"""
        logger.debug(f"调用 LLM API, 消息: {json.dumps(messages, ensure_ascii=False)}")

        response = None
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=self.temperature
            )
            logger.debug(f"LLM API 调用成功,返回结果: {response.to_json()}")
            result = self._convert_response(response)
        except requests.HTTPError as e:
            logger.error(f"LLM API HTTPError: {str(e)}  response.status_code: {str(response.status_code)}")
            raise
        except requests.RequestException as e:
            logger.error(f"LLM API RequestException: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"LLM API 返回结果解析失败: {str(e)}")
            raise
        return result

    @staticmethod
    def _convert_response(response: Completion) -> LLMResponse:
        """将智谱 API 响应转换为 LLMResponse"""
        choice = response.choices[0]
        message = choice.message

        # 解析 tool_calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                # arguments 是 JSON 字符串，需要解析
                arguments = tc.function.arguments
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments
                ))

        # 构建 usage 字典
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=usage,
            reasoning_content=getattr(message, 'reasoning_content', None)
        )