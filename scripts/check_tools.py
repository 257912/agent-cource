"""四个工具的语义自检：python scripts/check_tools.py

覆盖：read 行号/分页/图片、write 原子写与覆盖保护、edit 唯一性检查、bash 三件套。
会在 workspace/_selftest 下造临时文件，跑完自动清理。
"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.config import Settings
from agent.tools import build_default_registry
from agent.tools.base import ToolContext

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


async def main() -> int:
    settings = Settings.from_env()
    settings.ensure_workspace()
    ws = settings.workspace
    tmp_dir = ws / "_selftest"
    tmp_dir.mkdir(exist_ok=True)
    ctx = ToolContext(workspace=ws, settings=settings)
    reg = build_default_registry(settings)

    src = tmp_dir / "demo.py"
    src.write_text("def add(a, b):\n    return a - b\n\n\ndef add(a, b):\n    return a + b\n", encoding="utf-8")

    print("[read]")
    r = await reg.call("read", {"path": "_selftest/demo.py"}, ctx)
    check("带行号返回", r.ok and "     1\tdef add(a, b):" in r.output, r.error)
    r = await reg.call("read", {"path": "_selftest/nope.py"}, ctx)
    check("文件不存在报错且不猜", (not r.ok) and "文件不存在" in r.error, r.error)
    r = await reg.call("read", {"path": "../README.md"}, ctx)
    check("越界路径被拒绝", (not r.ok) and "越界" in r.error, r.error)
    r = await reg.call("read", {"path": "_selftest/demo.py", "offset": 5, "limit": 2}, ctx)
    check("分页 offset/limit", r.ok and r.meta.get("offset") == 5, r.output)

    png = tmp_dir / "pixel.png"
    png.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    ))
    r = await reg.call("read", {"path": "_selftest/pixel.png"}, ctx)
    check("图片返回多模态块", r.ok and len(r.images) == 1 and r.images[0].mime == "image/png", r.error)

    print("[write]")
    target = tmp_dir / "nested" / "new.txt"
    r = await reg.call("write", {"path": "_selftest/nested/new.txt", "content": "hello\n"}, ctx)
    check("自动创建父目录", r.ok and target.exists(), r.error)
    r = await reg.call("write", {"path": "_selftest/nested/new.txt", "content": "again\n"}, ctx)
    check("覆盖前必须确认", (not r.ok) and "overwrite=true" in r.error, r.error)
    check("拒绝覆盖时文件未被改动", target.read_text(encoding="utf-8") == "hello\n")
    r = await reg.call("write", {"path": "_selftest/nested/new.txt", "content": "again\n", "overwrite": True}, ctx)
    check("确认后可覆盖并给出 diff", r.ok and "-hello" in r.meta.get("diff", ""), r.error)

    print("[edit]")
    r = await reg.call("edit", {"path": "_selftest/demo.py", "old_str": "return a - b", "new_str": "return a + b"}, ctx)
    check("唯一匹配可替换", r.ok and "return a + b" in src.read_text(encoding="utf-8"), r.error)
    r = await reg.call("edit", {"path": "_selftest/demo.py", "old_str": "def add(a, b):", "new_str": "def add2(a, b):"}, ctx)
    check("多处匹配直接报错", (not r.ok) and "不唯一" in r.error and r.meta.get("matched") == 2, r.error)
    check("报错后文件未被改动", "def add2" not in src.read_text(encoding="utf-8"))
    r = await reg.call("edit", {"path": "_selftest/demo.py", "old_str": "return a * b", "new_str": "x"}, ctx)
    check("匹配不到报错", (not r.ok) and "未找到" in r.error, r.error)

    print("[bash]")
    echo = "echo hi" if sys.platform != "win32" else "echo hi"
    r = await reg.call("bash", {"command": echo}, ctx)
    check("拿到 stdout 与 exit_code", r.ok and r.meta.get("exit_code") == 0 and "hi" in r.meta.get("stdout", ""), r.error)
    r = await reg.call("bash", {"command": "exit 3"}, ctx)
    check("非零退出码判失败", (not r.ok) and r.meta.get("exit_code") == 3, r.error)
    r = await reg.call(
        "bash",
        {"command": f'"{sys.executable}" -c "import time; time.sleep(5)"', "timeout": 1},
        ctx,
    )
    check("超时被中断", (not r.ok) and r.meta.get("timed_out") is True, r.error)

    # 清理
    for p in tmp_dir.rglob("*"):
        if p.is_file():
            p.unlink(missing_ok=True)
    for p in sorted(tmp_dir.rglob("*"), reverse=True):
        if p.is_dir():
            p.rmdir()
    tmp_dir.rmdir()

    print(f"\n通过 {passed} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
