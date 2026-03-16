"""智能体核心 - 控制层"""
import asyncio
from enum import Enum
from typing import Dict, List, Optional

from src.models import GLMProvider
from src.utils import get_logger

from .context import ContextBuilder
from .planner import Planner
from .session import Session
from .task import Task, TaskManager, TaskStatus, StepStatus, TaskStep
from .tools import ToolRegistry, MCPManager
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

    def __init__(self, enable_planning: bool = True):
        self.config = globe_config_manager
        self.enable_planning = enable_planning

        # 初始化组件
        self.provider = GLMProvider()
        self.context_builder = ContextBuilder(self.config)
        self.mcp_manager = MCPManager()
        self.task_manager = TaskManager()
        self.planner = Planner() if enable_planning else None

        # 状态
        self.state = AgentState.INIT
        self.step_count = 0
        self.retry_count = 0

        logger.debug(f"Agent 初始化完成 (规划模式: {enable_planning})")

    async def runloop(self, session: Session, description: Optional[str] = None):
        """执行智能体主循环

        Args:
            session: 会话对象
            description: 任务描述，如果提供则创建任务进行管理
        """
        self.state = AgentState.INIT
        self.step_count = 0
        self.retry_count = 0

        # 从配置加载 MCP 工具（提前加载，供规划使用）
        await self.mcp_manager.load_from_config()

        tool_registry = ToolRegistry()
        tool_registry.register(ExecTool())
        tool_registry.register(ReadFileTool())
        tool_registry.register(WriteFileTool())
        tool_registry.register(EditFileTool())
        tool_registry.register(ListDirTool())

        # 注册 MCP 工具
        for mcp_tool in self.mcp_manager.get_tools():
            tool_registry.register(mcp_tool)
            logger.debug(f"注册 MCP 工具: {mcp_tool.name}")

        # 创建任务（如果提供了描述）
        current_task = None
        planned_steps: List[TaskStep] = []  # 规划的步骤列表
        current_step_index = 0

        if description:
            current_task = self.task_manager.create_task(description)
            self.task_manager.update_status(current_task.id, TaskStatus.RUNNING)
            logger.info(f"Agent 开始执行任务 [{current_task.id}]: {description}")

            # 如果启用了规划，先进行任务规划
            if self.enable_planning and self.planner:
                self.state = AgentState.THINKING
                logger.info("开始任务规划 (Function Calling 模式)...")

                try:
                    # 传入 tool_registry 供 Planner 选择工具
                    plan = await asyncio.to_thread(
                        self.planner.plan,
                        description,
                        tool_registry  # 传入可用工具
                    )

                    # 将规划结果转换为步骤并添加到任务
                    if plan.steps:
                        planned_steps = plan.to_task_steps()
                        for step in planned_steps:
                            current_task.steps.append(step)
                        logger.info(f"规划完成，共 {len(planned_steps)} 个步骤:")
                        for i, step in enumerate(planned_steps, 1):
                            tool_info = f" [{step.tool}]" if step.tool else ""
                            logger.info(f"  [{i}]{tool_info} {step.description}")
                    else:
                        logger.warning("规划结果为空，将直接执行")

                except Exception as e:
                    logger.error(f"任务规划失败: {str(e)}")
                    # 规划失败时继续执行，不影响主流程
        else:
            logger.info("Agent 开始执行（无任务管理）")

        try:
            while self.step_count < self.MAX_STEPS:
                self.step_count += 1

                # 确定当前步骤
                current_step = None
                if current_task:
                    # 优先使用规划的步骤
                    if planned_steps and current_step_index < len(planned_steps):
                        current_step = planned_steps[current_step_index]
                        current_step_index += 1
                        self.task_manager.update_step(
                            current_task.id, current_step.id, StepStatus.RUNNING
                        )
                        tool_info = f" [{current_step.tool}]" if current_step.tool else ""
                        logger.info(f"执行步骤 [{current_step_index}/{len(planned_steps)}]{tool_info}: {current_step.description}")
                    else:
                        # 没有规划或规划已执行完，创建动态步骤
                        current_step = self.task_manager.add_step(
                            current_task.id,
                            f"Step {self.step_count}: 动态执行"
                        )
                        self.task_manager.update_step(
                            current_task.id, current_step.id, StepStatus.RUNNING
                        )

                # 执行步骤
                if current_step and current_step.tool:
                    # 步骤已指定工具，直接执行
                    self.state = AgentState.ACTING
                    logger.debug(f"直接执行工具: {current_step.tool}")

                    try:
                        tool_result = await tool_registry.execute(
                            current_step.tool,
                            current_step.args or {}
                        )
                        await session.add_tool_result(current_step.tool, {"result": tool_result})

                        # 标记步骤完成
                        self.task_manager.update_step(
                            current_task.id, current_step.id,
                            StepStatus.COMPLETED, tool_result
                        )

                        # 将结果添加到会话，供后续 LLM 思考
                        # 注意：直接执行模式需要观察结果决定下一步

                    except Exception as e:
                        error_msg = f"工具执行失败: {str(e)}"
                        logger.error(error_msg)
                        self.task_manager.update_step(
                            current_task.id, current_step.id,
                            StepStatus.FAILED, error_msg
                        )

                        # 尝试重规划
                        if self.enable_planning and self.planner:
                            new_plan = await asyncio.to_thread(
                                self.planner.replan,
                                current_task,
                                current_step,
                                error_msg,
                                tool_registry
                            )
                            if new_plan.steps:
                                new_steps = new_plan.to_task_steps()
                                planned_steps.extend(new_steps)
                                current_task.steps.extend(new_steps)
                                logger.info(f"重规划完成，添加了 {len(new_steps)} 个新步骤")

                        self.retry_count += 1
                        if self.retry_count > self.MAX_RETRY:
                            logger.error("重试次数超限")
                            if current_task:
                                self.task_manager.update_status(
                                    current_task.id, TaskStatus.FAILED, "重试次数超限"
                                )
                            return
                        continue

                else:
                    # 步骤未指定工具，走传统 LLM 思考路径
                    self.state = AgentState.THINKING
                    logger.debug(f"Step {self.step_count}: LLM 思考模式")

                    try:
                        context_messages = self.context_builder.build(session)
                        logger.debug(f"构建上下文完成，消息数: {len(context_messages)}")
                        response = await asyncio.to_thread(
                            self.provider.chat,
                            context_messages,
                            tool_registry.get_definitions()
                        )
                        logger.debug(f"LLM 响应: {response}")
                    except Exception as e:
                        logger.error(f"LLM 调用失败: {str(e)}")
                        self.retry_count += 1
                        if current_step:
                            self.task_manager.update_step(
                                current_task.id, current_step.id,
                                StepStatus.FAILED, str(e)
                            )
                        if self.retry_count > self.MAX_RETRY:
                            logger.error("LLM 调用重试次数超限")
                            if current_task:
                                self.task_manager.update_status(
                                    current_task.id, TaskStatus.FAILED, "LLM 调用重试次数超限"
                                )
                            return
                        continue

                    if response.content is not None:
                        await session.add_agent_response(response.content)

                    if response.finish_reason == "stop":
                        self.state = AgentState.DONE
                        if current_step:
                            self.task_manager.update_step(
                                current_task.id, current_step.id,
                                StepStatus.COMPLETED, response.content
                            )
                        if current_task:
                            self.task_manager.update_status(
                                current_task.id, TaskStatus.COMPLETED, response.content
                            )
                        logger.info(f"任务完成 [{current_task.id if current_task else 'N/A'}]")
                        return

                    # 执行工具
                    if response.has_tool_calls:
                        self.state = AgentState.ACTING
                        for tool_call in response.tool_calls:
                            print(f"{tool_call.name} {tool_call.arguments}")
                            tool_result = await tool_registry.execute(tool_call.name, tool_call.arguments)
                            await session.add_tool_result(tool_call.id, tool_result)

                        # 标记步骤完成
                        if current_step:
                            self.task_manager.update_step(
                                current_task.id, current_step.id,
                                StepStatus.COMPLETED, f"执行了 {len(response.tool_calls)} 个工具"
                            )

            # 达到最大步骤数
            if current_task:
                self.task_manager.update_status(
                    current_task.id, TaskStatus.FAILED, "达到最大步骤数限制"
                )
            logger.warning(f"达到最大步骤数限制: {self.MAX_STEPS}")

        except Exception as e:
            logger.error(f"Agent 执行异常: {str(e)}")
            if current_task:
                self.task_manager.update_status(
                    current_task.id, TaskStatus.FAILED, str(e)
                )
            raise
        finally:
            # 清理 MCP 连接
            await self.mcp_manager.close_all()

    def get_status(self) -> Dict:
        """获取当前状态"""
        status = {
            "state": self.state.value,
            "step": self.step_count,
            "retry": self.retry_count,
        }

        # 添加任务信息
        current_task = self.task_manager.get_current_task()
        if current_task:
            completed, total = current_task.get_progress()
            status["task"] = {
                "id": current_task.id,
                "description": current_task.description,
                "status": current_task.status.value,
                "progress": f"{completed}/{total}",
            }

        return status
