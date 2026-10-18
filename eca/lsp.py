"""Session-scoped LSP clients with synchronized files and versioned diagnostics."""
import asyncio
from copy import deepcopy
import json
import os
import subprocess

from .tools import terminate


def validate_servers(servers):
    if not isinstance(servers, dict):
        raise ValueError('lsp_servers must be a table')
    for cfg in servers.values():
        if not isinstance(cfg, dict) or set(cfg) - {'command', 'args', 'language_id', 'timeout', 'diagnostic_timeout'}:
            raise ValueError('Invalid LSP options')
        if not isinstance(cfg.get('command'), str) or not cfg['command'].strip():
            raise ValueError('LSP command is required')
        if not isinstance(cfg.get('args', []), list) or not all(isinstance(x, str) for x in cfg.get('args', [])):
            raise ValueError('LSP args must be strings')
        if not isinstance(cfg.get('language_id', ''), str):
            raise ValueError('Invalid LSP language_id')
        if type(cfg.get('timeout', 30)) is not int or not 1 <= cfg.get('timeout', 30) <= 120:
            raise ValueError('LSP timeout must be 1..120')
        if type(cfg.get('diagnostic_timeout', 2)) is not int or not 1 <= cfg.get('diagnostic_timeout', 2) <= 30:
            raise ValueError('LSP diagnostic_timeout must be 1..30')


class LSPError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(f'Language server rejected query ({code})')


class Client:
    def __init__(self, root, cfg):
        self.root, self.cfg = root, deepcopy(cfg)
        self.proc = self.reader = None
        self.pending, self.documents, self.diagnostics = {}, {}, {}
        self.changed = asyncio.Event()
        self.ident = 0
        self.capabilities = {}

    @property
    def alive(self):
        return self.proc is not None and self.proc.returncode is None and self.reader is not None and not self.reader.done()

    async def start(self):
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(self.cfg['command'], *self.cfg.get('args', []),
            cwd=self.root, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, **options))
        try:
            self.proc = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            self.proc = await spawn
            await terminate(self.proc)
            raise
        self.reader = asyncio.create_task(self.read())
        result = await self.request('initialize', dict(processId=None, rootUri=self.root.as_uri(),
            capabilities={'general': {'positionEncodings': ['utf-16']},
                          'textDocument': {'publishDiagnostics': {'versionSupport': True}, 'diagnostic': {}},
                          'workspace': {'configuration': True, 'workspaceFolders': True}},
            workspaceFolders=[{'uri': self.root.as_uri(), 'name': self.root.name}]))
        self.capabilities = (result or {}).get('capabilities', {})
        if self.capabilities.get('positionEncoding', 'utf-16') != 'utf-16':
            raise ValueError('Language server did not negotiate UTF-16 positions')
        await self.send(dict(method='initialized', params={}))

    async def send(self, value):
        data = json.dumps(dict(jsonrpc='2.0', **value)).encode('utf-8')
        self.proc.stdin.write(f'Content-Length: {len(data)}\r\n\r\n'.encode() + data)
        await self.proc.stdin.drain()

    async def read(self):
        try:
            while True:
                headers = await self.proc.stdout.readuntil(b'\r\n\r\n')
                lengths = [int(x.split(b':', 1)[1]) for x in headers.split(b'\r\n') if x.lower().startswith(b'content-length:')]
                if len(lengths) != 1 or not 0 < lengths[0] <= 2_000_000:
                    raise ValueError('Invalid LSP frame')
                msg = json.loads(await self.proc.stdout.readexactly(lengths[0]))
                if 'method' in msg and 'id' in msg:
                    if msg['method'] == 'workspace/configuration':
                        items = msg.get('params', {}).get('items', [])
                        if not isinstance(items, list) or len(items) > 100:
                            raise ValueError('Invalid LSP configuration request')
                        await self.send(dict(id=msg['id'], result=[{} for _ in items]))
                    elif msg['method'] == 'workspace/workspaceFolders':
                        await self.send(dict(id=msg['id'], result=[dict(uri=self.root.as_uri(), name=self.root.name)]))
                    else:
                        await self.send(dict(id=msg['id'], error=dict(code=-32601, message='Client request unsupported')))
                elif msg.get('method') == 'textDocument/publishDiagnostics':
                    params = msg.get('params', {})
                    uri = params.get('uri')
                    doc = self.documents.get(uri)
                    if doc and (params.get('version') is None or params['version'] == doc[0]):
                        items = params.get('diagnostics')
                        if not isinstance(items, list):
                            raise ValueError('Invalid LSP diagnostics')
                        self.diagnostics[uri] = dict(items=items[:200], truncated=len(items)>200,
                            freshness='versioned' if params.get('version') is not None else 'unversioned')
                        self.changed.set()
                elif 'id' in msg:
                    future = self.pending.get(msg['id'])
                    if future and not future.done():
                        if 'error' in msg:
                            future.set_exception(LSPError(msg['error'].get('code')))
                        else:
                            future.set_result(msg.get('result'))
        except asyncio.CancelledError:
            raise
        except Exception:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(ValueError('Language server disconnected or sent invalid data'))
            self.changed.set()

    async def request(self, method, params):
        self.ident += 1
        ident = self.ident
        future = asyncio.get_running_loop().create_future()
        self.pending[ident] = future
        try:
            await self.send(dict(id=ident, method=method, params=params))
            return await future
        finally:
            self.pending.pop(ident, None)
            if not future.done():
                future.cancel()

    async def sync(self, target, content):
        uri = target.as_uri()
        previous = self.documents.get(uri)
        if previous and previous[1] == content:
            return uri
        if not previous and len(self.documents) >= 32:
            oldest = next(iter(self.documents))
            await self.send(dict(method='textDocument/didClose', params={'textDocument': {'uri': oldest}}))
            self.documents.pop(oldest)
            self.diagnostics.pop(oldest, None)
        version = previous[0]+1 if previous else 1
        self.documents[uri] = (version, content)
        self.diagnostics.pop(uri, None)
        self.changed.clear()
        if previous:
            await self.send(dict(method='textDocument/didChange', params=dict(
                textDocument=dict(uri=uri, version=version), contentChanges=[dict(text=content)])))
        else:
            await self.send(dict(method='textDocument/didOpen', params=dict(textDocument=dict(
                uri=uri, languageId=self.cfg.get('language_id', ''), version=version, text=content))))
        return uri

    async def query(self, operation, target, content, line, character, new_name=None):
        uri = await self.sync(target, content)
        if operation == 'diagnostics':
            if self.capabilities.get('diagnosticProvider') is not None:
                try:
                    result = await self.request('textDocument/diagnostic', dict(textDocument=dict(uri=uri)))
                    if not isinstance(result, dict) or result.get('kind') != 'full' or not isinstance(result.get('items'), list):
                        raise ValueError('Expected a full diagnostic report')
                    return dict(status='reported', source='pull', items=result['items'][:200], truncated=len(result['items'])>200)
                except LSPError as exc:
                    if exc.code != -32601:
                        raise
            try:
                async with asyncio.timeout(self.cfg.get('diagnostic_timeout', 2)):
                    while uri not in self.diagnostics:
                        self.changed.clear()
                        if not self.alive:
                            raise ValueError('Language server disconnected')
                        await self.changed.wait()
            except TimeoutError:
                return dict(status='pending', source='push', notice='No current diagnostic report received; this does not mean no errors.')
            return dict(status='reported', source='push', **self.diagnostics[uri])
        methods = dict(definition='definition', references='references', hover='hover', symbols='documentSymbol', implementation='implementation', rename='rename')
        params = dict(textDocument=dict(uri=uri))
        if operation != 'symbols':
            params['position'] = dict(line=line-1, character=character)
        if operation == 'references':
            params['context'] = dict(includeDeclaration=True)
        if operation == 'rename':
            params['newName'] = new_name
        return await self.request('textDocument/'+methods[operation], params)

    async def close(self):
        try:
            if self.alive:
                try:
                    async with asyncio.timeout(1):
                        await self.request('shutdown', None)
                        await self.send(dict(method='exit'))
                except (TimeoutError, ValueError, OSError):
                    pass
        finally:
            if self.proc:
                await terminate(self.proc)
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(ValueError('Language server closed'))
            if self.reader:
                self.reader.cancel()
                await asyncio.gather(self.reader, return_exceptions=True)


