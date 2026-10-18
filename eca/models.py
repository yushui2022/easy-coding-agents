"""Explicit endpoint profiles. Credentials resolve at use time, never from history."""
from dataclasses import replace
import os
import re
from dotenv import dotenv_values

FIELDS = {'model', 'base_url', 'api_format', 'api_key_env', 'reasoning_effort',
          'max_output_tokens', 'context_chars', 'stream_usage', 'context_window_tokens', 'context_reserve_tokens'}


def validate_profiles(profiles, root):
    from .config import Settings
    if not isinstance(profiles, dict):
        raise ValueError('model_profiles must be a table')
    for name, cfg in profiles.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name) or not isinstance(cfg, dict):
            raise ValueError('Invalid model profile')
        if set(cfg)-FIELDS or not {'model', 'base_url', 'api_format', 'api_key_env'} <= set(cfg):
            raise ValueError('Model profiles require model, base_url, api_format, api_key_env; unknown options rejected')
        if not isinstance(cfg['api_key_env'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', cfg['api_key_env']):
            raise ValueError('Model profile api_key_env must name an environment variable')
        from .model_limits import apply_defaults
        values = {k:v for k,v in cfg.items() if k != 'api_key_env'}
        apply_defaults(values, set(cfg))
        Settings(root=root, **values).validate()


def select(settings, name):
    cfg = settings.model_profiles.get(name)
    if cfg is None:
        raise ValueError('Unknown model profile; configure [model_profiles.NAME]')
    env = {**dotenv_values(settings.root/'.env'), **os.environ}
    result = replace(settings, **{k:v for k,v in cfg.items() if k != 'api_key_env'},
                     api_key=env.get(cfg['api_key_env'], ''), model_profile=name)
    # Reset model-specific optional knobs instead of inheriting another endpoint's values.
    for name, default in [('reasoning_effort', ''), ('stream_usage', True),
                          ('max_output_tokens', 8192), ('context_chars', 100_000),
                          ('context_window_tokens', 32768), ('context_reserve_tokens', 1024)]:
        if name not in cfg:
            setattr(result, name, default)
    from .model_limits import apply_defaults
    limits = {k: getattr(result, k) for k in ('model', 'base_url', 'context_window_tokens', 'max_output_tokens')}
    apply_defaults(limits, set(cfg))
    result.max_output_tokens = limits['max_output_tokens']
    result.context_window_tokens = limits['context_window_tokens']
    result.validate()
    return result


def worker_settings(settings, profile=None):
    """Only explicitly enabled profiles may receive delegated source/context."""
    if profile is None:
        return settings
    if not isinstance(profile, str) or profile not in settings.worker_profiles:
        raise ValueError('Worker model is not enabled in agent.worker_profiles')
    return select(settings, profile)


def delegation_schemas(schemas, settings):
    if not settings.worker_profiles:
        return schemas
    from copy import deepcopy
    result = deepcopy(schemas)
    option = {'type': 'string', 'enum': list(settings.worker_profiles),
              'description': 'Optional worker model profile; omit to use the current main model.'}
    for schema in result:
        fn = schema['function']
        if fn['name'] == 'delegate':
            fn['parameters']['properties']['model_profile'] = option
        elif fn['name'] == 'delegate_parallel':
            fn['parameters']['properties']['tasks']['items']['properties']['model_profile'] = option
    return result
