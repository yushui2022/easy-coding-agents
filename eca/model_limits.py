"""Verified defaults for exact official model/endpoint pairs, never proxy guesses.

Source: https://api-docs.deepseek.com/api/list-models/ (2026-10-18).
Explicit user values take precedence. No network requests during configuration.
"""
from urllib.parse import urlsplit


def apply_defaults(values, explicit):
    if not isinstance(values.get('base_url', ''), str):
        return
    url = urlsplit(values.get('base_url', ''))
    if (url.scheme != 'https' or url.hostname != 'api.deepseek.com' or url.port not in (None, 443)
            or url.path.rstrip('/') not in ('', '/v1') or url.username or url.password
            or values.get('model') not in {'deepseek-flash', 'deepseek-v4-pro'}):
        return
    if 'context_window_tokens' not in explicit:
        values['context_window_tokens'] = 1048576
    if 'max_output_tokens' not in explicit:
        # Respect an explicitly smaller local context window, keeping room for input.
        window = values.get('context_window_tokens', 1048576)
        if type(window) is int:
            values['max_output_tokens'] = min(393216, max(1, window // 2))
