"""无界面冒烟测试：不打开窗口，直接看 SSE 事件流。

用法：
  python -m uvicorn server.app:app --port 8765      # 另开一个终端
  python scripts/smoke.py --text "读取 workspace/README.md"
等价的 curl：
  curl -N -X POST http://127.0.0.1:8765/api/run -H "Content-Type: application/json" -d "{\"text\":\"你好\"}"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def render(ev: dict) -> str:
    t = ev.get("type")
    if t == "assistant.delta":
        return ev.get("text", "")
    if t == "tool.call":
        return f"\n[tool.call ] {ev['name']} {json.dumps(ev.get('args', {}), ensure_ascii=False)}"
    if t == "tool.result":
        flag = "OK " if ev.get("ok") else "ERR"
        body = ev.get("output") or ev.get("error") or ""
        out = f"\n[tool.result] {flag} {ev['name']}\n{body}"
        if ev.get("diff"):
            out += "\n" + ev["diff"]
        return out
    if t == "assistant.message":
        return "\n" + ev.get("text", "")
    if t == "error":
        return f"\n[error] {ev.get('message')}"
    if t == "run.end":
        return f"\n[run.end] reason={ev.get('reason')} steps={ev.get('steps')}"
    if t == "run.start":
        return f"[run.start] run_id={ev.get('run_id')} model={ev.get('model')}"
    if t == "status":
        return f"[status] step={ev.get('step')} phase={ev.get('phase')}"
    return f"[{t}] {json.dumps(ev, ensure_ascii=False)[:200]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--text", default="读取 workspace/README.md，然后告诉我有几个文件")
    args = ap.parse_args()

    with httpx.stream("POST", f"{args.url}/api/run", json={"text": args.text}, timeout=None) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            print(render(json.loads(data)), end="", flush=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
