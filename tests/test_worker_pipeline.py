import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from eca.agent import Agent
from eca.config import Settings
from eca.store import Store
from eca.workflow import verified_run, suite_status
from eca.cli import parser, async_main
from test_runtime import FakeProvider, yes, call

DONE = {'role':'assistant', 'content':'done'}
OK = json.dumps({'exit_code':0, 'timed_out':False, 'stdout':'ok'})
FAIL = json.dumps({'exit_code':1, 'timed_out':False, 'stdout':'failed'})

class WorkerPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root)
        settings = Settings(self.root, project_memory=False, auto_compact=False, model='main-model',
            model_profiles={'helper':dict(model='small-model',base_url='http://localhost:11434/v1',api_format='openai',api_key_env='TEST_HELPER')},
            worker_profiles=['helper'])
        self.main = FakeProvider([DONE]*5)
        self.worker = FakeProvider([DONE]*5)
        self.agent = Agent(settings,self.store,self.store.create(),yes,yes,lambda *_:None,self.main)

    async def asyncTearDown(self):
        await self.agent.close()
        self.store.close()
        self.tmp.cleanup()

    async def test_success_skips_main_model_and_preserves_child(self):
        with patch('eca.agent.Provider', return_value=self.worker), patch('eca.tools.run_process',AsyncMock(return_value=OK)):
            self.assertTrue(await verified_run(self.agent,'work',['check'],1,'helper'))
        suite = suite_status(self.agent)
        self.assertEqual(suite['status'],'passed')
        self.assertEqual(suite['worker']['status'],'idle')
        self.assertEqual(len(self.main.contexts),0)
        self.assertEqual(len(self.worker.contexts),1)
        self.assertEqual(self.store.peek(suite['worker']['session'])['model_profile'],'helper')

    async def test_actual_command_failure_hands_existing_changes_to_main(self):
        self.worker = FakeProvider([call('write',{'path':'value.txt','content':'wrong'}),DONE])
        self.agent.provider = self.main = FakeProvider([call('edit',{'path':'value.txt','old':'wrong','new':'correct'}),DONE])
        command = 'python -B -c "from pathlib import Path; assert Path(\'value.txt\').read_text() == \'correct\'"'
        with patch('eca.agent.Provider',return_value=self.worker):
            self.assertTrue(await verified_run(self.agent,'Write correct to value.txt',[command],1,'helper'))
        suite = suite_status(self.agent)
        self.assertEqual([r['status'] for r in suite['rounds']],['failed','passed'])
        self.assertEqual(suite['handoff']['model'],'main-model')
        self.assertEqual((self.root/'value.txt').read_text(),'correct')
        self.assertIn('original task',str(self.main.contexts[0]).lower())
        self.assertIn('assert',str(self.main.contexts[0]))
        rows = self.store.db.execute('SELECT DISTINCT model,root_id FROM usage_requests').fetchall()
        self.assertEqual(set(rows),{('small-model',self.agent.state['id']),('main-model',self.agent.state['id'])})
        # The delegate call and every verification call retain their matching results.
        messages = self.agent.state['messages']
        ids = [c['id'] for m in messages for c in m.get('tool_calls',[])]
        results = [m['tool_call_id'] for m in messages if m['role']=='tool']
        self.assertCountEqual(ids,results)

    async def test_zero_budget_and_uncertain_check_do_not_handoff(self):
        for budget,output in [(0,FAIL),(2,json.dumps({'exit_code':1,'timed_out':True})),(2,'Denied')]:
            with patch('eca.agent.Provider',return_value=self.worker), patch('eca.tools.run_process',AsyncMock(return_value=output)) as process:
                self.assertFalse(await verified_run(self.agent,'work',['check'],budget,'helper'))
                self.assertEqual(process.await_count,1)
        self.assertEqual(self.main.contexts,[])

    async def test_worker_error_does_not_verify_or_fallback(self):
        worker = FakeProvider([RuntimeError('offline')])
        with patch('eca.agent.Provider',return_value=worker), patch('eca.tools.run_process',AsyncMock()) as process:
            self.assertFalse(await verified_run(self.agent,'work',['check'],1,'helper'))
            process.assert_not_awaited()
        self.assertEqual(suite_status(self.agent)['status'],'task_incomplete')
        self.assertEqual(self.main.contexts,[])

    async def test_cancel_persists_interruption_and_load_does_not_replay(self):
        worker = FakeProvider([asyncio.CancelledError()])
        with patch('eca.agent.Provider',return_value=worker), self.assertRaises(asyncio.CancelledError):
            await verified_run(self.agent,'work',['check'],1,'helper')
        state = self.store.load(self.agent.state['id'])
        self.assertEqual(state['verification_suite']['status'],'interrupted')
        self.assertEqual(state['verification_suite']['worker']['status'],'interrupted')
        self.assertEqual(state['messages'][-1]['role'],'tool')
        self.assertFalse(self.agent.busy)
        self.assertEqual(self.main.contexts,[])

    async def test_invalid_opt_in_rejected_before_dispatch(self):
        for profile,commands in [('unknown',['check']),('helper',[])]:
            with self.assertRaises(ValueError):
                await verified_run(self.agent,'work',commands,0,profile)
        self.agent.settings.mode='plan'
        with self.assertRaises(ValueError):
            await verified_run(self.agent,'work',['check'],0,'helper')
        self.assertNotIn('children',self.agent.state)
        with self.assertRaises(ValueError):
            await async_main(parser().parse_args(['-p','work','--worker-first','helper']))
