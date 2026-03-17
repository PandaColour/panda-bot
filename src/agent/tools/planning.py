"""规划工具 - 让 LLM 通过 tool call 来规划和结束任务"""
import json
from typing import Any

from .base import Tool


class PlanTaskTool(Tool):
    """将任务拆分为步骤，记录执行计划"""

    @property
    def name(self) -> str:
        return "plan_task"

    @property
    def description(self) -> str:
        return "将当前任务拆分为具体的执行步骤。收到用户请求后应优先调用此工具。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "执行步骤列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {
                                "type": "string",
                                "description": "要使用的工具名称"
                            },
                            "reason": {
                                "type": "string",
                                "description": "执行此步骤的原因"
                            }
                        },
                        "required": ["tool", "reason"]
                    }
                }
            },
            "required": ["steps"]
        }

    async def execute(self, steps: list) -> str:
        summary = "\n".join(
            f"  [{i+1}] {s.get('tool', '?')}: {s.get('reason', '')}"
            for i, s in enumerate(steps)
        )
        return f"计划已制定，共 {len(steps)} 个步骤：\n{summary}"


class FinishTaskTool(Tool):
    """标记任务已完成并输出最终结果"""

    @property
    def name(self) -> str:
        return "finish_task"

    @property
    def description(self) -> str:
        return "任务全部完成后调用此工具，输出最终结果给用户。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "description": "任务执行结果的总结"
                }
            },
            "required": ["result"]
        }

    async def execute(self, result: str) -> str:
        return result
