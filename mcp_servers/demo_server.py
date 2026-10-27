"""一个最小可用的 MCP server（stdio），用来演示「外部 MCP 工具真的被调起来了」。

工具：
  get_time()               返回当前时间
  count_words(text)        统计中英文词数
  list_python_files(path)  列出目录下所有 .py 文件
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-tools")


@mcp.tool()
def get_time() -> str:
    """返回当前系统时间。"""
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
def count_words(text: str) -> str:
    """统计一段文本里的中文字数与英文单词数。"""
    cn = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    en = len([w for w in text.replace("\n", " ").split(" ") if w.strip()])
    return f"中文字数 {cn}，英文单词数 {en}，总字符 {len(text)}"


@mcp.tool()
def list_python_files(path: str = ".") -> str:
    """列出目录下的 .py 文件（相对路径，最多 100 个）。"""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return f"不是目录：{root}"
    files = [str(p.relative_to(root)) for p in sorted(root.rglob("*.py"))[:100]]
    return "\n".join(files) if files else "(没有找到 .py 文件)"


if __name__ == "__main__":
    mcp.run(transport="stdio")
