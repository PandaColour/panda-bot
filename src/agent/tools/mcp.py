"""MCP (Model Context Protocol) integration for Agent.

支持连接到 MCP 服务器并动态加载工具到 ToolRegistry。

支持两种连接方式：
1. Stdio - 通过命令行启动 MCP 服务器 (如 npx @playwright/mcp)
2. HTTP - 连接到 HTTP MCP 服务器

使用方式：
    from src.agent.tools.mcp import MCPManager

    manager = MCPManager()

    # 添加 stdio MCP 服务器
    await manager.add_stdio_server(
        "playwright",
        "npx @playwright/mcp@latest --extension",
        env={"PLAYWRIGHT_MCP_EXTENSION_TOKEN": "xxx"}
    )

    # 添加 HTTP MCP 服务器
    await manager.add_http_server("ftd", "https://example.com/mcp")

    # 获取所有 MCP 工具并注册到 ToolRegistry
    for tool in manager.get_tools():
        registry.register(tool)
"""

import asyncio
import json
import os
import re
import traceback
from abc import ABC, abstractmethod
from typing import Any, Optional
import aiohttp

from .base import Tool
from src.utils import get_logger
from ...config.config_manager import globe_config_manager

logger = get_logger(__name__)


class MCPConnection(ABC):
    """MCP 连接基类"""

    def __init__(self, name: str):
        self.name = name
        self._initialized = False
        self._request_id = 0
        self._tools: list[dict] = []

    @abstractmethod
    async def start(self) -> None:
        """启动连接并初始化协议"""
        pass

    @abstractmethod
    async def send_request(self, method: str, params: dict = None) -> dict:
        """发送 JSON-RPC 请求"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        pass

    async def initialize(self) -> None:
        """执行 MCP 协议握手"""
        result = await self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "panda-bot", "version": "1.0.0"}
        })
        logger.debug(f"[{self.name}] Initialize result: {result}")

        await self.send_notification("notifications/initialized")

        tools_result = await self.send_request("tools/list", {})
        self._tools = tools_result.get("tools", [])
        logger.info(f"[{self.name}] 已加载 {len(self._tools)} 个 MCP 工具")
        self._initialized = True

    async def send_notification(self, method: str, params: dict = None) -> None:
        """发送 JSON-RPC 通知（无响应）"""
        pass  # 子类实现

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用 MCP 工具"""
        if not self._initialized:
            await self.start()

        result = await self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {}
        })
        return self._parse_result(result)

    def _parse_result(self, result: dict) -> str:
        """解析 MCP 工具返回结果"""
        if isinstance(result, dict) and "content" in result:
            texts = []
            for item in result.get("content", []):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif item.get("type") == "image":
                    texts.append(f"[Image: {item.get('mimeType', 'unknown')}]")
                elif item.get("type") == "resource":
                    texts.append(f"[Resource: {item.get('resource', {}).get('uri', 'unknown')}]")
            return "\n".join(texts) if texts else str(result)
        return str(result)

    @property
    def tools(self) -> list[dict]:
        """获取工具定义列表"""
        return self._tools


class StdioMCPConnection(MCPConnection):
    """Stdio MCP 连接 - 通过子进程通信"""

    def __init__(self, name: str, command: str, env: dict = None):
        super().__init__(name)
        self.command = command
        self.env = env or {}
        self._process: Optional[asyncio.subprocess.Process] = None

    async def start(self) -> None:
        """启动子进程"""
        if self._process is not None:
            return

        env = os.environ.copy()
        env.update(self.env)

        # Windows 上 npx 是 .cmd 文件，需要用 shell=True
        self._process = await asyncio.create_subprocess_shell(
            self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        await asyncio.sleep(2)
        logger.info(f"[{self.name}] 已启动 MCP 进程: {self.command}")
        await self.initialize()

    async def send_request(self, method: str, params: dict = None) -> dict:
        """发送请求并等待响应"""
        if not self._process:
            raise RuntimeError(f"[{self.name}] 连接未启动")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }

        line = json.dumps(request) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        # 读取响应，跳过非 JSON 行（日志输出等）
        for _ in range(50):
            response_line = await asyncio.wait_for(
                self._process.stdout.readline(), timeout=60.0
            )
            if not response_line:
                raise RuntimeError(f"[{self.name}] 连接已断开（EOF）")

            line_text = response_line.decode().strip()
            if not line_text:
                continue

            try:
                response = json.loads(line_text)
            except json.JSONDecodeError:
                logger.debug(f"[{self.name}] 跳过非 JSON 行: {line_text[:100]}")
                continue

            if "error" in response:
                error = response["error"]
                msg = error.get("message", error) if isinstance(error, dict) else error
                raise RuntimeError(f"[{self.name}] MCP 错误: {msg}")

            return response.get("result", {})

        raise RuntimeError(f"[{self.name}] 未收到有效 JSON 响应")

    async def send_notification(self, method: str, params: dict = None) -> None:
        if not self._process:
            return
        notification = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._process.stdin.write((json.dumps(notification) + "\n").encode())
        await self._process.stdin.drain()

    async def close(self) -> None:
        if not self._process:
            return
        try:
            self._request_id += 1
            shutdown = {"jsonrpc": "2.0", "id": self._request_id, "method": "shutdown"}
            self._process.stdin.write((json.dumps(shutdown) + "\n").encode())
            await self._process.stdin.drain()
            await asyncio.sleep(0.2)
        except Exception:
            pass

        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=3)
        except asyncio.TimeoutError:
            self._process.kill()

        self._process = None
        self._initialized = False
        logger.info(f"[{self.name}] 已关闭连接")


