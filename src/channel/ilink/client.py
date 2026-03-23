"""iLink Bot HTTP 客户端：长轮询接收消息 + 发送消息"""
import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx

from src.utils import get_logger
from .models import ILinkCredentials, ILinkMessage

logger = get_logger(__name__)

POLL_TIMEOUT = 35.0   # 长轮询超时（秒），略大于服务端 ~30s
MAX_TEXT_LEN = 2048   # 单条消息最大字符数
MAX_RECENT_IDS = 1000 # 去重集合最大容量
SESSION_EXPIRED_RET = -14


class ILinkClient:
    """iLink Bot API 异步客户端。

    使用 httpx.AsyncClient，需在 async with 上下文中使用，或手动管理生命周期。
    """

    def __init__(self, creds: ILinkCredentials, state_file: str):
        self._creds = creds
        self._state_file = Path(state_file).expanduser()
        self._uin = base64.b64encode(os.urandom(4)).decode()
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {creds.bot_token}",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": self._uin,
        }
        self._buf: str = self._load_buf()
        self._recent_ids: set[int] = set()
        self._send_counter: int = 0
        self._http: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """创建 HTTP 会话"""
        timeout = httpx.Timeout(POLL_TIMEOUT + 5, connect=10)
        self._http = httpx.AsyncClient(
            base_url=self._creds.base_url,
            headers=self._headers,
            timeout=timeout,
        )

    async def close(self) -> None:
        """关闭 HTTP 会话"""
        if self._http:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------ #
    # 消息接收
    # ------------------------------------------------------------------ #

    async def get_updates(self) -> list[ILinkMessage]:
        """长轮询获取新消息。

        返回经过去重和过滤的消息列表（只含文本消息）。
        每次调用后自动持久化 get_updates_buf。
        """
        body = {"get_updates_buf": self._buf} if self._buf else {}
        resp = await self._http.post(
            "/ilink/bot/getupdates",
            json=body,
            timeout=POLL_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        # 保存游标（即使 ret != 0 也要保存）
        new_buf = data.get("get_updates_buf", "")
        if new_buf:
            self._buf = new_buf
            self._save_buf(new_buf)

        # 会话过期
        if data.get("ret") == SESSION_EXPIRED_RET:
            raise SessionExpiredError("iLink 会话已过期，需重新登录")

        messages = []
        for msg in data.get("msgs") or []:
            # 只处理用户消息
            if msg.get("message_type") != 1:
                continue

            mid = msg.get("message_id")
            if mid and mid in self._recent_ids:
                continue  # 去重
            if mid:
                self._recent_ids.add(mid)
                if len(self._recent_ids) > MAX_RECENT_IDS:
                    # 淘汰旧的一半
                    old = list(self._recent_ids)[:MAX_RECENT_IDS // 2]
                    for x in old:
                        self._recent_ids.discard(x)

            text = self._extract_text(msg.get("item_list") or [])
            if not text:
                continue  # 暂不处理非文本消息

            messages.append(ILinkMessage(
                message_id=mid or 0,
                from_user_id=msg.get("from_user_id", ""),
                context_token=msg.get("context_token", ""),
                text=text,
                raw=msg,
            ))

        return messages

    # ------------------------------------------------------------------ #
    # 消息发送
    # ------------------------------------------------------------------ #

    async def send_message(self, to_user_id: str, context_token: str, text: str) -> None:
        """发送文本消息，超长自动分段。"""
        chunks = self._split_text(text)
        for chunk in chunks:
            self._send_counter += 1
            client_id = f"agent-{time.time_ns()}-{self._send_counter}"
            payload = {
                "msg": {
                    "from_user_id": self._creds.account_id,
                    "to_user_id": to_user_id,
                    "client_id": client_id,
                    "message_type": 2,   # BOT
                    "message_state": 2,  # FINISH
                    "context_token": context_token,
                    "item_list": [{"type": 1, "text_item": {"text": chunk}}],
                }
            }
            resp = await self._http.post("/ilink/bot/sendmessage", json=payload)
            resp.raise_for_status()
            logger.debug(f"消息已发送至 {to_user_id}，长度={len(chunk)}")

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_text(item_list: list) -> str:
        """从 item_list 提取文本内容"""
        texts = []
        for item in item_list:
            if item.get("type") == 1:
                text = item.get("text_item", {}).get("text", "")
                if text:
                    texts.append(text)
        return "\n".join(texts)

    @staticmethod
    def _split_text(text: str, max_len: int = MAX_TEXT_LEN) -> list[str]:
        """将长文本分段，优先在换行处截断"""
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            split_pos = text.rfind('\n', 0, max_len)
            if split_pos == -1:
                split_pos = max_len
            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip('\n')
        return chunks

    def _load_buf(self) -> str:
        """从磁盘加载 get_updates_buf"""
        try:
            if self._state_file.exists():
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                return data.get("get_updates_buf", "")
        except Exception as e:
            logger.warning(f"加载 iLink 状态失败: {e}")
        return ""

    def _save_buf(self, buf: str) -> None:
        """持久化 get_updates_buf"""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps({"get_updates_buf": buf}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"保存 iLink 状态失败: {e}")


class SessionExpiredError(Exception):
    """iLink 会话过期异常"""
    pass
