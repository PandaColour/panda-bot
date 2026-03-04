"""智能体核心 - 控制层"""
from typing import Dict, Optional

from src.config import ConfigManager
from src.providers import GLMProvider
from src.session import Session
from src.agent.tools import TOOLS
from src.utils import get_logger

from .context import ContextBuilder

# 模块 logger
logger = get_logger(__name__)


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

        logger.debug("Agent 初始化完成")

    def run(self) -> str:
        """执行智能体主循环"""
        self.state = "INIT"
        logger.info("Agent 开始执行任务")

        while self.step_count < self.MAX_STEPS:
            self.step_count += 1
            self.state = "THINK"
            logger.debug(f"Step {self.step_count}: 状态={self.state}")

            # 构建上下文并调用 LLM
            try:
                messages = self.context_builder.build(self.session)
                logger.debug(f"构建上下文完成，消息数: {len(messages)}")
                response = self.provider.call(messages)
                logger.debug(f"LLM 响应类型: {response.get('type')}")
            except Exception as e:
                logger.error(f"LLM 调用失败: {str(e)}")
                self.session.add_error(f"LLM call failed: {str(e)}")
                self.retry_count += 1
                if self.retry_count > self.MAX_RETRY:
                    logger.error("LLM 调用重试次数超限")
                    return "LLM 调用失败次数过多，任务终止。"
                continue

            # 处理响应
            response_type = response.get("type")

            if response_type == "final":
                self.state = "DONE"
                logger.info(f"任务完成，步数: {self.step_count}")
                return response.get("content", "任务完成")

            elif response_type == "think":
                # 思考阶段，添加到历史继续
                logger.debug("思考阶段，继续...")
                self.session.add_message("assistant", response.get("content", ""))
                continue

            elif response_type == "tool":
                self.state = "ACT"
                tool_name = response.get("tool")
                tool_input = response.get("input", "")
                logger.info(f"执行工具: {tool_name}, 输入: {tool_input[:100]}...")

                # 验证工具
                if tool_name not in TOOLS:
                    logger.warning(f"未知工具: {tool_name}")
                    self.session.add_error(f"Unknown tool: {tool_name}")
                    continue

                # 执行工具
                try:
                    result = TOOLS[tool_name](tool_input)
                    logger.debug(f"工具执行结果: code={result.get('code')}")
                except Exception as e:
                    logger.error(f"工具执行异常: {str(e)}")
                    result = {"stdout": "", "stderr": str(e), "code": -1}

                # 验证结果
                self.state = "VALIDATE"
                if self._validate_result(result):
                    self.retry_count = 0
                else:
                    self.retry_count += 1
                    logger.warning(f"工具执行失败，重试次数: {self.retry_count}")
                    if self.retry_count > self.MAX_RETRY:
                        logger.error("工具执行重试次数超限")
                        return "工具执行失败次数过多，任务终止。"

                # 添加结果到会话
                self.session.add_tool_result(tool_name, result)

            else:
                logger.warning(f"未知响应类型: {response_type}")
                self.session.add_error(f"Unknown response type: {response_type}")

        self.state = "ERROR"
        logger.error(f"超过最大步数限制: {self.MAX_STEPS}")
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
