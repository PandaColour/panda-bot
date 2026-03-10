"""GLM-5 模型提供商"""
import json
import re
from typing import Any, Dict, List, Optional

import requests

from src.utils import get_logger
from .base_provider import BaseProvider
from ..config.config_manager import globe_config_manager

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

    def chat(self,
             messages: List[Dict[str, str]],
             tools: Optional[List[Dict[str, Any]]] = None,
             temperature: Optional[float] = None,
             **kwargs) -> str:
        """调用智谱 API"""
        logger.debug(f"调用 LLM API, 消息数: {len(messages)}")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {"model": self.model,
                   "max_tokens": self.max_tokens,
                   "stream": "false",
                   "messages": messages}

        if tools is not None:
            payload["tools"] = tools

        if temperature is not None:
            payload["temperature"] = temperature
        else:
            payload["temperature"] = self.temperature

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
            logger.error(f"LLM API 调用失败: {str(e)}")
            raise

        # 提取文本内容 (智谱 API 响应格式)
        text = result["content"][0]["text"].strip()
        logger.debug(f"LLM 响应长度: {len(text)}")
        return text