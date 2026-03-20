"""Provider 工厂 - 根据配置动态创建 LLM Provider"""
from src.config.config_manager import globe_config_manager
from src.utils import get_logger
from .base_provider import BaseProvider
from .glm_provider import GLMProvider
from .http_provider import HttpProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider

logger = get_logger(__name__)

_PROVIDER_MAP = {
    "glm":       GLMProvider,
    "http":      HttpProvider,       # 旧的通用 http，实际是 Anthropic 格式
    "openai":    OpenAIProvider,
    "anthropic": AnthropicProvider,
}


class ProviderFactory:
    """根据配置创建 LLM Provider"""

    @staticmethod
    def create_provider() -> BaseProvider:
        """
        根据配置创建 Provider 实例

        从 globe_config_manager 读取:
        - models.active: 当前激活的 provider id
        - models.providers: provider 配置列表
        """
        config = globe_config_manager
        active_id = config.get("models.active")
        providers = config.get("models.providers", [])

        if not active_id:
            raise ValueError("models.active not configured")

        provider_config = next((p for p in providers if p.get("id") == active_id), None)
        if not provider_config:
            raise ValueError(f"Provider '{active_id}' not found in models.providers")

        provider_type = provider_config.get("type")
        if not provider_type:
            raise ValueError(f"Provider '{active_id}' missing 'type' field")

        cls = _PROVIDER_MAP.get(provider_type)
        if not cls:
            raise ValueError(f"Unknown provider type: '{provider_type}'. Available: {list(_PROVIDER_MAP)}")

        logger.info(f"创建 Provider: {active_id} (type={provider_type})")
        return cls(provider_config)
