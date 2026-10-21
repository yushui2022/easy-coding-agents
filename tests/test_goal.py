import json
import os
from pathlib import Path
import tempfile
import unittest

from eca import goal
from eca.config import Settings
from eca.desktop_rpc import DesktopRPC
from eca.tools import Tools, allowed


class GoalStateTests(unittest.TestCase):
    def test_clean_normalises_and_validates(self):
        value = goal.clean('  ship plan mode  ', ['  a  ', {'text': 'b', 'done': True}])
        self.assertEqual(value['text'], 'ship plan mode')
        self.assertEqual([item['text'] for item in value['criteria']], ['a', 'b'])
        self.assertFalse(value['criteria'][0]['done'])
        self.assertEqual(value['status'], 'active')
        for bad in (( '', ['a']), ('goal', []), ('goal', ['a' * 401]), ('goal', [''])):
            with self.assertRaises(ValueError):
                goal.clean(*bad)

    def test_update_marks_progress_and_settles_status(self):
        value = goal.clean('goal', ['one', 'two'])
        goal.update(value, [{'index': 1, 'done': True}])
        self.assertEqual(goal.progress(value), (1, 2))
        self.assertEqual(value['status'], 'active')
        goal.update(value, [{'index': 2, 'done': True}])
        self.assertEqual(value['status'], 'done')
        goal.update(value, [{'index': 2, 'done': False}])
        self.assertEqual(value['status'], 'active')

    def test_update_rejects_bad_index_and_types(self):
        value = goal.clean('goal', ['one'])
        for bad in ([{'index': 0, 'done': True}], [{'index': 2, 'done': True}],
                    [{'index': 1, 'done': 'yes'}], [{'index': '1', 'done': True}],
                    [{'index': 1, 'done': True, 'extra': 1}], 'nope'):
            with self.assertRaises(ValueError):
                goal.update(value, bad)

    def test_abandon_sticks(self):
        value = goal.clean('goal', ['one'])
        goal.update(value, [], status='abandoned')
        goal.update(value, [{'index': 1, 'done': True}])
        self.assertEqual(value['status'], 'abandoned')

    def test_prompt_lists_criteria_and_warns_labels_are_not_proof(self):
        value = goal.clean('ship it', ['tests pass', 'docs updated'])
        goal.update(value, [{'index': 1, 'done': True}])
        text = goal.prompt(value)
        self.assertIn('ship it', text)
        self.assertIn('1. [done] tests pass', text)
        self.assertIn('not proof', text)
        # A fully marked goal is no longer active, so it stops steering the model.
        goal.update(value, [{'index': 2, 'done': True}])
        self.assertEqual(goal.prompt(value), '')
        self.assertEqual(goal.prompt(None), '')

    def test_plan_mode_tool_set_is_read_only(self):
        self.assertIn('goal_update', allowed('plan'))
        self.assertIn('read', allowed('plan'))
        for name in ('write', 'edit', 'shell', 'delete', 'mcp_call'):
            self.assertNotIn(name, allowed('plan'))
        self.assertEqual(allowed('chat'), set())
        self.assertIn('write', allowed('code'))


class GoalToolTests(unittest.TestCase):
    def setUp(self):
        events = []

        def emit(name, data=None):
            events.append((name, data))

        self.state = {'id': 'session', 'tasks': [], 'goal': goal.clean('goal', ['one', 'two'])}
        settings = Settings(Path(tempfile.gettempdir()), model='local', base_url='http://localhost:1/v1',
                            api_format='openai', api_key='local-secret')
        self.tools = Tools(settings, self.state, lambda *a: True, lambda *a: '', emit)
        self.events = events

    def test_goal_update_tool_marks_and_emits(self):
        result = json.loads(asyncio_run(self.tools.goal_update([{'index': 1, 'done': True}])))
        self.assertEqual(result, {'status': 'active', 'done': 1, 'total': 2,
                                  'note': 'Criterion labels are planning state, not proof of completion.'})
        self.assertEqual(self.state['goal']['criteria'][0]['done'], True)
        self.assertEqual(self.events[-1], ('goal', goal.public(self.state['goal'])))

    def test_goal_update_without_goal_is_rejected(self):
        self.state.pop('goal')
        with self.assertRaises(ValueError):
            asyncio_run(self.tools.goal_update([{'index': 1, 'done': True}]))


def asyncio_run(coroutine):
    import asyncio
    return asyncio.run(coroutine)


class DesktopGoalRPCTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.temp.name)
        (self.root / 'eca.toml').write_text('[agent]\nproject_memory=false\nauto_compact=false\n')
        self.rpc = DesktopRPC(lambda _: None)
        await self.rpc.dispatch('initialize', {'protocol': 1})
        self.model = dict(model='deepseek-flash', base_url='http://localhost:1234/v1',
                          api_format='openai', api_key='local-secret', thinking_mode='fast', reasoning_effort='')
        await self.rpc.dispatch('project.open', {'path': str(self.root), 'model': self.model})

    async def asyncTearDown(self):
        await self.rpc.close()
        self.temp.cleanup()

    async def test_mode_set_switches_and_persists(self):
        session = self.rpc.runtime.agent.state['id']
        live = await self.rpc.dispatch('mode.set', {'mode': 'plan'})
        self.assertEqual(self.rpc.runtime.agent.settings.mode, 'plan')
        self.assertEqual(live['goal'], None)
        state = self.rpc.runtime.agent.store.load(session)
        self.assertEqual(state['mode'], 'plan')
        # Re-selecting the session keeps the chosen mode instead of the project default.
        await self.rpc.dispatch('session.switch', {'id': session, 'preview': True})
        self.assertEqual(self.rpc.runtime.agent.settings.mode, 'plan')
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('mode.set', {'mode': 'turbo'})

    async def test_plan_mode_denies_writes(self):
        await self.rpc.dispatch('mode.set', {'mode': 'plan'})
        result = await self.rpc.runtime.agent.tools.execute('write', {'path': 'a.txt', 'content': 'x'})
        self.assertIn('unavailable in plan mode', result)
        self.assertFalse((self.root / 'a.txt').exists())

    async def test_goal_set_update_and_clear_through_snapshot(self):
        await self.rpc.dispatch('goal.set', {'goal': {'text': 'ship it', 'criteria': ['tests pass', 'docs updated']}})
        snapshot = await self.rpc.dispatch('snapshot', {})
        self.assertEqual(snapshot['goal']['text'], 'ship it')
        self.assertEqual(len(snapshot['goal']['criteria']), 2)
        await self.rpc.runtime.agent.tools.execute('goal_update', {'updates': [{'index': 1, 'done': True}]})
        snapshot = await self.rpc.dispatch('snapshot', {})
        self.assertEqual(snapshot['goal']['criteria'][0]['done'], True)
        self.assertEqual(snapshot['goal']['status'], 'active')
        await self.rpc.dispatch('goal.set', {'goal': None})
        self.assertIsNone((await self.rpc.dispatch('snapshot', {}))['goal'])

    async def test_goal_prompt_reaches_system_prompt(self):
        await self.rpc.dispatch('goal.set', {'goal': {'text': 'ship it', 'criteria': ['tests pass']}})
        prompt = self.rpc.runtime.agent.system_prompt()
        self.assertIn('Session goal: ship it', prompt)
        self.assertIn('tests pass', prompt)

    async def test_goal_set_rejects_empty_criteria(self):
        with self.assertRaises(ValueError):
            await self.rpc.dispatch('goal.set', {'goal': {'text': 'x', 'criteria': []}})


if __name__ == '__main__':
    unittest.main()
