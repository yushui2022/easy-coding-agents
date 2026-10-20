"""Stateless Responses adapter preserving reasoning items and tool identities."""
import json
import hashlib
from .errors import OutputLimitError


def input_items(messages, scope=None, root=None):
    items = []
    for message in messages:
        role = message['role']
        if role == 'tool':
            items.append(dict(type='function_call_output', call_id=message['tool_call_id'], output=message['content']))
        elif role == 'assistant' and message.get('response_items') and (scope is None or message.get('response_scope') == scope):
            items.extend(message['response_items'])
        else:
            if message.get('attachments'):
                from .attachments import content
                items.append(dict(role=role, content=content(message, root, 'responses')))
            elif message.get('content'):
                items.append(dict(role=role, content=message['content']))
            for call in message.get('tool_calls', []):
                items.append(dict(type='function_call', call_id=call['id'], **call['function']))
    return items


async def complete(client, settings, messages, tools, emit, usage_callback):
    scope = hashlib.sha256((settings.base_url+'\0'+settings.model).encode()).hexdigest()
    kwargs = dict(model=settings.model, input=input_items(messages, scope, settings.root), store=False, stream=True,
                  max_output_tokens=settings.max_output_tokens, include=['reasoning.encrypted_content'])
    if tools:
        kwargs['tools'] = [dict(type='function', **t['function'], strict=False) for t in tools]
    if settings.reasoning_effort:
        kwargs['reasoning'] = dict(effort=settings.reasoning_effort)
    stream = await client.responses.create(**kwargs)
    response = None
    names = {}
    try:
        async for event in stream:
            if event.type == 'response.output_text.delta':
                emit('text', event.delta)
            elif event.type == 'response.output_item.added':
                if event.item.type == 'function_call':
                    names[event.output_index] = event.item.name
                    emit('model_delta', {'tool': event.item.name, 'phase': 'tool_arguments'})
                elif event.item.type == 'reasoning':
                    emit('model_delta', {'phase': 'thinking'})
            elif event.type == 'response.function_call_arguments.delta':
                emit('model_delta', {'tool': names.get(event.output_index, ''),
                                    'arguments': event.delta, 'phase': 'tool_arguments'})
            if event.type in {'response.completed', 'response.incomplete', 'response.failed'}:
                response = event.response
                if response.usage:
                    u = response.usage.model_dump()
                    usage_callback(dict(prompt_tokens=u['input_tokens'], completion_tokens=u['output_tokens'],
                                        prompt_tokens_details=u.get('input_tokens_details', {}),
                                        completion_tokens_details=u.get('output_tokens_details', {})))
    finally:
        await stream.close()
    if (response is not None and response.status == 'incomplete' and
            getattr(getattr(response, 'incomplete_details', None), 'reason', None) == 'max_output_tokens'):
        raise OutputLimitError()
    if response is None or response.status != 'completed':
        raise RuntimeError('Incomplete Responses result; no tools executed')
    calls, text, items, ids = [], [], [], set()
    for item in response.output:
        value = item.model_dump(exclude_none=True)
        if item.type == 'function_call':
            if not item.call_id or item.call_id in ids or not item.name or not isinstance(json.loads(item.arguments), dict):
                raise ValueError('Invalid Responses function call')
            ids.add(item.call_id)
            calls.append(dict(id=item.call_id, type='function', function=dict(name=item.name, arguments=item.arguments)))
        elif item.type == 'message':
            for block in item.content:
                if block.type == 'output_text':
                    text.append(block.text)
        elif item.type != 'reasoning':
            raise ValueError('Unsupported Responses output item')
        items.append(value)
    if not text and not calls:
        raise RuntimeError('Empty Responses output')
    message = dict(role='assistant', content=''.join(text) or None, response_items=items, response_scope=scope)
    if calls:
        message['tool_calls'] = calls
    u = response.usage.model_dump() if response.usage else {}
    usage = dict(prompt_tokens=u['input_tokens'], completion_tokens=u['output_tokens'],
                 prompt_tokens_details=u.get('input_tokens_details', {}),
                 completion_tokens_details=u.get('output_tokens_details', {})) if u else {}
    return message, usage
