"""Exercise an installed npm launcher against a local HTTP fixture, no paid API."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    args = parser.parse_args()
    root = args.project.resolve()
    root.mkdir(parents=True, exist_ok=False)
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'path': self.path, 'stream': bool(body.get('stream'))})
            if self.headers.get('Authorization') != 'Bearer synthetic-smoke-key' or self.path != '/v1/chat/completions':
                self.send_response(401)
                self.end_headers()
                return
            self.send_response(200)
            if not body.get('stream'):
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'choices': [{'message': {'role': 'assistant', 'content': 'OK'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 1, 'total_tokens': 4}}).encode())
                return
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for delta, reason in (({'role': 'assistant', 'content': 'READY'}, None), ({}, 'stop')):
                data = {'id': 'smoke', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'fixture',
                        'choices': [{'index': 0, 'delta': delta, 'finish_reason': reason}]}
                self.wfile.write(('data: ' + json.dumps(data) + '\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = {k: v for k, v in os.environ.items() if not k.startswith('ECA_') and k not in
           {'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'MODELSCOPE_API_KEY', 'MODEL_NAME'}}
    for k in ('ECA_RUNTIME_HOME', 'ECA_PYTHON'):
        if k in os.environ:
            env[k] = os.environ[k]
    env['ECA_SMOKE_KEY'] = 'synthetic-smoke-key'
    env['NO_PROXY'] = env['no_proxy'] = '127.0.0.1,localhost'
    command = ['node', str(args.launcher.resolve())]
    def run(*argv, stdin=None):
        result = subprocess.run(command + list(argv), cwd=root, env=env, input=stdin,
                                text=True, encoding='utf-8', capture_output=True, timeout=60)
        assert result.returncode == 0, (argv, result.returncode, result.stdout, result.stderr)
        assert 'synthetic-smoke-key' not in result.stdout + result.stderr
        return result.stdout
    try:
        version = run('--version').strip()
        answers = f'openai\nhttp://127.0.0.1:{server.server_port}/v1\nfixture\nECA_SMOKE_KEY\ny\n'
        run('--configure', stdin=answers)
        assert not (root/'.env').exists()
        local = json.loads(run('--doctor', '--json'))
        assert local['ready'] and not local['network_checked'] and not calls
        live = json.loads(run('--doctor', '--check-api', '--json'))
        assert live['ready'] and len(calls) == 1
        assert not (root/'.eca').exists(), 'diagnostics must not create a session'
        (root/'eca.py').write_text('raise RuntimeError("workspace module must not be loaded")\n')
        response = run('-p', 'Say READY.', '--json')
        assert 'READY' in response and len(calls) == 2
        sessions = json.loads(run('--list-sessions', '--json'))
        assert len(sessions) == 1
        report = {'version': version, 'configuration': 'passed', 'offline_doctor': 'passed',
                  'api_doctor': 'passed', 'installed_streaming_task': 'passed', 'session_listing': 'passed',
                  'workspace_module_isolation': 'passed', 'fixture_requests': calls, 'paid_api_calls': 0}
        (root.parent/'installed-smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
