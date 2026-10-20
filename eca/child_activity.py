"""Child identity and read-only desktop views; opening a view never resumes work."""
import json

ACTIVE = {'preparing', 'queued', 'running'}
FIELDS = ('id', 'title', 'mode', 'status', 'model', 'model_profile', 'isolated',
          'parent_id', 'parent_call_id', 'parent_message_index', 'stop_reason')


def describe(state):
    return {key: state.get(key) for key in FIELDS}


def origin(agent, task, settings):
    return dict(title=task[:80], delegated_task=task, model=settings.model,
                parent_call_id=getattr(agent, 'active_call_id', None),
                parent_message_index=getattr(agent, 'active_message_index', None))


def progress(agent, state, event, data):
    agent.emit('subagent_progress', dict(session=state['id'], child=describe(state), event=event, data=data))


class ChildViews:
    def __init__(self, rpc):
        self.rpc = rpc
        self.key = None
        self.records = {}
        self.origins = {}
        self.message_count = -1

    def bind(self):
        agent = self.rpc.require().agent
        key = (id(agent.store), str(agent.store.root), agent.state['id'])
        if self.key != key:
            self.key, self.records = key, {}
            self.origins, self.message_count = {}, -1
        return agent

    def update(self, data):
        agent = self.bind()
        meta = data.get('child', {})
        if meta.get('parent_id') != agent.state['id']:
            return
        ident = data['session']
        row = self.records.setdefault(ident, dict(stream='', stream_id=0, revision=0, live=True))
        row['meta'] = meta
        event, value = data['event'], data['data']
        if event in {'turn', 'tool'}:
            row.update(stream='', stream_id=row['stream_id'] + 1)
        elif event == 'text':
            # Bound the live preview only. The full answer stays in the child session.
            row['stream'] += str(value)
            row['stream'] = row['stream'][-64000:]
        if event not in {'text', 'model_activity'}:
            row['revision'] += 1
        if event == 'status' and value not in ACTIVE:
            row['stream'] = ''

    def summaries(self):
        agent = self.bind()
        needs_origins = (any(ident not in self.records for ident in agent.state.get('children', [])) or
                         any(not row['meta'].get('parent_call_id') for row in self.records.values()))
        if needs_origins and len(agent.state['messages']) != self.message_count:
            # Legacy child sessions did not store their originating tool exchange.
            # Read the full in-memory journal, not its truncated renderer preview.
            pending, origins = {}, {}
            for index, message in enumerate(agent.state['messages']):
                for call in message.get('tool_calls', []):
                    if call.get('function', {}).get('name') in {'delegate', 'delegate_parallel'}:
                        pending[call['id']] = index
                if message.get('role') != 'tool' or message.get('tool_call_id') not in pending:
                    continue
                try:
                    value = json.loads(message.get('content') or '')
                    for row in value if isinstance(value, list) else [value]:
                        if isinstance(row, dict) and isinstance(row.get('session'), str):
                            origins[row['session']] = (message['tool_call_id'], pending[message['tool_call_id']])
                except (TypeError, ValueError):
                    pass
            self.origins, self.message_count = origins, len(agent.state['messages'])
        result = []
        for ident in agent.state.get('children', []):
            if ident not in self.records:
                try:
                    state = agent.store.peek(ident)
                except ValueError:
                    continue
                if state.get('parent_id') != agent.state['id'] or state.get('kind') == 'side_chat':
                    continue
                self.records[ident] = dict(meta=describe(state), stream='', stream_id=0, revision=0, live=False)
            row = self.records[ident]
            meta = dict(row['meta'])
            if not meta.get('parent_call_id') and ident in self.origins:
                meta['parent_call_id'], meta['parent_message_index'] = self.origins[ident]
            if meta['status'] in ACTIVE and (not row['live'] or not self.rpc.run_id):
                meta.update(status='interrupted', stop_reason='上次执行已中断，查看记录不会重新运行。')
            result.append(dict(meta, ordinal=len(result) + 1))
        return result

    def snapshot(self, params):
        agent = self.bind()
        if params.get('owner') != agent.state['id']:
            raise ValueError('主会话已变化，请重新打开子 Agent。')
        ident = params.get('id')
        meta = next((m for m in self.summaries() if m['id'] == ident), None)
        if meta is None:
            raise ValueError('该子 Agent 不属于当前主会话。')
        row = self.records[ident]
        # Text deltas do not require reparsing the saved conversation.
        if row.get('cached_revision') != row['revision']:
            state = agent.store.peek(ident)
            if state.get('parent_id') != agent.state['id'] or state.get('kind') == 'side_chat':
                raise ValueError('Invalid child session')
            row.update(state=state, cached_revision=row['revision'])
        state = row['state']
        messages = state['messages']
        before = params.get('before', len(messages))
        if type(before) is not int or before < 0:
            raise ValueError('Invalid history cursor')
        before = min(before, len(messages))
        start = max(0, before - 50)
        result = dict(**meta, backend_id=self.rpc.backend_id, task=state.get('delegated_task') or next(
            (m['content'] for m in messages if m['role'] == 'user'), meta['title']),
            message_total=len(messages), before=start, message_revision=row['revision'],
            stream=row['stream'], stream_id=row['stream_id'],
            busy=meta['status'] in ACTIVE,
            changes_count=agent.store.db.execute(
                'SELECT COUNT(*) FROM file_changes WHERE session_id=?', (ident,)).fetchone()[0])
        if ('before' in params or params.get('backend_id') != self.rpc.backend_id or
                params.get('message_revision') != row['revision']):
            result['messages'] = self.rpc.public_messages(messages[start:before], start, True)
        return self.rpc.safe(result)
