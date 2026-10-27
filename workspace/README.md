# 工作区（Agent 的沙盒）

MiniCursor 的 `read / write / edit / bash` 全部被限制在这个目录内，
任何 `../` 越界路径都会被直接拒绝。

## 里面有什么

- `calculator.py`：一个故意留了 bug 的小计算器，适合现场演示「读文件 → 定位 bug → edit 修复 → bash 跑测试」。
- 你可以随时往这里放自己的项目，让 Agent 帮你改。
