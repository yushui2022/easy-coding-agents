"""One project lock, independent session runtimes, one selected desktop view."""
import asyncio
from dataclasses import replace

from .agent import Agent
from .config import Settings
from .desktop_rpc import DesktopRPC
from .runtime import Runtime
from . import reasoning


class DesktopSessions(DesktopRPC):
    def __init__(self, send):
        super().__init__(send)
        self.workers = {}
        self.active_id = None
        self.store = None
        self.view_revision = 0
        self.transitioning = False
        self.side_status = {}
        self.sidebar_sessions = []

    @property
    def active(self):
        return self.workers.get(self.active_id)

    def worker(self):
        worker = DesktopRPC(self.forward)
        worker.ready = True
        worker.backend_id = self.backend_id
        # Secrets from any connection must be redacted even in another session.
        worker.secrets = self.secrets
        return worker

    def forward(self, message):
        params = message.get('params', {})
        if params.get('event') == 'sidechat':
            busy, branch = bool(params.get('run_id')), params.get('branch_id')
            if self.side_status.get(branch) != busy:
                self.side_status[branch] = busy
                self.send({'jsonrpc': '2.0', 'method': 'event', 'params': {'event': 'sessions_changed'}})
            if params.get('session_id') != self.active_id:
                return
        if params.get('session_id') != self.active_id:
            # Background streams stay in their worker, not in the visible transcript.
            # Only structural changes refresh sidebar status.
            if params.get('event') in {'text', 'model_activity'}:
                return
            if params.get('event') == 'subagent_progress' and params.get('data', {}).get('event') in {'text', 'model_activity'}:
                return
            message = {'jsonrpc': '2.0', 'method': 'event', 'params': {
                'event': 'sessions_changed', 'session_id': params.get('session_id')}}
        self.send(message)

    def running(self):
        return [{'id': ident, 'title': w.runtime.agent.state['title'],
                 'busy': w.run_id is not None, 'side_busy': w.side_chats.busy,
                 'pending_count': sum(not future.done() for _, future in w.pending.values()),
                 'status': w.runtime.agent.state['status'], 'phase': w.activity.get('phase'),
                 'model': w.runtime.agent.settings.model}
                for ident, w in self.workers.items()]

    def decorate(self, value):
        if not isinstance(value, dict) or 'backend_id' not in value:
            return value
        sessions = self.running()
        active = {s['id']: s for s in sessions}
        value = {**value, 'view_revision': self.view_revision, 'active_sessions': sessions,
                 'any_busy': any(s['busy'] or s['side_busy'] for s in sessions),
                 'running_count': sum(s['busy'] or s['side_busy'] for s in sessions)}
        if 'sessions' in value:
            value['sessions'] = [{**s, **active.get(s['id'], {})} for s in value['sessions']]
            listed = {s['id'] for s in value['sessions']}
            value['sessions'] += [s for s in sessions if s['id'] not in listed
                                  and (s['busy'] or s['side_busy'] or s['id'] == self.active_id)]
            self.sidebar_sessions = value['sessions']
        return self.safe(value)

    def project_idle(self):
        if any(w.run_id or w.side_chats.busy for w in self.workers.values()):
            raise ValueError('项目中仍有会话在运行，请停止所有任务和侧聊后再切换项目。')
        if any(w.lock.locked() for w in self.workers.values()):
            raise ValueError('会话配置仍在更新，请稍候再切换项目。')

    async def release(self):
        workers, self.workers = list(self.workers.values()), {}
        self.active_id = None
        self.side_status.clear()
        # Cancel all first; a slow cleanup in one session must not delay the others.
        for worker in workers:
            worker.runtime.cancel()
        try:
            results = await asyncio.gather(*(w.close() for w in workers), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result
        finally:
            if self.store:
                self.store.close()
                self.store = None

    async def select(self, params):
        current = self.active
        if not current:
            raise ValueError('Open a project first.')
        requested = params.get('id')
        state = self.store.peek(requested) if requested else None
        if state and (state.get('parent_id') or state.get('kind') == 'side_chat'):
            raise ValueError('Open child conversations in the workspace.')
        ident = state['id'] if state else None
        if ident not in self.workers:
            worker = self.worker()
            base = Settings.load(self.store.root, **current.model_override)
            state = self.store.load(ident) if ident else self.store.create(base.mode)
            if state.get('model_profile') and not current.model_override:
                base = base.select_profile(state['model_profile'])
            settings = replace(base, mode=state.get('mode', base.mode), permission='ask',
                               sandbox=state.get('sandbox', base.sandbox),
                               sandbox_image=state.get('sandbox_image', base.sandbox_image))
            settings = reasoning.restore(settings, state)
            settings.validate()
            if settings.api_key:
                self.secrets.add(settings.api_key)
            worker.runtime = Runtime(Agent(settings, self.store, state, worker.approve,
                                           worker.question, worker.emit), owns_store=False)
            worker.model_override = dict(current.model_override)
            worker.source = current.source
            # Elevated access is deliberately not inherited by a new conversation.
            worker.approval_mode = base.permission
            ident = state['id']
            self.workers[ident] = worker
        self.active_id = ident
        self.view_revision += 1
        return self.decorate(self.active.snapshot(preview=params.get('preview') is True))

    async def dispatch(self, method, params):
        if method == 'initialize':
            result = await super().dispatch(method, params)
            result['capabilities'].append('concurrent_sessions')
            return result
        if not self.ready or self.closed:
            raise ValueError('Desktop connection is not initialized or is closed.')
        if self.transitioning:
            raise ValueError('Project is changing; retry after it opens.')
        if method in {'project.open', 'project.close', 'session.switch'}:
            async with self.lock:
                if method == 'session.switch':
                    return await self.select(params)
                self.project_idle()
                self.transitioning = True
                try:
                    await self.release()
                    self.view_revision += 1
                    if method == 'project.open':
                        worker = self.worker()
                        try:
                            await worker.dispatch(method, params)
                        except BaseException:
                            await worker.close()
                            raise
                        self.store = worker.runtime.agent.store
                        worker.runtime.owns_store = False
                        self.active_id = worker.runtime.agent.state['id']
                        self.workers[self.active_id] = worker
                    return self.decorate(self.active.snapshot(preview=params.get('preview') is True)
                                         if self.active else super().snapshot())
                finally:
                    self.transitioning = False
        if method in {'snapshot', 'live'}:
            # Cursors are only valid within one session, even if stream IDs match.
            if params.get('session_id') != self.active_id:
                params = {k: v for k, v in params.items() if k not in {'stream_id', 'stream_offset'}}
            return self.decorate(await self.active.dispatch(method, params) if self.active
                                 else await super().dispatch(method, params))
        worker = self.active
        if params.get('session_id'):
            worker = self.workers.get(params['session_id'])
            if not worker:
                raise ValueError('Session is no longer open.')
        elif method in {'task.cancel', 'input.reply'}:
            worker = next((w for w in self.workers.values() if w.run_id and w.run_id == params.get('run_id')), None)
            if not worker:
                raise ValueError('Run is no longer active.')
        if not worker:
            return await super().dispatch(method, params)
        result = await worker.dispatch(method, params)
        if method in {'task.start', 'sidechat.send', 'sidechat.cancel'}:
            self.send({'jsonrpc': '2.0', 'method': 'event', 'params': {'event': 'sessions_changed'}})
        return self.decorate(result)

    async def close(self):
        self.closed = True
        await self.release()
