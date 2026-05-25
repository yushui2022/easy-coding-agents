import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class MemoryStorage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.fts_enabled = True
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                kind TEXT NOT NULL,
                role TEXT,
                content TEXT,
                summary TEXT,
                tool_name TEXT,
                tool_args TEXT,
                ref_id TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS refs (
                ref_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                tool_name TEXT,
                node_id TEXT,
                size_chars INTEGER DEFAULT 0,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS task_nodes (
                node_id TEXT PRIMARY KEY,
                goal TEXT,
                status TEXT NOT NULL,
                node_type TEXT NOT NULL DEFAULT 'tool',
                importance REAL NOT NULL DEFAULT 0.5,
                is_current_focus INTEGER NOT NULL DEFAULT 0,
                tool_name TEXT,
                summary TEXT NOT NULL,
                files TEXT,
                result_ref TEXT,
                next_action TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS task_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                state TEXT NOT NULL,
                goal TEXT,
                goal_version INTEGER NOT NULL DEFAULT 1,
                reason TEXT,
                confidence REAL NOT NULL DEFAULT 0.0,
                evidence_refs TEXT,
                next_actions TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS claims (
                claim_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                claim_type TEXT NOT NULL,
                evidence_refs TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.0,
                event_id TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.0,
                source_refs TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memory_items (
                item_id TEXT PRIMARY KEY,
                item_type TEXT NOT NULL,
                content TEXT NOT NULL,
                source_refs TEXT NOT NULL,
                entities TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.0,
                goal_version INTEGER NOT NULL DEFAULT 1,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_text TEXT NOT NULL,
                normalized TEXT NOT NULL,
                source_ref TEXT,
                event_id TEXT,
                confidence REAL NOT NULL DEFAULT 0.0,
                metadata TEXT,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memory_sources (
                memory_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                PRIMARY KEY (memory_id, source_type, source_id)
            );

            CREATE TABLE IF NOT EXISTS retrieval_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                results TEXT NOT NULL,
                selected_results TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._ensure_column("task_nodes", "node_type", "TEXT NOT NULL DEFAULT 'tool'")
        self._ensure_column("task_nodes", "importance", "REAL NOT NULL DEFAULT 0.5")
        self._ensure_column("task_nodes", "is_current_focus", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("retrieval_logs", "selected_results", "TEXT NOT NULL DEFAULT '[]'")
        try:
            self.conn.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts
                USING fts5(event_id, kind, content, summary, tool_name);

                CREATE VIRTUAL TABLE IF NOT EXISTS refs_fts
                USING fts5(ref_id, kind, summary, tool_name, node_id);

                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(memory_id, memory_type, content);

                CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts
                USING fts5(item_id, item_type, content, entities);

                CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts
                USING fts5(entity_id, entity_type, entity_text, normalized);
                """
            )
        except sqlite3.OperationalError:
            self.fts_enabled = False
        self.conn.execute(
            """
            INSERT OR IGNORE INTO task_state
            (id, state, goal, goal_version, reason, confidence, evidence_refs, next_actions)
            VALUES (1, 'UNKNOWN', '', 1, 'Memory initialized.', 0.0, '[]', '[]')
            """
        )
        self.conn.commit()

    def insert_memory_item(
        self,
        item_id: str,
        item_type: str,
        content: str,
        source_refs: Optional[List[str]] = None,
        entities: Optional[List[Dict[str, Any]]] = None,
        confidence: float = 0.0,
        goal_version: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        current = self.get_task_state()
        version = int(goal_version or current.get("goal_version") or 1)
        entity_text = " ".join(entity.get("normalized", "") for entity in entities or [])
        self.conn.execute(
            """
            INSERT INTO memory_items
            (item_id, item_type, content, source_refs, entities, confidence, goal_version, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                item_type,
                content,
                json.dumps(source_refs or [], ensure_ascii=False),
                json.dumps(entities or [], ensure_ascii=False),
                confidence,
                version,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        if self.fts_enabled:
            self.conn.execute(
                "INSERT INTO memory_items_fts(item_id, item_type, content, entities) VALUES (?, ?, ?, ?)",
                (item_id, item_type, content, entity_text),
            )
        self.conn.commit()

    def insert_entities(
        self,
        entities: List[Dict[str, Any]],
        source_ref: Optional[str] = None,
        event_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        for entity in entities:
            entity_id = entity.get("entity_id")
            if not entity_id:
                digest = hashlib.sha1(
                    f"{entity.get('entity_type')}:{entity.get('normalized')}:{source_ref}:{event_id}".encode(
                        "utf-8", errors="ignore"
                    )
                ).hexdigest()[:16]
                entity_id = f"ent_{digest}"
            self.conn.execute(
                """
                INSERT OR IGNORE INTO entities
                (entity_id, entity_type, entity_text, normalized, source_ref, event_id, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    entity.get("entity_type", "unknown"),
                    entity.get("text", ""),
                    entity.get("normalized", ""),
                    source_ref,
                    event_id,
                    float(entity.get("confidence") or 0.0),
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            if self.fts_enabled:
                self.conn.execute(
                    "INSERT INTO entities_fts(entity_id, entity_type, entity_text, normalized) VALUES (?, ?, ?, ?)",
                    (
                        entity_id,
                        entity.get("entity_type", "unknown"),
                        entity.get("text", ""),
                        entity.get("normalized", ""),
                    ),
                )
        self.conn.commit()

    def insert_event(
        self,
        event_id: str,
        kind: str,
        role: Optional[str] = None,
        content: str = "",
        summary: str = "",
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        ref_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        args_json = json.dumps(tool_args or {}, ensure_ascii=False)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO events
            (event_id, kind, role, content, summary, tool_name, tool_args, ref_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, kind, role, content, summary, tool_name, args_json, ref_id, metadata_json),
        )
        if self.fts_enabled:
            self.conn.execute(
                "INSERT INTO events_fts(event_id, kind, content, summary, tool_name) VALUES (?, ?, ?, ?, ?)",
                (event_id, kind, content, summary, tool_name or ""),
            )
        self.conn.commit()

    def insert_ref(
        self,
        ref_id: str,
        path: str,
        kind: str,
        summary: str,
        tool_name: Optional[str],
        node_id: Optional[str],
        size_chars: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO refs
            (ref_id, path, kind, summary, tool_name, node_id, size_chars, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ref_id,
                path,
                kind,
                summary,
                tool_name,
                node_id,
                size_chars,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        if self.fts_enabled:
            self.conn.execute(
                "INSERT INTO refs_fts(ref_id, kind, summary, tool_name, node_id) VALUES (?, ?, ?, ?, ?)",
                (ref_id, kind, summary, tool_name or "", node_id or ""),
            )
        self.conn.commit()

    def upsert_task_node(
        self,
        node_id: str,
        goal: str,
        status: str,
        summary: str,
        node_type: str = "tool",
        importance: float = 0.5,
        is_current_focus: bool = False,
        tool_name: Optional[str] = None,
        files: Optional[List[str]] = None,
        result_ref: Optional[str] = None,
        next_action: str = "",
    ) -> None:
        if is_current_focus:
            self.conn.execute("UPDATE task_nodes SET is_current_focus=0")
        self.conn.execute(
            """
            INSERT INTO task_nodes
            (node_id, goal, status, node_type, importance, is_current_focus, tool_name, summary, files, result_ref, next_action)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                goal=excluded.goal,
                status=excluded.status,
                node_type=excluded.node_type,
                importance=excluded.importance,
                is_current_focus=excluded.is_current_focus,
                tool_name=excluded.tool_name,
                summary=excluded.summary,
                files=excluded.files,
                result_ref=excluded.result_ref,
                next_action=excluded.next_action,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                node_id,
                goal,
                status,
                node_type,
                importance,
                1 if is_current_focus else 0,
                tool_name,
                summary,
                json.dumps(files or [], ensure_ascii=False),
                result_ref,
                next_action,
            ),
        )
        self.conn.commit()

    def update_task_state(
        self,
        state: str,
        goal: Optional[str] = None,
        reason: str = "",
        confidence: float = 0.0,
        evidence_refs: Optional[List[str]] = None,
        next_actions: Optional[List[str]] = None,
        bump_goal_version: bool = False,
    ) -> None:
        current = self.get_task_state()
        goal_value = goal if goal is not None else current.get("goal", "")
        version = int(current.get("goal_version") or 1)
        if bump_goal_version:
            version += 1
        self.conn.execute(
            """
            UPDATE task_state
            SET state=?, goal=?, goal_version=?, reason=?, confidence=?,
                evidence_refs=?, next_actions=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=1
            """,
            (
                state,
                goal_value,
                version,
                reason,
                confidence,
                json.dumps(evidence_refs or [], ensure_ascii=False),
                json.dumps(next_actions or [], ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def insert_claim(
        self,
        claim_id: str,
        text: str,
        claim_type: str,
        evidence_refs: List[str],
        confidence: float = 0.0,
        event_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO claims
            (claim_id, text, claim_type, evidence_refs, confidence, event_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim_id,
                text,
                claim_type,
                json.dumps(evidence_refs, ensure_ascii=False),
                confidence,
                event_id,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def insert_memory(
        self,
        memory_id: str,
        memory_type: str,
        content: str,
        source_refs: List[str],
        confidence: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO memories
            (memory_id, memory_type, content, confidence, source_refs, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                memory_id,
                memory_type,
                content,
                confidence,
                json.dumps(source_refs, ensure_ascii=False),
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        for ref in source_refs:
            self.conn.execute(
                "INSERT OR IGNORE INTO memory_sources(memory_id, source_type, source_id) VALUES (?, ?, ?)",
                (memory_id, "ref", ref),
            )
        if self.fts_enabled:
            self.conn.execute(
                "INSERT INTO memories_fts(memory_id, memory_type, content) VALUES (?, ?, ?)",
                (memory_id, memory_type, content),
            )
        self.conn.commit()

    def get_task_state(self) -> Dict[str, Any]:
        row = self.conn.execute("SELECT * FROM task_state WHERE id=1").fetchone()
        if not row:
            return {}
        data = dict(row)
        data["evidence_refs"] = self._loads(data.get("evidence_refs"), [])
        data["next_actions"] = self._loads(data.get("next_actions"), [])
        return data

    def get_recent_events(self, limit: int = 12, roles: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        params: List[Any] = []
        where = ""
        if roles:
            placeholders = ",".join("?" for _ in roles)
            where = f"WHERE role IN ({placeholders})"
            params.extend(list(roles))
        params.append(limit)
        rows = self.conn.execute(
            f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_task_nodes(self, limit: int = 12) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM task_nodes
            ORDER BY CAST(SUBSTR(node_id, 2) AS INTEGER) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = [dict(row) for row in reversed(rows)]
        for item in result:
            item["files"] = self._loads(item.get("files"), [])
            item["is_current_focus"] = bool(item.get("is_current_focus"))
        return result

    def get_recent_refs(self, limit: int = 5, kinds: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        params: List[Any] = []
        where = ""
        if kinds:
            kind_list = list(kinds)
            placeholders = ",".join("?" for _ in kind_list)
            where = f"WHERE kind IN ({placeholders})"
            params.extend(kind_list)
        params.append(limit)
        rows = self.conn.execute(
            f"SELECT * FROM refs {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_focus_task_nodes(self, limit: int = 3) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM task_nodes
            WHERE is_current_focus=1
            ORDER BY importance DESC, CAST(SUBSTR(node_id, 2) AS INTEGER) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = [dict(row) for row in rows]
        for item in result:
            item["files"] = self._loads(item.get("files"), [])
            item["is_current_focus"] = bool(item.get("is_current_focus"))
        return result

    def get_refs_for_files(self, files: Iterable[str], limit: int = 5) -> List[Dict[str, Any]]:
        file_list = [str(item).replace("\\", "/") for item in files if str(item).strip()]
        if not file_list:
            return []
        rows: List[sqlite3.Row] = []
        for file_name in file_list:
            basename = Path(file_name).name
            like_full = f"%{file_name}%"
            like_base = f"%{basename}%"
            rows.extend(
                self.conn.execute(
                    """
                    SELECT refs.* FROM refs
                    LEFT JOIN task_nodes ON task_nodes.result_ref = refs.ref_id
                    WHERE refs.path LIKE ?
                       OR refs.summary LIKE ?
                       OR refs.metadata LIKE ?
                       OR task_nodes.files LIKE ?
                    ORDER BY refs.created_at DESC
                    LIMIT ?
                    """,
                    (like_full, like_base, like_base, like_base, limit),
                ).fetchall()
            )
        seen = set()
        result = []
        for row in rows:
            item = dict(row)
            if item["ref_id"] in seen:
                continue
            seen.add(item["ref_id"])
            result.append(item)
            if len(result) >= limit:
                break
        return result

    def get_refs_by_ids(self, ref_ids: List[str]) -> List[Dict[str, Any]]:
        if not ref_ids:
            return []
        placeholders = ",".join("?" for _ in ref_ids)
        rows = self.conn.execute(
            f"SELECT * FROM refs WHERE ref_id IN ({placeholders})",
            ref_ids,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_memories_with_sources(self, limit: int = 8) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM memories
            WHERE source_refs IS NOT NULL AND source_refs != '[]'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = [dict(row) for row in rows]
        for item in result:
            item["source_refs"] = self._loads(item.get("source_refs"), [])
        return result

    def get_memory_items(self, limit: int = 12) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM memory_items
            ORDER BY goal_version DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._decode_memory_item(dict(row)) for row in rows]

    def search_memory_items(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        if self.fts_enabled:
            rows = self.conn.execute(
                """
                SELECT memory_items.* FROM memory_items_fts
                JOIN memory_items ON memory_items.item_id = memory_items_fts.item_id
                WHERE memory_items_fts MATCH ?
                ORDER BY memory_items.goal_version DESC, memory_items.created_at DESC
                LIMIT ?
                """,
                (self._fts_query(query), limit),
            ).fetchall()
            return [self._decode_memory_item(dict(row)) for row in rows]
        like = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT * FROM memory_items
            WHERE content LIKE ? OR entities LIKE ?
            ORDER BY goal_version DESC, created_at DESC
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
        return [self._decode_memory_item(dict(row)) for row in rows]

    def search_entities(self, query: str, limit: int = 12) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        if self.fts_enabled:
            rows = self.conn.execute(
                """
                SELECT entities.* FROM entities_fts
                JOIN entities ON entities.entity_id = entities_fts.entity_id
                WHERE entities_fts MATCH ?
                ORDER BY entities.created_at DESC
                LIMIT ?
                """,
                (self._fts_query(query), limit),
            ).fetchall()
            return [dict(row) for row in rows]
        like = f"%{query.lower()}%"
        rows = self.conn.execute(
            """
            SELECT * FROM entities
            WHERE normalized LIKE ? OR entity_text LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def search(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        if self.fts_enabled:
            safe_query = self._fts_query(query)
            rows = []
            rows.extend(
                self.conn.execute(
                    """
                    SELECT 'event' AS source, event_id AS source_id, kind AS title, summary, 1.0 AS score
                    FROM events_fts
                    WHERE events_fts MATCH ?
                    LIMIT ?
                    """,
                    (safe_query, limit),
                ).fetchall()
            )
            rows.extend(
                self.conn.execute(
                    """
                    SELECT 'ref' AS source, ref_id AS source_id, kind AS title, summary, 1.0 AS score
                    FROM refs_fts
                    WHERE refs_fts MATCH ?
                    LIMIT ?
                    """,
                    (safe_query, limit),
                ).fetchall()
            )
            rows.extend(
                self.conn.execute(
                    """
                    SELECT 'memory' AS source, memory_id AS source_id, memory_type AS title, content AS summary, 1.0 AS score
                    FROM memories_fts
                    WHERE memories_fts MATCH ?
                    LIMIT ?
                    """,
                    (safe_query, limit),
                ).fetchall()
            )
            rows.extend(
                self.conn.execute(
                    """
                    SELECT 'memory_item' AS source, item_id AS source_id, item_type AS title, content AS summary, 1.0 AS score
                    FROM memory_items_fts
                    WHERE memory_items_fts MATCH ?
                    LIMIT ?
                    """,
                    (safe_query, limit),
                ).fetchall()
            )
            return [dict(row) for row in rows[:limit]]
        like = f"%{query}%"
        rows = []
        rows.extend(
            self.conn.execute(
                """
                SELECT 'event' AS source, event_id AS source_id, kind AS title, summary, 0.5 AS score
                FROM events
                WHERE content LIKE ? OR summary LIKE ? OR tool_name LIKE ?
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        )
        rows.extend(
            self.conn.execute(
                """
                SELECT 'ref' AS source, ref_id AS source_id, kind AS title, summary, 0.5 AS score
                FROM refs
                WHERE summary LIKE ? OR tool_name LIKE ? OR node_id LIKE ?
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        )
        return [dict(row) for row in rows[:limit]]

    def log_retrieval(
        self,
        query: str,
        results: List[Dict[str, Any]],
        selected_results: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO retrieval_logs(query, results, selected_results) VALUES (?, ?, ?)",
            (
                query,
                json.dumps(results, ensure_ascii=False),
                json.dumps(selected_results or results, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def next_task_node_id(self) -> str:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM task_nodes").fetchone()
        return f"N{int(row['count']) + 1}"

    @staticmethod
    def _loads(value: Optional[str], default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except Exception:
            return default

    def _decode_memory_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        item["source_refs"] = self._loads(item.get("source_refs"), [])
        item["entities"] = self._loads(item.get("entities"), [])
        item["metadata"] = self._loads(item.get("metadata"), {})
        return item

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = []
        for raw in query.replace('"', " ").replace("'", " ").split():
            token = "".join(ch for ch in raw if ch.isalnum() or ch in "_-./:")
            if token:
                terms.append(f'"{token}"')
        return " OR ".join(terms) if terms else '"memory"'

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        existing = {
            row["name"]
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            self.conn.commit()
