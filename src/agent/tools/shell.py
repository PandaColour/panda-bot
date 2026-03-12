"""Shell execution tool."""

import asyncio
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .base import Tool

if TYPE_CHECKING:
    from src.main import InputListener

# 独立的线程池，避免与 InputListener 等其他 to_thread 调用竞争
_shell_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="shell_")


def _get_input_listener() -> "InputListener | None":
    """获取全局 InputListener 实例（延迟导入避免循环依赖）"""
    try:
        from src.main import get_input_listener
        return get_input_listener()
    except ImportError:
        return None


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

    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        # 预处理：修复 LLM 错误转义的引号
        command = self._fix_escaped_quotes(command)

        cwd = working_dir or self.working_dir or os.getcwd()
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error

        env = os.environ.copy()
        if self.path_append:
            env["PATH"] = env.get("PATH", "") + os.pathsep + self.path_append

        listener = _get_input_listener()
        try:
            # 暂停 InputListener，避免 Windows 控制台 stdin 死锁
            if listener:
                listener.pause()

            # 使用 subprocess.run() 在独立线程池中执行
            # 避免与 InputListener 的 input() 产生 Windows 控制台冲突
            print(f"[DEBUG] 开始执行命令: {command[:100]}...")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                _shell_executor,
                lambda: subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    cwd=cwd,
                    env=env,
                    timeout=self.timeout,
                )
            )
            print(f"[DEBUG] 命令执行完成, returncode={result.returncode}")

            output_parts = []

            if result.stdout:
                print(f"[DEBUG] stdout 大小: {len(result.stdout)} bytes")
                stdout_text = result.stdout.decode(errors="replace")
                print(f"[DEBUG] 解码完成")
                output_parts.append(stdout_text)

            if result.stderr and result.stderr.strip():
                stderr_text = result.stderr.decode(errors="replace")
                output_parts.append(f"STDERR:\n{stderr_text}")

            if result.returncode != 0:
                output_parts.append(f"\nExit code: {result.returncode}")

            result_str = "\n".join(output_parts) if output_parts else "(no output)"

            # Truncate very long output
            max_len = 10000
            if len(result_str) > max_len:
                result_str = result_str[:max_len] + f"\n... (truncated, {len(result_str) - max_len} more chars)"

            return result_str

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {self.timeout} seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"
        finally:
            # 恢复 InputListener
            if listener:
                listener.resume()

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

    def _fix_escaped_quotes(self, command: str) -> str:
        """
        修复 LLM 错误生成的转义字符。

        常见问题：
        - python -c "\\nprint('hello')" → \n 应该是换行符
        - python -c "open(r\\'path\\')" → r\\' 应该是 r'
        - python -c "print(\\'hello\\')" → \\' 应该是 '

        跨平台考虑：
        - Windows: 路径含反斜杠，LLM 容易混淆转义
        - Mac/Linux: 路径用正斜杠，但 Python -c 仍有同样问题
        """
        # 检测 python -c "..." 或 python3 -c '...' 模式
        python_match = re.search(
            r"(python\d?\s+-c\s*)(['\"])(.+)\2\s*$",
            command,
            re.IGNORECASE | re.DOTALL
        )

        if not python_match:
            return command

        prefix = python_match.group(1)  # python -c
        quote = python_match.group(2)   # " 或 '
        code = python_match.group(3)    # 代码内容

        # 1. 修复 r\' → r'（raw string 后的转义引号，永远是语法错误）
        code = re.sub(r"r\\'", "r'", code)

        # 2. 修复 \' → '（普通转义单引号）
        # 使用负向前瞻，避免把 \\'（合法的字面反斜杠+引号）也改了
        code = re.sub(r"(?<!\\)\\'", "'", code)

        # 3. 修复转义序列：\n → 换行，\t → 制表符
        # 但要保留 \\（字面反斜杠，如 Windows 路径 D:\\path）
        # 使用占位符保护已有的双反斜杠
        code = code.replace("\\\\", "\x00DBLBACKSLASH\x00")
        code = code.replace("\\n", "\n")
        code = code.replace("\\t", "\t")
        code = code.replace("\\r", "\r")
        code = code.replace("\x00DBLBACKSLASH\x00", "\\\\")

        return prefix + quote + code + quote
