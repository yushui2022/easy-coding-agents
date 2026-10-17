"""Durable before/after images for ECA file tools; never resets Git state."""
import difflib

from .tools import atomic_write


class Changes:
    def __init__(self, store, session_id, resolve):
        self.db, self.session_id, self.resolve = store.db, session_id, resolve
        self.db.execute("""CREATE TABLE IF NOT EXISTS file_changes (
            id INTEGER PRIMARY KEY, session_id TEXT, path TEXT,
            before BLOB, after BLOB, status TEXT NOT NULL)""")
        self.db.commit()

    def prepare(self, path, before, after):
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO file_changes(session_id,path,before,after,status) VALUES(?,?,?,?,?)",
                (self.session_id, path, before, after, "prepared"))
        return cursor.lastrowid

    def mark(self, ident, status):
        with self.db:
            self.db.execute("UPDATE file_changes SET status=? WHERE id=? AND session_id=?",
                            (status, ident, self.session_id))

    def get(self, ident):
        row = self.db.execute("SELECT id,path,before,after,status FROM file_changes WHERE id=? AND session_id=?",
                              (ident, self.session_id)).fetchone()
        if row is None:
            raise ValueError("Change ID not found in this session. Use /changes.")
        return row

    def current(self, path):
        target = self.resolve(path)
        if target.relative_to(self.resolve(".")).as_posix() != path:
            raise ValueError("Recorded file path now resolves elsewhere")
        if target.exists() and (not target.is_file() or target.stat().st_size > 2_000_000):
            raise ValueError("Current file cannot be compared safely")
        return target, target.read_bytes() if target.exists() else None

    def list(self):
        rows = self.db.execute("SELECT id,path,status FROM file_changes WHERE session_id=? ORDER BY id DESC LIMIT 100",
                               (self.session_id,)).fetchall()
        return [{"id": i, "path": p, "status": s} for i, p, s in rows]

    def diff(self, ident):
        _, path, before, after, _ = self.get(ident)
        return "".join(difflib.unified_diff(
            (before or b"").decode("utf-8").splitlines(True), after.decode("utf-8").splitlines(True),
            fromfile="a/" + path if before is not None else "/dev/null", tofile="b/" + path))

    def accept(self, ident):
        _, path, _, after, status = self.get(ident)
        if status not in {"applied", "accepted"}:
            raise ValueError("Only applied changes can be accepted")
        _, current = self.current(path)
        if current != after:
            raise ValueError("File has changed since this edit; review the newer change first")
        self.mark(ident, "accepted")

    def undo(self, ident):
        _, path, before, after, status = self.get(ident)
        if status not in {"applied", "accepted", "prepared", "undoing"}:
            raise ValueError("Change is already undone")
        target, current = self.current(path)
        if status in {"prepared", "undoing"} and current == before:
            self.mark(ident, "undone")
            return
        if current != after:
            raise ValueError("File differs from the recorded result; refusing to overwrite newer user or tool edits")
        # Persist intention before changing disk, including when deleting a new file.
        self.mark(ident, "undoing")
        if before is None:
            target.unlink()
        else:
            atomic_write(target, before.decode("utf-8"))
        self.mark(ident, "undone")
