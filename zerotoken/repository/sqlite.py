"""SQLite 存储实现 -- 每个 Repo 只管自己的表"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .migrations import MigrationRunner


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _json_loads(s: Optional[str]) -> Any:
    if s is None:
        return None
    return json.loads(s)


def new_connection(db_path: str) -> sqlite3.Connection:
    """创建并初始化数据库连接（运行迁移）"""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    MigrationRunner(conn).run()
    return conn


class SQLiteScriptRepo:
    """scripts 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def script_save(
        self,
        task_id: str,
        *,
        goal: str,
        steps: list[dict[str, Any]],
        params_schema: dict[str, Any] | None = None,
        source_trajectory_id: int | None = None,
    ) -> None:
        now = _now_iso()
        self.conn.execute(
            """INSERT INTO scripts (task_id, goal, steps_json, params_schema_json, source_trajectory_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(task_id) DO UPDATE SET
                 goal=excluded.goal, steps_json=excluded.steps_json,
                 params_schema_json=excluded.params_schema_json,
                 source_trajectory_id=excluded.source_trajectory_id,
                 updated_at=excluded.updated_at""",
            (
                task_id,
                goal,
                _json_dumps(steps),
                _json_dumps(params_schema or {}),
                source_trajectory_id,
                now,
                now,
            ),
        )
        self.conn.commit()

    def script_load(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT task_id, goal, steps_json, params_schema_json, source_trajectory_id, created_at, updated_at FROM scripts WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "task_id": row["task_id"],
            "goal": row["goal"],
            "steps": _json_loads(row["steps_json"]),
            "params_schema": _json_loads(row["params_schema_json"]),
            "source_trajectory_id": row["source_trajectory_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def script_list(
        self,
        limit: int = 100,
        status: str = "active",
    ) -> list[dict[str, Any]]:
        if status == "all":
            sql = (
                "SELECT task_id, goal, status, consecutive_failures, "
                "last_run_status, created_at FROM scripts "
                "ORDER BY updated_at DESC LIMIT ?"
            )
            params: tuple = (limit,)
        else:
            sql = (
                "SELECT task_id, goal, status, consecutive_failures, "
                "last_run_status, created_at FROM scripts "
                "WHERE status = ? ORDER BY updated_at DESC LIMIT ?"
            )
            params = (status, limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "task_id": r["task_id"],
                "goal": r["goal"],
                "status": r["status"],
                "consecutive_failures": r["consecutive_failures"],
                "last_run_status": r["last_run_status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def script_delete(self, task_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM scripts WHERE task_id=?", (task_id,))
        self.conn.commit()
        return cur.rowcount > 0

    _HEALTH_COLUMNS = (
        "task_id",
        "status",
        "consecutive_failures",
        "total_runs",
        "total_completed",
        "last_run_at",
        "last_run_status",
        "last_session_id",
        "deprecated_at",
        "deprecated_reason",
    )

    def health(self, task_id: str) -> dict[str, Any] | None:
        """返回脚本的健康指标快照"""
        cols = ", ".join(self._HEALTH_COLUMNS)
        row = self.conn.execute(
            f"SELECT {cols} FROM scripts WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        total = row["total_runs"] or 0
        success = row["total_completed"] or 0
        return {
            "task_id": row["task_id"],
            "status": row["status"],
            "consecutive_failures": row["consecutive_failures"] or 0,
            "total_runs": total,
            "total_completed": success,
            "success_rate": round(success / total, 4) if total else 0.0,
            "last_run_at": row["last_run_at"],
            "last_run_status": row["last_run_status"],
            "last_session_id": row["last_session_id"],
            "deprecated_at": row["deprecated_at"],
            "deprecated_reason": row["deprecated_reason"],
        }

    def record_run_result(
        self,
        task_id: str,
        terminal_status: str,
        session_id: str,
    ) -> dict[str, Any]:
        """在脚本执行到达终态时更新统计。
        terminal_status: completed / failed / aborted
        连续 5 次非 completed 自动把 active 升级为 warning。
        一次 completed 把 warning 降回 active 并清零 consecutive_failures。
        """
        now = _now_iso()
        is_success = terminal_status == "completed"
        if is_success:
            self.conn.execute(
                """UPDATE scripts SET
                    consecutive_failures = 0,
                    total_runs = total_runs + 1,
                    total_completed = total_completed + 1,
                    last_run_at = ?, last_run_status = ?, last_session_id = ?,
                    status = CASE WHEN status = 'warning' THEN 'active' ELSE status END,
                    updated_at = ?
                   WHERE task_id = ?""",
                (now, terminal_status, session_id, now, task_id),
            )
        else:
            self.conn.execute(
                """UPDATE scripts SET
                    consecutive_failures = consecutive_failures + 1,
                    total_runs = total_runs + 1,
                    last_run_at = ?, last_run_status = ?, last_session_id = ?,
                    status = CASE
                        WHEN status = 'active' AND consecutive_failures + 1 >= 5
                        THEN 'warning' ELSE status
                    END,
                    updated_at = ?
                   WHERE task_id = ?""",
                (now, terminal_status, session_id, now, task_id),
            )
        self.conn.commit()
        return self.health(task_id) or {}

    def deprecate(self, task_id: str, *, reason: str = "") -> dict[str, Any]:
        """标记脚本为 deprecated"""
        now = _now_iso()
        cur = self.conn.execute(
            """UPDATE scripts SET status='deprecated',
               deprecated_at=?, deprecated_reason=?, updated_at=?
               WHERE task_id=?""",
            (now, reason, now, task_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"script not found: {task_id}")
        self.conn.commit()
        return self.health(task_id) or {}

    def restore(self, task_id: str) -> dict[str, Any]:
        """将 deprecated 脚本恢复为 active"""
        h = self.health(task_id)
        if h is None:
            raise KeyError(f"script not found: {task_id}")
        if h["status"] != "deprecated":
            raise ValueError(f"script {task_id} is not deprecated")
        now = _now_iso()
        self.conn.execute(
            """UPDATE scripts SET status='active',
               consecutive_failures=0,
               deprecated_at=NULL, deprecated_reason=NULL,
               updated_at=?
               WHERE task_id=?""",
            (now, task_id),
        )
        self.conn.commit()
        return self.health(task_id) or {}


class SQLiteTrajectoryRepo:
    """trajectories 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def trajectory_save(
        self,
        *,
        task_id: str,
        goal: str,
        operations: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = _now_iso()
        cur = self.conn.execute(
            "INSERT INTO trajectories (task_id, goal, operations_json, metadata_json, created_at) VALUES (?,?,?,?,?)",
            (task_id, goal, _json_dumps(operations), _json_dumps(metadata or {}), now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def trajectory_load(self, trajectory_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, task_id, goal, operations_json, metadata_json, created_at FROM trajectories WHERE id=?",
            (trajectory_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "goal": row["goal"],
            "operations": _json_loads(row["operations_json"]),
            "metadata": _json_loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def trajectory_load_by_task_id(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, task_id, goal, operations_json, metadata_json, created_at FROM trajectories WHERE task_id=? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "goal": row["goal"],
            "operations": _json_loads(row["operations_json"]),
            "metadata": _json_loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def trajectory_list(
        self,
        limit: int = 100,
        since: float | None = None,
    ) -> list[dict[str, Any]]:
        if since is not None:
            since_iso = datetime.fromtimestamp(since, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S+00:00"
            )
            rows = self.conn.execute(
                "SELECT id, task_id, goal, created_at FROM trajectories WHERE created_at>=? ORDER BY id DESC LIMIT ?",
                (since_iso, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, task_id, goal, created_at FROM trajectories ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "task_id": r["task_id"],
                "goal": r["goal"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def trajectory_delete_by_task_id(self, task_id: str) -> int:
        cur = self.conn.execute("DELETE FROM trajectories WHERE task_id=?", (task_id,))
        self.conn.commit()
        return cur.rowcount


class SQLiteSessionRepo:
    """session_headers + session_steps 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def session_start(
        self,
        session_id: str,
        *,
        task_id: str | None = None,
        session_type: str = "replay",
    ) -> None:
        now = _now_iso()
        self.conn.execute(
            "INSERT OR REPLACE INTO session_headers (session_id, task_id, session_type, created_at) VALUES (?,?,?,?)",
            (session_id, task_id, session_type, now),
        )
        self.conn.commit()

    def session_append(
        self,
        session_id: str,
        *,
        step_index: int,
        action: str,
        selector: str | None = None,
        url: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        now = _now_iso()
        self.conn.execute(
            "INSERT INTO session_steps (session_id, step_index, action, selector, url, timestamp, payload_json) VALUES (?,?,?,?,?,?,?)",
            (
                session_id,
                step_index,
                action,
                selector,
                url,
                now,
                _json_dumps(payload or {}),
            ),
        )
        self.conn.commit()

    def session_get(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT step_index, action, selector, url, timestamp, payload_json FROM session_steps WHERE session_id=? ORDER BY step_index",
            (session_id,),
        ).fetchall()
        return [
            {
                "step_index": r["step_index"],
                "action": r["action"],
                "selector": r["selector"],
                "url": r["url"],
                "timestamp": r["timestamp"],
                "payload": _json_loads(r["payload_json"]),
            }
            for r in rows
        ]

    def session_list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT session_id, task_id, session_type, created_at FROM session_headers ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "session_id": r["session_id"],
                "task_id": r["task_id"],
                "session_type": r["session_type"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


class SQLiteRuntimeRepo:
    """session_runtime 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def runtime_init(
        self,
        session_id: str,
        *,
        task_id: str | None,
        cursor_step_index: int,
        status: str,
        pause_event: dict[str, Any] | None = None,
        vars: dict[str, Any] | None = None,
    ) -> None:
        now = _now_iso()
        self.conn.execute(
            """INSERT INTO session_runtime (session_id, task_id, cursor_step_index, step_path_json, status, pause_event_json, vars_json, updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
                 task_id=excluded.task_id, cursor_step_index=excluded.cursor_step_index,
                 step_path_json=excluded.step_path_json, status=excluded.status,
                 pause_event_json=excluded.pause_event_json, vars_json=excluded.vars_json,
                 updated_at=excluded.updated_at""",
            (
                session_id,
                task_id,
                cursor_step_index,
                _json_dumps([]),
                status,
                _json_dumps(pause_event) if pause_event else None,
                _json_dumps(vars or {}),
                now,
            ),
        )
        self.conn.commit()

    def runtime_get(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT session_id, task_id, cursor_step_index, step_path_json, status, pause_event_json, vars_json, updated_at FROM session_runtime WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "task_id": row["task_id"],
            "cursor_step_index": int(row["cursor_step_index"]),
            "step_path": _json_loads(row["step_path_json"]) or [],
            "status": row["status"],
            "pause_event": _json_loads(row["pause_event_json"]),
            "vars": _json_loads(row["vars_json"]) or {},
            "updated_at": row["updated_at"],
        }

    def runtime_update(self, session_id: str, **fields: Any) -> None:
        existing = self.runtime_get(session_id)
        if existing is None:
            raise KeyError(f"runtime not found: {session_id}")
        now = _now_iso()
        new_cursor = fields.get("cursor_step_index", existing["cursor_step_index"])
        new_status = fields.get("status", existing["status"])
        new_step_path = fields.get("step_path", existing["step_path"])
        pe = fields.get("pause_event", existing["pause_event"])
        new_pe_json = _json_dumps(pe) if pe is not None else None
        new_vars = fields.get("vars", existing["vars"])
        self.conn.execute(
            """UPDATE session_runtime SET cursor_step_index=?, step_path_json=?, status=?,
               pause_event_json=?, vars_json=?, updated_at=? WHERE session_id=?""",
            (
                int(new_cursor),
                _json_dumps(new_step_path),
                new_status,
                new_pe_json,
                _json_dumps(new_vars or {}),
                now,
                session_id,
            ),
        )
        self.conn.commit()


class SQLiteFingerprintRepo:
    """fingerprints 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def fingerprint_save(
        self, domain: str, identifier: str, fingerprint_dict: dict[str, Any]
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO fingerprints (domain, identifier, fingerprint_json, updated_at) VALUES (?,?,?,?)",
            (domain, identifier, _json_dumps(fingerprint_dict), time.time()),
        )
        self.conn.commit()

    def fingerprint_load(self, domain: str, identifier: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT fingerprint_json FROM fingerprints WHERE domain=? AND identifier=?",
            (domain, identifier),
        ).fetchone()
        if row is None:
            return None
        return _json_loads(row["fingerprint_json"])

    def fingerprint_delete(self, domain: str, identifier: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM fingerprints WHERE domain=? AND identifier=?",
            (domain, identifier),
        )
        self.conn.commit()
        return cur.rowcount > 0


class SQLiteBindingRepo:
    """script_bindings 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def binding_set(
        self,
        binding_key: str,
        *,
        script_task_id: str,
        description: str = "",
        default_vars: dict[str, Any] | None = None,
    ) -> None:
        now = _now_iso()
        self.conn.execute(
            """INSERT INTO script_bindings (binding_key, script_task_id, description, default_vars_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(binding_key) DO UPDATE SET
                 script_task_id=excluded.script_task_id, description=excluded.description,
                 default_vars_json=excluded.default_vars_json, updated_at=excluded.updated_at""",
            (
                binding_key,
                script_task_id,
                description,
                _json_dumps(default_vars or {}),
                now,
                now,
            ),
        )
        self.conn.commit()

    def binding_get(self, binding_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT binding_key, script_task_id, description, default_vars_json, created_at, updated_at FROM script_bindings WHERE binding_key=?",
            (binding_key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "binding_key": row["binding_key"],
            "script_task_id": row["script_task_id"],
            "description": row["description"] or "",
            "default_vars": _json_loads(row["default_vars_json"]) or {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def binding_list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT binding_key, script_task_id, description, updated_at FROM script_bindings ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "binding_key": r["binding_key"],
                "script_task_id": r["script_task_id"],
                "description": r["description"] or "",
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def binding_delete(self, binding_key: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM script_bindings WHERE binding_key=?", (binding_key,)
        )
        self.conn.commit()
        return cur.rowcount > 0
