"""Shell execution tool."""

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .base import Tool


class ExecTool(Tool):
    """Tool to execute shell commands."""
    
    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
    ):
        self.timeout = timeout
        self.working_dir = working_dir
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf, rm -fr
            r"\bdel\s+/[fq]\b",              # del /f, del /q
            r"\brmdir\s+/s\b",               # rmdir /s
            r"(?:^|[;&|]\s*)format\b",       # format (as standalone command only)
            r"\b(mkfs|diskpart)\b",          # disk operations
            r"\bdd\s+if=",                   # dd
            r">\s*/dev/sd",                  # write to disk
            r"\b(shutdown|reboot|poweroff)\b",  # system power
            r":\(\)\s*\{.*\};\s*:",          # fork bomb
        ]
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
        self.path_append = path_append
    
    @property
    def name(self) -> str:
        return "exec"
    
    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use with caution."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command"
                }
            },
            "required": ["command"]
        }
    
    def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error

        env = os.environ.copy()
        if self.path_append:
            env["PATH"] = env.get("PATH", "") + os.pathsep + self.path_append

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                cwd=cwd,
                env=env,
                timeout=self.timeout,
            )

            output_parts = []

            if result.stdout:
                output_parts.append(result.stdout.decode("utf-8", errors="replace"))

            if result.stderr:
                stderr_text = result.stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            if result.returncode != 0:
                output_parts.append(f"\nExit code: {result.returncode}")

            output = "\n".join(output_parts) if output_parts else "(no output)"

            # Truncate very long output
            max_len = 10000
            if len(output) > max_len:
                output = output[:max_len] + f"\n... (truncated, {len(output) - max_len} more chars)"

            return output

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {self.timeout} seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Best-effort safety guard for potentially destructive commands."""
        cmd = command.strip()
        lower = cmd.lower()

        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            cwd_path = Path(cwd).resolve()

            win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
            # Only match absolute paths — avoid false positives on relative
            # paths like ".venv/bin/python" where "/bin/python" would be
            # incorrectly extracted by the old pattern.
            posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)

            for raw in win_paths + posix_paths:
                try:
                    p = Path(raw.strip()).resolve()
                except Exception:
                    continue
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None
