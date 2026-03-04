"""工具层 - bash 和 python 执行器"""
import subprocess
import uuid
from pathlib import Path
from typing import Dict


def run_bash(cmd: str) -> Dict:
    """执行 bash 命令"""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=300  # 5 分钟超时
    )
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "code": result.returncode
    }


def run_python(code: str) -> Dict:
    """执行 Python 代码"""
    # 使用系统临时目录
    import tempfile
    temp_dir = Path(tempfile.gettempdir())
    filename = temp_dir / f"{uuid.uuid4().hex}.py"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)

        result = subprocess.run(
            ["python", str(filename)],
            capture_output=True,
            text=True,
            timeout=300
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "code": result.returncode
        }
    finally:
        # 清理临时文件
        if filename.exists():
            filename.unlink()


# 工具注册表
TOOLS = {
    "bash": run_bash,
    "python": run_python
}
