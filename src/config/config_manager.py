"""配置管理模块"""
import json
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    """管理 config/ 目录下的所有配置文件"""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path(__file__).parent.parent.parent / "config"
        self._cache: Dict[str, Any] = {}

    def _load_config(self, filename: str) -> Dict[str, Any]:
        """加载指定配置文件"""
        if filename in self._cache:
            return self._cache[filename]

        config_path = self.config_dir / filename
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            self._cache[filename] = config
            return config

    def _save_config(self, filename: str, data: Dict[str, Any]) -> None:
        """保存配置到指定文件"""
        config_path = self.config_dir / filename
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._cache[filename] = data

    def get_llm_config(self) -> Dict[str, Any]:
        """获取 LLM 配置"""
        config = self._load_config("config.json")
        return config.get("llm", {})

    def set_llm_config(self, llm_config: Dict[str, Any]) -> None:
        """设置 LLM 配置"""
        config = self._load_config("config.json")
        config["llm"] = llm_config
        self._save_config("config.json", config)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项 (支持点分隔路径，如 llm.model)"""
        keys = key.split(".")
        config = self._load_config("config.json")

        for k in keys:
            if isinstance(config, dict) and k in config:
                config = config[k]
            else:
                return default
        return config

    def set(self, key: str, value: Any) -> None:
        """设置配置项 (支持点分隔路径)"""
        keys = key.split(".")
        config = self._load_config("config.json")

        # 导航到目标位置
        current = config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value
        self._save_config("config.json", config)

    def reload(self, filename: Optional[str] = None) -> None:
        """重新加载配置 (清除缓存)"""
        if filename:
            self._cache.pop(filename, None)
        else:
            self._cache.clear()
