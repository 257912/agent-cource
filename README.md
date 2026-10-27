# MiniCursor · 桌面 AI 编程助手

一个本地桌面窗口里的 AI 编程助手：**接大模型 + 接 MCP + 只有四个工具（read / write / edit / bash）**，
每一次工具调用、每一处改动、每一条命令输出都在界面上可见、可中断。

```
桌面窗口(pywebview)  ──WebSocket──▶  FastAPI 后端  ──▶  LLM(OpenAI 兼容协议)
        ▲                                │
        └──────── SSE/WS 事件流 ─────────┤──▶ read / write / edit / bash
                                         └──▶ MCP server(s)
```

## 三步启动

```bash
# 1) 建环境
python -m venv .venv
.venv\Scripts\activate           # macOS/Linux: source .venv/bin/activate
pip install -e .[desktop,dev]

# 2) 配 Key（.env 绝不入库，只在后端进程里）
cp .env.example .env             # 填入 OPENAI_API_KEY

# 3) 启动
python main.py                   # 自动起后端 + 弹出桌面窗口
```

没有 Key 也能跑通：`.env` 里设 `AGENT_MOCK=1`，用离线假模型验证全链路。

**方式二：Release 里的安装包** → 下载 → 双击 `MiniCursor.exe` → 填 Key。

## 四个工具（语义严格按作业要求）

| 工具 | 行为 |
| --- | --- |
| `read` | 文本按行返回**带行号**；图片(png/jpg/gif/webp)返回 **base64 多模态内容块**；超过 `max_read_lines` 自动分页并提示 `offset` |
| `write` | 自动创建父目录；**临时文件 + `os.replace` 原子写**；覆盖已存在文件必须先传 `overwrite=true`，结果给出 diff |
| `edit` | **精确字符串替换 + 唯一性检查**：匹配 0 处或 N>1 处都直接报错（绝不模糊匹配），支持 `replace_all` 兜底 |
| `bash` | 返回 **stdout + stderr + exit_code + 耗时**，支持超时强制 kill |

所有路径通过 `safe_path()` 限制在 `AGENT_WORKSPACE` 内，`../` 越界一律拒绝。

## 关掉前端也能看到事件流

```bash
python -m uvicorn server.app:app --port 8765

curl http://127.0.0.1:8765/api/health
curl -N -X POST http://127.0.0.1:8765/api/run ^
  -H "Content-Type: application/json" -d "{\"text\":\"读取 workspace/README.md\"}"
# 或
python scripts/smoke.py --text "读取 workspace/README.md"
```

事件协议见 [`docs/trace.md`](docs/trace.md)。

## MCP

编辑 [`mcp.json`](mcp.json)，默认启用本地示例 server（`mcp_servers/demo_server.py`，工具：`get_time` / `count_words` / `list_python_files`），
接入后工具名为 `mcp__demo__get_time`，可在界面右侧看到调用。单个 server 挂掉不影响其它功能。

## 目录

```
agent/         Agent 核心：config / llm / loop / mcp_client / events
  tools/       read · write · edit · bash
server/        FastAPI：WebSocket + SSE + REST
ui/            三栏界面（原生 HTML/CSS/JS，无构建）
scripts/       dev(启动) · smoke(无界面自检) · build(打包)
workspace/     Agent 的操作沙盒
docs/          trace.md(事件协议) · build.md(打包发布)
```

## 打包

```bash
python scripts/build.py     # → dist/MiniCursor.exe
```

## 安全

- `.env` 在 `.gitignore` 中，仓库只有 `.env.example`。
- 模型请求只发生在后端进程，前端拿不到任何 Key（它只收事件流）。
- 工具路径被限制在工作区内，bash 有超时上限。
