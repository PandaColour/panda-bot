"""全局常量定义"""
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent

# 默认工作目录: 项目根目录/workspace
DEFAULT_WORKSPACE = _PROJECT_ROOT / "workspace"

# agent 模板目录（prompts + skills 原始副本）
TEMPLATE_DIR = _PROJECT_ROOT / "template"

# 消息角色
USER = "user"
ASSISTANT = "assistant"
