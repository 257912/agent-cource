"""四个核心工具：read / write / edit / bash。"""

from __future__ import annotations

from ..config import Settings
from .base import Tool, ToolContext, ToolRegistry
from .bash import BashTool
from .edit import EditTool
from .read import ReadTool
from .write import WriteTool

__all__ = [
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "BashTool",
    "build_default_registry",
]


def build_default_registry(settings: Settings) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(BashTool())
    return registry
