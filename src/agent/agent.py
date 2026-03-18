"""智能体核心 - 统一 LLM 决策循环"""
import asyncio
from enum import Enum
from typing import Dict

from src.models import ProviderFactory
from src.utils import get_logger

from .context import ContextBuilder
from .session import Session
from .tools import ToolRegistry, MCPManager
from .tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from .tools.shell import ExecTool
from .tools.python3 import Python3Tool
from .tools.planning import PlanTaskTool, FinishTaskTool
from ..config.config_manager import globe_config_manager

logger = get_logger(__name__)


class AgentState(Enum):
    IDLE     = "idle"
    THINKING = "thinking"
    ACTING   = "acting"
    DONE     = "done"
    ERROR    = "error"


class AgentLoop:

    MAX_STEPS = 30
    MAX_RETRY = 3

    def __init__(self, session: Session):
        self.session         = session
        self.provider        = ProviderFactory.create_provider()
        self.context_builder = ContextBuilder(globe_config_manager)
        self.mcp_manager     = MCPManager()
        self.tool_registry   = ToolRegistry()
        self.state           = AgentState.IDLE
        self.step_count      = 0
        self.retry_count     = 0
        logger.debug("AgentLoop 初始化完成")

    async def run(self):
        await self._register_tools()
        await self._runloop()

    async def _register_tools(self):
        await self.mcp_manager.load_from_config()
        for tool in [ExecTool(), Python3Tool(), ReadFileTool(), WriteFileTool(),
                     EditFileTool(), ListDirTool(),
                     PlanTaskTool(), FinishTaskTool()]:
            self.tool_registry.register(tool)
        for mcp_tool in self.mcp_manager.get_tools():
            self.tool_registry.register(mcp_tool)
            logger.debug(f"MCP 工具已注册: {mcp_tool.name}")

    async def _runloop(self):
        logger.info("Agent 就绪，等待输入...")
        self.state = AgentState.IDLE
        while True:
            user_input = await self.session.user_inputs.get()
            extra = await self.session.take_all_inputs_nowait()
            if extra:
                user_input += extra
            await self._execute_task(user_input)

    async def _execute_task(self, task: str):
        self.step_count  = 0
        self.retry_count = 0
        self.state       = AgentState.THINKING
        logger.info(f"任务开始: {task}")

        await self.session.add_user_input(task)

        try:
            while self.step_count < self.MAX_STEPS:
                self.step_count += 1

                try:
                    response = await asyncio.to_thread(
                        self.provider.chat,
                        self.context_builder.build(self.session),
                        self.tool_registry.get_definitions()
                    )
                except Exception as e:
                    logger.error(f"LLM 调用失败: {e}")
                    self.retry_count += 1
                    if self.retry_count > self.MAX_RETRY:
                        self.state = AgentState.ERROR
                        return
                    continue

                if response.finish_reason == "stop" or not response.has_tool_calls:
                    if response.content:
                        await self.session.add_agent_response(response.content)
                    if response.finish_reason == "stop":
                        self.state = AgentState.DONE
                        logger.info("任务完成")
                        return
                    continue

                self.state = AgentState.ACTING
                await self.session.add_assistant_tool_calls(response.content, response.tool_calls)
                for tool_call in response.tool_calls:
                    logger.info(f"调用工具: {tool_call.name}")
                    result = await self.tool_registry.execute(
                        tool_call.name, tool_call.arguments
                    )
                    await self.session.add_tool_result(tool_call.id, result)

                    if tool_call.name == "finish_task":
                        self.state = AgentState.DONE
                        logger.info("任务完成")
                        return

            logger.warning("超出最大步骤限制")
            self.state = AgentState.ERROR

        except Exception as e:
            logger.error(f"任务执行异常: {e}")
            self.state = AgentState.ERROR

    def get_status(self) -> Dict:
        return {
            "state": self.state.value,
            "step":  self.step_count,
            "retry": self.retry_count,
        }
