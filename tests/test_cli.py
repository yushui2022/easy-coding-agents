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
        self.run_fixture("openai")

    def test_anthropic_http_stream_tool_execution_and_resume(self):
        self.run_fixture("anthropic")

    def run_fixture(self, api_format):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(payload)
                if len(requests) > 1:
                    delta, reason = {"content": "Fixture completed."}, "stop"
                else:
                    delta = {"tool_calls": [{"index": 0, "id": "fixture-1", "type": "function", "function": {"name": "write", "arguments": json.dumps({"path": "hello.py", "content": "print('hello')\n"})}}]}
                    reason = "tool_calls"
                chunk = {"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture", "choices": [{"index": 0, "delta": delta, "finish_reason": reason}], "usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7}}
                data = ("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode()
                if api_format == "anthropic":
                    if reason == "tool_calls":
                        fn = delta["tool_calls"][0]["function"]
                        block = {"type": "tool_use", "id": "fixture-1", "name": fn["name"], "input": {}}
                        change = {"type": "input_json_delta", "partial_json": fn["arguments"]}
                    else:
                        block = {"type": "text", "text": ""}
                        change = {"type": "text_delta", "text": delta["content"]}
                    events = [
                        {"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
                        {"type": "content_block_start", "index": 0, "content_block": block},
                        {"type": "content_block_delta", "index": 0, "delta": change},
                        {"type": "content_block_stop", "index": 0},
                        {"type": "message_delta", "delta": {"stop_reason": "tool_use" if reason == "tool_calls" else "end_turn"}, "usage":{"output_tokens":2}},
                        {"type": "message_stop"},
                    ]
                    data = "".join("data: " + json.dumps(e) + "\n\n" for e in events).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        base = Path(os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            (Path(tmp) / "eca.toml").write_text("[agent]\nmax_output_tokens = 384\n", encoding="utf-8")
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env = {**{k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}, "ECA_API_KEY": "fixture-secret", "ECA_MODEL": "fixture", "PYTHONUTF8": "1",
                   "ECA_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1", "ECA_API_FORMAT": api_format}
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
                usage = subprocess.run([*command, '--usage'],env=env,capture_output=True,text=True,encoding='utf-8',timeout=60)
                self.assertEqual(usage.returncode,0,usage.stdout+usage.stderr)
                totals=json.loads(usage.stdout)
                self.assertEqual(totals['requests'],3)
                self.assertEqual(totals['reported_tokens']['input'],15)
                self.assertEqual(totals['reported_tokens']['output'],6)
                self.assertEqual(totals['incomplete_usage_requests'],0)
                self.assertTrue(all(payload.get("max_tokens") == 384 for payload in requests))
                if api_format == "anthropic":
                    self.assertTrue(any(b["type"] == "tool_result" for m in requests[-1]["messages"] for b in m["content"]))
                    self.assertTrue(any(b.get("text") == "Continue with summary" for m in requests[-1]["messages"] for b in m["content"]))
                else:
                    self.assertIn("tool", [m["role"] for m in requests[-1]["messages"]])
                    self.assertTrue(any(m.get("content") == "Continue with summary" for m in requests[-1]["messages"]))
                review = subprocess.run([*command, "--changes"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
                self.assertEqual(review.returncode, 0, review.stdout + review.stderr)
                changes = json.loads(review.stdout)["data"]
                self.assertEqual(changes[0]["path"], "hello.py")
                ident = str(changes[0]["id"])
                accepted = subprocess.run([*command, "--accept-change", ident], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
                self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
                undo = subprocess.run([*command, "--undo", ident], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
                self.assertEqual(undo.returncode, 0, undo.stdout + undo.stderr)
                self.assertFalse((Path(tmp) / "hello.py").exists())
                self.assertEqual(len(requests), 3, "Review and undo must not call the model")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
