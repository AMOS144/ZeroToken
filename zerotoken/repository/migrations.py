"""版本化数据库迁移"""
from __future__ import annotations

import sqlite3

# 迁移列表：(版本号, SQL)；多语句用 executescript 一次执行
MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_initial",
        """
        CREATE TABLE IF NOT EXISTS scripts (
            task_id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            params_schema_json TEXT,
            source_trajectory_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trajectories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            goal TEXT NOT NULL,
            operations_json TEXT NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS session_headers (
            session_id TEXT PRIMARY KEY,
            task_id TEXT,
            session_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS session_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            action TEXT NOT NULL,
            selector TEXT,
            url TEXT,
            timestamp TEXT NOT NULL,
            payload_json TEXT,
            FOREIGN KEY (session_id) REFERENCES session_headers(session_id)
        );
        CREATE TABLE IF NOT EXISTS session_runtime (
            session_id TEXT PRIMARY KEY,
            task_id TEXT,
            cursor_step_index INTEGER NOT NULL,
            step_path_json TEXT,
            status TEXT NOT NULL,
            pause_event_json TEXT,
            vars_json TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fingerprints (
            domain TEXT NOT NULL,
            identifier TEXT NOT NULL,
            fingerprint_json TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (domain, identifier)
        );
        CREATE TABLE IF NOT EXISTS script_bindings (
            binding_key TEXT PRIMARY KEY,
            script_task_id TEXT NOT NULL,
            description TEXT,
            default_vars_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """,
    ),
    (
        "002_script_health",
        """
        ALTER TABLE scripts ADD COLUMN status TEXT DEFAULT 'active';
        ALTER TABLE scripts ADD COLUMN consecutive_failures INTEGER DEFAULT 0;
        ALTER TABLE scripts ADD COLUMN total_runs INTEGER DEFAULT 0;
        ALTER TABLE scripts ADD COLUMN total_completed INTEGER DEFAULT 0;
        ALTER TABLE scripts ADD COLUMN last_run_at TEXT;
        ALTER TABLE scripts ADD COLUMN last_run_status TEXT;
        ALTER TABLE scripts ADD COLUMN last_session_id TEXT;
        ALTER TABLE scripts ADD COLUMN deprecated_at TEXT;
        ALTER TABLE scripts ADD COLUMN deprecated_reason TEXT;
        """,
    ),
]


class MigrationRunner:
    """跟踪已执行的迁移版本，只跑增量"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def run(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """
        )
        self.conn.commit()
        cursor = self.conn.execute("SELECT version FROM _migrations")
        applied = {row[0] for row in cursor.fetchall()}
        for version, sql in MIGRATIONS:
            if version not in applied:
                self.conn.executescript(sql)
                self.conn.execute(
                    "INSERT INTO _migrations (version, applied_at) VALUES (?, datetime('now'))",
                    (version,),
                )
                self.conn.commit()
