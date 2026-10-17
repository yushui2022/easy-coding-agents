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
from .doctor import diagnose
from .usage import UsageLedger


HELP = {
    '/map [QUERY]': 'Show local indexed symbols/imports without a model request',
    '/search QUERY': 'Search indexed source without a model request',
    "/sandbox": "Show durable container execution and cleanup records (no Docker calls)",
    "/progress": "Show recent runtime observations retained across compaction",
    "/verify COMMAND": "Run a user-selected check with normal shell approval",
    "/usage": "Show durable usage and priced subtotals, including child agents",
    "/agents": "List child sessions; resume one to inspect its changes",
    "/models": "List configured model profiles; /model @NAME selects one",
    "/lsp": "Show language-server status; /lsp disconnect NAME closes one",
    "/mcp": "List configured MCP servers without connecting",
    "/help": "Show commands", "/new": "Start a new session", "/sessions": "List saved sessions",
    "/resume ID": "Resume a session (or latest)", "/mode code|plan|chat": "Change execution mode",
    "/model NAME": "Change model for this process", "/permission ask|accept-edits": "File edit approvals",
    "/agent NAME": "Select an eca.toml profile (off resets)", "/compact": "Summarize context (one API request)",
    "/tasks": "Show the task plan", "/status": "Show session and configuration", "/diff": "Show Git diff",
    "/export": "Export full session to Markdown", "/exit": "Save and quit",
    "/changes [ID]": "List recent file edits or inspect one saved diff",
    "/accept ID": "Mark a file edit reviewed (does not commit Git)",
    "/undo ID": "Undo one file edit if no newer edits would be overwritten",
    "/continue": "Continue saved work; inspect uncertain effects before retrying",
    "/memory": "Show project memories with sources and freshness",
    "/remember TEXT": "Explicitly confirm a project constraint for future sessions",
    "/forget ID": "Remove a project memory from storage and search",
}


