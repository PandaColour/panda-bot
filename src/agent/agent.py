"""智能体核心 - 控制层"""
from typing import Dict, Optional

from src.config import ConfigManager
from src.providers import GLMProvider
from src.session import Session
from src.tools import TOOLS

from .context_builder import ContextBuilder


class Agent:
    """
    智能体控制层
    状态机: INIT → THINK → ACT → VALIDATE → DONE / ERROR
    """

    MAX_STEPS = 30
    MAX_RETRY = 3

    def __init__(self, session: Session, config_manager: Optional[ConfigManager] = None):
        self.session = session  # 外部传入
        self.config = config_manager or ConfigManager()

        # 初始化组件
        self.provider = GLMProvider(self.config.get_llm_config())
        self.context_builder = ContextBuilder(self.config)

        # 状态
        self.state = "INIT"
        self.step_count = 0
        self.retry_count = 0

    def run(self) -> str:
        """执行智能体主循环"""
        self.state = "INIT"

        while self.step_count < self.MAX_STEPS:
            self.step_count += 1
            self.state = "THINK"

            # 构建上下文并调用 LLM
            try:
                messages = self.context_builder.build(self.session)
                response = self.provider.call(messages)
            except Exception as e:
                self.session.add_error(f"LLM call failed: {str(e)}")
                self.retry_count += 1
                if self.retry_count > self.MAX_RETRY:
                    return "LLM 调用失败次数过多，任务终止。"
                continue

            # 处理响应
            response_type = response.get("type")

            if response_type == "final":
                self.state = "DONE"
                return response.get("content", "任务完成")

            elif response_type == "think":
                # 思考阶段，添加到历史继续
                self.session.add_message("assistant", response.get("content", ""))
                continue

            elif response_type == "tool":
                self.state = "ACT"
                tool_name = response.get("tool")
                tool_input = response.get("input", "")

                # 验证工具
                if tool_name not in TOOLS:
                    self.session.add_error(f"Unknown tool: {tool_name}")
                    continue

                # 执行工具
                try:
                    result = TOOLS[tool_name](tool_input)
                except Exception as e:
                    result = {"stdout": "", "stderr": str(e), "code": -1}

                # 验证结果
                self.state = "VALIDATE"
                if self._validate_result(result):
                    self.retry_count = 0
                else:
                    self.retry_count += 1
                    if self.retry_count > self.MAX_RETRY:
                        return "工具执行失败次数过多，任务终止。"

                # 添加结果到会话
                self.session.add_tool_result(tool_name, result)

            else:
                self.session.add_error(f"Unknown response type: {response_type}")

        self.state = "ERROR"
        return "超过最大步数限制，任务终止。"

    def _validate_result(self, result: Dict) -> bool:
        """验证工具执行结果"""
        # 硬规则: exit code 为 0 表示成功
        return result.get("code", -1) == 0

    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "state": self.state,
            "step": self.step_count,
            "retry": self.retry_count,
            "session": self.session.summary()
        }
