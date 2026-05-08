"""
SQLite implementation of ScriptStore, TrajectoryStore, SessionStore, AdaptiveStore.
Single DB file (e.g. zerotoken.db); tables: scripts, trajectories, session_headers, session_steps, fingerprints.
"""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import (
    ScriptStore,
    TrajectoryStore,
    SessionStore,
    DFUStore,
    SessionRuntimeStore,
    ScriptBindingStore,
    AdaptiveStore,
)

_RUNTIME_UNSET = object()


def _json_serializer(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_deserializer(s: Optional[str]) -> Any:
    if s is None:
        return None
    return json.loads(s)


class SQLiteStorage(
    ScriptStore,
    TrajectoryStore,
    SessionStore,
    DFUStore,
    SessionRuntimeStore,
    ScriptBindingStore,
    AdaptiveStore,
):
    """Single SQLite-backed storage for scripts, trajectories, and sessions."""

    def __init__(self, db_path: str = "zerotoken.db"):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_tables()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_tables(self) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scripts (
                task_id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                steps TEXT NOT NULL,
                params_schema TEXT,
                source_trajectory_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # Backward-compatible migration: add provenance column if DB existed before.
        cur.execute("PRAGMA table_info(scripts)")
        cols = {r[1] for r in cur.fetchall()}
        if "source_trajectory_id" not in cols:
            cur.execute("ALTER TABLE scripts ADD COLUMN source_trajectory_id INTEGER")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                goal TEXT NOT NULL,
                operations TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_headers (
                session_id TEXT PRIMARY KEY,
                task_id TEXT,
                session_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                action TEXT NOT NULL,
                selector TEXT,
                url TEXT,
                timestamp TEXT NOT NULL,
                payload TEXT,
                FOREIGN KEY (session_id) REFERENCES session_headers(session_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dfus (
                dfu_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                triggers_json TEXT NOT NULL,
                prompt TEXT,
                allowed_resolutions_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_runtime (
                session_id TEXT PRIMARY KEY,
                task_id TEXT,
                cursor_step_index INTEGER NOT NULL,
                status TEXT NOT NULL,
                pause_event_json TEXT,
                vars_json TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS script_bindings (
                binding_key TEXT PRIMARY KEY,
                script_task_id TEXT NOT NULL,
                description TEXT,
                default_vars_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                domain TEXT NOT NULL,
                identifier TEXT NOT NULL,
                fingerprint_json TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (domain, identifier)
            )
        """)
        self.conn.commit()

    # --- ScriptStore ---
    def script_save(
        self,
        task_id: str,
        *,
        goal: str,
        steps: List[Dict[str, Any]],
        params_schema: Optional[Dict[str, Any]] = None,
        source_trajectory_id: Optional[int] = None,
    ) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO scripts (task_id, goal, steps, params_schema, source_trajectory_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                goal = excluded.goal,
                steps = excluded.steps,
                params_schema = excluded.params_schema,
                source_trajectory_id = excluded.source_trajectory_id,
                updated_at = excluded.updated_at
            """,
            (
                task_id,
                goal,
                _json_serializer(steps),
                _json_serializer(params_schema or {}),
                source_trajectory_id,
                now,
                now,
            ),
        )
        self.conn.commit()

    # --- ScriptBindingStore ---
    def script_binding_set(
        self,
        binding_key: str,
        *,
        script_task_id: str,
        description: str = "",
        default_vars: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO script_bindings (binding_key, script_task_id, description, default_vars_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(binding_key) DO UPDATE SET
                script_task_id = excluded.script_task_id,
                description = excluded.description,
                default_vars_json = excluded.default_vars_json,
                updated_at = excluded.updated_at
            """,
            (
                binding_key,
                script_task_id,
                description,
                _json_serializer(default_vars or {}),
                now,
                now,
            ),
        )
        self.conn.commit()

    def script_binding_get(self, binding_key: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT binding_key, script_task_id, description, default_vars_json, created_at, updated_at FROM script_bindings WHERE binding_key = ?",
            (binding_key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "binding_key": row["binding_key"],
            "script_task_id": row["script_task_id"],
            "description": row["description"] or "",
            "default_vars": _json_deserializer(row["default_vars_json"]) or {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def script_binding_list(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT binding_key, script_task_id, description, updated_at FROM script_bindings ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "binding_key": r["binding_key"],
                "script_task_id": r["script_task_id"],
                "description": r["description"] or "",
                "updated_at": r["updated_at"],
            }
            for r in cur.fetchall()
        ]

    def script_binding_delete(self, binding_key: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM script_bindings WHERE binding_key = ?", (binding_key,))
        self.conn.commit()
        return cur.rowcount > 0

    # --- AdaptiveStore ---
    def fingerprint_save(
        self, domain: str, identifier: str, fingerprint_dict: Dict[str, Any]
    ) -> None:
        updated_at = time.time()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO fingerprints (domain, identifier, fingerprint_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (domain, identifier, _json_serializer(fingerprint_dict), updated_at),
        )
        self.conn.commit()

    def fingerprint_load(self, domain: str, identifier: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT fingerprint_json FROM fingerprints WHERE domain = ? AND identifier = ?",
            (domain, identifier),
        ).fetchone()
        if row is None:
            return None
        return _json_deserializer(row["fingerprint_json"])

    def fingerprint_delete(self, domain: str, identifier: str) -> bool:
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM fingerprints WHERE domain = ? AND identifier = ?",
            (domain, identifier),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def script_load(self, task_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT task_id, goal, steps, params_schema, source_trajectory_id, created_at, updated_at FROM scripts WHERE task_id = ?",
            (task_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "task_id": row["task_id"],
            "goal": row["goal"],
            "steps": _json_deserializer(row["steps"]),
            "params_schema": _json_deserializer(row["params_schema"]),
            "source_trajectory_id": row["source_trajectory_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def script_list(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT task_id, goal, created_at FROM scripts ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [
            {"task_id": r["task_id"], "goal": r["goal"], "created_at": r["created_at"]}
            for r in cur.fetchall()
        ]

    def script_delete(self, task_id: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM scripts WHERE task_id = ?", (task_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # --- TrajectoryStore ---
    def trajectory_save(
        self,
        *,
        task_id: str,
        goal: str,
        operations: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        now = datetime.utcnow().isoformat() + "Z"
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO trajectories (task_id, goal, operations, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, goal, _json_serializer(operations), _json_serializer(metadata or {}), now),
        )
        self.conn.commit()
        return cur.lastrowid

    def trajectory_load(self, trajectory_id: int) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, task_id, goal, operations, metadata, created_at FROM trajectories WHERE id = ?",
            (trajectory_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "goal": row["goal"],
            "operations": _json_deserializer(row["operations"]),
            "metadata": _json_deserializer(row["metadata"]),
            "created_at": row["created_at"],
        }

    def trajectory_load_by_task_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load latest trajectory with given task_id."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, task_id, goal, operations, metadata, created_at FROM trajectories WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "goal": row["goal"],
            "operations": _json_deserializer(row["operations"]),
            "metadata": _json_deserializer(row["metadata"]),
            "created_at": row["created_at"],
        }

    def trajectory_list(
        self, limit: int = 100, since: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        if since is not None:
            since_iso = datetime.utcfromtimestamp(since).strftime("%Y-%m-%dT%H:%M:%SZ")
            cur.execute(
                "SELECT id, task_id, goal, created_at FROM trajectories WHERE created_at >= ? ORDER BY id DESC LIMIT ?",
                (since_iso, limit),
            )
        else:
            cur.execute(
                "SELECT id, task_id, goal, created_at FROM trajectories ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        return [
            {
                "id": r["id"],
                "task_id": r["task_id"],
                "goal": r["goal"],
                "created_at": r["created_at"],
            }
            for r in cur.fetchall()
        ]

    def trajectory_delete(self, trajectory_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM trajectories WHERE id = ?", (trajectory_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def trajectory_delete_by_task_id(self, task_id: str) -> int:
        """Delete all trajectories with given task_id. Returns number deleted."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM trajectories WHERE task_id = ?", (task_id,))
        self.conn.commit()
        return cur.rowcount

    # --- SessionStore ---
    def session_start(
        self,
        session_id: str,
        *,
        task_id: Optional[str] = None,
        session_type: str = "replay",
    ) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO session_headers (session_id, task_id, session_type, created_at) VALUES (?, ?, ?, ?)",
            (session_id, task_id, session_type, now),
        )
        self.conn.commit()

    def session_append(
        self,
        session_id: str,
        *,
        step_index: int,
        action: str,
        selector: Optional[str] = None,
        url: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO session_steps (session_id, step_index, action, selector, url, timestamp, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, step_index, action, selector, url, now, _json_serializer(payload or {})),
        )
        self.conn.commit()

    def session_get(self, session_id: str) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT step_index, action, selector, url, timestamp, payload FROM session_steps WHERE session_id = ? ORDER BY step_index",
            (session_id,),
        )
        return [
            {
                "step_index": r["step_index"],
                "action": r["action"],
                "selector": r["selector"],
                "url": r["url"],
                "timestamp": r["timestamp"],
                "payload": _json_deserializer(r["payload"]),
            }
            for r in cur.fetchall()
        ]

    def session_list(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT session_id, task_id, session_type, created_at FROM session_headers ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "session_id": r["session_id"],
                "task_id": r["task_id"],
                "session_type": r["session_type"],
                "created_at": r["created_at"],
            }
            for r in cur.fetchall()
        ]

    # --- DFUStore ---
    def dfu_save(
        self,
        dfu_id: str,
        *,
        name: str,
        description: str = "",
        triggers: List[Dict[str, Any]],
        prompt: str = "",
        allowed_resolutions: Optional[List[str]] = None,
    ) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO dfus (dfu_id, name, description, triggers_json, prompt, allowed_resolutions_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dfu_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                triggers_json = excluded.triggers_json,
                prompt = excluded.prompt,
                allowed_resolutions_json = excluded.allowed_resolutions_json,
                updated_at = excluded.updated_at
            """,
            (
                dfu_id,
                name,
                description,
                _json_serializer(triggers),
                prompt,
                _json_serializer(allowed_resolutions or []),
                now,
                now,
            ),
        )
        self.conn.commit()

    def dfu_load(self, dfu_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT dfu_id, name, description, triggers_json, prompt, allowed_resolutions_json, created_at, updated_at FROM dfus WHERE dfu_id = ?",
            (dfu_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "dfu_id": row["dfu_id"],
            "name": row["name"],
            "description": row["description"] or "",
            "triggers": _json_deserializer(row["triggers_json"]) or [],
            "prompt": row["prompt"] or "",
            "allowed_resolutions": _json_deserializer(row["allowed_resolutions_json"]) or [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def dfu_list(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT dfu_id, name, updated_at FROM dfus ORDER BY updated_at DESC LIMIT ?", (limit,)
        )
        return [
            {"dfu_id": r["dfu_id"], "name": r["name"], "updated_at": r["updated_at"]}
            for r in cur.fetchall()
        ]

    def dfu_delete(self, dfu_id: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM dfus WHERE dfu_id = ?", (dfu_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # --- SessionRuntimeStore ---
    def runtime_init(
        self,
        session_id: str,
        *,
        task_id: Optional[str],
        cursor_step_index: int,
        status: str,
        pause_event: Optional[Dict[str, Any]] = None,
        vars: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO session_runtime (session_id, task_id, cursor_step_index, status, pause_event_json, vars_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                task_id = excluded.task_id,
                cursor_step_index = excluded.cursor_step_index,
                status = excluded.status,
                pause_event_json = excluded.pause_event_json,
                vars_json = excluded.vars_json,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                task_id,
                int(cursor_step_index),
                status,
                _json_serializer(pause_event) if pause_event is not None else None,
                _json_serializer(vars or {}),
                now,
            ),
        )
        self.conn.commit()

    def runtime_get(self, session_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT session_id, task_id, cursor_step_index, status, pause_event_json, vars_json, updated_at FROM session_runtime WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "task_id": row["task_id"],
            "cursor_step_index": int(row["cursor_step_index"]),
            "status": row["status"],
            "pause_event": _json_deserializer(row["pause_event_json"]),
            "vars": _json_deserializer(row["vars_json"]) or {},
            "updated_at": row["updated_at"],
        }

    # Note: runtime_update uses read-modify-write; safe for single-process MCP (stdio serializes calls).
    def runtime_update(
        self,
        session_id: str,
        *,
        cursor_step_index: Optional[int] = None,
        status: Optional[str] = None,
        pause_event: Any = _RUNTIME_UNSET,
        vars: Any = _RUNTIME_UNSET,
    ) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        existing = self.runtime_get(session_id)
        if existing is None:
            raise KeyError(f"runtime state not found: {session_id}")
        new_cursor = int(
            existing["cursor_step_index"] if cursor_step_index is None else cursor_step_index
        )
        new_status = existing["status"] if status is None else status
        if pause_event is _RUNTIME_UNSET:
            new_pause_event_json = (
                _json_serializer(existing["pause_event"])
                if existing["pause_event"] is not None
                else None
            )
        else:
            new_pause_event_json = (
                _json_serializer(pause_event) if pause_event is not None else None
            )
        if vars is _RUNTIME_UNSET:
            new_vars_json = _json_serializer(existing["vars"] or {})
        else:
            new_vars_json = _json_serializer(vars or {})
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE session_runtime
            SET cursor_step_index = ?,
                status = ?,
                pause_event_json = ?,
                vars_json = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                new_cursor,
                new_status,
                new_pause_event_json,
                new_vars_json,
                now,
                session_id,
            ),
        )
        self.conn.commit()
