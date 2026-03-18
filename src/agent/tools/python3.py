"""Python3 code execution tool."""

import asyncio
import sys
import tempfile
import os
from pathlib import Path
from typing import Any

from .base import Tool


class Python3Tool(Tool):
    """Execute Python3 code and return the output."""

    def __init__(self, timeout: int = 30, working_dir: str | None = None):
        self.timeout = timeout
        self.working_dir = working_dir

    @property
    def name(self) -> str:
        return "python3"

    @property
    def description(self) -> str:
        return (
            "Execute Python3 code and return stdout/stderr output. "
            "Use for calculations, data processing, file operations, and any task "
            "better expressed as a Python script than a shell command."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python3 source code to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the script"
                }
            },
            "required": ["code"]
        }

    async def execute(self, code: str, working_dir: str | None = None, **kwargs: Any) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()
        python = sys.executable

        # 写入临时文件，避免多行代码在 -c 参数中的转义问题
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                python, tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return f"Error: Python execution timed out after {self.timeout} seconds"

            output_parts = []
            if stdout:
                output_parts.append(stdout.decode(errors="replace"))
            if stderr and stderr.strip():
                output_parts.append(f"STDERR:\n{stderr.decode(errors='replace')}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"

            return result

        except Exception as e:
            return f"Error executing Python code: {str(e)}"
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
