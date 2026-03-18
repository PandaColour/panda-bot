"""Skill 数据结构"""
from dataclasses import dataclass, field


@dataclass
class Skill:
    name: str
    description: str
    content: str                    # skill 的 markdown 正文
    triggers: list[str] = field(default_factory=list)
    always_load: bool = False
    priority: int = 0

    def matches(self, text: str) -> bool:
        """判断 text 是否触发该 skill（关键词匹配，不区分大小写）"""
        lower = text.lower()
        return any(t.lower() in lower for t in self.triggers)
