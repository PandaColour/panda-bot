"""智能体核心 - 控制层"""
import asyncio
from enum import Enum
from typing import Dict, Optional, List

from src.models import GLMProvider
from src.utils import get_logger

from .context import ContextBuilder
from .session import Session
from .tools import ToolRegistry
from .tools.filesystem import *
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

    async def runloop(self, session: Session):
        """执行智能体主循环（异步生成器，实时输出）"""
        self.state = AgentState.INIT
        self.step_count = 0
        self.retry_count = 0
        logger.info("Agent 开始执行任务")


        tool_registry = ToolRegistry()
        tool_registry.register(ExecTool())
        tool_registry.register(ReadFileTool())
        tool_registry.register(WriteFileTool())
        tool_registry.register(EditFileTool())
        tool_registry.register(ListDirTool())

        while self.step_count < self.MAX_STEPS:
            self.step_count += 1
            self.state = AgentState.THINKING
            logger.debug(f"Step {self.step_count}: 状态={self.state}")

            # 构建上下文并调用 LLM (在线程池中运行同步调用)
            try:
                context_messages = self.context_builder.build(session)
                logger.debug(f"构建上下文完成，消息数: {len(context_messages)}")
                response = await asyncio.to_thread(self.provider.chat, context_messages, tool_registry.get_definitions())
                logger.debug(f"LLM 响应: {response}")
            except Exception as e:
                logger.error(f"LLM 调用失败: {str(e)}")
                self.retry_count += 1
                if self.retry_count > self.MAX_RETRY:
                    logger.error("LLM 调用重试次数超限")
                    return
                continue

            if response.content is not None:
                await session.add_agent_response(response.content)

            if response.finish_reason == "stop":
                self.state = AgentState.DONE
                return

            # 执行工具
            if response.has_tool_calls:
                self.state = AgentState.ACTING
                for tool_call in response.tool_calls:
                    print(f"{tool_call.name} {tool_call.arguments}")
                    tool_result = await tool_registry.execute(tool_call.name, tool_call.arguments)
                    await session.add_tool_result(tool_call.id, tool_result)


    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "state": self.state,
            "step": self.step_count,
            "retry": self.retry_count,
        }
