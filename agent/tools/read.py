"""read：带行号读文本，图片返回多模态块，大文件强制分页。"""

from __future__ import annotations

import base64
from typing import Any

from .base import (
    IMAGE_SUFFIXES,
    MIME_BY_SUFFIX,
    Tool,
    ToolContext,
    ToolImage,
    ToolResult,
    rel_path,
    safe_path,
)


class ReadTool(Tool):
    name = "read"
    description = (
        "读取工作区内的文件。文本文件按行返回带行号的内容；图片(png/jpg/gif/webp)返回多模态内容块，"
        "你可以直接看图。大文件会自动分页，需要用 offset/limit 继续读。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径，相对工作区根目录，例如 'app.py'"},
            "offset": {"type": "integer", "description": "起始行号，从 1 开始，默认 1", "minimum": 1},
            "limit": {"type": "integer", "description": "本次最多读取多少行，默认由服务端配置", "minimum": 1},
        },
        "required": ["path"],
    }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = safe_path(ctx.workspace, str(args.get("path") or "").strip())
        rel = rel_path(ctx.workspace, path)

        if not path.exists():
            hint = ""
            if path.parent.is_dir():
                siblings = sorted(p.name for p in path.parent.iterdir())[:20]
                if siblings:
                    hint = "；同目录有：" + ", ".join(siblings)
            return ToolResult(ok=False, error=f"文件不存在：{rel}{hint}")

        if path.is_dir():
            entries = sorted((p.name + ("/" if p.is_dir() else "")) for p in path.iterdir())[:100]
            return ToolResult(ok=False, error=f"{rel} 是目录不是文件。目录内容：{', '.join(entries)}")

        data = path.read_bytes()
        suffix = path.suffix.lower()

        # 图片 -> 多模态内容块
        if suffix in IMAGE_SUFFIXES:
            b64 = base64.b64encode(data).decode("ascii")
            return ToolResult(
                ok=True,
                output=f"图片 {rel}（{len(data)} 字节），已作为图片内容块返回，可直接查看。",
                images=[ToolImage(mime=MIME_BY_SUFFIX.get(suffix, "image/png"), b64=b64)],
                meta={"path": rel, "bytes": len(data), "kind": "image"},
            )

        # 明显的二进制文件不要硬读
        if b"\x00" in data[:4096]:
            return ToolResult(ok=False, error=f"{rel} 看起来是二进制文件，无法按文本读取")

        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        total = len(lines)

        offset = max(1, int(args.get("offset") or 1))
        limit = int(args.get("limit") or getattr(ctx.settings, "max_read_lines", 400))
        if offset > total and total > 0:
            return ToolResult(ok=False, error=f"offset={offset} 超出范围，{rel} 一共只有 {total} 行")

        chunk = lines[offset - 1 : offset - 1 + limit]
        body = "\n".join(f"{offset + i:>6}\t{line}" for i, line in enumerate(chunk))
        shown_end = offset + len(chunk) - 1
        out = f"{rel}（第 {offset}-{shown_end} 行 / 共 {total} 行）\n{body}"

        meta = {
            "path": rel,
            "total_lines": total,
            "offset": offset,
            "limit": limit,
            "truncated": False,
        }
        if offset - 1 + limit < total:
            meta["truncated"] = True
            out += (
                f"\n... 剩余 {total - shown_end} 行未显示，继续阅读请调用 "
                f'read(path="{rel}", offset={shown_end + 1}, limit={limit})'
            )
        return ToolResult(ok=True, output=out, meta=meta)
