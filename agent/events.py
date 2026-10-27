"""事件协议。

后端与前端之间只通过事件流通信：WebSocket (/ws) 与 SSE (/api/run) 推送的是同一批事件。
事件是 {type, seq, ts, ...payload} 的 JSON 对象。

常见 type:
  run.start          一轮开始
  status             阶段性状态（thinking / tool / done）
  assistant.delta    模型文本增量
  assistant.message  模型最终文本
  tool.call          准备调用工具（含参数）
  tool.result        工具返回（ok / output / error / diff）
  error              异常
  run.end            一轮结束（reason: done | cancelled | max_steps | error）
"""

from __future__ import annotations

import itertools
import time
from typing import Any

_seq = itertools.count(1)


def event(type_: str, **payload: Any) -> dict[str, Any]:
    """构造一个事件对象。"""
    return {
        "type": type_,
        "seq": next(_seq),
        "ts": round(time.time(), 3),
        **payload,
    }
