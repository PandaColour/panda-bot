"""智能体核心 - 统一 LLM 决策循环"""
import asyncio
from enum import Enum
from typing import Dict, Optional

from src.models import GLMProvider
from src.utils import get_logger

from .context import ContextBuilder
from .session import Session
from .task import TaskManager, TaskStatus, StepStatus
from .tools import ToolRegistry, MCPManager
from .tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from .tools.shell import ExecTool
from .tools.planning import PlanTaskTool, FinishTaskTool
from ..config.config_manager import globe_config_manager

logger = get_logger(__name__)


class AgentState(Enum):
    IDLE     = "idle"      # 等待用户输入
    THINKING = "thinking"  # LLM 决策中
    ACTING   = "acting"    # 执行工具中
    DONE     = "done"      # 任务完成
    ERROR    = "error"     # 任务失败


class AgentLoop:

    MAX_STEPS = 30
    MAX_RETRY = 3

    def __init__(self, session: Session):
        self.session          = session
        self.config           = globe_config_manager
        self.provider         = GLMProvider()
        self.context_builder  = ContextBuilder(self.config)
        self.mcp_manager      = MCPManager()
        self.task_manager     = TaskManager()
        self.tool_registry    = ToolRegistry()
        self.state            = AgentState.IDLE
        self.step_count       = 0
        self.retry_count      = 0
        logger.debug("AgentLoop 初始化完成")

    # ──────────────────────────────────────────────
    # 启动
    # ──────────────────────────────────────────────

    async def run(self):
        await self._register_tools()
        await self._runloop()

    async def _register_tools(self):
        await self.mcp_manager.load_from_config()

        for tool in [ExecTool(), ReadFileTool(), WriteFileTool(),
                     EditFileTool(), ListDirTool(),
                     PlanTaskTool(), FinishTaskTool()]:
            self.tool_registry.register(tool)

        for mcp_tool in self.mcp_manager.get_tools():
            self.tool_registry.register(mcp_tool)
            logger.debug(f"MCP 工具已注册: {mcp_tool.name}")

    # ──────────────────────────────────────────────
    # 主循环（事件驱动）
    # ──────────────────────────────────────────────

    async def _runloop(self):
        logger.info("Agent 就绪，等待输入...")
        self.state = AgentState.IDLE

        while True:
            # 阻塞等待用户输入
            user_input = await self.session.user_inputs.get()

            # 批量合并连续输入
            extra = await self.session.take_all_inputs_nowait()
            if extra:
                user_input += extra

            await self._execute_task(user_input)

    # ──────────────────────────────────────────────
    # 任务执行
    # ──────────────────────────────────────────────

    async def _execute_task(self, description: str):
        self.step_count  = 0
        self.retry_count = 0

        task = self.task_manager.create_task(description)
        self.task_manager.update_status(task.id, TaskStatus.RUNNING)
        logger.info(f"任务开始 [{task.id}]: {description}")

        await self.session.add_user_input(description)

        try:
            while self.step_count < self.MAX_STEPS:
                self.step_count += 1
                self.state = AgentState.THINKING

                # ── LLM 决策 ──────────────────────────
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
                        self.task_manager.update_status(task.id, TaskStatus.FAILED, str(e))
                        return
                    continue

                if response.content:
                    await self.session.add_agent_response(response.content)

                # LLM 自然停止（无 tool call）
                if response.finish_reason == "stop":
                    self.task_manager.update_status(task.id, TaskStatus.COMPLETED, response.content)
                    self.state = AgentState.DONE
                    logger.info(f"任务完成 [{task.id}]")
                    return

                # ── 执行 tool calls ────────────────────
                if not response.has_tool_calls:
                    continue

                self.state = AgentState.ACTING
                for tool_call in response.tool_calls:
                    logger.info(f"调用工具: {tool_call.name}")

                    result = await self.tool_registry.execute(
                        tool_call.name, tool_call.arguments
                    )
                    await self.session.add_tool_result(tool_call.id, result)

                    # finish_task → 任务结束
                    if tool_call.name == "finish_task":
                        step = self.task_manager.add_step(task.id, "finish_task")
                        self.task_manager.update_step(
                            task.id, step.id, StepStatus.COMPLETED, result
                        )
                        self.task_manager.update_status(task.id, TaskStatus.COMPLETED, result)
                        self.state = AgentState.DONE
                        logger.info(f"任务完成 [{task.id}]")
                        return

                    # 其他 tool → 记录步骤
                    step = self.task_manager.add_step(task.id, tool_call.name)
                    self.task_manager.update_step(
                        task.id, step.id, StepStatus.COMPLETED, result
                    )

            # 超出最大步骤
            self.task_manager.update_status(task.id, TaskStatus.FAILED, "超出最大步骤限制")
            logger.warning(f"任务 [{task.id}] 超出最大步骤限制")

        except Exception as e:
            logger.error(f"任务执行异常: {e}")
            self.state = AgentState.ERROR
            self.task_manager.update_status(task.id, TaskStatus.FAILED, str(e))

    # ──────────────────────────────────────────────
    # 状态查询
    # ──────────────────────────────────────────────

    def get_status(self) -> Dict:
        status = {
            "state": self.state.value,
            "step":  self.step_count,
            "retry": self.retry_count,
        }
        task = self.task_manager.get_current_task()
        if task:
            completed, total = task.get_progress()
            status["task"] = {
                "id":          task.id,
                "description": task.description,
                "status":      task.status.value,
                "progress":    f"{completed}/{total}",
            }
        return status