def parser():
    p = argparse.ArgumentParser(prog="eca", description="Easy Coding Agent - your project, your model, your terminal")
    p.add_argument("--version", action="version", version=f"Easy Coding Agent {__version__}")
    p.add_argument("--cwd", type=Path, default=Path.cwd(), help="Project directory")
    p.add_argument("-p", "--prompt", help="Run a single task and exit")
    p.add_argument("--json", action="store_true", help="JSONL events for --prompt")
    p.add_argument("--verify-command", action='append', default=[], help="Run a check after the task; repeat for up to 10 checks; requires --allow-shell")
    p.add_argument('--repair-attempts', type=int, default=0, help='Opt in to 1..3 repair rounds and rerunning selected checks (default: 0)')
    p.add_argument("--model")
    p.add_argument("--model-profile", help="Select [model_profiles.NAME] with its own endpoint and credential variable")
    p.add_argument("--base-url")
    p.add_argument("--api-format", choices=["openai", "anthropic", "responses"], help="Model wire protocol")
    p.add_argument("--mode", choices=["code", "plan", "chat"])
    p.add_argument('--sandbox', choices=['none', 'docker'], help='Docker runs shell in disposable offline Linux containers; never falls back to host')
    p.add_argument('--sandbox-image', help='Preinstalled trusted Linux image with required tools; never downloaded automatically')
    p.add_argument("--accept-edits", action="store_true", help="Approve file edits inside project; shell still requires approval")
    p.add_argument("--allow-shell", action="store_true", help="Explicitly approve ALL shell commands (including outside project); for trusted one-shot tasks only")
    p.add_argument("--allow-lsp", action="append", default=[], metavar="SERVER", help="Approve startup of one configured language server in one-shot mode")
    p.add_argument("--allow-mcp", action="append", default=[], metavar="SERVER", help="Approve MCP operations for one configured server in one-shot mode; repeat per server")
    p.add_argument("--usage", action="store_true", help="Show saved usage without contacting the model; defaults to latest session")
    p.add_argument("--resume", nargs="?", const="latest", help="Resume session ID prefix, or latest")
    p.add_argument("--list-sessions", action="store_true")
    p.add_argument("--doctor", action="store_true", help="Check local configuration without an API request")
    review = p.add_mutually_exclusive_group()
    review.add_argument("--changes", nargs="?", const="all", metavar="ID", help="Review saved file edits; defaults to latest session")
    review.add_argument("--undo", type=int, metavar="ID", help="Undo a recorded file edit without overwriting newer edits")
    review.add_argument("--accept-change", type=int, metavar="ID", help="Mark a recorded edit reviewed")
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
        review_only = args.changes is not None or args.undo is not None or args.accept_change is not None
        if not review_only and args.resume and not any((args.model_profile, args.model, args.base_url, args.api_format)) and self.state.get('model_profile'):
            try:
                self.settings = settings = settings.select_profile(self.state['model_profile'])
            except Exception:
                self.store.close()
                raise
        if not review_only and settings.model_profile:
            self.state['model_profile'] = settings.model_profile
        elif not review_only:
            self.state.pop('model_profile', None)
        if not review_only:
            if args.resume and args.sandbox is None and self.state.get('sandbox'):
                settings.sandbox = self.state['sandbox']
            if args.resume and args.sandbox_image is None and self.state.get('sandbox_image'):
                settings.sandbox_image = self.state['sandbox_image']
            settings.validate()
            self.state.update(sandbox=settings.sandbox, sandbox_image=settings.sandbox_image)
        self.state["mode"] = settings.mode
        self.store.save(self.state)
        self.prompt = None
        self.agent = self.make_agent()
        self.streaming = False

    def make_agent(self):
        return Agent(self.settings, self.store, self.state, self.approve, self.question, self.emit,
                     child=bool(self.state.get('parent_id')))

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
        elif event == 'verification_suite':
            self.console.print(f"Verification suite: {data['status']} ({len(data.get('rounds', []))} round(s))", markup=False)
        elif event == 'subagent_progress' and data['event'] in {'turn', 'tool', 'error', 'status'}:
            value = data['data']
            label = value.get('name', '') if isinstance(value, dict) else str(value)
            self.console.print(f"  Agent {data['session'][:8]} · {data['event']} · {self.redact(label)}", markup=False)
        elif event in {"notice", "error"}:
            self.console.print(self.redact(str(data)), style="yellow" if event == "notice" else "red", markup=False)

    async def approve(self, message, detail):
        if message.startswith('Start language server') and self.args.prompt is not None:
            return json.loads(detail)['server'] in self.args.allow_lsp
        if message.startswith('Run MCP') and self.args.prompt is not None:
            return json.loads(detail)['server'] in self.args.allow_mcp
        if message.startswith("Run shell") and self.args.allow_shell:
            return True
        if self.args.prompt is not None:
            self.emit("notice", "Approval unavailable in one-shot mode; action denied. Use --accept-edits / --allow-shell explicitly if appropriate.")
            return False
        self.console.print(message, style="yellow", markup=False)
        if message.startswith(("Run shell", "Run MCP", "Start language server")):
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
        from .workflow import verified_run
        task = asyncio.create_task(verified_run(self.agent, text, self.args.verify_command, self.args.repair_attempts))
        loop = asyncio.get_running_loop()
        previous = signal.getsignal(signal.SIGINT)
        def interrupt(*_):
            # Do not interrupt the cleanup await on a second Ctrl+C.
            if not task.cancelling():
                loop.call_soon_threadsafe(task.cancel)
        signal.signal(signal.SIGINT, interrupt)
        try:
            verified = await task
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
        return (0 if verified else 3) if self.state["status"] == "idle" else 2

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
        data = {"project": str(self.agent.settings.root), "session": self.state["id"], "status": self.state["status"],
                "model": self.settings.model, "api_format": self.settings.api_format, "mode": self.settings.mode, "permission": self.settings.permission,
                "messages": len(self.state["messages"]), "last_reported_usage": self.state.get("usage", {})}
        data['usage'] = self.agent.ledger.summary(self.state)
        data['children'] = self.state.get('children',[])
        data["stop_reason"] = self.state.get("stop_reason")
        data['verification'] = self.agent.verification_status()
        from .workflow import suite_status
        data['verification_suite'] = suite_status(self.agent)
        data['sandbox'] = self.agent.settings.sandbox
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
            selected = self.settings.select_profile(state['model_profile']) if state.get('model_profile') else self.settings
            if state.get('sandbox') == 'docker':
                selected.sandbox = 'docker'
                selected.sandbox_image = state.get('sandbox_image', selected.sandbox_image)
            await self.agent.close()
            self.settings = selected
            self.state = state
            self.state.update(sandbox=selected.sandbox, sandbox_image=selected.sandbox_image)
            self.settings.mode = state["mode"]
            if self.settings.model_profile:
                self.state["model_profile"] = self.settings.model_profile
            self.store.save(self.state)
            self.agent = self.make_agent()
            self.status()
        elif command == '/sandbox':
            self.emit('notice', json.dumps({'sandbox_runs': self.state.get('sandbox_runs', [])}, ensure_ascii=False))
        elif command == '/progress':
            from .workflow import suite_status
            self.emit('notice', json.dumps({'observations': self.state.get('progress', []),
                'tasks': self.state['tasks'], 'changes': self.agent.changes.list(),
                'verification': self.agent.verification_status(),
                'verification_suite': suite_status(self.agent)}, ensure_ascii=False))
        elif command == '/verify':
            await self.agent.verify(arg)
        elif command in {'/map', '/search'}:
            result = await self.agent.tools.execute('repo_map' if command == '/map' else 'code_search', {'query': arg})
            self.emit('notice', result)
        elif command == "/sessions":
            self.show_sessions()
        elif command == "/mode":
            if arg not in {"code", "plan", "chat"}:
                raise ValueError("Usage: /mode code|plan|chat")
            self.agent.settings.mode = self.settings.mode = self.state["mode"] = arg
            self.store.save(self.state)
        elif command == "/permission":
            if arg not in {"ask", "accept-edits"}:
                raise ValueError("Usage: /permission ask|accept-edits")
            self.agent.settings.permission = self.settings.permission = arg
        elif command == '/models':
            self.emit('notice', json.dumps({name: {'model': cfg['model'], 'api_format': cfg['api_format'],
                                                          'worker_enabled': name in self.settings.worker_profiles}
                                          for name, cfg in self.settings.model_profiles.items()}))
        elif command == "/model":
            if not arg:
                raise ValueError("Usage: /model MODEL_NAME or /model @PROFILE")
            if arg.startswith('@'):
                selected = self.settings.select_profile(arg[1:])
                await self.agent.close()
                self.settings = selected
                self.state['model_profile'] = arg[1:]
                self.agent = self.make_agent()
            else:
                self.agent.settings.model = self.settings.model = arg
                self.agent.settings.model_profile = self.settings.model_profile = ''
                self.state.pop('model_profile', None)
            self.store.save(self.state)
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
        elif command == '/usage':
            data = self.agent.ledger.summary(self.state)
            if self.args.json:
                self.emit('usage',data)
            else:
                self.console.print(json.dumps(data,ensure_ascii=False,indent=2),markup=False)
        elif command == '/lsp':
            manager = self.agent.tools.language_servers
            if arg:
                if not arg.startswith('disconnect '):
                    raise ValueError('Usage: /lsp [disconnect SERVER]')
                if manager:
                    await manager.disconnect(arg.split(' ', 1)[1])
                self.emit('notice', 'Language server disconnected.')
            else:
                self.emit('notice', json.dumps(manager.status() if manager else
                    {name:'disconnected' for name in self.agent.settings.lsp_servers}))
        elif command == '/mcp':
            if arg:
                if not arg.startswith('disconnect '):
                    raise ValueError('Usage: /mcp [disconnect SERVER]')
                if self.agent.tools.mcp:
                    await self.agent.tools.mcp.disconnect(arg.split(' ',1)[1])
                self.emit('notice', 'MCP connection closed; next operation requires approval.')
            else:
                self.emit('notice',json.dumps({k:dict(transport=v.get('transport','stdio'),
                    **(self.agent.tools.mcp.status(k) if self.agent.tools.mcp else {'connected':False, 'last_error':None}))
                    for k,v in self.agent.settings.mcp_servers.items()}))
        elif command == '/agents':
            children=[]
            identifiers = [self.store.peek(arg)['id']] if arg else self.state.get('children', [])
            for ident in identifiers:
                row=self.store.db.execute('SELECT state FROM sessions WHERE id=?',(ident,)).fetchone()
                if row:
                    child=json.loads(row[0])
                    entry = {k:child.get(k) for k in ('id','title','status','mode','stop_reason', 'isolated')}
                    if arg:
                        if child.get('parent_id') != self.state['id']:
                            raise ValueError('Session is not a child of this parent')
                        from .workspaces import review
                        entry['changes'] = review(self.agent, child)
                    children.append(entry)
            if self.args.json:
                self.emit('agents',children)
            else:
                self.console.print(json.dumps(children,ensure_ascii=False,indent=2),markup=False)
        elif command == "/memory":
            rows = self.agent.memory().listing()
            if self.args.json:
                self.emit("memory", rows)
            else:
                self.console.print(self.redact(json.dumps(rows, ensure_ascii=False, indent=2)), markup=False)
        elif command == "/remember":
            ident = self.agent.memory().add("user_constraint", arg, f"session:{self.state['id']}/explicit-user-confirmation")
            self.emit("notice", f"Saved project constraint {ident}. Use /memory to inspect or /forget {ident} to remove.")
        elif command == "/forget":
            self.agent.memory().forget(arg)
            self.agent.memory_context = ""
            self.state["messages"].append({"role": "user", "content": f"I removed project memory {arg}. Do not rely on that memory; verify current files or ask me if needed."})
            self.store.save(self.state)
            self.emit("notice", "Memory removed from active storage and search. Existing conversation transcripts are retained.")
        elif command == "/continue":
            await self.run_task("Continue the unfinished task. First inspect actual state for any interrupted or uncertain tool actions; do not blindly repeat mutations.")
        elif command == "/changes":
            if arg and arg != "all":
                self.emit("diff", self.agent.changes.diff(int(arg)))
            else:
                rows = self.agent.changes.list()
                if self.args.json:
                    self.emit("changes", rows)
                else:
                    table = Table("ID", "File", "Status", title="File-tool edits · newest first · last 100")
                    for row in rows:
                        table.add_row(str(row["id"]), row["path"], row["status"])
                    self.console.print(table)
                    self.emit("notice", "Inspect /changes ID; /accept ID marks reviewed; /undo ID restores the pre-edit file. Shell edits are not recorded.")
        elif command in {"/accept", "/undo"}:
            if not arg.isdigit():
                raise ValueError(f"Usage: {command} ID (from /changes)")
            ident = int(arg)
            if command == "/undo":
                self.agent.changes.undo(ident)
                # Inform the next model turn that its earlier tool result is obsolete.
                path = self.agent.changes.get(ident)[1]
                self.state["messages"].append({"role": "user", "content": f"I undid file change #{ident} ({path}). Re-read current files before making further changes; do not automatically reapply it."})
                self.store.save(self.state)
            else:
                self.agent.changes.accept(ident)
            self.emit("notice", f"Change #{ident}: {'undone' if command == '/undo' else 'accepted'}. Git index unchanged.")
        elif command == "/diff":
            result = json.loads(await run_process(["git", "-c", "core.fsmonitor=false", "--no-pager", "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", ".", ":(exclude).env", ":(exclude).env.*", ":(exclude).eca", ":(exclude)venv", ":(exclude)*.pyc"], self.settings.root, 20))
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
            self.agent.settings.mode = self.settings.mode = self.state["mode"] = modes[(modes.index(self.settings.mode) + 1) % len(modes)]
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
    if args.verify_command and (args.prompt is None or not args.allow_shell or any(not c.strip() for c in args.verify_command)):
        raise ValueError('--verify-command requires --prompt, --allow-shell and a nonempty command')
    if len(args.verify_command) > 10 or not 0 <= args.repair_attempts <= 3 or (args.repair_attempts and not args.verify_command):
        raise ValueError('At most 10 checks; --repair-attempts requires checks and must be 0..3')
    if args.verify_command and (args.usage or args.doctor or args.list_sessions or args.changes is not None or args.undo is not None or args.accept_change is not None):
        raise ValueError('Verification cannot be combined with offline actions')
    if args.usage:
        if args.prompt is not None or args.doctor or args.list_sessions or args.changes is not None or args.undo is not None or args.accept_change is not None:
            raise ValueError('--usage cannot be combined with other actions')
        root = args.cwd.resolve()
        if not root.is_dir() or not (root/'.eca').exists():
            raise ValueError('No saved usage in this project')
        store = Store(root)
        try:
            state=store.load(args.resume or 'latest')
            print(json.dumps(UsageLedger(store).summary(state),ensure_ascii=False,indent=None if args.json else 2))
        finally:
            store.close()
        return 0
    review = args.changes is not None or args.undo is not None or args.accept_change is not None
    if review and (args.prompt is not None or args.list_sessions or args.doctor):
        raise ValueError("Review actions cannot be combined with prompt, doctor or session listing")
    if review and args.resume is None:
        args.resume = "latest"
    if args.json and args.prompt is None and not args.list_sessions and not args.doctor and not review:
        raise ValueError("--json requires a one-shot, review, session listing or doctor action")
    if args.allow_shell and args.prompt is None:
        raise ValueError("--allow-shell is only for explicit one-shot tasks")
    if args.allow_lsp and args.prompt is None:
        raise ValueError('--allow-lsp is only for one-shot tasks')
    if args.allow_mcp and args.prompt is None:
        raise ValueError('--allow-mcp is only for one-shot tasks')
    if args.doctor:
        report = diagnose(args.cwd, model_profile=args.model_profile, model=args.model, base_url=args.base_url, api_format=args.api_format, mode=args.mode,
                          permission="accept-edits" if args.accept_edits else None, sandbox=args.sandbox, sandbox_image=args.sandbox_image)
        print(json.dumps(report, ensure_ascii=False, indent=None if args.json else 2))
        return 0 if report["ready"] else 1
    if review or args.list_sessions:
        # Recovery must remain available even when .env/eca.toml is broken.
        root = args.cwd.resolve()
        if not root.is_dir():
            raise ValueError("Project directory does not exist")
        settings = Settings(root)
    else:
        settings = Settings.load(args.cwd, model_profile=args.model_profile, model=args.model, base_url=args.base_url, api_format=args.api_format, mode=args.mode,
                                 permission="accept-edits" if args.accept_edits else None, sandbox=args.sandbox, sandbox_image=args.sandbox_image)
    if args.list_sessions:
        if not settings.state_dir.exists():
            print("[]")
            return 0
        store = Store(settings.root)
        try:
            print(json.dumps([{"id": i, "title": t, "updated": u} for i, t, u in store.list()], ensure_ascii=False, indent=None if args.json else 2))
        finally:
            store.close()
        return 0
    app = App(settings, args)
    try:
        if review:
            command = f"/changes {args.changes}" if args.changes is not None else (
                f"/undo {args.undo}" if args.undo is not None else f"/accept {args.accept_change}")
            await app.command(command)
            return 0
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
