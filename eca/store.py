"""SQLite snapshots and tool journal; all writes are committed before dispatch."""
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid


class Store:
    def __init__(self, root: Path):
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
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?)",
                            (state["id"], state["title"], time.time(), json.dumps(state, ensure_ascii=False)))

    def list(self):
        return self.db.execute("SELECT id, title, updated FROM sessions ORDER BY updated DESC LIMIT 100").fetchall()

    def load(self, identifier):
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
        self.repair(state)
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
                row = self.db.execute("SELECT status,result FROM actions WHERE session_id=? AND call_id=? ORDER BY id DESC LIMIT 1",
                                      (state["id"], f"{exchange}:{call_id}")).fetchone()
                result = row[1] if row and row[0] == "completed" else "Interrupted: outcome unknown. Inspect current files/processes before retrying. Do not assume this action failed or succeeded."
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
        if state["status"] == "running":
            state["status"] = "interrupted"
        self.save(state)

    def close(self):
        self.db.close()
        self.lock.close()
