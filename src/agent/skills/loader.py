"""Skill 加载器 - 扫描目录、解析 frontmatter、动态匹配"""
import re
from pathlib import Path

from .skill import Skill


class SkillLoader:
    """
    从 skills_dir 扫描子目录，每个子目录是一个 skill：
      skills/
      └── playwright-cli/
          ├── SKILL.md        # frontmatter + 主内容
          └── references/     # 补充文档（按需加载）

    SKILL.md frontmatter 格式:
    ---
    name: playwright-cli          # 可选，默认用目录名
    description: ...
    triggers: [browser, 网页, 爬虫]
    always_load: false
    priority: 10
    ---
    """

    SKILL_FILE = "SKILL.md"

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._cache: list[Skill] | None = None

    def load_all(self) -> list[Skill]:
        """扫描所有 skill 子目录（带缓存）"""
        if self._cache is not None:
            return self._cache

        skills = []
        if self.skills_dir.exists():
            for skill_dir in sorted(self.skills_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill = self._parse(skill_dir)
                if skill:
                    skills.append(skill)

        skills.sort(key=lambda s: s.priority, reverse=True)
        self._cache = skills
        return skills

    def match(self, text: str) -> list[Skill]:
        """返回 text 触发的 skill 列表（不含 always_load）"""
        return [s for s in self.load_all() if not s.always_load and s.matches(text)]

    def always_on(self) -> list[Skill]:
        """返回 always_load=true 的 skill"""
        return [s for s in self.load_all() if s.always_load]

    def get_prompt(self, text: str) -> str:
        """
        组合 always_on + 匹配到的 skill，返回注入 system prompt 的文本。
        去重，按 priority 排序。
        """
        seen: set[str] = set()
        selected: list[Skill] = []

        for skill in self.always_on() + self.match(text):
            if skill.name not in seen:
                seen.add(skill.name)
                selected.append(skill)

        if not selected:
            return ""

        parts = ["## Skills\n"]
        for skill in selected:
            parts.append(skill.content.strip())

        return "\n\n".join(parts)

    def reload(self) -> None:
        """清除缓存，下次 load_all 重新扫描"""
        self._cache = None

    # ------------------------------------------------------------------

    def _parse(self, skill_dir: Path) -> Skill | None:
        """解析单个 skill 目录"""
        skill_file = skill_dir / self.SKILL_FILE
        if not skill_file.exists():
            return None

        try:
            raw = skill_file.read_text(encoding="utf-8")
        except OSError:
            return None

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", raw, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            content = fm_match.group(2).strip()
        else:
            fm_text = ""
            content = raw.strip()

        meta = self._parse_frontmatter(fm_text)

        # 目录名作为默认 skill 名
        name = meta.get("name") or skill_dir.name

        return Skill(
            name=name,
            description=meta.get("description", ""),
            content=content,
            triggers=meta.get("triggers", []),
            always_load=meta.get("always_load", False),
            priority=int(meta.get("priority", 0)),
        )

    @staticmethod
    def _parse_frontmatter(text: str) -> dict:
        """极简 YAML 子集解析，支持 key: value / key: [a, b] / bool / int"""
        result: dict = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()

            if val.startswith("[") and val.endswith("]"):
                result[key] = [i.strip().strip("'\"") for i in val[1:-1].split(",") if i.strip()]
            elif val.lower() == "true":
                result[key] = True
            elif val.lower() == "false":
                result[key] = False
            elif val.lstrip("-").isdigit():
                result[key] = int(val)
            else:
                result[key] = val.strip("'\"")

        return result
