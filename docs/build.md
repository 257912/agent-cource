# 打包与发布（Release）

## 1. 本地开发

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e .[desktop,dev]  # desktop=pywebview, dev=pyinstaller
cp .env.example .env           # 填入 OPENAI_API_KEY（.env 绝不入库）
python main.py                 # 弹出桌面窗口
```

没有 Key 也能跑：`.env` 里设 `AGENT_MOCK=1`，使用离线假模型验证全链路。

## 2. 打安装包

```bash
pip install pyinstaller
python scripts/build.py
# 产物：dist/MiniCursor.exe（Windows）
```

macOS 建议 `--onedir` 生成 `.app`，再用 `hdiutil` 打 dmg；Windows 可直接把 exe 作为 Release 附件。

## 3. 发 Release

```bash
git tag v1.0.0
git push origin main --tags
# GitHub → Releases → New release → 选择 v1.0.0 → 上传 dist 里的安装包
```

README 顶部要给出 Release 下载链接，保证「三步内能启动」：
下载 → 双击 → 填 Key。

## 4. 常见坑

- **.env 入库**：提交前 `git status` 确认没有 `.env`；若误提交需重写历史。
- **前端直连模型**：本项目所有模型请求都在后端进程里，前端只拿事件流。
- **Windows 下 bash 工具**：走 `cmd.exe`，`ls` 要换成 `dir`。
- **打包后找不到 ui**：`--add-data ui;ui` 必须带上（build.py 已处理）。