class LSPManager:
    def __init__(self, tools):
        self.tools, self.clients, self.locks = tools, {}, {}

    async def disconnect(self, server):
        client = self.clients.pop(server, None)
        if client:
            await client.close()

    def status(self):
        return {name: ('connected' if name in self.clients and self.clients[name].alive else 'disconnected')
                for name in self.tools.settings.lsp_servers}

    async def query(self, server, operation, path, line=1, character=0, new_name=None):
        if operation not in {'definition', 'references', 'hover', 'symbols', 'diagnostics', 'implementation', 'rename'} or line<1 or character<0:
            raise ValueError('Invalid LSP query/position')
        cfg = self.tools.settings.lsp_servers.get(server)
        if not cfg:
            raise ValueError('Unknown LSP server')
        target = self.tools.path(path)
        if target.stat().st_size>2_000_000:
            raise ValueError('LSP file exceeds 2 MB')
        content = target.read_text('utf-8')
        async with self.locks.setdefault(server, asyncio.Lock()):
            client = self.clients.get(server)
            if client and (not client.alive or client.cfg != cfg):
                await self.disconnect(server)
                client = None
            try:
                async with asyncio.timeout(cfg.get('timeout', 30)):
                    if client is None:
                        detail = json.dumps(dict(server=server, command=cfg['command'], args=cfg.get('args', []), path=path))
                        if await self.tools.approve('Start language server? It runs with your user permissions until disconnected.', detail) is not True:
                            return 'Denied: language server not started.'
                        client = Client(self.tools.settings.root, cfg)
                        self.clients[server] = client
                        await client.start()
                    result = await client.query(operation, target, content, line, character, new_name) if operation == 'rename' else await client.query(operation, target, content, line, character)
                    return json.dumps(dict(result=result, notice='Untrusted server data; positions use UTF-16.'), ensure_ascii=False)
            except BaseException:
                await self.disconnect(server)
                raise

    async def close(self):
        for name in list(self.clients):
            await self.disconnect(name)
