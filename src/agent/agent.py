"""智能体核心 - 控制层"""
from enum import Enum
from typing import Dict, Optional, List

from src.models import GLMProvider
from src.utils import get_logger

from .context import ContextBuilder
from .session import Session
from .tools.shell import ExecTool
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

        exec_tool = ExecTool()
        TOOLS = [
            exec_tool.to_schema()
        ]

        loop_result = ""
        while self.step_count < self.MAX_STEPS:
            self.step_count += 1
            self.state = AgentState.THINKING
            logger.debug(f"Step {self.step_count}: 状态={self.state}")

            # 构建上下文并调用 LLM
            response = None
            try:
                context_messages = self.context_builder.build(session)
                logger.debug(f"构建上下文完成，消息数: {len(context_messages)}")
                response = self.provider.chat(context_messages, TOOLS)
                logger.debug(f"LLM 响应: {response}")
            except Exception as e:
                logger.error(f"LLM 调用失败: {str(e)}")
                self.retry_count += 1
                if self.retry_count > self.MAX_RETRY:
                    logger.error("LLM 调用重试次数超限")
                    return "LLM 调用失败次数过多，任务终止。"
                continue

            tool_calls = []
            for e in response.get("content"):
                if e.get("type") == "tool_use":
                    self.state = AgentState.ACTING
                    tool_calls.append(e)
                    tool_result = exec_tool.execute(e.get("name"), e.get("input"))
                    session.add_tool_result(e.get("name"), tool_result)
                    logger.debug(f"工具执行结果: {tool_result}")
            if len(tool_calls) > 0:
                continue
            else:
                self.state = AgentState.DONE
                for e in response:
                    if e.get("type") == "text":
                        loop_result = e.get("text")
                        session.add_agent_response(loop_result)
                break
        return loop_result

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
