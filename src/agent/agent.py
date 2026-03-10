"""智能体核心 - 控制层"""
from enum import Enum
from typing import Dict, Optional, List

from src.models import GLMProvider
from src.utils import get_logger

from .context import ContextBuilder
from .session import Session
from ..config.config_manager import globe_config_manager

# 模块 logger
logger = get_logger(__name__)



# 状态机: INIT → THINK → ACTING → VALIDATE → DONE / ERROR
class AgentState(Enum):
    IDLE = "idle"           # 等待用户输入
    INIT = "init"           # 初始化中
    THINKING = "thinking"   # LLM 思考中
    ACTING = "acting"       # 执行工具中
    PAUSED = "paused"       # 已暂停
    DONE = "done"           # 任务完成
    ERROR = "error"         # 任务失败

class AgentLoop:

    MAX_STEPS = 30
    MAX_RETRY = 3

    def __init__(self):
        self.config = globe_config_manager

        # 初始化组件
        self.provider = GLMProvider()
        self.context_builder = ContextBuilder(self.config)

        # 状态
        self.state = AgentState.INIT
        self.step_count = 0
        self.retry_count = 0

        logger.debug("Agent 初始化完成")

    def runloop(self, session: Session) -> str:
        """执行智能体主循环"""
        self.state = AgentState.INIT
        self.step_count = 0
        self.retry_count = 0
        logger.info("Agent 开始执行任务")

        while self.step_count < self.MAX_STEPS:
            self.step_count += 1
            self.state = AgentState.THINKING
            logger.debug(f"Step {self.step_count}: 状态={self.state}")

            # 构建上下文并调用 LLM
            try:
                context_messages = self.context_builder.build(session)
                logger.debug(f"构建上下文完成，消息数: {len(context_messages)}")
                response = self.provider.chat(context_messages)
                logger.debug(f"LLM 响应: {response}")
            except Exception as e:
                logger.error(f"LLM 调用失败: {str(e)}")
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
                self.state = AgentState.ACTING
                tool_name = response.get("tool")
                tool_input = response.get("input", "")
                logger.info(f"执行工具: {tool_name}, 输入: {tool_input}...")

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
            else:
                logger.warning(f"未知响应类型: {response_type}")

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
        }
