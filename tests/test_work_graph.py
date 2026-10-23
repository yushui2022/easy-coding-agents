import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

from eca import workgraph
from eca.config import Settings
from eca.tools import Tools


def run(coroutine):
    return asyncio.run(coroutine)


def plan(*tasks):
    return workgraph.validate(list(tasks))


class GraphValidation(unittest.TestCase):
    def test_plan_without_ids_keeps_the_old_shape(self):
        tasks = plan({'content': 'read', 'status': 'completed'}, {'content': 'edit', 'status': 'pending'})
        self.assertEqual(tasks, [{'content': 'read', 'status': 'completed'},
                                 {'content': 'edit', 'status': 'pending'}])

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate task id'):
            plan({'content': 'a', 'status': 'pending', 'id': 'step'},
                 {'content': 'b', 'status': 'pending', 'id': 'step'})

    def test_unknown_dependency_names_the_known_ids(self):
        with self.assertRaises(ValueError) as error:
            plan({'content': 'build', 'status': 'pending', 'id': 'build'},
                 {'content': 'ship', 'status': 'pending', 'id': 'ship', 'depends_on': ['tests']})
        self.assertIn("unknown id 'tests'", str(error.exception))
        self.assertIn('build', str(error.exception))

    def test_self_dependency_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'depends on itself'):
            plan({'content': 'build', 'status': 'pending', 'id': 'build', 'depends_on': ['build']})

    def test_cycle_is_rejected_with_its_path(self):
        with self.assertRaises(ValueError) as error:
            plan({'content': 'a', 'status': 'pending', 'id': 'a', 'depends_on': ['b']},
                 {'content': 'b', 'status': 'pending', 'id': 'b', 'depends_on': ['a']})
        self.assertIn('Circular dependency', str(error.exception))
        self.assertIn('a -> b -> a', str(error.exception))

    def test_ids_are_case_folded_and_deduplicated(self):
        tasks = plan({'content': 'a', 'status': 'completed', 'id': 'Build'},
                     {'content': 'b', 'status': 'pending', 'id': 'ship', 'depends_on': ['BUILD', 'build']})
        self.assertEqual(tasks[0]['id'], 'build')
        self.assertEqual(tasks[1]['depends_on'], ['build'])
        self.assertNotIn('blocked', tasks[1])

    def test_limits_and_fields(self):
        with self.assertRaisesRegex(ValueError, 'At most 50'):
            plan(*[{'content': f'step {index}', 'status': 'pending'} for index in range(51)])
        with self.assertRaisesRegex(ValueError, 'more than 8 dependencies'):
            plan(*[{'content': f's{index}', 'status': 'pending', 'id': f's{index}'} for index in range(9)],
                 {'content': 'all', 'status': 'pending', 'id': 'all',
                  'depends_on': [f's{index}' for index in range(9)]})
        with self.assertRaisesRegex(ValueError, 'unsupported fields'):
            plan({'content': 'a', 'status': 'pending', 'owner': 'me'})
        with self.assertRaisesRegex(ValueError, 'must be one of'):
            plan({'content': 'a', 'status': 'blocked'})
        with self.assertRaisesRegex(ValueError, 'non-empty content'):
            plan({'content': '   ', 'status': 'pending'})
        with self.assertRaisesRegex(ValueError, 'lowercase letters'):
            plan({'content': 'a', 'status': 'pending', 'id': 'Bad Id'})


