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
    api_format: str = "openai"
    max_output_tokens: int = 8192
    network_retries: int = 2
    auto_compact: bool = True
    project_memory: bool = True
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
        if not isinstance(cfg, dict):
            raise ValueError("[agent] must be a TOML table")
        supported = set(cls.__dataclass_fields__) - {"root", "api_key"} | {"api_key_env"}
        if "api_key" in cfg:
            raise ValueError("Use api_key_env instead of storing a secret in eca.toml")
        if set(cfg) - supported:
            raise ValueError("Unknown [agent] option; compare eca.toml with eca.example.toml")
        key_name = cfg.get("api_key_env")
        if key_name is not None and (not isinstance(key_name, str) or not key_name.strip()):
            raise ValueError("api_key_env must be a nonempty environment variable name")
        api_format = overrides.get("api_format") or env.get("ECA_API_FORMAT") or cfg.get("api_format", "openai")
        native = api_format == "anthropic"
        key = env.get(key_name, "") if key_name else (env.get("ECA_API_KEY") or
            (env.get("ANTHROPIC_API_KEY") if native else (env.get("OPENAI_API_KEY") or env.get("MODELSCOPE_API_KEY"))) or "")
        default_url = "https://api.anthropic.com/v1" if native else (
            "https://api.openai.com/v1" if env.get("OPENAI_API_KEY") and not env.get("MODELSCOPE_API_KEY") else cls.base_url)
        values = dict(root=root, api_key=key,
                      api_format=api_format,
                      model=env.get("ECA_MODEL") or env.get("MODEL_NAME") or cfg.get("model", "" if native else cls.model),
                      base_url=env.get("ECA_BASE_URL") or env.get("ANTHROPIC_BASE_URL" if native else "OPENAI_BASE_URL") or cfg.get("base_url", default_url))
        for name in ("mode", "permission", "max_turns", "context_chars", "command_timeout", "request_timeout", "output_limit", "max_output_tokens", "network_retries", "auto_compact", "project_memory"):
            if name in cfg:
                values[name] = cfg[name]
        values.update({k: v for k, v in overrides.items() if v is not None})
        settings = cls(**values)
        settings.validate()
        return settings

    def validate(self):
        if not isinstance(self.api_key, str):
            raise ValueError("API key must be text")
        if type(self.network_retries) is not int or not 0 <= self.network_retries <= 5:
            raise ValueError("network_retries must be an integer from 0 to 5")
        if type(self.auto_compact) is not bool:
            raise ValueError("auto_compact must be true or false")
        if type(self.project_memory) is not bool:
            raise ValueError("project_memory must be true or false")
        if self.api_format not in {"openai", "anthropic"}:
            raise ValueError("api_format must be openai or anthropic")
        if self.mode not in {"code", "plan", "chat"}:
            raise ValueError("mode must be code, plan or chat")
        if self.permission not in {"ask", "accept-edits"}:
            raise ValueError("permission must be ask or accept-edits")
        for name in ("max_turns", "context_chars", "command_timeout", "request_timeout", "output_limit", "max_output_tokens"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.base_url, str):
            raise ValueError("base_url must be text")
        url = urlsplit(self.base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("base_url must be an HTTP(S) URL without credentials, query parameters or fragments")
        try:
            url.port
        except ValueError:
            raise ValueError("base_url has an invalid port") from None
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model cannot be empty; set ECA_MODEL, --model or agent.model")
