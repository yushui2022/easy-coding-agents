"""Project-scoped session coordinators behind one desktop connection."""
import asyncio
import os
from pathlib import Path

from . import automations
from .desktop_rpc import DesktopRPC
from .desktop_sessions import DesktopSessions


class DesktopProjects(DesktopRPC):
    def __init__(self, send):
        super().__init__(send)
        self.projects = {}
        self.active_project = None
        self.view_revision = 0
        self.automation_library = automations.Library()
        self.scheduler = automations.Scheduler(self.automation_library,
                                               automations.Runner(self.automation_library, self.automation_event),
                                               self.automation_event)
        self.automation_tasks = set()

    @property
    def active(self):
        return self.projects.get(self.active_project)

    # -- scheduled sessions -------------------------------------------------
    def automation_event(self, event, data):
        """Automation pushes are not session activity, so they skip self.events."""
        self.send({'jsonrpc': '2.0', 'method': 'event', 'params': {
            'event': event, 'data': self.safe(data), 'seq': None, 'run_id': None, 'session_id': None}})
        if event == 'automation_run':
            self.refresh_automation_project(data.get('automation_id'))

    def refresh_automation_project(self, automation_id):
        """A scheduled run adds a session, so its sidebar has to reload."""
        try:
            project = self.automation_library.load(automation_id)['project']
        except (ValueError, OSError, KeyError):
            return
        ident = os.path.normcase(project)
        if ident in self.projects:
            self.forward(ident, {'jsonrpc': '2.0', 'method': 'event',
                                 'params': {'event': 'sessions_changed'}})

    def automation_view(self):
        return {'automations': self.automation_library.list(),
                'running': sorted(self.scheduler._inflight),
                'permissions': [{'value': key, 'label': label}
                                for key, label in automations.PERMISSION_TEXT.items()],
                'notifications': list(automations.NOTIFICATIONS),
                'enabled': automations.enabled()}

    async def dispatch_automation(self, method, params):
        library, scheduler = self.automation_library, self.scheduler
        if method == 'automations.list':
            return self.automation_view()
        if method == 'automations.rrule':
            start = params.get('start')
            text = automations.build_rrule(params.get('freq') or 'DAILY', interval=params.get('interval') or 1,
                                           at=params.get('time') or '09:00', weekdays=params.get('weekdays'),
                                           start=datetime.fromisoformat(start) if start else None)
            return {'rrule': text, 'schedule': automations.describe(automations.parse_rrule(text))}
        if method == 'automations.save':
            saved = library.save(params.get('automation') or {})
            self.automation_event('automations', self.automation_view())
            return {**self.automation_view(), 'saved': saved}
        if method == 'automations.delete':
            library.delete(params.get('id') or '')
            self.automation_event('automations', self.automation_view())
            return self.automation_view()
        if method == 'automations.history':
            return {'runs': library.history(params.get('id') or '', int(params.get('limit') or 20)),
                    'memory': library.memory(params.get('id') or '', 4000)}
        if method == 'automations.run':
            automation_id = params.get('id') or ''
            if automation_id in scheduler._inflight:
                raise ValueError('这个任务正在运行，等它结束再试')
            task = asyncio.create_task(scheduler.run_now(automation_id))
            self.automation_tasks.add(task)
            task.add_done_callback(self.automation_tasks.discard)
            self.automation_event('automations', self.automation_view())
            return {'started': True, **self.automation_view()}
        raise ValueError(f'Unknown automation method: {method}')

    # -- events and views ---------------------------------------------------
    def forward(self, project_id, message):
        params = message.get('params', {})
        if project_id != self.active_project:
            if params.get('event') in {'text', 'model_activity', 'sidechat'}:
                return
            if params.get('event') == 'subagent_progress' and params.get('data', {}).get('event') in {'text', 'model_activity'}:
                return
            params = {'event': 'sessions_changed'}
        self.send({**message, 'params': {**params, 'project_id': project_id}})

    def groups(self):
        result = []
        for ident, hub in self.projects.items():
            active = {s['id']: s for s in hub.running()}
            sessions = [{**s, **active.get(s['id'], {})} for s in hub.sidebar_sessions]
            known = {s['id'] for s in sessions}
            sessions += [s for s in active.values() if s['id'] not in known]
            result.append({'id': ident, 'path': str(hub.store.root),
                           'session_id': hub.active_id, 'sessions': sessions,
                           'running_count': sum(bool(s.get('busy') or s.get('side_busy')) for s in sessions)})
        return result

    def decorate(self, value, project_id=None):
        if not isinstance(value, dict) or 'backend_id' not in value:
            return value
        groups = self.groups()
        running = [{**s, 'project_id': g['id']} for g in groups for s in g['sessions']
                   if s.get('busy') or s.get('side_busy')]
        return self.safe({**value, 'project_id': project_id or self.active_project,
                          'view_revision': self.view_revision, 'projects': groups,
                          'active_sessions': running, 'running_count': len(running),
                          'any_busy': bool(running)})

    async def snapshot_view(self, method='snapshot', params=None):
        value = await self.active.dispatch(method, params or {}) if self.active else self.snapshot()
        return self.decorate(value)

    async def dispatch(self, method, params):
        if method == 'initialize':
            result = await super().dispatch(method, params)
            result['capabilities'] += ['concurrent_sessions', 'concurrent_projects']
            if automations.enabled():
                self.scheduler.start()
            return result
        if not self.ready or self.closed:
            raise ValueError('Desktop connection is not initialized or is closed.')
        if method.startswith('automations.'):
            # Schedules outlive any single project, so these never require one.
            return await self.dispatch_automation(method, params)
        if method in {'project.open', 'project.close', 'session.switch'}:
            async with self.lock:
                if method == 'project.open':
                    root = Path(params['path']).resolve(strict=True)
                    if not root.is_dir():
                        raise ValueError('请选择项目文件夹。')
                    ident = os.path.normcase(str(root))
                    if ident not in self.projects:
                        hub = DesktopSessions(lambda m: self.forward(ident, m))
                        hub.ready, hub.backend_id, hub.secrets = True, self.backend_id, self.secrets
                        try:
                            await hub.dispatch('project.open', {**params, 'path': str(root)})
                        except BaseException:
                            await hub.close()
                            raise
                        self.projects[ident] = hub
                    self.active_project = ident
                elif method == 'project.close':
                    ident = params.get('project_id') or self.active_project
                    hub = self.projects.get(ident)
                    if not hub:
                        raise ValueError('项目已关闭。')
                    # Closing a project is explicit and never stops its live work.
                    await hub.dispatch('project.close', {})
                    del self.projects[ident]
                    if self.active_project == ident:
                        self.active_project = next(iter(self.projects), None)
                else:
                    ident = params.get('project_id') or self.active_project
                    hub = self.projects.get(ident)
                    if not hub:
                        raise ValueError('项目已关闭，请重新打开。')
                    await hub.dispatch(method, params)
                    self.active_project = ident
                self.view_revision += 1
                return await self.snapshot_view(params=params)
        if method in {'snapshot', 'live'}:
            # A live cursor from another project cannot be applied to this view.
            if params.get('project_id') and params['project_id'] != self.active_project:
                params = {k: v for k, v in params.items() if k not in {'stream_id', 'stream_offset'}}
            return await self.snapshot_view(method, params)
        if method in {'model.capabilities', 'connection.check', 'connection.models',
                      'external.sessions', 'external.session'}:
            return await super().dispatch(method, params)
        if method.startswith('skills.'):
            # Browsable with or without an open project; when a project is open,
            # its own .agents/skills is included as well.
            hub = self.projects.get(self.active_project)
            return await (hub.dispatch(method, params) if hub else super().dispatch(method, params))
        ident = params.get('project_id') or self.active_project
        hub = self.projects.get(ident)
        if not hub:
            raise ValueError('项目已关闭，请重新打开。')
        result = await hub.dispatch(method, params)
        return self.decorate(result, ident)

    async def close(self):
        self.closed = True
        await self.scheduler.stop()
        # Begin cancellation in every project before awaiting any cleanup.
        for hub in self.projects.values():
            for worker in hub.workers.values():
                worker.runtime.cancel()
        async with self.lock:
            hubs, self.projects = list(self.projects.values()), {}
            self.active_project = None
        results = await asyncio.gather(*(hub.close() for hub in hubs), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
