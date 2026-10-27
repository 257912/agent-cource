"""MCP 接入：从 mcp.json 拉起 stdio server，把它的工具注册进工具表。"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from .tools.base import Tool, ToolContext, ToolResult

PREFIX = "mcp__"
CALL_TIMEOUT = 60


def _resolve_command(command: str) -> str:
    """配置里写 python 时，用当前解释器（避免 PATH 里没有 python 的情况）。"""
    if command in {"python", "python3"}:
        return sys.executable
    return command


class MCPTool(Tool):
    """把一个远端 MCP 工具包装成本地 Tool。"""

    def __init__(self, server: str, name: str, description: str, input_schema: dict, manager: "MCPManager") -> None:
        self.server = server
        self.remote_name = name
        self.name = f"{PREFIX}{server}__{name}"
        self.description = f"[MCP:{server}] {description or name}"
        self.parameters = input_schema or {"type": "object", "properties": {}}
        self._manager = manager

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await self._manager.call(self.server, self.remote_name, args)


class MCPManager:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.servers: dict[str, dict[str, Any]] = {}
        self.errors: list[str] = []
        self._stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, Any] = {}

    # ---------- 配置 ----------
    def load(self) -> None:
        if not self.config_path.exists():
            self.errors.append(f"未找到 MCP 配置：{self.config_path}")
            return
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.errors.append(f"mcp.json 解析失败：{exc}")
            return
        for name, cfg in (raw.get("mcpServers") or {}).items():
            if cfg.get("enabled") is False:
                continue
            self.servers[name] = cfg

    # ---------- 连接 ----------
    async def _ensure(self, server: str) -> Any:
        if server in self._sessions:
            return self._sessions[server]
        cfg = self.servers[server]
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise RuntimeError(f"缺少 mcp 依赖：{exc}（pip install mcp）") from exc

        stack = AsyncExitStack()
        params = StdioServerParameters(
            command=_resolve_command(cfg["command"]),
            args=cfg.get("args", []),
            env=cfg.get("env"),
        )
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await asyncio.wait_for(session.initialize(), timeout=CALL_TIMEOUT)
        self._stacks[server] = stack
        self._sessions[server] = session
        return session

    async def tools(self) -> list[Tool]:
        """连接所有 server 并列出工具；单个 server 失败不影响其它。"""
        if not self.servers:
            return []
        found: list[Tool] = []
        for name in list(self.servers):
            try:
                session = await self._ensure(name)
                listing = await asyncio.wait_for(session.list_tools(), timeout=CALL_TIMEOUT)
            except Exception as exc:
                self.errors.append(f"{name} 连接失败：{type(exc).__name__}: {exc}")
                continue
            for t in listing.tools:
                found.append(
                    MCPTool(
                        server=name,
                        name=t.name,
                        description=t.description or "",
                        input_schema=getattr(t, "inputSchema", None) or {},
                        manager=self,
                    )
                )
        return found

    async def call(self, server: str, tool: str, args: dict[str, Any]) -> ToolResult:
        try:
            session = await self._ensure(server)
            res = await asyncio.wait_for(session.call_tool(tool, args or {}), timeout=CALL_TIMEOUT)
        except Exception as exc:
            return ToolResult(ok=False, error=f"MCP 调用失败（{server}/{tool}）：{type(exc).__name__}: {exc}")

        parts: list[str] = []
        for item in getattr(res, "content", []) or []:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(json.dumps(getattr(item, "model_dump", lambda: str(item))(), ensure_ascii=False))
        ok = not bool(getattr(res, "isError", False))
        body = "\n".join(parts) or "(MCP 返回空内容)"
        return ToolResult(
            ok=ok,
            output=body,
            error="" if ok else body,
            meta={"server": server, "tool": tool, "mcp": True},
        )

    async def aclose(self) -> None:
        for stack in self._stacks.values():
            try:
                await stack.aclose()
            except Exception:
                pass
        self._stacks.clear()
        self._sessions.clear()
