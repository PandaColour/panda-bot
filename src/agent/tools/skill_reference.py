"""Skill reference 按需加载工具"""
from pathlib import Path
from typing import Any

from .base import Tool

# skills 目录的绝对路径
_SKILLS_DIR = Path(__file__).parent.parent / "prompts" / "skills"


class ReadReferenceTool(Tool):
    """
    按需读取 skill 的 reference 文档。
    当 skill 内容中提到 references/ 下的文件时，调用此工具获取详细内容。
    """

    @property
    def name(self) -> str:
        return "read_reference"

    @property
    def description(self) -> str:
        return (
            "Read a reference document from a skill's references/ directory. "
            "Use this when a skill mentions a reference file and you need its detailed content. "
            "Example: skill='playwright-cli', reference='request-mocking'"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "Skill directory name, e.g. 'playwright-cli'"
                },
                "reference": {
                    "type": "string",
                    "description": "Reference file name without extension, e.g. 'request-mocking'"
                }
            },
            "required": ["skill", "reference"]
        }

    async def execute(self, skill: str, reference: str, **kwargs: Any) -> str:
        # 限定路径在 skills 目录内，防止路径穿越
        ref_path = (_SKILLS_DIR / skill / "references" / reference).with_suffix(".md")

        try:
            resolved = ref_path.resolve()
            skills_resolved = _SKILLS_DIR.resolve()
            if not str(resolved).startswith(str(skills_resolved)):
                return "Error: path traversal detected"
        except Exception:
            return "Error: invalid path"

        if not ref_path.exists():
            # 列出可用的 references 帮助 LLM 纠正
            ref_dir = _SKILLS_DIR / skill / "references"
            if ref_dir.exists():
                available = [p.stem for p in ref_dir.glob("*.md")]
                return f"Error: '{reference}' not found. Available: {', '.join(available)}"
            return f"Error: skill '{skill}' has no references directory"

        try:
            return ref_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            return f"Error reading reference: {e}"
