"""Interactive terminal and scriptable one-shot entry point."""
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import signal
import sys
import tomllib

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from . import __version__
from .agent import Agent
from .config import Settings
from .store import Store
from .tools import atomic_write, run_process


HELP = {
    "/help": "Show commands", "/new": "Start a new session", "/sessions": "List saved sessions",
    "/resume ID": "Resume a session (or latest)", "/mode code|plan|chat": "Change execution mode",
    "/model NAME": "Change model for this process", "/permission ask|accept-edits": "File edit approvals",
    "/agent NAME": "Select an eca.toml profile (off resets)", "/compact": "Summarize context (one API request)",
    "/tasks": "Show the task plan", "/status": "Show session and configuration", "/diff": "Show Git diff",
    "/export": "Export full session to Markdown", "/exit": "Save and quit",
}


def parser():
    p = argparse.ArgumentParser(prog="eca", description="Easy Coding Agent - your project, your model, your terminal")
    p.add_argument("--version", action="version", version=f"Easy Coding Agent {__version__}")
    p.add_argument("--cwd", type=Path, default=Path.cwd(), help="Project directory")
    p.add_argument("-p", "--prompt", help="Run a single task and exit")
    p.add_argument("--json", action="store_true", help="JSONL events for --prompt")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--api-format", choices=["openai", "anthropic"], help="Model wire protocol")
    p.add_argument("--mode", choices=["code", "plan", "chat"])
    p.add_argument("--accept-edits", action="store_true", help="Approve file edits inside project; shell still requires approval")
    p.add_argument("--allow-shell", action="store_true", help="Explicitly approve ALL shell commands (including outside project); for trusted one-shot tasks only")
    p.add_argument("--resume", nargs="?", const="latest", help="Resume session ID prefix, or latest")
    p.add_argument("--list-sessions", action="store_true")
    p.add_argument("--doctor", action="store_true", help="Check local configuration without an API request")
    return p


