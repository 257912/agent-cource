"""bash：拿 stdout + stderr + exit_code，带超时强制中断。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .base import Tool, ToolContext, ToolResult, safe_path, truncate

MAX_TIMEOUT = 600


class BashTool(Tool):
    name = "bash"
    description = (
        "在工作区根目录执行命令（Windows 下走 cmd.exe）。"
        "返回 stdout、stderr、exit_code 与耗时；超时会被强制中断。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令，例如 'python -m pytest -q'"},
            "timeout": {"type": "integer", "description": "超时秒数，默认取服务端配置（30）", "minimum": 1},
            "cwd": {"type": "string", "description": "执行目录，相对工作区根目录，默认工作区根"},
        },
        "required": ["command"],
    }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = str(args.get("command") or "").strip()
        if not command:
            return ToolResult(ok=False, error="command 不能为空")

        default_timeout = getattr(ctx.settings, "bash_timeout", 30)
        try:
            timeout = int(args.get("timeout") or default_timeout)
        except (TypeError, ValueError):
            timeout = default_timeout
        timeout = max(1, min(timeout, MAX_TIMEOUT))

        cwd = safe_path(ctx.workspace, str(args.get("cwd") or "."))
        if not cwd.is_dir():
            return ToolResult(ok=False, error=f"执行目录不存在：{cwd}")

        started = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"无法启动命令：{type(exc).__name__}: {exc}")

        timed_out = False
        try:
            raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            code = proc.returncode
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                raw_out, raw_err = await proc.communicate()
            except Exception:
                raw_out, raw_err = b"", b""
            code = proc.returncode if proc.returncode is not None else -1
        duration = time.perf_counter() - started

        limit = getattr(ctx.settings, "max_output_chars", 20000)
        out, out_cut = truncate(_decode(raw_out), limit)
        err, err_cut = truncate(_decode(raw_err), limit)

        ok = code == 0 and not timed_out
        error = "" if ok else (f"命令退出码 {code}" + ("（超时被中断）" if timed_out else ""))
        output = (
            f"$ {command}\n"
            f"[exit_code] {code}\n"
            f"[duration] {duration:.2f}s"
            f"{'  [TIMEOUT]' if timed_out else ''}\n"
            f"----- stdout -----\n{out}\n"
            f"----- stderr -----\n{err}"
        )
        return ToolResult(
            ok=ok,
            output=output,
            error=error,
            meta={
                "command": command,
                "exit_code": code,
                "stdout": out,
                "stderr": err,
                "timed_out": timed_out,
                "truncated": out_cut or err_cut,
                "duration_ms": int(duration * 1000),
            },
        )


def _decode(raw: bytes | None) -> str:
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace")