class HTTPMCPConnection(MCPConnection):
    """HTTP MCP 连接 - 通过 HTTP/SSE 通信"""

    def __init__(self, name: str, url: str, headers: dict = None):
        super().__init__(name)
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        if self._session is not None:
            return
        self._session = aiohttp.ClientSession(headers=self.headers)
        logger.info(f"[{self.name}] 已连接到 HTTP MCP: {self.url}")
        await self.initialize()

    async def send_request(self, method: str, params: dict = None) -> dict:
        if not self._session:
            raise RuntimeError(f"[{self.name}] 连接未启动")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }

        async with self._session.post(
            self.url,
            json=request,
            headers={"Content-Type": "application/json"}
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise RuntimeError(f"[{self.name}] HTTP {response.status}: {text}")
            data = await response.json()

        if "error" in data:
            error = data["error"]
            msg = error.get("message", error) if isinstance(error, dict) else error
            raise RuntimeError(f"[{self.name}] MCP 错误: {msg}")

        return data.get("result", {})

    async def send_notification(self, method: str, params: dict = None) -> None:
        if not self._session:
            return
        notification = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        try:
            await self._session.post(
                self.url,
                json=notification,
                headers={"Content-Type": "application/json"}
            )
        except Exception:
            pass  # 通知不需要确认

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
            self._initialized = False
            logger.info(f"[{self.name}] 已关闭连接")


class MCPTool(Tool):
    """MCP 工具包装器 - 将 MCP 工具包装为 Agent Tool"""

    def __init__(self, connection: MCPConnection, tool_def: dict):
        self._connection = connection
        self._name = tool_def.get("name", "unknown")
        self._description = tool_def.get("description", "")
        self._parameters = tool_def.get("inputSchema", {})

    @property
    def name(self) -> str:
        return f"mcp_{self._name}"

    @property
    def description(self) -> str:
        return f"[MCP:{self._connection.name}] {self._description}"

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        try:
            return await self._connection.call_tool(self._name, kwargs)
        except Exception as e:
            return f"Error: {str(e)}"


class MCPManager:
    """MCP 管理器 - 管理多个 MCP 连接和工具"""

    def __init__(self):
        self._connections: dict[str, MCPConnection] = {}
        self._tools: list[MCPTool] = []
        self._config = globe_config_manager

    async def load_from_config(self) -> None:
        """从配置文件自动加载 MCP 服务器"""
        mcp_servers = self._config.get("mcp_servers", {})
        if not mcp_servers:
            logger.warning("未配置任何 MCP 服务器")
            return

        for name, server_config in mcp_servers.items():
            if not server_config.get("enabled", True):
                logger.debug(f"[{name}] 已禁用，跳过")
                continue

            server_type = server_config.get("type", "stdio")
            try:
                if server_type == "stdio":
                    command = server_config.get("command")
                    if not command:
                        logger.error(f"[{name}] 缺少 command 配置")
                        continue
                    env = self._resolve_env_vars(server_config.get("env", {}))
                    logger.info(f"[{name}] 正在加载 stdio MCP: {command}")
                    await self.add_stdio_server(name, command, env)

                elif server_type == "http":
                    url = server_config.get("url")
                    if not url:
                        logger.error(f"[{name}] 缺少 url 配置")
                        continue
                    logger.info(f"[{name}] 正在加载 HTTP MCP: {url}")
                    await self.add_http_server(name, url, server_config.get("headers", {}))

                else:
                    logger.warning(f"[{name}] 未知的 MCP 类型: {server_type}")

            except Exception as e:
                logger.error(f"[{name}] 加载失败: {e}")

    def _resolve_env_vars(self, env: dict) -> dict:
        """解析环境变量中的配置引用，如 ${playwright.token}"""
        resolved = {}
        pattern = re.compile(r'\$\{([^}]+)\}')
        for key, value in env.items():
            if isinstance(value, str):
                def replace_ref(match):
                    config_value = self._config.get(match.group(1))
                    if config_value is None:
                        logger.warning(f"配置引用未找到: {match.group(1)}")
                        return match.group(0)
                    return str(config_value)
                resolved[key] = pattern.sub(replace_ref, value)
            else:
                resolved[key] = value
        return resolved

    async def _add_connection(self, name: str, conn: MCPConnection) -> list["MCPTool"]:
        """启动连接并将其工具加入注册表，返回加载的工具列表"""
        if name in self._connections:
            logger.warning(f"[{name}] 连接已存在，跳过")
            return []
        try:
            await conn.start()
            self._connections[name] = conn
            tools = [MCPTool(conn, td) for td in conn.tools]
            self._tools.extend(tools)
            logger.info(f"[{name}] 加载成功，共 {len(tools)} 个工具: {[t.name for t in tools]}")
            return tools
        except Exception as e:
            logger.error(f"[{name}] 连接失败: {e}")
            logger.debug(f"[{name}] 错误详情:\n{traceback.format_exc()}")
            await conn.close()
            return []

    async def add_stdio_server(self, name: str, command: str, env: dict = None) -> list["MCPTool"]:
        return await self._add_connection(name, StdioMCPConnection(name, command, env))

    async def add_http_server(self, name: str, url: str, headers: dict = None) -> list["MCPTool"]:
        return await self._add_connection(name, HTTPMCPConnection(name, url, headers))

    def get_tools(self) -> list["MCPTool"]:
        """获取所有 MCP 工具"""
        return self._tools.copy()

    async def close_all(self) -> None:
        """关闭所有连接"""
        for name, conn in self._connections.items():
            try:
                await conn.close()
            except Exception as e:
                logger.error(f"[{name}] 关闭失败: {e}")
        self._connections.clear()
        self._tools.clear()

    @property
    def connections(self) -> dict[str, MCPConnection]:
        return self._connections.copy()

    def __len__(self) -> int:
        return len(self._tools)
