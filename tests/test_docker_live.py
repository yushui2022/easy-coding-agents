"""Explicit real-engine acceptance: ECA_DOCKER_LIVE=1. Never pulls an image."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from eca.config import Settings
from eca.tools import Tools, run_process
from test_runtime import yes


@unittest.skipUnless(os.environ.get('ECA_DOCKER_LIVE') == '1', 'Real Docker acceptance requires explicit opt-in')
class DockerLiveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP', tempfile.gettempdir()))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.docker = shutil.which('docker')
        self.assertTrue(self.docker, 'Docker CLI is required')
        self.tools = Tools(Settings(self.root, sandbox='docker', sandbox_image=os.environ.get('ECA_DOCKER_IMAGE', 'python:3.11-slim')), {}, yes, yes, lambda *_: None)
        self.addAsyncCleanup(self.tools.close)
        (self.root/'source.txt').write_text('original', encoding='utf-8')
        (self.root/'.env').write_text('SYNTHETIC_TEST_SECRET=not-a-credential', encoding='utf-8')

    async def removed(self):
        record = self.tools.state['sandbox_runs'][-1]
        self.assertEqual(record['cleanup'], 'removed')
        result = json.loads(await run_process([self.docker, '--host', record['endpoint'], 'inspect', record['container']], self.root, 10, 2000))
        self.assertNotEqual(result['exit_code'], 0)
        self.assertIn('no such', result['stderr'].lower())

    async def test_real_filesystem_network_user_and_capability_boundaries(self):
        (self.root/'probe.py').write_text('''import os,socket
from pathlib import Path
assert os.geteuid()==65534
assert {name for _,name in socket.if_nameindex()}=={'lo'}
assert not Path('.env').exists()
assert not Path('/var/run/docker.sock').exists()
try:
    assert not Path('/root/.ssh').exists()
except PermissionError:
    pass  # An inaccessible root home is also an enforced boundary.
caps=next(line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('CapEff:'))
assert int(caps.split()[1],16)==0
assert 'NoNewPrivs:\t1' in Path('/proc/self/status').read_text()
for path in ['/input/source.txt','/etc/eca-test-write']:
    try: Path(path).write_text('must fail')
    except OSError: pass
    else: raise AssertionError('write boundary failed')
Path('source.txt').write_text('disposable change')
print('isolation-probe-passed')
''', encoding='utf-8')
        result = json.loads(await self.tools.shell('python probe.py', timeout=20))
        self.assertEqual(result['exit_code'], 0, result)
        self.assertIn('isolation-probe-passed', result['stdout'])
        self.assertEqual((self.root/'source.txt').read_text(), 'original')
        await self.removed()

    async def test_real_timeout_cleanup(self):
        result = json.loads(await self.tools.shell('sleep 30', timeout=1))
        self.assertTrue(result['timed_out'], result)
        await self.removed()

    async def test_missing_image_never_pulls_or_falls_back(self):
        self.tools.settings.sandbox_image = 'eca-missing-' + uuid.uuid4().hex + ':test'
        result = json.loads(await self.tools.shell('echo escaped > host-escape.txt', timeout=10))
        self.assertNotEqual(result['exit_code'], 0, result)
        self.assertFalse((self.root/'host-escape.txt').exists())
        self.assertIn('No such image', result['stderr'])
        await self.removed()

    async def test_real_cancellation_cleanup(self):
        task = asyncio.create_task(self.tools.shell('sleep 60', timeout=90))
        started = False
        try:
            for _ in range(100):
                if task.done():
                    self.fail('Container did not remain running: ' + str(await task))
                records = self.tools.state.get('sandbox_runs', [])
                if records:
                    r = records[-1]
                    result = json.loads(await run_process([self.docker, '--host', r['endpoint'], 'inspect', '--format', '{{.State.Running}}', r['container']], self.root, 3, 2000))
                    if result['exit_code'] == 0 and result['stdout'].strip() == 'true':
                        config = json.loads(await run_process([self.docker, '--host', r['endpoint'], 'inspect', '--format', '{{json .HostConfig}}', r['container']], self.root, 3, 8000))
                        self.assertEqual(config['exit_code'], 0, config)
                        limits = json.loads(config['stdout'])
                        self.assertEqual(limits['Memory'], 512 * 1024 * 1024)
                        self.assertEqual(limits['MemorySwap'], 512 * 1024 * 1024)
                        self.assertEqual(limits['NanoCpus'], 1_000_000_000)
                        self.assertEqual(limits['PidsLimit'], 128)
                        self.assertTrue(limits['ReadonlyRootfs'])
                        self.assertEqual(limits['NetworkMode'], 'none')
                        started = True
                        break
                await asyncio.sleep(0.1)
        finally:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        self.assertTrue(started, 'Cancellation must exercise a running container')
        self.assertEqual(self.tools.state['sandbox_runs'][-1]['execution'], 'cancelled')
        await self.removed()