class App:
    def __init__(self, settings, args):
        self.settings, self.args = settings, args
        self.console = Console(highlight=False)
        self.store = Store(settings.root)
        try:
            self.state = self.store.load(args.resume) if args.resume else self.store.create(settings.mode)
        except Exception:
            self.store.close()
            raise
        if args.resume and args.mode is None:
            settings.mode = self.state.get("mode", "code")
        self.state["mode"] = settings.mode
        self.prompt = None
        self.agent = self.make_agent()
        self.streaming = False

    def make_agent(self):
        return Agent(self.settings, self.store, self.state, self.approve, self.question, self.emit)

    def redact(self, text):
        return text.replace(self.settings.api_key, "[redacted]") if self.settings.api_key else text

    def emit(self, event, data):
        if self.args.json:
            print(self.redact(json.dumps({"event": event, "data": data}, ensure_ascii=False)), flush=True)
            return
        if event == "text":
            self.console.print(self.redact(data), end="", markup=False, highlight=False)
            self.streaming = True
            return
        if self.streaming:
            self.console.print()
            self.streaming = False
        if event == "diff":
            self.console.print(Syntax(self.redact(data[:20_000]), "diff", word_wrap=True))
        elif event == "tool":
            details = {k: (v[:180] + "…" if isinstance(v, str) and len(v) > 180 else v) for k, v in data["args"].items()}
            self.console.print(f"  › {data['name']}  {self.redact(json.dumps(details, ensure_ascii=False))}", style="cyan", markup=False)
        elif event == "result":
            self.console.print(self.redact(data[:1500]), style="dim", markup=False)
        elif event == "tasks":
            for task in data:
                self.console.print(f"  [{task['status']}] {task['content']}", markup=False)
        elif event in {"notice", "error"}:
            self.console.print(self.redact(str(data)), style="yellow" if event == "notice" else "red", markup=False)

    async def approve(self, message, detail):
        if message.startswith("Run shell") and self.args.allow_shell:
            return True
        if self.args.prompt is not None:
            self.emit("notice", "Approval unavailable in one-shot mode; action denied. Use --accept-edits / --allow-shell explicitly if appropriate.")
            return False
        self.console.print(message, style="yellow", markup=False)
        if message.startswith("Run shell"):
            self.console.print(detail, markup=False)
        try:
            answer = await self.prompt.prompt_async("Allow once? [y/N] ", completer=None, bottom_toolbar=None)
            return answer.strip().lower() in {"y", "yes"}
        except (EOFError, KeyboardInterrupt):
            return False

    async def question(self, question):
        if self.args.prompt is not None:
            return "User input is unavailable in one-shot mode. Explain what is missing and stop."
        self.console.print(question, markup=False)
        try:
            return await self.prompt.prompt_async("Answer › ", completer=None, bottom_toolbar=None)
        except (EOFError, KeyboardInterrupt):
            raise asyncio.CancelledError

    async def run_task(self, text):
        task = asyncio.create_task(self.agent.run(text))
        loop = asyncio.get_running_loop()
        previous = signal.getsignal(signal.SIGINT)
        def interrupt(*_):
            # Do not interrupt the cleanup await on a second Ctrl+C.
            if not task.cancelling():
                loop.call_soon_threadsafe(task.cancel)
        signal.signal(signal.SIGINT, interrupt)
        try:
            await task
        except asyncio.CancelledError:
            return 130
        except Exception as exc:
            self.emit("error", f"{type(exc).__name__}: {exc}")
            return 1
        finally:
            signal.signal(signal.SIGINT, previous)
            if self.streaming:
                self.console.print()
                self.streaming = False
        return 0 if self.state["status"] == "idle" else 2

    def show_sessions(self):
        rows = self.store.list()
        if self.args.json:
            self.emit("sessions", [{"id": i, "title": t, "updated": u} for i, t, u in rows])
            return
        table = Table("ID", "Updated", "Title", title="Sessions · this project")
        for ident, title, updated in rows:
            table.add_row(ident[:12], datetime.fromtimestamp(updated).strftime("%m-%d %H:%M"), title)
        self.console.print(table)

    def status(self):
        data = {"project": str(self.settings.root), "session": self.state["id"], "status": self.state["status"],
                "model": self.settings.model, "api_format": self.settings.api_format, "mode": self.settings.mode, "permission": self.settings.permission,
                "messages": len(self.state["messages"]), "last_reported_usage": self.state.get("usage", {})}
        if self.args.json:
            self.emit("status", data)
        else:
            self.console.print(json.dumps(data, ensure_ascii=False, indent=2), markup=False)

    async def command(self, text):
        command, _, arg = text.partition(" ")
        arg = arg.strip()
        if command == "/exit":
            return False
        if command == "/help":
            table = Table("Command", "Action")
            for key, value in HELP.items():
                table.add_row(key, value)
            self.console.print(table)
        elif command in {"/new", "/resume"}:
            state = self.store.create(self.settings.mode) if command == "/new" else self.store.load(arg or "latest")
            await self.agent.close()
            self.state = state
            self.settings.mode = state["mode"]
            self.agent = self.make_agent()
            self.status()
        elif command == "/sessions":
            self.show_sessions()
        elif command == "/mode":
            if arg not in {"code", "plan", "chat"}:
                raise ValueError("Usage: /mode code|plan|chat")
            self.settings.mode = self.state["mode"] = arg
            self.store.save(self.state)
        elif command == "/permission":
            if arg not in {"ask", "accept-edits"}:
                raise ValueError("Usage: /permission ask|accept-edits")
            self.settings.permission = arg
        elif command == "/model":
            if not arg:
                raise ValueError("Usage: /model MODEL_NAME")
            self.settings.model = arg
        elif command == "/agent":
            path = self.settings.root / "eca.toml"
            profiles = tomllib.loads(path.read_text("utf-8")).get("profiles", {}) if path.exists() else {}
            if not arg:
                self.console.print("Profiles: " + ", ".join(profiles) + " (off resets)", markup=False)
            elif arg == "off":
                self.state.pop("profile", None)
            elif arg in profiles and isinstance(profiles[arg], str):
                self.state["profile"] = profiles[arg]
            else:
                raise ValueError("Unknown profile; define a string in [profiles] in eca.toml")
            self.store.save(self.state)
        elif command == "/compact":
            await self.agent.compact()
            self.emit("notice", "Context summarized; full session retained.")
        elif command == "/tasks":
            self.emit("tasks", self.state["tasks"])
        elif command == "/status":
            self.status()
        elif command == "/diff":
            result = json.loads(await run_process(["git", "--no-pager", "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", ".", ":(exclude).env", ":(exclude).env.*", ":(exclude).eca", ":(exclude)venv", ":(exclude)*.pyc"], self.settings.root, 20))
            self.console.print(Syntax(result["stdout"] or result["stderr"] or "No tracked changes. New untracked files are not included.", "diff"))
        elif command == "/export":
            path = self.settings.state_dir / "exports" / f"{self.state['id']}.md"
            body = "# " + self.state["title"] + "\n\n"
            for msg in self.state["messages"]:
                body += f"## {msg['role']}\n\n{msg.get('content') or ''}\n\n"
                if msg.get("tool_calls"):
                    body += "````json\n" + json.dumps(msg["tool_calls"], ensure_ascii=False, indent=2) + "\n````\n\n"
            atomic_write(path, self.redact(body))
            self.emit("notice", f"Exported to {path}")
        else:
            raise ValueError("Unknown command. Use /help.")
        return True

    async def interactive(self):
        self.console.print(Panel(f"[bold cyan]Easy Coding Agent[/]  {__version__}\nYour project. Your model. Your terminal.", border_style="cyan", expand=False))
        self.console.print(f"Project: {self.settings.root}\nModel: {self.settings.model}\n/help · Shift+Tab mode · Ctrl+J newline · Ctrl+C stop · /exit", markup=False)
        if not self.settings.api_key:
            self.emit("notice", "No API key configured. See README or run eca --doctor.")
        bindings = KeyBindings()

        @bindings.add("s-tab")
        def toggle(event):
            modes = ["code", "plan", "chat"]
            self.settings.mode = self.state["mode"] = modes[(modes.index(self.settings.mode) + 1) % len(modes)]
            self.store.save(self.state)
            event.app.invalidate()

        @bindings.add("c-j")
        def newline(event):
            event.current_buffer.insert_text("\n")

        completer = WordCompleter([c.split()[0] for c in HELP], sentence=True)
        self.prompt = PromptSession(history=FileHistory(str(self.settings.state_dir / "input.history")))
        while True:
            try:
                text = await self.prompt.prompt_async(lambda: f"{self.settings.mode} › ", completer=completer, key_bindings=bindings,
                    bottom_toolbar=lambda: [("", f" {self.settings.model} | {self.settings.permission} | {self.state['id'][:8]} | {len(self.state['messages'])} messages ")])
                if not text.strip():
                    continue
                if text.startswith("/"):
                    if not await self.command(text.strip()):
                        break
                else:
                    await self.run_task(text)
            except KeyboardInterrupt:
                self.emit("notice", "Input cancelled. Use /exit to quit.")
            except EOFError:
                break
            except Exception as exc:
                self.emit("error", str(exc))
        return 0

    async def close(self):
        await self.agent.close()
        self.store.close()


