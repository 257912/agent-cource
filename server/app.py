"""FastAPI 后端：WebSocket 与 SSE 推送同一批事件，关掉前端也能用 curl -N 看到事件流。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent.config import Settings, load_env
from agent.events import event
from agent.llm import MockLLM, OpenAICompatLLM
from agent.loop import AgentLoop, RunRequest
from agent.mcp_client import MCPManager
from agent.tools import build_default_registry
from agent.tools.base import rel_path, safe_path

load_env()
settings = Settings.from_env()
settings.ensure_workspace()

registry = build_default_registry(settings)
mcp_manager = MCPManager(settings.mcp_config)
loop = AgentLoop(settings, registry)

state: dict[str, Any] = {"mode": "mock", "warning": ""}


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_manager.load()
    for tool in await mcp_manager.tools():
        registry.register(tool)

    if settings.mock or not settings.api_key:
        loop.llm = MockLLM()
        state["mode"] = "mock"
        if not settings.api_key:
            state["warning"] = "未配置 OPENAI_API_KEY，已自动切换到离线假模型（AGENT_MOCK）"
    else:
        try:
            loop.llm = OpenAICompatLLM(settings)
            state["mode"] = "remote"
        except Exception as exc:
            loop.llm = MockLLM()
            state["mode"] = "mock"
            state["warning"] = str(exc)
    yield
    await mcp_manager.aclose()


app = FastAPI(title="MiniCursor", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- 事件流核心 ----------------
async def run_events(text: str, holder: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    """驱动一次 Agent 运行，并逐个产出事件；holder['cancel'] 供外部中断。"""
    queue: asyncio.Queue = asyncio.Queue()
    cancel = asyncio.Event()
    holder["cancel"] = cancel
    task = asyncio.create_task(loop.run(RunRequest(text=text), queue.put, cancel))
    try:
        while True:
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                ev = getter.result()
                if ev is None:
                    break
                yield ev
            else:
                getter.cancel()
                while not queue.empty():
                    ev = queue.get_nowait()
                    if ev is not None:
                        yield ev
                break
    finally:
        holder.pop("cancel", None)
        if not task.done():
            task.cancel()


async def sse_iter(gen: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async for ev in gen:
        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


# ---------------- HTTP API ----------------
@app.get("/api/health")
def health() -> dict[str, Any]:
    mcp_tools = [n for n in registry.names() if n.startswith("mcp__")]
    return {
        "ok": True,
        "mode": state["mode"],
        "warning": state["warning"],
        "model": settings.model,
        "base_url": settings.base_url,
        "workspace": str(settings.workspace),
        "tools": registry.names(),
        "mcp": {
            "servers": list(mcp_manager.servers),
            "tools": mcp_tools,
            "errors": mcp_manager.errors,
        },
    }


@app.post("/api/run")
async def run_sse(body: dict[str, Any] = Body(default={})) -> StreamingResponse:
    """SSE 事件流：curl -N -X POST http://127.0.0.1:8765/api/run -d '{\"text\":\"...\"}'"""
    text = str((body or {}).get("text", "")).strip()
    if not text:
        return JSONResponse({"error": "text 不能为空"}, status_code=400)
    holder: dict[str, Any] = {}
    return StreamingResponse(
        sse_iter(run_events(text, holder)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/tree")
def tree(path: str = "") -> Any:
    root = safe_path(settings.workspace, path or ".")
    if not root.is_dir():
        return JSONResponse({"error": f"不是目录：{path}"}, status_code=400)
    items = []
    for p in sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        if p.name in {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache"} or p.name.startswith("."):
            continue
        items.append(
            {
                "name": p.name,
                "path": rel_path(settings.workspace, p),
                "type": "dir" if p.is_dir() else "file",
                "size": p.stat().st_size if p.is_file() else 0,
            }
        )
    return {"root": rel_path(settings.workspace, root) or ".", "items": items}


@app.get("/api/file")
def get_file(path: str) -> Any:
    try:
        p = safe_path(settings.workspace, path)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if not p.is_file():
        return JSONResponse({"error": f"文件不存在：{path}"}, status_code=404)
    content = p.read_text(encoding="utf-8", errors="replace")
    return {"path": rel_path(settings.workspace, p), "content": content[:200000], "lines": len(content.splitlines())}


# ---------------- WebSocket ----------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    holder: dict[str, Any] = {}
    pump_task: asyncio.Task | None = None

    await ws.send_text(json.dumps(event("hello", **health()), ensure_ascii=False))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = msg.get("type")

            if kind == "run":
                if pump_task is not None and not pump_task.done():
                    await ws.send_text(json.dumps(event("error", message="上一轮还在运行，请先等待或中断"), ensure_ascii=False))
                    continue
                text = str(msg.get("text", "")).strip()
                if not text:
                    continue

                async def pump() -> None:
                    async for ev in run_events(text, holder):
                        await ws.send_text(json.dumps(ev, ensure_ascii=False))

                pump_task = asyncio.create_task(pump())
            elif kind == "cancel":
                cancel = holder.get("cancel")
                if cancel:
                    cancel.set()
            elif kind == "reset":
                loop.reset()
                await ws.send_text(json.dumps(event("session.reset"), ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    finally:
        cancel = holder.get("cancel")
        if cancel:
            cancel.set()
        if pump_task is not None:
            pump_task.cancel()


# ---------------- 静态前端（必须放在 API 之后） ----------------
app.mount("/", StaticFiles(directory=ROOT / "ui", html=True), name="ui")
