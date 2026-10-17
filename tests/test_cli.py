"""End-to-end CLI tests against a local streaming HTTP fixture, never paid APIs."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


class CLITests(unittest.TestCase):
    def test_real_http_stream_tool_execution_and_resume(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(payload)
                if payload["messages"][-1]["role"] == "tool" or "Continue" in payload["messages"][-1].get("content", ""):
                    delta, reason = {"content": "Fixture completed."}, "stop"
                else:
                    delta = {"tool_calls": [{"index": 0, "id": "fixture-1", "type": "function", "function": {"name": "write", "arguments": json.dumps({"path": "hello.py", "content": "print('hello')\n"})}}]}
                    reason = "tool_calls"
                chunk = {"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture", "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
                data = ("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        base = Path(os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env = {**{k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}, "ECA_API_KEY": "fixture-secret", "ECA_MODEL": "fixture", "PYTHONUTF8": "1",
                   "ECA_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1"}
            command = [sys.executable, "-B", "-m", "eca", "--cwd", tmp, "--json"]
            try:
                first = subprocess.run([*command, "--accept-edits", "-p", "Create hello.py"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
                self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                events = [json.loads(line) for line in first.stdout.splitlines()]
                self.assertTrue(any(e["event"] == "result" for e in events))
                self.assertNotIn("fixture-secret", first.stdout)
                self.assertEqual((Path(tmp) / "hello.py").read_text(), "print('hello')\n")
                second = subprocess.run([*command, "--resume", "latest", "-p", "Continue with summary"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
                self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
                self.assertEqual(len(requests), 3)
                self.assertIn("tool", [m["role"] for m in requests[-1]["messages"]])
                self.assertEqual(requests[-1]["messages"][-1]["content"], "Continue with summary")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
