"""GLM-5 模型提供商"""
import json
import re
from typing import Any, Dict, List, Optional

import requests

from src.utils import get_logger
from .base import BaseProvider

logger = get_logger(__name__)


class GLMProvider(BaseProvider):
    """智谱 GLM-5 模型提供商"""

    # 错误提醒模板
    JSON_ERROR_REMINDER = """ERROR: Your last response was NOT valid JSON.

You MUST respond with ONLY a JSON object, nothing else.

Required format examples:
{"type": "final", "content": "your answer"}
{"type": "tool", "tool": "bash", "input": "ls"}
{"type": "think", "content": "your reasoning"}

DO NOT include:
- Markdown formatting
- Code blocks (```)
- Any text before or after the JSON
- Explanations outside the JSON

Start your response with { and end with }"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = self.config.get("base_url")
        self.api_key = self.config.get("api_key", "")
        self.model = self.config.get("model", "glm-5")
        self.temperature = self.config.get("temperature", 0.7)
        self.max_tokens = self.config.get("max_tokens", 102400)

    def call(self,
             messages: List[Dict[str, str]],
             temperature: Optional[float] = None,
             **kwargs) -> Dict[str, Any]:
        """调用智谱 API"""
        logger.debug(f"调用 LLM API, 消息数: {len(messages)}")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {"model": self.model, "max_tokens": self.max_tokens, "stream": "false", "messages": messages}

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

        # 解析 JSON 响应
        return self._parse_response(text)

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """解析 LLM 响应为 JSON"""
        original_text = text
        text = text.strip()

        # 1. 尝试直接解析
        try:
            result = json.loads(text)
            if self._validate_response(result):
                return result
        except json.JSONDecodeError:
            pass

        # 2. 尝试提取 JSON 代码块
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if json_match:
            try:
                result = json.loads(json_match.group(1).strip())
                if self._validate_response(result):
                    return result
            except json.JSONDecodeError:
                pass

        # 3. 尝试提取 { } 之间的内容
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            try:
                result = json.loads(brace_match.group(0))
                if self._validate_response(result):
                    return result
            except json.JSONDecodeError:
                pass

        # 4. 解析失败，返回错误提醒让 LLM 重试
        return {
            "type": "think",
            "content": f"{self.JSON_ERROR_REMINDER}\n\nYour invalid response was:\n```\n{original_text[:500]}\n```"
        }

    def _validate_response(self, result: Dict[str, Any]) -> bool:
        """验证响应格式是否正确"""
        if not isinstance(result, dict):
            return False
        if "type" not in result:
            return False
        return result["type"] in ["final", "tool", "think"]
