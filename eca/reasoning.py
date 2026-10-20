"""Desktop reasoning controls. Unknown models keep their provider defaults."""
import hashlib
import re
from dataclasses import replace


def describe(settings):
    get = settings.get if isinstance(settings, dict) else lambda key, default='': getattr(settings, key, default)
    model, protocol = get('model', '').lower(), get('api_format', 'openai')
    options, note = ['default'], ''
    if protocol in {'openai', 'responses'}:
        if re.fullmatch(r'deepseek-(?:flash|v4(?:\.1)?-(?:flash|pro))(?:-.*)?', model):
            options += ['none', 'low', 'medium', 'high', 'max']
            note = 'DeepSeek 的 medium 由服务端按 high 处理。'
        elif re.fullmatch(r'gpt-6(?:\.1)?-(?:astra|sol|luna)(?:-\d{4}-\d\d-\d\d)?', model):
            if protocol == 'responses':
                options += ([] if 'astra' in model or '6.1' in model else ['none']) + ['low', 'medium', 'high', 'xhigh', 'max']
            elif 'astra' not in model and '6.1' not in model:
                options += ['none']
                note = '此系列在 Chat Completions 下调用工具需关闭推理；完整档位请使用 Responses 协议。'
        elif re.fullmatch(r'gpt-5\.6(?:-\d{4}-\d\d-\d\d)?', model):
            options += ['none', 'low', 'medium', 'high', 'xhigh', 'max']
        elif re.fullmatch(r'gpt-5\.[245](?:-\d{4}-\d\d-\d\d)?', model):
            options += ['none', 'low', 'medium', 'high', 'xhigh']
        elif re.fullmatch(r'gpt-5\.1(?:-\d{4}-\d\d-\d\d)?', model):
            options += ['none', 'low', 'medium', 'high']
        elif re.fullmatch(r'gpt-5(?:-(?:mini|nano))?(?:-\d{4}-\d\d-\d\d)?', model):
            options += ['minimal', 'low', 'medium', 'high']
        elif re.fullmatch(r'(?:o1|o3|o3-mini|o4-mini)(?:-\d{4}-\d\d-\d\d)?', model):
            options += ['low', 'medium', 'high']
    value = get('reasoning_effort') or 'default'
    if protocol == 'openai' and model.startswith('deepseek'):
        value = {'fast': 'none', 'balanced': 'low', 'deep': 'high'}.get(get('thinking_mode'), value)
    if protocol == 'anthropic':
        value = 'default'  # The current native adapter does not send an effort field.
    if len(options) == 1:
        note = '此模型暂未接入强度切换，继续使用现有服务配置。'
    return {'value': value, 'options': options, 'note': note}


def with_effort(settings, effort):
    if not isinstance(effort, str) or effort not in describe(settings)['options']:
        raise ValueError('此模型不支持所选推理强度。')
    return replace(settings, thinking_mode='default', reasoning_effort='' if effort == 'default' else effort)


def identity(settings):
    return hashlib.sha256(f'{settings.api_format}|{settings.base_url.rstrip("/")}|{settings.model}'.encode()).hexdigest()


def restore(settings, state):
    value = state.get('desktop_reasoning', {}).get(identity(settings))
    return with_effort(settings, value) if value in describe(settings)['options'] else settings


async def change(agent, effort):
    """Only replace the provider; keep permissions, tools, budget and conversation."""
    from .provider import Provider
    settings = with_effort(agent.settings, effort)
    settings.validate()
    await agent.provider.close()
    agent.settings = settings
    agent.tools.settings = settings
    agent.provider = Provider(settings)
    saved = dict(agent.state.get('desktop_reasoning', {}))
    saved.pop(identity(settings), None)
    saved[identity(settings)] = effort
    agent.state['desktop_reasoning'] = dict(list(saved.items())[-32:])
    agent.store.save(agent.state)