async def async_main(args):
    if args.json and args.prompt is None and not args.list_sessions and not args.doctor:
        raise ValueError("--json requires --prompt, --list-sessions or --doctor")
    if args.allow_shell and args.prompt is None:
        raise ValueError("--allow-shell is only for explicit one-shot tasks")
    settings = Settings.load(args.cwd, model=args.model, base_url=args.base_url, api_format=args.api_format, mode=args.mode,
                             permission="accept-edits" if args.accept_edits else None)
    if args.doctor:
        print(json.dumps({"version": __version__, "python": sys.version.split()[0], "project": str(settings.root),
              "model": settings.model, "api_format": settings.api_format, "base_url": settings.base_url, "api_key_configured": bool(settings.api_key),
              "permission": settings.permission, "mode": settings.mode, "state_dir": str(settings.state_dir),
              "network_checked": False}, ensure_ascii=False, indent=None if args.json else 2))
        return 0
    if args.list_sessions:
        store = Store(settings.root)
        try:
            print(json.dumps([{"id": i, "title": t, "updated": u} for i, t, u in store.list()], ensure_ascii=False, indent=None if args.json else 2))
        finally:
            store.close()
        return 0
    app = App(settings, args)
    try:
        if args.prompt is not None:
            code = await app.run_task(args.prompt)
            app.status()
            return code
        return await app.interactive()
    finally:
        await app.close()


def main():
    args = parser().parse_args()
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        # Startup errors must never print a Settings repr or secret-bearing environment.
        if args.json:
            print(json.dumps({"event": "error", "data": str(exc)}, ensure_ascii=False))
        else:
            print(f"ECA: {exc}", file=sys.stderr)
        return 1
