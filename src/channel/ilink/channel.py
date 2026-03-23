"""iLink Channel 主体"""
import asyncio
from typing import Optional

from src.utils import get_logger
from ..base import BaseChannel
from .auth import load_credentials, login
from .client import ILinkClient, SessionExpiredError
from .models import ILinkMessage

logger = get_logger(__name__)

# 轮询失败退避策略
BACKOFF_SHORT = 3    # 失败次数 < 3 时等待秒数
BACKOFF_LONG  = 30   # 失败次数 >= 3 时等待秒数
SESSION_EXPIRED_WAIT = 3600  # 会话过期后等待秒数（1 小时）


class ILinkChannel(BaseChannel):
    """企业微信 iLink Bot Channel。

    通过长轮询接收微信用户消息，将回复通过 sendmessage 接口发送。
    单账号模式：只登录一个机器人账号，记录最新消息的发送者和 context_token 用于回复。
    """

    channel_id = "ilink"

    def __init__(self, config: dict = None):
        self._config = config or {}
        self._credentials_file: str = self._config.get(
            "credentials_file", "~/.panda-bot/ilink_credentials.json"
        )
        self._state_file: str = self._config.get(
            "state_file", "~/.panda-bot/ilink_state.json"
        )
        self._client: Optional[ILinkClient] = None
        self._running: bool = False
        # 最近一条消息的发送者信息（用于回复）
        self._last_from_user_id: str = ""
        self._last_context_token: str = ""

    async def start(self, session) -> None:
        """启动 iLink Channel：登录 → 注册回调 → 长轮询"""
        # 1. 登录（优先加载已保存凭据，否则扫码）
        creds = load_credentials(self._credentials_file)
        if creds is None:
            logger.info("未找到 iLink 凭据，启动扫码登录...")
            creds = await login(self._credentials_file)

        # 2. 初始化 HTTP 客户端
        self._client = ILinkClient(creds=creds, state_file=self._state_file)
        await self._client.start()

        # 3. 注册回复回调
        session._reply_callback = self.send_reply

        self._running = True
        logger.info(f"ILinkChannel 已启动，account_id={creds.account_id}")

        # 4. 长轮询循环
        try:
            await self._poll_loop(session)
        finally:
            await self._client.close()

    async def stop(self) -> None:
        self._running = False

    async def send_reply(self, content: str) -> None:
        """将 Agent 回复发送给最近一条消息的发送者"""
        if not self._client:
            logger.error("iLink 客户端未初始化，无法发送消息")
            return
        if not self._last_from_user_id or not self._last_context_token:
            logger.warning("没有可用的消息上下文，跳过发送")
            return
        try:
            await self._client.send_message(
                to_user_id=self._last_from_user_id,
                context_token=self._last_context_token,
                text=content,
            )
        except Exception as e:
            logger.error(f"发送消息失败: {e}")

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    async def _poll_loop(self, session) -> None:
        """长轮询主循环，带指数退避"""
        failures = 0
        while self._running:
            try:
                messages = await self._client.get_updates()
                failures = 0  # 成功后重置

                for msg in messages:
                    await self._handle_message(msg, session)

            except SessionExpiredError:
                logger.error(f"iLink 会话已过期，{SESSION_EXPIRED_WAIT // 3600} 小时后重试")
                print(f"\n[iLink] 会话已过期，请重新扫码登录后重启程序\n")
                await asyncio.sleep(SESSION_EXPIRED_WAIT)

            except asyncio.TimeoutError:
                # 35s 长轮询超时是正常现象，直接继续
                pass

            except Exception as e:
                failures += 1
                backoff = BACKOFF_LONG if failures >= 3 else BACKOFF_SHORT
                logger.warning(f"[iLink] 轮询失败 ({failures}次): {e}，等待 {backoff}s")
                await asyncio.sleep(backoff)

    async def _handle_message(self, msg: ILinkMessage, session) -> None:
        """处理单条消息"""
        logger.info(f"[iLink] 收到消息 from={msg.from_user_id}: {msg.text[:50]}")

        # 保存最新上下文（用于回复）
        self._last_from_user_id = msg.from_user_id
        self._last_context_token = msg.context_token

        # 推送到 Agent
        await session.push_user_input(msg.text)
