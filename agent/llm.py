"""模型接入层：OpenAI 兼容协议（流式 + function calling），以及离线假模型。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator

from .config import Settings

LLMEvent = tuple[str, Any]  # ("text", str) 或 ("tool_calls", list[ToolCall])


class LLMError(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


class BaseLLM:
    async def stream(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[LLMEvent]:
        raise NotImplementedError
        yield  # pragma: no cover


class OpenAICompatLLM(BaseLLM):
    """任何 OpenAI 兼容端点都能用：DeepSeek / 通义 / Kimi / OpenAI / 本地 vLLM。"""

    def __init__(self, settings: Settings) -> None:
        if not settings.api_key:
            raise LLMError(
                "缺少 API Key：请在 .env 中配置 OPENAI_API_KEY；"
                "没有 Key 时可设置 AGENT_MOCK=1 用离线假模型验证链路"
            )
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=120)
        self.model = settings.model

    async def stream(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[LLMEvent]:
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or None,
            tool_choice="auto" if tools else None,
            stream=True,
        )
        acc: dict[int, dict[str, str]] = {}
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                yield ("text", delta.content)
            for tc in getattr(delta, "tool_calls", None) or []:
                entry = acc.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                if tc.id:
                    entry["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        entry["name"] = tc.function.name
                    if tc.function.arguments:
                        entry["args"] += tc.function.arguments
        if acc:
            yield (
                "tool_calls",
                [
                    ToolCall(
                        id=entry["id"] or f"call_{idx}",
                        name=entry["name"],
                        arguments=entry["args"] or "{}",
                    )
                    for idx, entry in sorted(acc.items())
                ],
            )


class MockLLM(BaseLLM):
    """离线假模型：不发任何网络请求，用来在没有 Key 时验证事件流、工具链路和界面。"""

    async def stream(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[LLMEvent]:
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content")
                last_user = content if isinstance(content, str) else str(content)
                break

        has_tool_result = any(m.get("role") == "tool" for m in messages)
        if not has_tool_result:
            listing = "dir" if os.name == "nt" else "ls -la"
            yield ("text", f"（离线假模型）收到：{last_user[:80]}\n我先看一下工作区里有什么。\n")
            yield (
                "tool_calls",
                [ToolCall(id="mock_1", name="bash", arguments=json.dumps({"command": listing}, ensure_ascii=False))],
            )
        else:
            tool_msg = next(m for m in reversed(messages) if m.get("role") == "tool")
            content = tool_msg.get("content")
            content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            yield (
                "text",
                "（离线假模型）工具已返回结果，说明 后端→工具→事件流→前端 全链路打通：\n"
                f"{content[:600]}\n",
            )