class Blocking(unittest.TestCase):
    def test_unfinished_dependency_blocks_completion(self):
        with self.assertRaises(ValueError) as error:
            plan({'content': 'migrate', 'status': 'in_progress', 'id': 'db'},
                 {'content': 'deploy', 'status': 'completed', 'id': 'ship', 'depends_on': ['db']})
        message = str(error.exception)
        self.assertIn('cannot be completed', message)
        self.assertIn('db (in_progress)', message)
        self.assertIn('Finish the prerequisite first', message)

    def test_failed_dependency_blocks_and_asks_for_a_repair(self):
        with self.assertRaises(ValueError) as error:
            plan({'content': 'run tests', 'status': 'failed', 'id': 'tests'},
                 {'content': 'release', 'status': 'completed', 'id': 'ship', 'depends_on': ['tests']})
        message = str(error.exception)
        self.assertIn('tests (failed)', message)
        self.assertIn('Repair the failed prerequisite', message)

    def test_dependent_is_unblocked_once_the_dependency_completes(self):
        tasks = plan({'content': 'migrate', 'status': 'completed', 'id': 'db'},
                     {'content': 'deploy', 'status': 'completed', 'id': 'ship', 'depends_on': ['db']})
        self.assertNotIn('blocked', tasks[1])

    def test_blocked_state_is_derived_and_reported(self):
        tasks = plan({'content': 'migrate', 'status': 'in_progress', 'id': 'db'},
                     {'content': 'deploy', 'status': 'pending', 'id': 'ship', 'depends_on': ['db']},
                     {'content': 'write notes', 'status': 'pending', 'id': 'notes'})
        self.assertEqual(tasks[1]['blocked'], True)
        self.assertEqual(tasks[1]['blocked_by'], ['db'])
        self.assertNotIn('blocked', tasks[2])
        report = workgraph.report(tasks)
        self.assertEqual(report['ready'], ['db', 'notes'])
        self.assertEqual(report['blocked'], ['ship'])
        self.assertIn('cannot be marked completed', report['note'])

    def test_failed_work_is_reported_as_failed_and_blocking(self):
        tasks = plan({'content': 'run tests', 'status': 'failed', 'id': 'tests'},
                     {'content': 'release', 'status': 'pending', 'id': 'ship', 'depends_on': ['tests']})
        report = workgraph.report(tasks)
        self.assertEqual(report['failed'], ['tests'])
        self.assertEqual(report['blocked'], ['ship'])
        self.assertEqual(tasks[1]['failed_by'], ['tests'])
        self.assertIn('do not unblock dependents', report['note'])


class TodoTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.root = Path(self.tmp.name).resolve()
        self.state = {'tasks': []}
        self.events = []
        self.tools = Tools(Settings(self.root), self.state, lambda *_: True, lambda *_: True,
                           lambda event, data: self.events.append((event, data)))

    def tearDown(self):
        self.tmp.cleanup()

    async def test_valid_plan_is_stored_and_emitted(self):
        result = json.loads(await self.tools.execute('todo', {'items': [
            {'content': 'migrate', 'status': 'in_progress', 'id': 'db'},
            {'content': 'deploy', 'status': 'pending', 'id': 'ship', 'depends_on': ['db']}]}))
        self.assertEqual(result['counts']['in_progress'], 1)
        self.assertEqual(result['blocked'], ['ship'])
        self.assertEqual(self.state['tasks'][1]['blocked_by'], ['db'])
        self.assertEqual(self.events[-1][0], 'tasks')

    async def test_rejected_plan_leaves_the_previous_one_intact(self):
        await self.tools.execute('todo', {'items': [{'content': 'migrate', 'status': 'in_progress', 'id': 'db'}]})
        kept = list(self.state['tasks'])
        result = await self.tools.execute('todo', {'items': [
            {'content': 'a', 'status': 'pending', 'id': 'a', 'depends_on': ['b']},
            {'content': 'b', 'status': 'pending', 'id': 'b', 'depends_on': ['a']}]})
        self.assertTrue(result.startswith('Error: Circular dependency'))
        self.assertEqual(self.state['tasks'], kept)

    async def test_blocked_completion_is_refused_through_the_tool(self):
        result = await self.tools.execute('todo', {'items': [
            {'content': 'run tests', 'status': 'failed', 'id': 'tests'},
            {'content': 'ship', 'status': 'completed', 'id': 'ship', 'depends_on': ['tests']}]})
        self.assertIn('cannot be completed', result)
        self.assertEqual(self.state['tasks'], [])

    async def test_prompt_text_marks_a_blocked_plan(self):
        self.state['tasks'] = plan({'content': 'run tests', 'status': 'failed', 'id': 'tests'},
                                   {'content': 'ship', 'status': 'pending', 'id': 'ship',
                                    'depends_on': ['tests']})
        from eca.agent import Agent
        prompt = Agent.system_prompt(self._agent())
        self.assertIn('"blocked": true', prompt)
        self.assertIn('unfinished dependency', prompt)

    def _agent(self):
        from types import SimpleNamespace
        agent = SimpleNamespace(settings=SimpleNamespace(root=self.root, sandbox='host', mode='code',
                                                         worker_profiles={}, skills_dirs=None),
                                state=self.state, child=False)
        return agent


if __name__ == '__main__':
    unittest.main()
