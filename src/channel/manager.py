"""Channel 管理器：根据配置创建并运行所有 Channel"""
import asyncio
from typing import List

from src.config.config_manager import ConfigManager, globe_config_manager
from src.utils import get_logger
from .base import BaseChannel
from .console import ConsoleChannel

logger = get_logger(__name__)

# Channel 类型注册表
_REGISTRY: dict[str, type[BaseChannel]] = {
    "console": ConsoleChannel,
}


def _get_registry() -> dict[str, type[BaseChannel]]:
    """延迟导入 ilink，避免强依赖（未安装 pycryptodome 时也能启动）"""
    registry = dict(_REGISTRY)
    try:
        from .ilink.channel import ILinkChannel
        registry["ilink"] = ILinkChannel
    except ImportError as e:
        logger.warning(f"ilink channel 不可用（缺少依赖）: {e}")
    return registry


class ChannelManager:
    """根据 config.json 中的 channels 配置，实例化并管理所有 Channel。

    config.json 格式：
    {
      "channels": [
        {"type": "console", "enabled": true},
        {"type": "ilink", "enabled": false, "config": {...}}
      ]
    }
    """

    def __init__(self, config: ConfigManager = None):
        self._config = config or globe_config_manager
        self._channels: List[BaseChannel] = []

    def load_channels(self) -> List[BaseChannel]:
        """从配置加载并实例化所有启用的 Channel"""
        registry = _get_registry()
        channels_cfg = self._config.get("channels") or []

        if not channels_cfg:
            # 没有配置时默认启用 console
            logger.info("未配置 channels，使用默认 ConsoleChannel")
            self._channels = [ConsoleChannel()]
            return self._channels

        loaded = []
        for ch_cfg in channels_cfg:
            ch_type = ch_cfg.get("type", "")
            enabled = ch_cfg.get("enabled", True)
            if not enabled:
                logger.debug(f"Channel [{ch_type}] 已禁用，跳过")
                continue

            cls = registry.get(ch_type)
            if cls is None:
                logger.error(f"未知的 channel 类型: {ch_type}，跳过")
                continue

            channel = cls(config=ch_cfg.get("config") or {})
            loaded.append(channel)
            logger.info(f"已加载 Channel: {ch_type}")

        if not loaded:
            logger.warning("没有启用的 Channel，使用默认 ConsoleChannel")
            loaded = [ConsoleChannel()]

        self._channels = loaded
        return self._channels

    async def run(self, session) -> None:
        """并发运行 AgentLoop 和所有 Channel，直到全部退出"""
        if not self._channels:
            self.load_channels()

        tasks = [session.start_agent_loop()]
        tasks += [ch.start(session) for ch in self._channels]

        await asyncio.gather(*tasks)

    async def stop_all(self) -> None:
        """停止所有 Channel"""
        for ch in self._channels:
            await ch.stop()
