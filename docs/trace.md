# 事件流协议（trace）

后端与前端之间**只有事件流**：WebSocket `/ws` 与 SSE `POST /api/run` 推送的是同一批事件。
关掉前端也能用 `curl -N` 看到完整过程，这是验收「工具调用必须看得见」的依据。

事件统一为 JSON 对象：`{ "type": ..., "seq": n, "ts": 1710000000.123, ...payload }`

| type | payload | 说明 |
| --- | --- | --- |
| `hello` | `mode, model, workspace, tools, mcp, warning` | 连接建立时的握手信息（仅 WebSocket） |
| `run.start` | `run_id, model, input` | 一轮开始 |
| `status` | `run_id, step, phase` | 阶段性状态（thinking） |
| `assistant.delta` | `run_id, text` | 模型文本增量（流式） |
| `assistant.message` | `run_id, text` | 本轮模型最终回复 |
| `tool.call` | `run_id, step, id, name, args` | 即将调用工具 |
| `tool.result` | `run_id, id, name, ok, output, error, diff, meta, images` | 工具返回结果，含 diff |
| `error` | `run_id, message` | 异常 |
| `run.end` | `run_id, reason, steps` | 结束，`reason ∈ {done, cancelled, max_steps, error}` |
| `session.reset` | - | 会话被清空 |

## 一次真实 trace（离线假模型）

```
[run.start] run_id=3f9c1a2b model=mock
[status] step=1 phase=thinking
（离线假模型）收到：读取 workspace/README.md …
[tool.call ] bash {"command": "dir"}
[tool.result] OK bash
$ dir
[exit_code] 0
[duration] 0.06s
----- stdout -----
README.md
calculator.py
...
[status] step=2 phase=thinking
（离线假模型）工具已返回结果，说明 后端→工具→事件流→前端 全链路打通
[run.end] reason=done steps=2
```

## 自检命令

```bash
# 健康检查
curl http://127.0.0.1:8765/api/health

# 事件流（无界面）
curl -N -X POST http://127.0.0.1:8765/api/run ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"读取 workspace/README.md\"}"

# 或
python scripts/smoke.py --text "读取 workspace/README.md"
```
