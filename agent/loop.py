"""Agent 主循环：模型 -> 工具 -> 结果回灌，全程以事件形式外抛，可中途取消。"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .config import Settings
from .events import event
from .llm import BaseLLM, ToolCall
from .tools.base import ToolContext, ToolRegistry, ToolResult

Emit = Callable[[Any], Awaitable[None]]

SYSTEM_PROMPT = """你是 MiniCursor，一个运行在用户本机桌面上的 AI 编程助手。

工作方式：
1. 先看事实再动手。不确定文件内容就先用 read 读，禁止凭记忆猜测代码。
2. 修改优先用 edit 做最小差异替换；只有新建文件、或确实需要整篇重写时才用 write。
3. 需要跑测试、装依赖、看目录时用 bash。
4. 一次只推进一小步，遇到错误先读错误信息，再修正重试，不要原地打转。

工具规则：
- read / write / edit 的 path 相对工作区根目录，不允许用 .. 逃出工作区。
- edit 的 old_str 必须唯一；返回“匹配到 N 处”时，补充更多上下文后重试，绝不模糊匹配。
- write 覆盖已有文件必须传 overwrite=true，并确认这确实是用户想要的。
- bash 有超时限制，长任务要自己拆分。
- 用中文回复，回答简洁，说明你改了哪个文件、为什么这么改。
"""

MAX_HISTORY = 40


@dataclass
class RunRequest:
    text: str


class AgentLoop:
    def __init__(self, settings: Settings, registry: ToolRegistry, llm: BaseLLM | None = None) -> None:
        self.settings = settings
        self.registry = registry
        self.llm = llm
        self.history: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.history = []

    async def run(self, req: RunRequest, emit: Emit, cancel: asyncio.Event | None = None) -> None:
        run_id = uuid.uuid4().hex[:8]
        cancel = cancel or asyncio.Event()
        if self.llm is None:
            await emit(event("error", run_id=run_id, message="模型未初始化"))
            await emit(event("run.end", run_id=run_id, reason="error"))
            await emit(None)
            return

        await emit(
            event(
                "run.start",
                run_id=run_id,
                model=getattr(self.llm, "model", "mock"),
                input=req.text,
            )
        )
        self.history.append({"role": "user", "content": req.text})
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self.history,
        ]
        ctx = ToolContext(workspace=self.settings.workspace, settings=self.settings, run_id=run_id)

        try:
            for step in range(1, self.settings.max_steps + 1):
                if cancel.is_set():
                    await emit(event("run.end", run_id=run_id, reason="cancelled", steps=step - 1))
                    return

                await emit(event("status", run_id=run_id, phase="thinking", step=step))
                text_parts: list[str] = []
                calls: list[ToolCall] = []
                async for kind, payload in self.llm.stream(messages, self.registry.specs()):
                    if cancel.is_set():
                        break
                    if kind == "text":
                        text_parts.append(payload)
                        await emit(event("assistant.delta", run_id=run_id, text=payload))
                    elif kind == "tool_calls":
                        calls = payload

                if cancel.is_set():
                    await emit(event("run.end", run_id=run_id, reason="cancelled", steps=step))
                    return

                text = "".join(text_parts)

                if not calls:
                    await emit(event("assistant.message", run_id=run_id, text=text))
                    self.history.append({"role": "assistant", "content": text})
                    await emit(event("run.end", run_id=run_id, reason="done", steps=step))
                    return

                assistant_msg: dict[str, Any] = {"role": "assistant", "content": text}
                assistant_msg["tool_calls"] = [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                    for c in calls
                ]
                messages.append(assistant_msg)
                self.history.append(assistant_msg)

                for call in calls:
                    if cancel.is_set():
                        await emit(event("run.end", run_id=run_id, reason="cancelled", steps=step))
                        return
                    args = _parse_args(call.arguments)
                    await emit(
                        event("tool.call", run_id=run_id, step=step, id=call.id, name=call.name, args=args)
                    )
                    result = await self.registry.call(call.name, args, ctx)
                    await emit(
                        event(
                            "tool.result",
                            run_id=run_id,
                            id=call.id,
                            name=call.name,
                            ok=result.ok,
                            output=result.output,
                            error=result.error,
                            diff=result.meta.get("diff", ""),
                            meta={k: v for k, v in result.meta.items() if k != "diff"},
                            images=[{"mime": i.mime, "b64": i.b64} for i in result.images],
                        )
                    )
                    tool_msg = _tool_message(call, result)
                    messages.append(tool_msg)
                    self.history.append(tool_msg)

                if len(self.history) > MAX_HISTORY:
                    self.history = self.history[-MAX_HISTORY:]

            await emit(event("run.end", run_id=run_id, reason="max_steps", steps=self.settings.max_steps))
        except asyncio.CancelledError:
            await emit(event("run.end", run_id=run_id, reason="cancelled"))
            raise
        except Exception as exc:
            await emit(event("error", run_id=run_id, message=f"{type(exc).__name__}: {exc}"))
            await emit(event("run.end", run_id=run_id, reason="error"))
        finally:
            await emit(None)


def _parse_args(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"_raw": raw}


def _tool_message(call: ToolCall, result: ToolResult) -> dict[str, Any]:
    if not result.ok:
        content: Any = f"[TOOL ERROR] {result.error}"
    elif result.images:
        content = result.output + "\n（图片内容已随本次结果返回）"
    else:
        content = result.output
    return {"role": "tool", "tool_call_id": call.id, "content": content}
