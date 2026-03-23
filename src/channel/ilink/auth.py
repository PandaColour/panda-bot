"""iLink Bot QR 码登录与凭据持久化"""
import json
import sys
from pathlib import Path

import httpx

from src.utils import get_logger
from .models import ILinkCredentials

logger = get_logger(__name__)

ILINK_BASE = "https://ilinkai.weixin.qq.com"
QR_POLL_INTERVAL = 3   # 秒


def load_credentials(credentials_file: str) -> ILinkCredentials | None:
    """从文件加载已保存的凭据，失败返回 None"""
    path = Path(credentials_file).expanduser()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        creds = ILinkCredentials.from_dict(data)
        logger.info(f"已加载 iLink 凭据: account_id={creds.account_id}")
        return creds
    except Exception as e:
        logger.warning(f"加载 iLink 凭据失败: {e}")
        return None


def save_credentials(creds: ILinkCredentials, credentials_file: str) -> None:
    """持久化凭据到文件"""
    path = Path(credentials_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(creds.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"iLink 凭据已保存: {path}")


async def login(credentials_file: str) -> ILinkCredentials:
    """执行 QR 码扫码登录流程，返回凭据并持久化。"""
    async with httpx.AsyncClient(timeout=60) as client:
        # 第一阶段：获取 QR 码
        resp = await client.get(f"{ILINK_BASE}/ilink/bot/get_bot_qrcode", params={"bot_type": 3})
        resp.raise_for_status()
        data = resp.json()
        if data.get("ret") != 0:
            raise RuntimeError(f"获取 QR 码失败: {data}")

        qrcode_id: str = data["qrcode"]
        qrcode_url: str = data["qrcode_img_content"]

        # 尝试用 qrcode 库在终端打印二维码
        _print_qrcode(qrcode_url)

        logger.info("请用微信扫描上方二维码...")
        print("\n请用微信扫描二维码完成登录（每 3 秒检测一次）...\n")

        # 第二阶段：轮询扫码状态
        import asyncio
        while True:
            await asyncio.sleep(QR_POLL_INTERVAL)
            poll_resp = await client.get(
                f"{ILINK_BASE}/ilink/bot/get_qrcode_status",
                params={"qrcode": qrcode_id},
            )
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()
            status = poll_data.get("status", "")

            if status == "wait":
                print("等待扫码...", end="\r")
            elif status == "scaned":
                print("已扫码，等待确认...", end="\r")
            elif status == "confirmed":
                creds = ILinkCredentials(
                    bot_token=poll_data["bot_token"],
                    account_id=poll_data["ilink_bot_id"],
                    base_url=poll_data.get("baseurl", ILINK_BASE),
                    user_id=poll_data.get("ilink_user_id", ""),
                )
                print(f"\n登录成功！account_id={creds.account_id}\n")
                logger.info(f"iLink 登录成功: account_id={creds.account_id}")
                save_credentials(creds, credentials_file)
                return creds
            elif status == "expired":
                raise RuntimeError("二维码已过期，请重新启动登录")
            else:
                logger.warning(f"未知 QR 状态: {status}")


def _print_qrcode(url: str) -> None:
    """在终端打印二维码，依赖 qrcode[pil] 库"""
    try:
        import qrcode
        qr = qrcode.QRCode()
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        print(f"[提示] 安装 qrcode[pil] 可在终端显示二维码: pip install qrcode[pil]")
        print(f"iLink 登录 URL: {url}")
    except Exception as e:
        logger.warning(f"打印二维码失败: {e}")
        print(f"iLink 登录 URL: {url}")
