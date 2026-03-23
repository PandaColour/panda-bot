"""iLink Bot 数据模型"""
from dataclasses import dataclass, field


@dataclass
class ILinkCredentials:
    """iLink Bot 登录凭据（扫码后持久化）"""
    bot_token: str
    account_id: str   # ilink_bot_id，发消息时作为 from_user_id
    base_url: str     # 默认 https://ilinkai.weixin.qq.com
    user_id: str      # 绑定的微信用户 ID（ilink_user_id）

    def to_dict(self) -> dict:
        return {
            "bot_token": self.bot_token,
            "account_id": self.account_id,
            "base_url": self.base_url,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ILinkCredentials":
        return cls(
            bot_token=data["bot_token"],
            account_id=data["account_id"],
            base_url=data.get("base_url", "https://ilinkai.weixin.qq.com"),
            user_id=data.get("user_id", ""),
        )


@dataclass
class ILinkMessage:
    """从 getupdates 解析出的单条用户消息"""
    message_id: int
    from_user_id: str     # 发送者微信 ID
    context_token: str    # 回复时必须原样携带
    text: str             # 已提取的文本内容
    raw: dict = field(default_factory=dict)
