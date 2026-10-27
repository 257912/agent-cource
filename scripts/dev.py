"""启动后端并弹出桌面窗口：python main.py

后端用 uvicorn 在后台线程跑起来，前端用 pywebview 包一个真正的桌面窗口；
pywebview 不可用时自动降级为 Edge/Chrome 的 app 模式窗口。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def free_port(start: int = 8765) -> int:
    for port in range(start, start + 100):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def wait_health(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def open_desktop_window(url: str) -> None:
    try:
        import webview  # pywebview

        webview.create_window(
            "MiniCursor · 桌面 AI 编程助手",
            url,
            width=1440,
            height=920,
            min_size=(1024, 640),
        )
        webview.start()
        return
    except Exception as exc:  # 降级
        print(f"[dev] pywebview 不可用（{exc}），降级为浏览器 app 窗口")

    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for exe in candidates:
        if Path(exe).exists():
            subprocess.Popen([exe, f"--app={url}", "--window-size=1440,920"])
            return
    webbrowser.open(url)


def main() -> None:
    from agent.config import load_env

    load_env()
    import uvicorn

    port = int(os.getenv("AGENT_PORT", "0") or 0) or free_port()
    url = f"http://127.0.0.1:{port}"

    config = uvicorn.Config("server.app:app", host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    print(f"[dev] 后端已启动：{url}/api/health")
    print(f"[dev] 事件流自检：curl -N -X POST {url}/api/run -d \"{{\\\"text\\\":\\\"你好\\\"}}\"")
    if not wait_health(f"{url}/api/health"):
        print("[dev] 后端健康检查超时，请查看上面的日志")
        return

    open_desktop_window(url)
    print("[dev] 窗口已关闭，退出")
    os._exit(0)


if __name__ == "__main__":
    main()
