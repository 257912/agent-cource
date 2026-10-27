"""工具基类、结果结构与路径安全。"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}

MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
}


class ToolError(Exception):
    """可预期的工具失败，错误信息需要原样回传给模型。"""


@dataclass
class ToolImage:
    mime: str
    b64: str


@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    error: str = ""
    images: list[ToolImage] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "output": self.output,
            "error": self.error,
            "images": [{"mime": i.mime, "b64": i.b64} for i in self.images],
            "meta": self.meta,
        }


@dataclass
class ToolContext:
    workspace: Path
    settings: Any = None
    run_id: str = ""


def safe_path(workspace: Path, raw: str) -> Path:
    """把任意输入路径限制在工作区内，拒绝越界访问。"""
    if not raw:
        raise ToolError("path 不能为空")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = workspace / p
    p = p.resolve()
    ws = workspace.resolve()
    if p != ws and ws not in p.parents:
        raise ToolError(f"路径越界，只能访问工作区内的文件：{raw}（工作区：{ws}）")
    return p


def rel_path(workspace: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path)


def atomic_write(path: Path, content: str) -> None:
    """临时文件 + os.replace 原子写入，避免写一半崩溃留下半截文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:6]}")
    try:
        tmp.write_text(content, encoding="utf-8", newline="")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def unified_diff(old: str, new: str, path: str, n: int = 3) -> str:
    import difflib

    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", n=n
    )
    return "".join(diff)


def truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = text[: limit // 2]
    tail = text[-limit // 3 :]
    return f"{head}\n\n... [已截断 {len(text) - limit} 字符] ...\n\n{tail}", True


class Tool:
    """工具基类：子类给出 name / description / parameters 并实现 run。"""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def spec(self) -> dict[str, Any]:
        """OpenAI function calling 格式的工具声明。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        return [t.spec() for t in self._tools.values()]

    async def call(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                ok=False,
                error=f"未知工具：{name}。可用工具：{', '.join(self.names())}",
            )
        try:
            return await tool.run(args or {}, ctx)
        except ToolError as exc:
            return ToolResult(ok=False, error=str(exc))
        except Exception as exc:  # 兜底：任何异常都要变成可回传的错误，不能炸掉主循环
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")
