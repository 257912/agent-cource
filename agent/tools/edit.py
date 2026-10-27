"""edit：精确字符串替换 + 唯一性检查（绝不模糊匹配）。"""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolContext, ToolResult, atomic_write, rel_path, safe_path, unified_diff


class EditTool(Tool):
    name = "edit"
    description = (
        "对文件做精确字符串替换。old_str 必须与文件内容逐字节一致，且在文件中唯一存在；"
        "匹配不到或匹配到多处都会直接报错（不做模糊匹配）。适合小步修改，不要用它整篇重写。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径，相对工作区根目录"},
            "old_str": {"type": "string", "description": "要被替换的原文，必须唯一且完全一致（含缩进与换行）"},
            "new_str": {"type": "string", "description": "替换后的新文本"},
            "replace_all": {
                "type": "boolean",
                "description": "当 old_str 出现多处时，是否确认全部替换，默认 false",
            },
        },
        "required": ["path", "old_str", "new_str"],
    }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = safe_path(ctx.workspace, str(args.get("path") or "").strip())
        rel = rel_path(ctx.workspace, path)

        old_str = args.get("old_str")
        new_str = args.get("new_str")
        if old_str is None or new_str is None:
            return ToolResult(ok=False, error="old_str 与 new_str 都是必填参数")
        if old_str == "":
            return ToolResult(ok=False, error="old_str 不能为空字符串")
        if old_str == new_str:
            return ToolResult(ok=False, error="old_str 与 new_str 相同，无需修改")

        if not path.exists():
            return ToolResult(ok=False, error=f"文件不存在：{rel}。请先确认路径或用 write 新建。")
        if path.is_dir():
            return ToolResult(ok=False, error=f"{rel} 是目录，不能用 edit 修改")

        original = path.read_text(encoding="utf-8", errors="replace")
        count = original.count(old_str)

        if count == 0:
            return ToolResult(
                ok=False,
                error=(
                    f"在 {rel} 中未找到 old_str（{len(old_str)} 字符）。"
                    f"常见原因：缩进/空白/换行不一致，或文件已被改过。"
                    f"请先用 read 重新确认原文，再原样复制后重试，不要凭记忆改。"
                ),
                meta={"path": rel, "matched": 0},
            )

        replace_all = bool(args.get("replace_all"))
        if count > 1 and not replace_all:
            line_nos = _occurrence_lines(original, old_str)
            return ToolResult(
                ok=False,
                error=(
                    f"old_str 在 {rel} 中匹配到 {count} 处（起始行：{', '.join(map(str, line_nos[:10]))}），"
                    f"不唯一，已拒绝修改。请补充更多上下文让 old_str 唯一；"
                    f"若确认要全部替换，请传入 replace_all=true。"
                ),
                meta={"path": rel, "matched": count, "lines": line_nos},
            )

        updated = original.replace(old_str, new_str) if replace_all else original.replace(old_str, new_str, 1)
        atomic_write(path, updated)
        diff = unified_diff(original, updated, rel)

        added = len(new_str.splitlines()) - len(old_str.splitlines())
        return ToolResult(
            ok=True,
            output=f"已修改 {rel}：替换 {count if replace_all else 1} 处（行数变化 {added:+d}）",
            meta={"path": rel, "matched": count, "diff": diff, "replaced": count if replace_all else 1},
        )


def _occurrence_lines(text: str, needle: str) -> list[int]:
    lines: list[int] = []
    pos = text.find(needle)
    while pos != -1:
        lines.append(text.count("\n", 0, pos) + 1)
        pos = text.find(needle, pos + 1)
    return lines
