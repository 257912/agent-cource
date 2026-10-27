"""write：自动建父目录 + 原子写 + 覆盖前必须确认。"""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolContext, ToolResult, atomic_write, rel_path, safe_path, unified_diff


class WriteTool(Tool):
    name = "write"
    description = (
        "把完整内容写入文件。会自动创建父目录，并用临时文件原子替换。"
        "覆盖已存在的文件必须显式传 overwrite=true，覆盖结果会给出 diff。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径，相对工作区根目录"},
            "content": {"type": "string", "description": "文件完整内容"},
            "overwrite": {
                "type": "boolean",
                "description": "目标已存在时是否确认覆盖，默认 false",
            },
        },
        "required": ["path", "content"],
    }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = safe_path(ctx.workspace, str(args.get("path") or "").strip())
        rel = rel_path(ctx.workspace, path)

        if "content" not in args or args.get("content") is None:
            return ToolResult(ok=False, error="缺少 content 参数")

        content: str = args["content"]
        existed = path.exists()
        old = path.read_text(encoding="utf-8", errors="replace") if existed else ""

        if existed and not bool(args.get("overwrite")):
            preview = "\n".join(old.splitlines()[:10])
            return ToolResult(
                ok=False,
                error=(
                    f"文件已存在：{rel}（{len(old.splitlines())} 行）。覆盖会丢失原内容，"
                    f"如确认要整篇重写，请再次调用 write 并传入 overwrite=true。\n"
                    f"当前内容前 10 行：\n{preview}"
                ),
                meta={"path": rel, "existed": True},
            )

        atomic_write(path, content)
        diff = unified_diff(old, content, rel)
        size = len(content.encode("utf-8"))
        return ToolResult(
            ok=True,
            output=f"已{'覆盖' if existed else '新建'} {rel}：{len(content.splitlines())} 行 / {size} 字节",
            meta={
                "path": rel,
                "existed": existed,
                "diff": diff,
                "lines": len(content.splitlines()),
                "bytes": size,
            },
        )
