"""配置：只从环境变量 / .env 读取，Key 永不进入前端。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = ROOT / "workspace"


def load_env() -> None:
    """加载项目根目录的 .env（不覆盖已存在的环境变量）。"""
    load_dotenv(ROOT / ".env", override=False)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"

    workspace: Path = DEFAULT_WORKSPACE
    max_steps: int = 24
    bash_timeout: int = 30
    max_read_lines: int = 400
    max_output_chars: int = 20000
    mcp_config: Path = ROOT / "mcp.json"
    mock: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        workspace = Path(os.getenv("AGENT_WORKSPACE") or DEFAULT_WORKSPACE).resolve()
        return cls(
            api_key=(os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip(),
            base_url=(os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").strip(),
            model=(os.getenv("LLM_MODEL") or "deepseek-chat").strip(),
            workspace=workspace,
            max_steps=int(os.getenv("AGENT_MAX_STEPS", "24")),
            bash_timeout=int(os.getenv("AGENT_BASH_TIMEOUT", "30")),
            max_read_lines=int(os.getenv("AGENT_MAX_READ_LINES", "400")),
            max_output_chars=int(os.getenv("AGENT_MAX_OUTPUT_CHARS", "20000")),
            mcp_config=Path(os.getenv("AGENT_MCP_CONFIG") or ROOT / "mcp.json").resolve(),
            mock=_as_bool(os.getenv("AGENT_MOCK")),
        )

    def ensure_workspace(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)

    def rel(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.workspace))
        except ValueError:
            return str(path)
