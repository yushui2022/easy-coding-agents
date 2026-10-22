"""SQLite snapshots and tool journal; all writes are committed before dispatch."""
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

INTERRUPTED_UNKNOWN = ("Interrupted: outcome unknown. Inspect current files/processes before retrying. "
                       "Do not assume this action failed or succeeded.")
# Tools that only read: an interrupted call to one of them provably changed nothing.
INTERRUPTED_SAFE = ("Interrupted: this read-only step was cancelled before it returned, so nothing was "
                    "changed and retrying it is safe.")
SAFE_TOOLS = {"skills", "read", "glob", "grep", "code_search", "repo_map", "code_relations",
              "web_fetch", "web_search", "todo", "ask", "lsp"}


class Store:
    def __init__(self, root: Path):
        self.resources = []
        self.root = root.resolve()
        directory = self.root / ".eca"
        if directory.is_symlink() or directory.resolve() != directory:
            raise ValueError(".eca must not be a symbolic link")
        directory.mkdir(exist_ok=True)
        self.lock = open(directory / "instance.lock", "a+b")
        try:
            if os.fstat(self.lock.fileno()).st_size == 0:
                self.lock.write(b"0")
                self.lock.flush()
            self.lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise ValueError("Another ECA process is using this project. Close it before starting another.") from None
        self.db = sqlite3.connect(directory / "sessions.sqlite3")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, title TEXT, updated REAL, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY, session_id TEXT, call_id TEXT,
                name TEXT, args TEXT, status TEXT, result TEXT, created REAL);
        """)

    def create(self, mode="code"):
        state = {"id": uuid.uuid4().hex, "root": str(self.root), "title": "New session",
                 "messages": [], "tasks": [], "mode": mode, "status": "idle", "usage": {}}
        self.save(state)
        return state

    def save(self, state):
        from .recovery import checkpoint
        state['checkpoint'] = checkpoint(state)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?)",
                            (state["id"], state["title"], time.time(), json.dumps(state, ensure_ascii=False)))

    def list(self, top_level=False):
        scope = " AND json_extract(state,'$.parent_id') IS NULL" if top_level else ""
        return self.db.execute("SELECT id, title, updated FROM sessions WHERE coalesce(json_extract(state,'$.kind'),'') != 'side_chat'" + scope + " ORDER BY updated DESC LIMIT 100").fetchall()

    def peek(self, identifier):
        if identifier == "latest":
            rows = self.db.execute("SELECT state FROM sessions ORDER BY updated DESC LIMIT 1").fetchall()
        else:
            # Literal prefix matching; SQL wildcard characters are not interpreted.
            rows = self.db.execute("SELECT state FROM sessions WHERE substr(id,1,?)=?", (len(identifier), identifier)).fetchall()
        if len(rows) != 1:
            raise ValueError("Session not found or ID is ambiguous")
        state = json.loads(rows[0][0])
        if Path(state["root"]).resolve() != self.root:
            raise ValueError("Session belongs to another project")
        return state

    def load(self, identifier):
        state = self.peek(identifier)
        self.repair(state)
        state['_resume_pending'] = True
        return state

    def begin(self, session_id, call_id, name, args):
        row = self.db.execute("SELECT state FROM sessions WHERE id=?", (session_id,)).fetchone()
        messages = json.loads(row[0])["messages"]
        exchange = next((i for i in range(len(messages)-1, -1, -1) if any(tc["id"] == call_id for tc in messages[i].get("tool_calls", []))), -1)
        journal_key = f"{exchange}:{call_id}"
        with self.db:
            cur = self.db.execute("INSERT INTO actions(session_id,call_id,name,args,status,created) VALUES(?,?,?,?,?,?)",
                                  (session_id, journal_key, name, json.dumps(args, ensure_ascii=False), "running", time.time()))
        return cur.lastrowid

    def finish(self, action_id, result, status="completed"):
        with self.db:
            self.db.execute("UPDATE actions SET result=?,status=? WHERE id=?", (result, status, action_id))

    def repair(self, state):
        """Close incomplete protocol exchanges without replaying their side effects."""
        repaired = []
        pending = {}

        def close_pending():
            for call_id, exchange in pending.items():
                row = self.db.execute("SELECT status,result,name FROM actions WHERE session_id=? AND call_id=? ORDER BY id DESC LIMIT 1",
                                      (state["id"], f"{exchange}:{call_id}")).fetchone()
                completed = bool(row) and row[0] == "completed"
                if completed:
                    result = row[1]
                elif row and row[2] in SAFE_TOOLS:
                    # A read cannot have changed anything, so say that instead of
                    # making every interrupted lookup look like a failed write.
                    result = INTERRUPTED_SAFE
                else:
                    result = INTERRUPTED_UNKNOWN
                repaired.append({"role": "tool", "tool_call_id": call_id, "content": result})
            pending.clear()

        for index, msg in enumerate(state["messages"]):
            if msg["role"] != "tool":
                close_pending()
            repaired.append(msg)
            if msg.get("tool_calls"):
                pending.update({tc["id"]: index for tc in msg["tool_calls"]})
            if msg["role"] == "tool":
                pending.pop(msg["tool_call_id"], None)
        close_pending()
        state["messages"] = repaired
        if state["status"] in {"running", "queued", "preparing"}:
            state["status"] = "interrupted"
            state["stop_reason"] = "Previous process stopped unexpectedly. Inspect /changes and uncertain shell effects before /continue."
        self.save(state)

    def close(self):
        for resource in self.resources:
            resource.close()
        self.db.close()
        self.lock.close()
