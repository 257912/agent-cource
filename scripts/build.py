"""用 PyInstaller 打包成单文件可执行程序（用于 Release 附件）。

Windows:  dist/MiniCursor.exe
macOS:    dist/MiniCursor.app（加 --onedir 更稳）
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sep = os.pathsep
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", "MiniCursor",
        "--onefile",
        "--noconsole",
        "--add-data", f"{ROOT / 'ui'}{sep}ui",
        "--add-data", f"{ROOT / '.env.example'}{sep}.",
        "--add-data", f"{ROOT / 'mcp.json'}{sep}.",
        "--hidden-import", "uvicorn.loops.asyncio",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "websockets.legacy",
        "--collect-submodules", "agent",
        "--collect-submodules", "server",
        str(ROOT / "main.py"),
    ]
    print(" ".join(cmd))
    return subprocess.check_call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
