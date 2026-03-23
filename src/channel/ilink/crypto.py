"""AES-128-ECB 媒体文件解密（可选）"""
import base64

from src.utils import get_logger

logger = get_logger(__name__)


def decrypt_cdn_media(encrypted_bytes: bytes, aes_key_b64: str) -> bytes:
    """解密 iLink CDN 媒体文件。

    aes_key_b64 有两种格式：
    1. base64(原始 16 字节) → 直接用
    2. base64(32 位 hex 字符串) → 先解码为字符串，再 hex decode
    """
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
    except ImportError:
        raise ImportError("解密媒体文件需要安装 pycryptodome: pip install pycryptodome")

    raw = base64.b64decode(aes_key_b64)
    if len(raw) == 16:
        aes_key = raw
    else:
        hex_str = raw.decode("utf-8")
        aes_key = bytes.fromhex(hex_str)

    cipher = AES.new(aes_key, AES.MODE_ECB)
    decrypted = cipher.decrypt(encrypted_bytes)
    return unpad(decrypted, 16)


def detect_mime_type(data: bytes) -> str:
    """根据文件头猜测图片 MIME 类型"""
    if data[:2] == b'\x89\x50':
        return "image/png"
    if data[:2] == b'\xff\xd8':
        return "image/jpeg"
    if data[:2] == b'\x47\x49':
        return "image/gif"
    if data[:2] == b'\x52\x49':
        return "image/webp"
    if data[:2] == b'\x42\x4d':
        return "image/bmp"
    return "image/jpeg"


async def download_image_as_base64(cdn_media: dict) -> str | None:
    """下载并解密 CDN 媒体文件，返回 data URI 字符串，失败返回 None"""
    import base64 as b64
    import httpx

    try:
        url = f"https://novac2c.cdn.weixin.qq.com/c2c?{cdn_media['encrypt_query_param']}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        decrypted = decrypt_cdn_media(resp.content, cdn_media["aes_key"])
        mime = detect_mime_type(decrypted)
        b64_data = b64.b64encode(decrypted).decode()
        return f"data:{mime};base64,{b64_data}"
    except Exception as e:
        logger.error(f"图片下载失败: {e}")
        return None
