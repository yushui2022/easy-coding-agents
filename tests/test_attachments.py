import base64
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from eca.attachments import prepare, content, public
from eca.anthropic import messages_payload
from eca.responses import input_items
import test_desktop_rpc

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1ioAAAAASUVORK5CYII=')

def upload(name='图.png', mime='image/png', raw=PNG):
    return dict(name=name, mime=mime, data=base64.b64encode(raw).decode())


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('ECA_TEST_TMP'))
        self.root = Path(self.tmp.name)
        (self.root / '.eca').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_three_protocols_and_snapshot_integrity(self):
        files = prepare(self.root, [upload(), upload('说明.md','text/plain','中文参考'.encode())])
        message = dict(role='user', content='请分析', attachments=files)
        self.assertNotIn('data', str(files[0]))
        self.assertNotIn('text', public(files)[1])
        chat = content(message, self.root)
        self.assertIn('中文参考', chat[0]['text'])
        self.assertTrue(chat[1]['image_url']['url'].startswith('data:image/png;base64,'))
        response = input_items([message], root=self.root)[0]['content']
        self.assertEqual(response[1]['type'], 'input_image')
        settings = SimpleNamespace(root=self.root, model='test', max_output_tokens=100)
        anthropic = messages_payload([message], [], settings)['messages'][0]['content']
        self.assertEqual(anthropic[1]['source']['data'], base64.b64encode(PNG).decode())
        (self.root/'.eca'/'attachments'/files[0]['id']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '变化'):
            content(message, self.root)

    def test_invalid_and_oversized_inputs_rejected(self):
        for value in [upload(raw=b'not png'), upload(mime='application/pdf'), upload('x','text/plain',b'\0binary'),
                      upload('x','text/plain',b'a'*(256*1024+1)), dict(name='x',mime='text/plain',data='%%%')]:
            with self.subTest(value=value['name']), self.assertRaises(ValueError):
                prepare(self.root,[value])
        with self.assertRaises(ValueError):
            prepare(self.root,[upload()]*7)

    def test_untrusted_name_not_used_as_path(self):
        item = prepare(self.root,[upload('../../outside.png')])[0]
        self.assertTrue((self.root/'.eca'/'attachments'/item['id']).is_file())
        self.assertFalse((self.root/'outside.png').exists())


class AttachmentRPCTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_desktop_rpc.DesktopTests.asyncSetUp
    asyncTearDown = test_desktop_rpc.DesktopTests.asyncTearDown
    fake = test_desktop_rpc.DesktopTests.fake
    async def test_attachment_only_main_and_reopen(self):
        await self.fake([{'role':'assistant','content':'received'}])
        await self.rpc.dispatch('task.start',dict(prompt='', attachments=[upload()]))
        await self.rpc.finishing
        message = self.rpc.runtime.agent.state['messages'][0]
        self.assertEqual(message['attachments'][0]['name'],'图.png')
        self.assertEqual(message['content'],'请分析这些附件。')
        preview = self.rpc.snapshot(preview=True)['messages'][0]
        self.assertNotIn('data', preview['attachments'][0])
        ident = self.rpc.runtime.agent.state['id']
        await self.rpc.dispatch('session.switch', {})
        await self.rpc.dispatch('session.switch', {'id':ident})
        self.assertEqual(self.rpc.runtime.agent.state['messages'][0]['attachments'],message['attachments'])
