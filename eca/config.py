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
    max_turns: int = 0
    output_recovery_limit: int = 0
    context_chars: int = 100_000
    context_window_tokens: int = 32768
    context_reserve_tokens: int = 1024
    command_timeout: int = 120
    request_timeout: int = 120
    output_limit: int = 24_000
    stream_usage: bool = True
    subagent_max_turns: int = 6
    subagent_max_calls: int = 3
    subagent_timeout: int = 180
    subagent_concurrency: int = 2
    shared_request_limit: int = 0
    mcp_servers: dict = field(default_factory=dict, repr=False)
    pricing: dict = field(default_factory=dict)
    lsp_servers: dict = field(default_factory=dict)
    reasoning_effort: str = ""
    thinking_mode: str = "default"
    model_profiles: dict = field(default_factory=dict, repr=False)
    model_profile: str = ""
    worker_profiles: list = field(default_factory=list)
    sandbox: str = 'none'
    sandbox_image: str = 'python:3.11-slim'
    web: dict = field(default_factory=dict)

    @property
    def state_dir(self):
        return self.root / ".eca"

    @classmethod
    def load(cls, root: Path, model_profile=None, **overrides):
        root = root.resolve()
        if not root.is_dir():
            raise ValueError(f"Project directory does not exist: {root}")
        env = {**dotenv_values(root / ".env"), **os.environ}
        config_path = root / "eca.toml"
        data = tomllib.loads(config_path.read_text("utf-8")) if config_path.exists() else {}
        cfg = data.get("agent", {})
        if not isinstance(cfg, dict):
            raise ValueError("[agent] must be a TOML table")
        supported = set(cls.__dataclass_fields__) - {"root", "api_key", "mcp_servers", "pricing", "lsp_servers", "model_profiles", "web"} | {"api_key_env"}
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
            "https://api.openai.com/v1" if api_format == "responses" or (env.get("OPENAI_API_KEY") and not env.get("MODELSCOPE_API_KEY")) else cls.base_url)
        values = dict(root=root, api_key=key,
                      api_format=api_format,
                      model=env.get("ECA_MODEL") or env.get("MODEL_NAME") or cfg.get("model", "" if native else cls.model),
                      base_url=env.get("ECA_BASE_URL") or env.get("ANTHROPIC_BASE_URL" if native else "OPENAI_BASE_URL") or cfg.get("base_url", default_url))
        values.update(mcp_servers=data.get("mcp_servers", {}), pricing=data.get("pricing", {}), lsp_servers=data.get("lsp_servers", {}), model_profiles=data.get("model_profiles", {}), web=data.get("web", {}))
        for name in ("sandbox", "sandbox_image", "reasoning_effort", "thinking_mode", "mode", "permission", "max_turns", "context_chars", "command_timeout", "request_timeout", "output_limit", "max_output_tokens", "network_retries", "auto_compact", "project_memory", "stream_usage", "subagent_max_turns", "subagent_max_calls", "subagent_timeout", "subagent_concurrency", "worker_profiles"):
            if name in cfg:
                values[name] = cfg[name]
        for name in ('context_window_tokens', 'context_reserve_tokens', 'shared_request_limit', 'output_recovery_limit'):
            if name in cfg:
                values[name] = cfg[name]
        selected = model_profile if model_profile is not None else cfg.get('model_profile', '')
        if not isinstance(selected, str):
            raise ValueError('model_profile must be text')
        if selected:
            from .models import select, validate_profiles
            validate_profiles(values['model_profiles'], root)
            profiled = select(cls(**values), selected)
            values = {name: getattr(profiled, name) for name in cls.__dataclass_fields__}
        values.update({k: v for k, v in overrides.items() if v is not None})
        if any(overrides.get(k) is not None for k in ('model', 'base_url', 'api_format')):
            values['model_profile'] = ''
        from .model_limits import apply_defaults
        explicit = set(values['model_profiles'][selected]) if selected else set(cfg)
        explicit |= {k for k, v in overrides.items() if v is not None}
        if selected and any(overrides.get(k) is not None for k in ('model', 'base_url', 'api_format')):
            for name in ('context_window_tokens', 'max_output_tokens'):
                if name not in explicit:
                    values[name] = getattr(cls, name)
        apply_defaults(values, explicit)
        settings = cls(**values)
        settings.validate()
        return settings

    def select_profile(self, name):
        from .models import select
        return select(self, name)

    def validate(self):
        for name in ('max_turns', 'output_recovery_limit'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f'{name} must be a nonnegative integer (0 means unlimited)')
        if type(self.shared_request_limit) is not int or not 0 <= self.shared_request_limit <= 10000:
            raise ValueError('shared_request_limit must be 0..10000 (0 disables the cap)')
        import re
        from .web import validate
        validate(self.web)
        if self.sandbox not in {'none', 'docker'}:
            raise ValueError('sandbox must be none or docker')
        if not isinstance(self.sandbox_image, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9./_:@-]{0,255}', self.sandbox_image):
            raise ValueError('Invalid sandbox image reference')
        from .models import validate_profiles
        validate_profiles(self.model_profiles, self.root)
        if (not isinstance(self.worker_profiles, list) or
            any(not isinstance(name, str) or name not in self.model_profiles for name in self.worker_profiles) or
            len(set(self.worker_profiles)) != len(self.worker_profiles)):
            raise ValueError('worker_profiles must be a unique list of configured model profile names')
        if not isinstance(self.model_profile, str):
            raise ValueError('model_profile must be text')
        from .usage import validate_pricing
        from .mcp_client import validate_servers
        validate_pricing(self.pricing)
        validate_servers(self.mcp_servers)
        if type(self.stream_usage) is not bool:
            raise ValueError("stream_usage must be true or false")
        if not isinstance(self.api_key, str):
            raise ValueError("API key must be text")
        if type(self.network_retries) is not int or not 0 <= self.network_retries <= 5:
            raise ValueError("network_retries must be an integer from 0 to 5")
        if type(self.auto_compact) is not bool:
            raise ValueError("auto_compact must be true or false")
        if type(self.project_memory) is not bool:
            raise ValueError("project_memory must be true or false")
        from .lsp import validate_servers as validate_lsp
        validate_lsp(self.lsp_servers)
        if self.thinking_mode not in {'default', 'fast', 'balanced', 'deep'}:
            raise ValueError('Invalid thinking_mode')
        if self.reasoning_effort not in {"", "none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Invalid reasoning_effort")
        if self.api_format not in {"openai", "anthropic", "responses"}:
            raise ValueError("api_format must be openai, responses or anthropic")
        from .modes import MODES
        if self.mode not in MODES:
            raise ValueError("mode must be " + ", ".join(MODES))
        if self.permission not in {"ask", "accept-edits"}:
            raise ValueError("permission must be ask or accept-edits")
        for name in ("context_chars", "command_timeout", "request_timeout", "output_limit", "max_output_tokens", "subagent_max_turns", "subagent_max_calls", "subagent_timeout", "subagent_concurrency"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.subagent_concurrency > 8:
            raise ValueError("subagent_concurrency must be 1..8")
        for name in ('context_window_tokens', 'context_reserve_tokens'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be a positive integer')
        if self.context_window_tokens <= self.max_output_tokens + self.context_reserve_tokens:
            raise ValueError('context_window_tokens must exceed max_output_tokens + context_reserve_tokens')
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
