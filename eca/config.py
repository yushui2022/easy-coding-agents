"""Explicit, project-scoped configuration. Secrets never enter session files."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import tomllib
from urllib.parse import urlsplit

from dotenv import dotenv_values


@dataclass
class Settings:
    root: Path
    model: str = "Qwen/Qwen2.5-Coder-32B-Instruct"
    base_url: str = "https://api-inference.modelscope.cn/v1"
    api_key: str = field(default="", repr=False)
    mode: str = "code"
    permission: str = "ask"
    max_turns: int = 40
    context_chars: int = 100_000
    command_timeout: int = 120
    request_timeout: int = 120
    output_limit: int = 24_000

    @property
    def state_dir(self):
        return self.root / ".eca"

    @classmethod
    def load(cls, root: Path, **overrides):
        root = root.resolve()
        if not root.is_dir():
            raise ValueError(f"Project directory does not exist: {root}")
        env = {**dotenv_values(root / ".env"), **os.environ}
        config_path = root / "eca.toml"
        data = tomllib.loads(config_path.read_text("utf-8")) if config_path.exists() else {}
        cfg = data.get("agent", {})
        if "api_key" in cfg:
            raise ValueError("Use api_key_env instead of storing a secret in eca.toml")
        key_name = cfg.get("api_key_env")
        key = env.get(key_name, "") if key_name else (env.get("ECA_API_KEY") or env.get("OPENAI_API_KEY") or env.get("MODELSCOPE_API_KEY") or "")
        default_url = "https://api.openai.com/v1" if env.get("OPENAI_API_KEY") and not env.get("MODELSCOPE_API_KEY") else cls.base_url
        values = dict(root=root, api_key=key,
                      model=env.get("ECA_MODEL") or env.get("MODEL_NAME") or cfg.get("model", cls.model),
                      base_url=env.get("ECA_BASE_URL") or env.get("OPENAI_BASE_URL") or cfg.get("base_url", default_url))
        for name in ("mode", "permission", "max_turns", "context_chars", "command_timeout", "request_timeout", "output_limit"):
            if name in cfg:
                values[name] = cfg[name]
        values.update({k: v for k, v in overrides.items() if v is not None})
        settings = cls(**values)
        settings.validate()
        return settings

    def validate(self):
        if self.mode not in {"code", "plan", "chat"}:
            raise ValueError("mode must be code, plan or chat")
        if self.permission not in {"ask", "accept-edits"}:
            raise ValueError("permission must be ask or accept-edits")
        for name in ("max_turns", "context_chars", "command_timeout", "request_timeout", "output_limit"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        url = urlsplit(self.base_url)
        if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.password:
            raise ValueError("base_url must be an HTTP(S) URL without embedded credentials")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model cannot be empty")
