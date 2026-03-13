"""智能体核心 - 控制层"""
import asyncio
import os
from enum import Enum
from typing import Dict, Optional, List

from src.models import GLMProvider
from src.utils import get_logger

from .context import ContextBuilder
from .session import Session
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

    def __init__(self):
        self.config = globe_config_manager

        # 初始化组件
        self.provider = GLMProvider()
        self.context_builder = ContextBuilder(self.config)
        self.mcp_manager = MCPManager()

        # 状态
        self.state = AgentState.INIT
        self.step_count = 0
        self.retry_count = 0

        logger.debug("Agent 初始化完成")

    async def _load_mcp_tools(self) -> None:
        """加载 MCP 工具"""
        # Playwright MCP - Extension 模式连接真实浏览器
        playwright_token = self.config.get("playwright.token", None)

        if playwright_token:
            logger.info("正在加载 Playwright MCP (Extension 模式)...")
            tools = await self.mcp_manager.add_stdio_server(
                "playwright",
                "npx @playwright/mcp@latest --extension",
                env={"PLAYWRIGHT_MCP_EXTENSION_TOKEN": playwright_token}
            )

            if not tools:
                logger.warning(
                    "Playwright MCP 加载失败。请检查:\n"
                    "  1. Chrome 扩展 Playwright MCP Bridge 是否已安装并启用\n"
                    "  2. 扩展中的 Token 是否与环境变量匹配\n"
                    "  3. 尝试重启 Chrome 浏览器"
                )
        else:
            logger.warning(
                "未设置 PLAYWRIGHT_MCP_EXTENSION_TOKEN，跳过 Playwright MCP。\n"
                "请在扩展中获取 Token 并设置环境变量。"
            )

        # 可以在这里添加更多 MCP 服务器
        # await self.mcp_manager.add_http_server("ftd", "https://example.com/mcp")

    async def runloop(self, session: Session):
        """执行智能体主循环（异步生成器，实时输出）"""
        self.state = AgentState.INIT
        self.step_count = 0
        self.retry_count = 0
        logger.info("Agent 开始执行任务")

        # 加载 MCP 工具
        await self._load_mcp_tools()

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

        # 清理 MCP 连接
        await self.mcp_manager.close_all()


    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "state": self.state,
            "step": self.step_count,
            "retry": self.retry_count,
        }
