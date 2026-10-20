"""ECA desktop protocol v1. JSON-RPC over private stdio, never a listening server."""
import asyncio
import hashlib
from collections import deque
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import threading
import uuid
import time

from . import __version__
from .agent import Agent
from .config import Settings
from .connectivity import check_api, list_models
from .doctor import diagnose
from .runtime import Runtime
from .store import Store
from .workflow import suite_status
from . import reasoning
from .activity import tool_target

PROTOCOL = 1
MODEL_FIELDS = {'model', 'base_url', 'api_format', 'api_key', 'thinking_mode', 'reasoning_effort'}


class DesktopRPC:
    def __init__(self, send):
        self.send_raw = send
        self.backend_id = uuid.uuid4().hex
        self.runtime = None
        self.run_id = None
        self.pending = {}
        self.stream = ''
        self.stream_id = 0
        self.events = deque(maxlen=200)
        self.secrets = {v for k, v in os.environ.items() if ('KEY' in k or 'TOKEN' in k) and len(v) >= 8}
        self.ready = False
        self.closed = False
        self.lock = asyncio.Lock()
        self.finishing = None
        self.model_override = {}
        self.source = 'project'
        self.sequence = 0
        self.activity = {}
        self.last_request = {}
        self.started_at = None
        self.approval_mode = 'ask'
        from .side_chat import SideChats
        self.side_chats = SideChats(self)
        from .child_activity import ChildViews
        self.child_views = ChildViews(self)

    def safe(self, value):
        text = json.dumps(value, ensure_ascii=False)
        for secret in self.secrets:
            text = text.replace(json.dumps(secret, ensure_ascii=False)[1:-1], '[redacted]')
        return json.loads(text)

    def send(self, value):
        try:
            self.send_raw(self.safe(value))
        except (BrokenPipeError, OSError):
            # Parent may already be gone; EOF still cancels work and closes tools.
            pass

    def emit(self, event, data):
        if event == 'subagent_progress':
            self.child_views.update(data)
        self.sequence += 1
        if event == 'request_start':
            self.activity = {'phase': 'waiting_model', 'since': time.time(), 'request_id': data['id']}
        elif event == 'model_activity':
            if data.get('request_id') and data['request_id'] != self.activity.get('request_id'):
                return
            self.activity = {**self.activity, **data}
        elif event == 'request_end':
            self.last_request = data
            if data['id'] == self.activity.get('request_id'):
                self.activity = {**self.activity, **{k: v for k, v in data.items()
                    if k not in {'id', 'usage', 'status', 'elapsed_ms'}}}
        elif event == 'tool':
            self.activity = {'phase': 'executing', 'tool': data.get('name', ''),
                             'target': tool_target(self.safe(data.get('args'))), 'since': time.time()}
            # The assistant message is saved before tools run. Its live copy
            # must disappear, including while a delegated task is still running.
            self.stream = ''
            self.stream_id += 1
        elif event == 'input_requested':
            self.activity = {**self.activity, 'phase': 'approval' if data['kind'] == 'approval' else 'question', 'since': time.time()}
        elif event == 'input_closed':
            self.activity = {**self.activity, 'phase': 'executing', 'since': time.time()}
        elif event == 'result':
            self.activity = {**self.activity, 'phase': 'tool_done', 'since': time.time()}
        elif event == 'verification_progress' and data.get('status') in {'running', 'repairing'}:
            self.activity = {'phase': 'repairing' if data['status'] == 'repairing' else 'verifying', 'since': time.time()}
        if event == 'turn':
            self.stream = ''
            self.stream_id += 1
        elif event == 'text':
            self.stream += data
        elif event != 'model_activity' and not (event == 'subagent_progress' and data['event'] in {'text', 'model_activity'}):
            self.events.append({'event': event, 'data': self.safe(data), 'seq': self.sequence})
        self.send({'jsonrpc': '2.0', 'method': 'event', 'params': {
            'event': event, 'data': data, 'seq': self.sequence, 'run_id': self.run_id,
            'session_id': self.runtime.agent.state['id'] if self.runtime else None}})

    async def ask(self, kind, message, detail=None):
        ident = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        entry = {'id': ident, 'kind': kind, 'message': message, 'detail': detail,
                 'run_id': self.run_id, 'session_id': self.runtime.agent.state['id']}
        self.pending[ident] = (entry, future)
        self.emit('input_requested', entry)
        try:
            return await future
        finally:
            self.pending.pop(ident, None)
            self.emit('input_closed', {'id': ident})

    async def approve(self, message, detail):
        if self.auto_approve(message):
            self.emit('approval_auto', {'message': message, 'mode': self.approval_mode})
            return True
        return await self.ask('approval', message, detail)

    def auto_approve(self, message):
        # These labels are generated by the tool layer, never supplied by a model.
        edit = message.startswith(('Write ', 'Delete ')) or message == 'Apply LSP rename?'
        return self.approval_mode == 'full-access' or (self.approval_mode == 'accept-edits' and edit)

    @staticmethod
    def message_ref(message):
        public = {k:v for k,v in message.items() if k in {'role','content','tool_calls','tool_call_id'}}
        return hashlib.sha256(json.dumps(public, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def public_messages(messages, start=0, preview=False):
        rows = []
        for index, message in enumerate(messages, start):
            row = {k: v for k, v in message.items() if k in {'role', 'content', 'tool_calls', 'tool_call_id'}}
            if message.get('reasoning_content'):
                # Thinking is shown in the conversation, bounded; provider replay data
                # still only travels back to the same model and endpoint.
                row['reasoning_content'] = message['reasoning_content'][:8000]
            if message.get('attachments'):
                from .attachments import public
                row['attachments'] = public(message['attachments'])
            if preview:
                row['message_index'] = index
                limit = 2000 if row.get('role') == 'tool' else 24000
                content = row.get('content')
                if row.get('role') == 'tool' and isinstance(content, str):
                    try:
                        data = json.loads(content)
                        if isinstance(data, dict):
                            row['tool_summary'] = {key:data[key] for key in ('exit_code','timed_out') if key in data}
                    except ValueError:
                        pass
                if isinstance(content, str) and len(content) > limit:
                    row['content'] = content[:limit]
                    row['truncated'] = True
                if row.get('tool_calls'):
                    row['tool_calls'] = json.loads(json.dumps(row['tool_calls']))
                    for call in row['tool_calls']:
                        value = call.get('function', {}).get('arguments', '')
                        if len(value) > 2000:
                            call['function']['arguments'] = value[:2000]
                            row['truncated'] = True
                if row.get('truncated'):
                    row['message_ref'] = DesktopRPC.message_ref(message)
            rows.append(row)
        return rows
    async def compact_context(self):
        """User-triggered compaction; refuses mid-turn and never drops history."""
        agent = self.runtime.agent if self.runtime else None
        if not agent:
            raise ValueError('Open a project before compacting')
        if self.run_id is not None or agent.busy:
            raise ValueError('Cannot compact while a turn is running')
        before = self.context_usage() or {}
        await agent.compact()
        self._context_usage = None
        after = self.context_usage() or {}
        removed = max(0, int(before.get('estimated_tokens') or 0) - int(after.get('estimated_tokens') or 0))
        self.emit('notice', f'Context compacted on request; roughly {removed} estimated tokens freed. '
                            'The full history remains on disk.')
        return {'before_tokens': before.get('estimated_tokens'), 'after_tokens': after.get('estimated_tokens'),
                'ratio': after.get('ratio'), 'summary_chars': len(agent.state.get('summary') or ''),
                'context': after}


    def context_usage(self):
        """Local estimate of the current request against the budget; never billing.

        Recomputed at most every two seconds and only when the session, message
        count, stream or mode changes, so the 80 ms live polling stays cheap.
        """
        agent = self.runtime.agent if self.runtime else None
        if not agent:
            return None
        try:
            key = (agent.state['id'], len(agent.state['messages']), len(self.stream), agent.settings.mode)
            cached = getattr(self, '_context_usage', None)
            now = time.time()
            if cached and cached[0] == key and now - cached[1] < 2:
                return cached[2]
            tools = agent.tool_schemas()
            used = agent.context_budget.estimate(agent.raw_context(), tools)
            limit = agent.context_budget.input_limit
            value = {'estimated_tokens': int(used), 'input_limit': int(limit),
                     'ratio': (used / limit) if limit else 0.0,
                     'auto_compact': bool(agent.settings.auto_compact), 'estimated': True}
            self._context_usage = (key, now, value)
            return value
        except Exception:
            return None

    def live(self, params=None):
        agent = self.runtime.agent if self.runtime else None
        result = {'backend_id': self.backend_id, 'project': str(agent.settings.root) if agent else None,
            'session_id': agent.state['id'] if agent else None, 'run_id': self.run_id,
            'status': agent.state['status'] if agent else 'idle', 'busy': self.run_id is not None,
            'stream': self.stream, 'stream_id': self.stream_id, 'stream_offset': len(self.stream),
            'activity': self.activity, 'last_request': self.last_request,
            'started_at': self.started_at, 'approval_mode': self.approval_mode,
                 'context': self.context_usage(),
            'side_busy': self.side_chats.busy,
            'pending': [entry for entry, future in self.pending.values() if not future.done()], 'seq': self.sequence}
        params = params or {}
        offset = params.get('stream_offset')
        if (self.safe(self.stream) == self.stream and params.get('stream_id') == self.stream_id and type(offset) is int
                and 0 <= offset <= len(self.stream)):
            result['stream_delta'] = self.stream[offset:]
            del result['stream']
        return self.safe(result)

    async def question(self, message):
        return await self.ask('question', message)

    def model(self, value):
        if not isinstance(value, dict) or set(value) - MODEL_FIELDS:
            raise ValueError('Invalid model configuration')
        if any(not isinstance(v, str) for v in value.values()):
            raise ValueError('Model configuration must contain strings')
        if value.get('api_key'):
            self.secrets.add(value['api_key'])
        return value

    def require(self):
        if not self.runtime:
            raise ValueError('Open a project first.')
        return self.runtime

    def idle(self):
        runtime = self.require()
        runtime.idle()
        if self.run_id is not None:
            raise ValueError('Task cleanup is still running.')
        return runtime

    def snapshot(self, preview=False):
        if not self.runtime:
            return {'backend_id': self.backend_id, 'project': None, 'busy': False, 'sessions': [], 'pending': [], 'events': [],
                    'messages': [], 'message_total': 0, 'changes': [], 'tasks': [], 'seq': self.sequence}
        runtime = self.runtime
        agent = runtime.agent
        state = agent.state
        messages = state['messages']
        return self.safe({'project': str(agent.settings.root), 'session_id': state['id'],
            'busy': self.run_id is not None, 'run_id': self.run_id, 'status': state['status'],
            'messages': self.public_messages(messages[-50:], max(0,len(messages)-50), preview), 'message_total': len(messages), 'stream': self.stream,
            'events': self.event_previews() if preview else list(self.events), 'seq': self.sequence, 'tasks': state['tasks'],
            **self.live(),
            'sessions': [{'id': i, 'title': t, 'updated': u} for i, t, u in agent.store.list(top_level=True)],
            'changes': agent.changes.list(), 'usage': agent.ledger.summary(state),
            'children': self.child_views.summaries(),
            'verification': agent.verification_status() if not self.run_id else state.get('verification', {}),
            'suite': suite_status(agent) if not self.run_id else state.get('verification_suite', {}),
            'change_impact': state.get('change_impact', []),
            'settings': {'model': agent.settings.model, 'base_url': agent.settings.base_url,
                         'api_format': agent.settings.api_format, 'source': self.source,
                         'mode': agent.settings.mode, 'thinking_mode': agent.settings.thinking_mode,
                         'reasoning': reasoning.describe(agent.settings),
                         'credential_configured': bool(agent.settings.api_key)}})

    def event_previews(self):
        # Detailed results remain in session history; the activity list is navigation.
        rows = []
        for entry in self.events:
            data = entry['data']
            text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
            rows.append({**entry, 'data': text[:2000], 'truncated': len(text)>2000})
        return rows

    async def finish(self, task):
        try:
            await task
        except asyncio.CancelledError:
            self.emit('notice', 'Task stopped; completed changes were preserved.')
        except Exception as exc:
            self.runtime.agent.state['status'] = 'error'
            self.runtime.agent.state['stop_reason'] = f'{type(exc).__name__}: task failed; inspect saved progress before continuing.'
            self.runtime.agent.store.save(self.runtime.agent.state)
            self.emit('error', str(exc))
        finally:
            self.stream = ''
            self.stream_id += 1
            self.activity = {}
            self.emit('run_finished', {'status': self.runtime.agent.state['status']})
            self.run_id = None

    async def dispatch(self, method, params):
        if method == 'initialize':
            if params.get('protocol') != PROTOCOL:
                raise ValueError('Incompatible desktop protocol; install matching app and runtime versions.')
            self.ready = True
            return {'protocol': PROTOCOL, 'version': __version__, 'capabilities': ['sidechat']}
        if not self.ready:
            raise ValueError('Initialize protocol first.')
        if method == 'snapshot':
            return self.snapshot(preview=params.get('preview') is True)
        if method == 'live':
            return self.live(params)
        if method == 'context.compact':
            return await self.compact_context()
        if method == 'subagent.snapshot':
            return self.child_views.snapshot(params)
        if method == 'permissions.set':
            self.require()
            mode = params.get('mode')
            if mode not in {'ask', 'accept-edits', 'full-access'}:
                raise ValueError('Invalid approval mode')
            self.approval_mode = mode
            self.emit('permissions_changed', {'mode': mode})
            for entry, future in list(self.pending.values()):
                if entry['kind'] == 'approval' and not future.done() and self.auto_approve(entry['message']):
                    self.emit('approval_auto', {'message': entry['message'], 'mode': mode})
                    future.set_result(True)
            return self.live()
        if method == 'task.cancel':
            runtime = self.require()
            if not self.run_id or params.get('run_id') != self.run_id:
                raise ValueError('Run is no longer active.')
            runtime.cancel()
            return {'cancelling': True}
        if method == 'input.reply':
            pair = self.pending.get(params.get('id'))
            if not pair or pair[0]['run_id'] != params.get('run_id') or pair[1].done():
                raise ValueError('Input request expired or was already answered.')
            value = params.get('value')
            if pair[0]['kind'] == 'approval' and type(value) is not bool:
                raise ValueError('Approval must be a boolean.')
            if pair[0]['kind'] == 'question' and not isinstance(value, str):
                raise ValueError('Answer must be text.')
            pair[1].set_result(value)
            return {'accepted': True}
        if method == 'model.capabilities':
            models = params.get('models', [])
            if not isinstance(models, list) or len(models) > 500 or any(not isinstance(m, dict) for m in models):
                raise ValueError('Invalid model list')
            return [reasoning.describe(m) for m in models]
        if method in {'connection.check', 'connection.models'}:
            model = self.model(params.get('model', {}))
            root = Path(params.get('root') or (self.runtime.agent.settings.root if self.runtime else Path.cwd()))
            settings = Settings.load(root, **model)
            return await (list_models(settings) if method == 'connection.models' else check_api(settings))
        async with self.lock:
            if method.startswith('sidechat.'):
                return await self.side_chats.dispatch(method, params)
            if method == 'model.select' and self.side_chats.busy:
                raise ValueError('侧边聊天仍在运行，请先停止或等待完成。')
            if method in {'project.open', 'project.close', 'session.switch'}:
                if self.side_chats.busy:
                    raise ValueError('侧边聊天仍在运行，请先停止或等待完成。')
                await self.side_chats.close()
            if method == 'project.open':
                if self.runtime:
                    self.idle()
                root = Path(params['path']).resolve()
                model = self.model(params.get('model', {}))
                settings = Settings.load(root, **model)
                self.secrets.add(settings.api_key) if settings.api_key else None
                if self.runtime:
                    await self.runtime.close()
                    self.runtime = None
                store = Store(root)
                try:
                    rows = store.list(top_level=True)
                    state = store.load(rows[0][0]) if rows else store.create(settings.mode)
                    if state.get('model_profile') and not model:
                        settings = settings.select_profile(state['model_profile'])
                    if state.get('sandbox'):
                        settings = replace(settings, sandbox=state['sandbox'], sandbox_image=state.get('sandbox_image', settings.sandbox_image))
                    initial_permission = settings.permission
                    # Keep callbacks active so changing modes also affects running children.
                    settings = replace(settings, mode=state.get('mode', settings.mode), permission='ask')
                    settings = reasoning.restore(settings, state)
                    settings.validate()
                    if settings.api_key:
                        self.secrets.add(settings.api_key)
                    self.runtime = Runtime(Agent(settings, store, state, self.approve, self.question, self.emit,
                                                 child=bool(state.get('parent_id'))))
                except BaseException:
                    store.close()
                    raise
                self.model_override = model
                self.source = 'desktop' if model else 'project/environment'
                self.approval_mode = initial_permission
                self.activity, self.last_request, self.started_at = {}, {}, None
                self.stream = ''
                self.stream_id += 1
                self.events.clear()
                return self.snapshot(preview=params.get('preview') is True)
            if method == 'project.close':
                self.idle()
                await self.runtime.close()
                self.runtime = None
                return self.snapshot()
            if method == 'session.switch':
                runtime = self.idle()
                base = replace(Settings.load(runtime.agent.settings.root, **self.model_override), permission='ask')
                await runtime.switch(params.get('id'), base_settings=base, restore_model_profile=not self.model_override)
                restored = reasoning.restore(runtime.agent.settings, runtime.agent.state)
                if restored != runtime.agent.settings:
                    await reasoning.change(runtime.agent, reasoning.describe(restored)['value'])
                runtime.agent.settings.permission = 'ask'
                if runtime.agent.settings.api_key:
                    self.secrets.add(runtime.agent.settings.api_key)
                self.source = 'desktop' if self.model_override else 'project/environment'
                self.stream = ''
                self.stream_id += 1
                self.events.clear()
                return self.snapshot(preview=params.get('preview') is True)
            if method == 'session.message':
                runtime = self.require()
                state = runtime.agent.state if params['id'] == runtime.agent.state['id'] else runtime.agent.store.peek(params['id'])
                index = params.get('index')
                if type(index) is not int or not 0 <= index < len(state['messages']):
                    raise ValueError('Invalid message index')
                if params.get('message_ref') and params['message_ref'] != self.message_ref(state['messages'][index]):
                    raise ValueError('Session history changed; refresh before loading this record.')
                return self.safe(self.public_messages([state['messages'][index]], index)[0])
            if method == 'session.messages':
                runtime = self.require()
                state = runtime.agent.state if params['id'] == runtime.agent.state['id'] else runtime.agent.store.peek(params['id'])
                before = params.get('before', len(state['messages']))
                if type(before) is not int or before < 0:
                    raise ValueError('Invalid message cursor')
                before = min(before, len(state['messages']))
                return self.safe({'messages': self.public_messages(state['messages'][max(0, before-50):before], max(0,before-50), params.get('preview') is True), 'before': max(0, before-50)})
            if method == 'task.start':
                runtime = self.idle()
                self.run_id = uuid.uuid4().hex
                self.events.clear()
                self.stream = ''
                self.stream_id += 1
                self.started_at = time.time()
                self.activity = {'phase': 'preparing', 'since': self.started_at}
                self.last_request = {}
                try:
                    task = runtime.start(params.get('prompt'), params.get('checks', []), params.get('repair_attempts', 0), attachments=params.get('attachments', []))
                except BaseException:
                    self.run_id = None
                    raise
                self.finishing = asyncio.create_task(self.finish(task))
                return {'run_id': self.run_id, 'session_id': runtime.agent.state['id']}
            if method == 'model.reasoning':
                agent = self.idle().agent
                if params.get('session_id') != agent.state['id']:
                    raise ValueError('Session changed; reopen model selection.')
                await reasoning.change(agent, params.get('effort'))
                return self.snapshot(preview=True)
            if method == 'model.select':
                runtime = self.idle()
                old = runtime.agent
                model = self.model(params.get('model', {}))
                settings = old.settings.select_profile(params['profile']) if params.get('profile') else Settings.load(old.settings.root, **model)
                # Selecting a model must not silently change the execution boundary.
                settings = replace(settings, mode=old.settings.mode, permission=old.settings.permission,
                                   sandbox=old.settings.sandbox, sandbox_image=old.settings.sandbox_image)
                settings = reasoning.restore(settings, old.state)
                if settings.api_key:
                    self.secrets.add(settings.api_key)
                await old.close()
                state = old.state
                if settings.model_profile:
                    state['model_profile'] = settings.model_profile
                else:
                    state.pop('model_profile', None)
                old.store.save(state)
                runtime.agent = Agent(settings, old.store, state, self.approve, self.question, self.emit, child=old.child)
                runtime.agent.budget = old.budget
                self.model_override = model
                self.source = 'desktop' if model else 'project/environment'
                return self.snapshot(preview=params.get('preview') is True)
            if method == 'changes.diff':
                return {'diff': self.require().agent.changes.diff(params['id'])}
            if method in {'changes.accept', 'changes.undo'}:
                changes = self.idle().agent.changes
                getattr(changes, method.split('.')[1])(params['id'])
                return self.snapshot(preview=params.get('preview') is True)
            if method == 'diagnostics':
                agent = self.require().agent
                return await asyncio.to_thread(diagnose, agent.settings.root,
                    **{key: getattr(agent.settings, key) for key in MODEL_FIELDS})
            raise ValueError('Unknown method')

    async def handle(self, message):
        ident = message.get('id') if isinstance(message, dict) else None
        try:
            if (not isinstance(message, dict) or message.get('jsonrpc') != '2.0'
                    or not isinstance(message.get('method'), str) or type(ident) not in (str, int)
                    or not isinstance(message.get('params', {}), dict)):
                raise ValueError('Invalid JSON-RPC request')
            result = await self.dispatch(message['method'], message.get('params', {}))
            self.send({'jsonrpc': '2.0', 'id': ident, 'result': result})
        except Exception as exc:
            self.send({'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32000, 'message': str(exc)}})

    async def close(self):
        self.closed = True
        await self.side_chats.close()
        if self.runtime:
            self.runtime.cancel()
            if self.finishing:
                await self.finishing
            await self.runtime.close()
            self.runtime = None


async def serve():
    # A daemon reader avoids asyncio's executor waiting forever on Windows stdin.
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    def reader():
        try:
            for line in sys.stdin:
                loop.call_soon_threadsafe(queue.put_nowait, line)
        finally:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except RuntimeError:
                pass
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    from .desktop_projects import DesktopProjects
    server = DesktopProjects(lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))
    threading.Thread(target=reader, daemon=True).start()
    requests = set()
    try:
        while (line := await queue.get()) is not None:
            try:
                value = json.loads(line)
            except ValueError:
                server.send({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Invalid JSON'}})
                continue
            task = asyncio.create_task(server.handle(value))
            requests.add(task)
            task.add_done_callback(requests.discard)
    finally:
        for task in requests:
            task.cancel()
        await asyncio.gather(*requests, return_exceptions=True)
        await server.close()


def main():
    asyncio.run(serve())


if __name__ == '__main__':
    main()
