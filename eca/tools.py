"""Workspace tools, explicit approvals, bounded output and cancellable processes."""
import asyncio
import difflib
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile


SKIP = {".git", ".eca", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".next", "target"}


def schema(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


STR = {"type": "string"}
INT = {"type": "integer"}
SCHEMAS = [
    schema("read", "Read a UTF-8 text file with 1-based lines. Read before editing.", {"path": STR, "offset": INT, "limit": INT}, ["path"]),
    schema("glob", "Find workspace files; ignores build/cache/secret directories.", {"pattern": STR}, ["pattern"]),
    schema("grep", "Search literal text in workspace files; optional filename glob.", {"query": STR, "include": STR}, ["query"]),
    schema("write", "Create or overwrite a UTF-8 file with diff approval; prefer edit for existing files.", {"path": STR, "content": STR}, ["path", "content"]),
    schema("edit", "Replace exactly one occurrence. Ambiguous matches are rejected.", {"path": STR, "old": STR, "new": STR}, ["path", "old", "new"]),
    schema("shell", "Run a shell command in the project. Windows uses PowerShell; requires approval. Includes exit code.", {"command": STR, "timeout": INT}, ["command"]),
    schema("todo", "Replace task plan. Completion is a planning label, not proof tests passed.", {"items": {"type": "array", "items": {"type": "object", "properties": {"content": STR, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["content", "status"], "additionalProperties": False}}}, ["items"]),
    schema("ask", "Ask for missing requirements; use only when needed.", {"question": STR}, ["question"]),
]


def allowed(mode):
    return {"read", "glob", "grep", "todo", "ask"} if mode == "plan" else (set() if mode == "chat" else {s["function"]["name"] for s in SCHEMAS})


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".eca-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            os.chmod(tmp, path.stat().st_mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


async def terminate(proc):
    if proc.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec("taskkill", "/PID", str(proc.pid), "/T", "/F",
                  stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                  creationflags=subprocess.CREATE_NO_WINDOW)
        await killer.wait()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(proc.wait(), 5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def run_process(argv, root, timeout=120, limit=24_000):
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    spawning = asyncio.create_task(asyncio.create_subprocess_exec(*argv, cwd=root, stdout=asyncio.subprocess.PIPE,
                                               stderr=asyncio.subprocess.PIPE, **options))
    try:
        proc = await asyncio.shield(spawning)
    except asyncio.CancelledError:
        # Cancellation may arrive while Windows is still creating the process.
        # Obtain the handle before leaving, so a child cannot escape cleanup.
        proc = await spawning
        await terminate(proc)
        await proc.communicate()
        raise

    async def drain(reader):
        parts, size, truncated = [], 0, False
        while chunk := await reader.read(8192):
            if size < limit:
                parts.append(chunk[:limit-size])
            size += len(chunk)
            truncated = size > limit
        return b"".join(parts).decode("utf-8", errors="replace") + ("\n[output truncated]" if truncated else "")

    out = asyncio.create_task(drain(proc.stdout))
    err = asyncio.create_task(drain(proc.stderr))
    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout)
        stdout, stderr = await asyncio.wait_for(asyncio.gather(out, err), 5)
    except asyncio.TimeoutError:
        timed_out = True
        await terminate(proc)
        for task in (out, err):
            if not task.done():
                task.cancel()
        await asyncio.gather(out, err, return_exceptions=True)
        stdout = out.result() if out.done() and not out.cancelled() and out.exception() is None else "[output unavailable after timeout]"
        stderr = err.result() if err.done() and not err.cancelled() and err.exception() is None else ""
    except asyncio.CancelledError:
        await terminate(proc)
        for task in (out, err):
            task.cancel()
        await asyncio.gather(out, err, return_exceptions=True)
        raise
    return json.dumps({"exit_code": proc.returncode, "timed_out": timed_out, "stdout": stdout, "stderr": stderr}, ensure_ascii=False)


class Tools:
    def __init__(self, settings, state, approve, ask, emit):
        self.settings, self.state = settings, state
        self.approve, self.question, self.emit = approve, ask, emit
        self.changes = None

    def path(self, value):
        path = (self.settings.root / value).resolve()
        if not path.is_relative_to(self.settings.root):
            raise ValueError("Path is outside the project")
        parts = [p.lower() for p in path.relative_to(self.settings.root).parts]
        if any(p in {".git", ".eca"} for p in parts) or any(p == ".env" or (p.startswith(".env.") and p != ".env.example") for p in parts):
            raise ValueError("Protected path (.git, .eca or secrets)")
        if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
            raise ValueError("Private key files are excluded")
        return path

    def files(self):
        count = 0
        for directory, dirs, files in os.walk(self.settings.root, followlinks=False):
            dirs[:] = [d for d in sorted(dirs) if d.lower() not in SKIP and not (Path(directory) / d).is_symlink()]
            for name in sorted(files):
                count += 1
                if count > 30_000:
                    return
                try:
                    path = self.path(str(Path(directory) / name))
                except ValueError:
                    continue
                if path.is_file():
                    yield path

    async def execute(self, name, args):
        if name not in allowed(self.settings.mode):
            return f"Denied: {name} is unavailable in {self.settings.mode} mode."
        try:
            spec = next(s["function"]["parameters"] for s in SCHEMAS if s["function"]["name"] == name)
            if not isinstance(args, dict) or set(args) - set(spec["properties"]) or set(spec["required"]) - set(args):
                raise ValueError("Unexpected or missing tool arguments")
            for key, value in args.items():
                kind = spec["properties"][key]["type"]
                if (kind == "string" and not isinstance(value, str)) or (kind == "integer" and type(value) is not int) or (kind == "array" and not isinstance(value, list)):
                    raise ValueError(f"Invalid type for {key}")
            result = await getattr(self, name)(**args)
            if name == "shell":
                return result  # Already bounded per stream; keep the JSON envelope valid.
            return result[:self.settings.output_limit] + ("\n[truncated]" if len(result) > self.settings.output_limit else "")
        except (ValueError, OSError, UnicodeError) as exc:
            return f"Error: {exc}"

    async def read(self, path, offset=1, limit=200):
        target = self.path(path)
        if offset < 1 or not 1 <= limit <= 2000:
            raise ValueError("offset >= 1; limit must be 1..2000")
        if target.stat().st_size > 2_000_000:
            raise ValueError("File exceeds 2 MB read limit")
        text = target.read_bytes().decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("Binary files are not supported")
        lines = text.splitlines()
        return "\n".join(f"{i+offset}: {line}" for i, line in enumerate(lines[offset-1:offset-1+limit])) + f"\n[total lines: {len(lines)}]"

    async def glob(self, pattern):
        return await asyncio.to_thread(self._glob, pattern)

    def _glob(self, pattern):
        results = []
        for path in self.files():
            rel = path.relative_to(self.settings.root).as_posix()
            if fnmatch.fnmatch(rel, pattern) or (pattern.startswith("**/") and fnmatch.fnmatch(rel, pattern[3:])):
                results.append(rel)
            if len(results) >= 200:
                results.append("[200-file limit reached]")
                break
        return "\n".join(results) or "No files matched."

    async def grep(self, query, include="*"):
        if not query:
            raise ValueError("query must not be empty")
        return await asyncio.to_thread(self._grep, query, include)

    def _grep(self, query, include):
        results = []
        for path in self.files():
            rel = path.relative_to(self.settings.root).as_posix()
            if not fnmatch.fnmatch(rel, include):
                continue
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                text = path.read_bytes().decode("utf-8-sig")
                if "\x00" in text:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if query in line:
                        results.append(f"{rel}:{i}: {line[:500]}")
                    if len(results) >= 100:
                        return "\n".join(results) + "\n[100-match limit reached]"
            except (OSError, UnicodeError):
                continue
        return "\n".join(results) or "No matches."

    async def change(self, path, before, content):
        if len(content.encode("utf-8")) > 2_000_000:
            raise ValueError("Change exceeds 2 MB limit")
        old = before.decode("utf-8") if before is not None else ""
        diff = "".join(difflib.unified_diff(old.splitlines(True), content.splitlines(True), fromfile=f"a/{path.relative_to(self.settings.root)}", tofile=f"b/{path.relative_to(self.settings.root)}"))
        if before is not None and old == content:
            return "No change."
        self.emit("diff", diff)
        if self.settings.permission != "accept-edits" and await self.approve(f"Write {path.relative_to(self.settings.root)}?", diff) is not True:
            return "Denied by user. File unchanged."
        current = path.read_bytes() if path.exists() else None
        if current != before:
            raise ValueError("File changed while awaiting approval. Read it again before editing.")
        # Resolve again: a directory symlink might have changed while approval was open.
        if self.path(str(path)) != path:
            raise ValueError("File path changed while awaiting approval")
        relative = path.relative_to(self.settings.root).as_posix()
        ident = self.changes.prepare(relative, before, content.encode("utf-8")) if self.changes else None
        atomic_write(path, content)
        if ident is not None:
            self.changes.mark(ident, "applied")
        review = f" Change #{ident}; review with /changes {ident}, undo with /undo {ident}." if ident is not None else ""
        return f"Saved {relative}.{review} This is not a test result; run appropriate checks."

    async def write(self, path, content):
        target = self.path(path)
        if len(content.encode("utf-8")) > 2_000_000:
            raise ValueError("Write exceeds 2 MB limit")
        if target.exists() and target.stat().st_size > 2_000_000:
            raise ValueError("Existing file exceeds 2 MB limit")
        before = target.read_bytes() if target.exists() else None
        return await self.change(target, before, content)

    async def edit(self, path, old, new):
        target = self.path(path)
        if target.stat().st_size > 2_000_000:
            raise ValueError("Existing file exceeds 2 MB limit")
        before = target.read_bytes()
        content = before.decode("utf-8")
        if "\r\n" in content:
            old = old.replace("\r\n", "\n").replace("\n", "\r\n")
            new = new.replace("\r\n", "\n").replace("\n", "\r\n")
        if not old or content.count(old) != 1:
            raise ValueError("old must match exactly once; read a larger unique section")
        return await self.change(target, before, content.replace(old, new, 1))

    async def shell(self, command, timeout=None):
        timeout = timeout or self.settings.command_timeout
        if not 1 <= timeout <= 600:
            raise ValueError("Shell timeout must be 1..600 seconds")
        if await self.approve("Run shell command? Commands have your user account's permissions.", command) is not True:
            return "Denied by user. Command not executed."
        if os.name == "nt":
            executable = shutil.which("pwsh") or shutil.which("powershell")
            if not executable:
                raise ValueError("PowerShell not found")
            prefix = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            argv = [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", prefix + command]
        else:
            argv = ["/bin/sh", "-c", command]
        return await run_process(argv, self.settings.root, timeout, max(1, self.settings.output_limit // 3))

    async def todo(self, items):
        if len(items) > 50:
            raise ValueError("At most 50 tasks")
        for item in items:
            if not isinstance(item, dict) or set(item) != {"content", "status"} or not isinstance(item["content"], str) or item["status"] not in {"pending", "in_progress", "completed"}:
                raise ValueError("Each task requires content and a valid status")
        self.state["tasks"] = items
        self.emit("tasks", items)
        return "Task plan updated."

    async def ask(self, question):
        # Instance callback is stored separately to avoid shadowing this tool method.
        response = await self.question(question)
        return response if isinstance(response, str) else "No user answer was provided."
