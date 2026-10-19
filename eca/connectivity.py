"""One bounded, explicit API probe. No project content, tools, redirects or retry."""
import asyncio
import json
import time

import httpx


async def list_models(settings, transport=None):
    """Fetch catalogue metadata only; explicit endpoint, bounded response, no redirects."""
    result = {'status': 'error', 'models': [], 'message': '', 'partial': False}
    if not settings.api_key:
        return {**result, 'message': '请先输入 API 密钥。'}
    headers = {'Authorization': 'Bearer ' + settings.api_key}
    params = {}
    if settings.api_format == 'anthropic':
        headers = {'x-api-key': settings.api_key, 'anthropic-version': '2023-06-01'}
        params = {'limit': 1000}
    try:
        async with asyncio.timeout(20):
            async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=transport) as client:
                async with client.stream('GET', settings.base_url.rstrip('/') + '/models', headers=headers, params=params) as response:
                    if response.status_code != 200:
                        return {**result, 'message': {401: '密钥无效，请检查后重试。', 403: '此密钥无权查看模型列表。',
                            404: '服务不提供模型列表，请手动填写模型 ID。', 429: '请求过于频繁，请稍后重试。'}.get(response.status_code,
                            '无法获取模型列表（HTTP %s），仍可手动填写模型 ID。' % response.status_code)}
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1024 * 1024:
                            return {**result, 'message': '模型列表超过 1 MiB，请手动填写模型 ID。'}
                    data = json.loads(raw)
                    if not isinstance(data, dict) or not isinstance(data.get('data'), list):
                        return {**result, 'message': '服务返回的模型列表格式不兼容，请手动填写模型 ID。'}
                    ids = []
                    for item in data['data']:
                        ident = item.get('id') if isinstance(item, dict) else None
                        if isinstance(ident, str) and ident.strip() and len(ident) <= 256 and not any(ord(c) < 32 for c in ident) and ident not in ids:
                            ids.append(ident)
                    partial = bool(data.get('has_more')) or len(ids) > 500
                    return {'status': 'ok', 'models': sorted(ids[:500]), 'partial': partial,
                            'message': '已读取部分模型，其他模型可手动输入。' if partial else '已获取可用模型。'}
    except (httpx.TimeoutException, TimeoutError):
        result['message'] = '读取模型列表超时，请检查地址或手动填写模型 ID。'
    except (httpx.RequestError, ImportError):
        result['message'] = '无法连接模型服务，请检查地址、网络或代理。'
    except (ValueError, TypeError):
        result['message'] = '服务未返回有效的模型列表，请手动填写模型 ID。'
    return result


async def check_api(settings, transport=None):
    if not settings.api_key:
        return {'name': 'api_connection', 'status': 'error', 'message': 'API key is missing; request not sent.', 'request_sent': False}
    headers = {'Authorization': 'Bearer ' + settings.api_key}
    message = {'role': 'user', 'content': 'Reply OK.'}
    if settings.api_format == 'anthropic':
        route = '/messages'
        headers = {'x-api-key': settings.api_key, 'anthropic-version': '2023-06-01'}
        payload = {'model': settings.model, 'messages': [message], 'max_tokens': 16}
    elif settings.api_format == 'responses':
        route = '/responses'
        payload = {'model': settings.model, 'input': [message], 'max_output_tokens': 16}
    else:
        route = '/chat/completions'
        payload = {'model': settings.model, 'messages': [message], 'max_tokens': 16, 'stream': False}
        if settings.model.lower().startswith('deepseek') and settings.thinking_mode != 'default':
            payload['thinking'] = {'type': 'disabled' if settings.thinking_mode == 'fast' else 'enabled'}
            if settings.thinking_mode != 'fast':
                payload['reasoning_effort'] = 'low' if settings.thinking_mode == 'balanced' else 'high'
    result = {'name': 'api_connection', 'status': 'error', 'request_sent': True,
              'cost': 'unknown', 'message': 'API probe failed.'}
    start = time.perf_counter()
    try:
        async with asyncio.timeout(25):
            async with httpx.AsyncClient(timeout=20, follow_redirects=False, transport=transport) as client:
                async with client.stream('POST', settings.base_url.rstrip('/') + route, headers=headers, json=payload) as response:
                    result['http_status'] = response.status_code
                    if response.status_code != 200:
                        result['message'] = ({401: 'Authentication failed; check the API key.', 403: 'Access denied; check model/account permissions.',
                            404: 'Endpoint or model not found; check base URL, protocol and model ID.',
                            429: 'Rate limit or account quota reached.'}.get(response.status_code,
                            'API rejected the probe; check protocol, model and its output-token requirements. No retry was made.'))
                        return result
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 65536:
                            result['message'] = 'Response exceeded the 64 KiB diagnostic limit.'
                            return result
                    data = json.loads(raw)
                    valid = isinstance(data, dict) and not data.get('error')
                    if valid and settings.api_format == 'openai':
                        choices = data.get('choices')
                        valid = isinstance(choices, list) and bool(choices) and isinstance(choices[0], dict) and isinstance(choices[0].get('message'), dict)
                    elif valid and settings.api_format == 'anthropic':
                        valid = data.get('type') == 'message' and isinstance(data.get('content'), list)
                    elif valid:
                        valid = data.get('status') in {'completed', 'incomplete'} and isinstance(data.get('output'), list)
                    if not valid:
                        result['message'] = 'Response does not match the configured protocol.'
                        return result
                    result.update(status='ok', message='API returned a protocol-shaped response. Streaming and tool calling were not tested.')
                    usage = data.get('usage')
                    if isinstance(usage, dict):
                        result['usage'] = {k: v for k, v in usage.items() if k in {'input_tokens', 'output_tokens', 'prompt_tokens', 'completion_tokens', 'total_tokens'} and type(v) is int and v >= 0}
    except (httpx.TimeoutException, TimeoutError):
        result['message'] = 'API request timed out; no retry was made.'
    except httpx.RequestError:
        result['message'] = 'Connection failed; check DNS, TLS, proxy and endpoint reachability.'
    except ImportError:
        result['message'] = 'Proxy support is unavailable; reinstall ECA with its declared dependencies (httpx[socks]).'
    except (ValueError, TypeError):
        result['message'] = 'API returned an invalid JSON response.'
    finally:
        result['elapsed_ms'] = round((time.perf_counter() - start) * 1000, 2)
    return result
