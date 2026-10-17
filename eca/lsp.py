"""Bounded stdio LSP queries. Server-initiated edits are never applied."""
import asyncio
import json
import os
import subprocess

from .tools import terminate


def validate_servers(servers):
    if not isinstance(servers, dict):
        raise ValueError('lsp_servers must be a table')
    for cfg in servers.values():
        if not isinstance(cfg, dict) or set(cfg) - {'command', 'args', 'language_id', 'timeout'}:
            raise ValueError('Invalid LSP options')
        if not isinstance(cfg.get('command'), str) or not cfg['command'].strip():
            raise ValueError('LSP command is required')
        if not isinstance(cfg.get('args', []), list) or not all(isinstance(x, str) for x in cfg.get('args', [])):
            raise ValueError('LSP args must be strings')
        if not isinstance(cfg.get('language_id', ''), str):
            raise ValueError('Invalid LSP language_id')
        if type(cfg.get('timeout', 30)) is not int or not 1 <= cfg.get('timeout', 30) <= 120:
            raise ValueError('LSP timeout must be 1..120')


async def query(tools, server, operation, path, line=1, character=0):
    methods = dict(definition='textDocument/definition', references='textDocument/references',
                   hover='textDocument/hover', symbols='textDocument/documentSymbol',
                   diagnostics='textDocument/diagnostic')
    if operation not in methods or line < 1 or character < 0:
        raise ValueError('Invalid LSP query/position')
    cfg = tools.settings.lsp_servers.get(server)
    if not cfg:
        raise ValueError('Unknown LSP server')
    target = tools.path(path)
    if target.stat().st_size > 2_000_000:
        raise ValueError('LSP file exceeds 2 MB')
    content = target.read_text('utf-8')
    detail = json.dumps(dict(server=server, command=cfg['command'], args=cfg.get('args', []), path=path))
    if await tools.approve('Start language server? It runs with your user permissions.', detail) is not True:
        return 'Denied: language server not started.'
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(cfg['command'], *cfg.get('args', []),
        cwd=tools.settings.root, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, **options))
    try:
        proc = await asyncio.shield(spawn)
    except asyncio.CancelledError:
        proc = await spawn
        await terminate(proc)
        raise

    async def send(value):
        data = json.dumps(dict(jsonrpc='2.0', **value)).encode('utf-8')
        proc.stdin.write(f'Content-Length: {len(data)}\r\n\r\n'.encode() + data)
        await proc.stdin.drain()

    async def request(ident, method, params):
        await send(dict(id=ident, method=method, params=params))
        for _ in range(1000):
            headers = await proc.stdout.readuntil(b'\r\n\r\n')
            lengths = [int(x.split(b':', 1)[1]) for x in headers.split(b'\r\n') if x.lower().startswith(b'content-length:')]
            if len(lengths) != 1 or not 0 < lengths[0] <= 2_000_000:
                raise ValueError('Invalid LSP frame')
            message = json.loads(await proc.stdout.readexactly(lengths[0]))
            if 'method' in message and 'id' in message:
                # Do not let workspace/applyEdit or configuration requests bypass policy.
                await send(dict(id=message['id'], error=dict(code=-32601, message='Client request unsupported')))
            elif message.get('id') == ident:
                if 'error' in message:
                    raise ValueError('Language server rejected query (possibly unsupported capability)')
                return message.get('result')
        raise ValueError('LSP notification limit exceeded')

    try:
        async with asyncio.timeout(cfg.get('timeout', 30)):
            initialized = await request(1, 'initialize', dict(processId=None, rootUri=tools.settings.root.as_uri(),
                capabilities={'general': {'positionEncodings': ['utf-16']}}, workspaceFolders=None))
            if (initialized or {}).get('capabilities', {}).get('positionEncoding', 'utf-16') != 'utf-16':
                raise ValueError('Language server did not negotiate UTF-16 positions')
            await send(dict(method='initialized', params={}))
            await send(dict(method='textDocument/didOpen', params=dict(textDocument=dict(
                uri=target.as_uri(), languageId=cfg.get('language_id', ''), version=1, text=content))))
            params = dict(textDocument=dict(uri=target.as_uri()))
            if operation in {'definition', 'references', 'hover'}:
                params['position'] = dict(line=line-1, character=character)
            if operation == 'references':
                params['context'] = dict(includeDeclaration=True)
            result = await request(2, methods[operation], params)
            await request(3, 'shutdown', None)
            await send(dict(method='exit', params=None))
            return json.dumps(dict(result=result, notice='Untrusted server data; positions use UTF-16.'), ensure_ascii=False)[:tools.settings.output_limit]
    finally:
        await terminate(proc)
