"""Channel 抽象基类"""
from abc import ABC, abstractmethod


class BaseChannel(ABC):
    """所有 IM 渠道的统一接口。

    每个 Channel 负责：
    1. 从 IM 平台接收用户消息 → session.push_user_input()
    2. 将 Agent 最终回复发送回 IM 平台 → send_reply()
    3. （可选）展示 Agent 执行过程 → on_progress()

    生命周期：
    - start(session) 通过 asyncio.gather 并发运行，不应自行返回
    - stop() 在程序退出时调用

    回调注册：start() 内部将 self.send_reply 赋给 session._reply_callback，
              将 self.on_progress 赋给 session._progress_callback（如有需要）。
    """

    channel_id: str  # 子类必须声明，如 "console", "ilink"

    @abstractmethod
    async def start(self, session) -> None:
        """启动 Channel 主循环，永不返回直到 stop() 被调用。"""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """优雅停止 Channel"""
        ...

    @abstractmethod
    async def send_reply(self, content: str) -> None:
        """将 Agent 最终文字回复发送给用户。仅由 add_agent_response 触发。"""
        ...

    async def on_progress(self, event: str, data: str) -> None:
        """Agent 执行过程事件（工具调用/结果）。默认忽略，Console 可覆盖实现。

        event: "tool_call" | "tool_result" | "error"
        data:  可读的过程描述字符串
        """
        pass
