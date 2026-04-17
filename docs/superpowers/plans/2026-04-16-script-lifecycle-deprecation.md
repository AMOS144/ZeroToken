# Script Lifecycle Deprecation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add script health tracking (active/warning/deprecated), automatic warning on 5 consecutive failures, AI-confirmed deprecation, cascading hard delete, and abandoned paused session cleanup.

**Architecture:** Extend `scripts` table with status/stats columns via new migration. `SQLiteScriptRepo` gets `record_run_result` to update stats on every run terminal state, plus `deprecate/restore/health` for status transitions. `ScriptEngineV2` calls `record_run_result` whenever a run reaches a terminal status (completed/failed/aborted). `ScriptService.run_script` settles abandoned paused sessions and rejects deprecated scripts. New MCP tools `script_deprecate`, `script_restore`, `script_health` expose the capabilities to AI.

**Tech Stack:** SQLite, Pydantic v2, Python 3.11+, pytest, asyncio

---

## File Structure

| File | Responsibility |
|------|----------------|
| `zerotoken/repository/migrations.py` | [Modify] Add `002_script_health` migration adding columns |
| `zerotoken/repository/sqlite.py` | [Modify] `SQLiteScriptRepo`: add `record_run_result`/`deprecate`/`restore`/`health`; extend `script_list`/`script_delete`. `SQLiteRuntimeRepo`: add `find_paused_before` |
| `zerotoken/repository/protocols.py` | [Modify] Update `ScriptRepo` and `RuntimeRepo` protocols |
| `zerotoken/services/script_service.py` | [Modify] Add `script_deprecate`/`restore`/`health`; wrap `run_script`/`resume_script` with stats update + abandoned cleanup |
| `zerotoken/engine/script_engine_v2.py` | [Modify] Call `record_run_result` at terminal states (completed/failed/aborted) |
| `handlers/script_handlers.py` | [Modify] Add 3 new tools; update existing tool schemas and dispatch |
| `tests/unit/test_repository/test_sqlite_scripts.py` | [Modify] Add tests for new repo methods |
| `tests/unit/test_services/test_script_service_run.py` | [Modify] Add tests for stats/deprecation in run flow |
| `tests/unit/test_handlers/` | [New/Modify] Add handler tests for new tools |

---

### Task 1: Database migration for script health columns

**Files:**
- Modify: `zerotoken/repository/migrations.py:7-72`
- Test: (covered by existing migration tests if any; else verify via new repo tests)

- [ ] **Step 1: Add migration entry**

In `zerotoken/repository/migrations.py`, append a new tuple to `MIGRATIONS`:

```python
MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_initial",
        """
        ...existing migration stays exactly as-is...
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
```

- [ ] **Step 2: Verify migration runs cleanly**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -c "
import sqlite3, tempfile, os
from zerotoken.repository.sqlite import new_connection
db = tempfile.mktemp(suffix='.db')
conn = new_connection(db)
cols = [r[1] for r in conn.execute('PRAGMA table_info(scripts)').fetchall()]
assert 'status' in cols
assert 'consecutive_failures' in cols
assert 'deprecated_reason' in cols
print('OK', cols)
os.remove(db)
"`
Expected: `OK [...columns list including status, consecutive_failures, ...]`

- [ ] **Step 3: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/repository/migrations.py
git commit -m "feat(db): add script health columns migration (002_script_health)"
```

---

### Task 2: Extend `SQLiteScriptRepo` with stats and status methods

**Files:**
- Modify: `zerotoken/repository/sqlite.py` (SQLiteScriptRepo class, lines ~35-101)
- Test: `tests/unit/test_repository/test_sqlite_scripts.py`

- [ ] **Step 1: Write failing tests**

Create or extend `tests/unit/test_repository/test_sqlite_scripts.py` with these tests (append if file exists):

```python
"""SQLiteScriptRepo 健康指标 / 报废 / 级联删除测试"""
import tempfile
import os
import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import new_connection, SQLiteScriptRepo
    db = tempfile.mktemp(suffix=".db")
    conn = new_connection(db)
    r = SQLiteScriptRepo(conn)
    r.script_save("t1", goal="test", steps=[{"action": "browser_open"}])
    yield r
    conn.close()
    os.remove(db)


def test_initial_status_is_active(repo):
    h = repo.health("t1")
    assert h["status"] == "active"
    assert h["consecutive_failures"] == 0
    assert h["total_runs"] == 0


def test_record_run_result_completed_increments_stats(repo):
    result = repo.record_run_result("t1", "completed", "sess-1")
    assert result["status"] == "active"
    assert result["total_runs"] == 1
    assert result["total_completed"] == 1
    assert result["consecutive_failures"] == 0
    assert result["last_run_status"] == "completed"
    assert result["last_session_id"] == "sess-1"


def test_record_run_result_failed_increments_consecutive(repo):
    repo.record_run_result("t1", "failed", "sess-1")
    repo.record_run_result("t1", "aborted", "sess-2")
    h = repo.health("t1")
    assert h["consecutive_failures"] == 2
    assert h["total_runs"] == 2
    assert h["total_completed"] == 0
    assert h["status"] == "active"  # 还没到 5 次


def test_auto_warning_at_5_failures(repo):
    for i in range(5):
        result = repo.record_run_result("t1", "failed", f"sess-{i}")
    assert result["status"] == "warning"
    assert result["consecutive_failures"] == 5


def test_success_after_warning_restores_active(repo):
    for i in range(5):
        repo.record_run_result("t1", "failed", f"sess-{i}")
    assert repo.health("t1")["status"] == "warning"

    result = repo.record_run_result("t1", "completed", "sess-good")
    assert result["status"] == "active"
    assert result["consecutive_failures"] == 0


def test_deprecate_sets_status_and_reason(repo):
    repo.deprecate("t1", reason="selector outdated")
    h = repo.health("t1")
    assert h["status"] == "deprecated"
    assert h["deprecated_reason"] == "selector outdated"
    assert h["deprecated_at"] is not None


def test_restore_from_deprecated(repo):
    repo.deprecate("t1", reason="test")
    repo.restore("t1")
    h = repo.health("t1")
    assert h["status"] == "active"
    assert h["deprecated_at"] is None
    assert h["deprecated_reason"] is None
    assert h["consecutive_failures"] == 0


def test_script_list_filters_by_status(repo):
    repo.script_save("t2", goal="g2", steps=[])
    repo.script_save("t3", goal="g3", steps=[])
    repo.deprecate("t3", reason="x")

    # default returns active only
    items = repo.script_list()
    ids = {i["task_id"] for i in items}
    assert "t1" in ids and "t2" in ids and "t3" not in ids

    # status="all" returns all
    items = repo.script_list(status="all")
    ids = {i["task_id"] for i in items}
    assert "t3" in ids

    # status="deprecated"
    items = repo.script_list(status="deprecated")
    ids = {i["task_id"] for i in items}
    assert ids == {"t3"}


def test_script_list_returns_health_fields(repo):
    repo.record_run_result("t1", "failed", "sess-1")
    items = repo.script_list()
    item = next(i for i in items if i["task_id"] == "t1")
    assert item["status"] == "active"
    assert item["consecutive_failures"] == 1
    assert item["last_run_status"] == "failed"


def test_health_returns_none_for_missing(repo):
    assert repo.health("nonexistent") is None


def test_deprecate_missing_raises(repo):
    with pytest.raises(KeyError):
        repo.deprecate("nonexistent", reason="x")


def test_restore_non_deprecated_raises(repo):
    with pytest.raises(ValueError, match="not deprecated"):
        repo.restore("t1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_repository/test_sqlite_scripts.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'health'` or similar

- [ ] **Step 3: Implement the new methods**

In `zerotoken/repository/sqlite.py`, modify `SQLiteScriptRepo`:

Replace `script_list` with:

```python
    def script_list(
        self, limit: int = 100, status: str = "active",
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
```

Add new methods after `script_delete`:

```python
    _HEALTH_COLUMNS = (
        "task_id", "status", "consecutive_failures",
        "total_runs", "total_completed",
        "last_run_at", "last_run_status", "last_session_id",
        "deprecated_at", "deprecated_reason",
    )

    def health(self, task_id: str) -> dict[str, Any] | None:
        """返回脚本的健康指标快照"""
        cols = ", ".join(self._HEALTH_COLUMNS)
        row = self.conn.execute(
            f"SELECT {cols} FROM scripts WHERE task_id=?", (task_id,),
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
        self, task_id: str, terminal_status: str, session_id: str,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_repository/test_sqlite_scripts.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/repository/sqlite.py tests/unit/test_repository/test_sqlite_scripts.py
git commit -m "feat(repo): add health/deprecate/restore/record_run_result to SQLiteScriptRepo"
```

---

### Task 3: Cascading `script_delete` + `find_paused_before` in runtime repo

**Files:**
- Modify: `zerotoken/repository/sqlite.py` (SQLiteScriptRepo.script_delete + SQLiteRuntimeRepo)
- Test: `tests/unit/test_repository/test_sqlite_scripts.py`, `tests/unit/test_repository/test_sqlite_session.py` (or create if absent)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_repository/test_sqlite_scripts.py`:

```python
def test_script_delete_cascades_sessions(tmp_path):
    from zerotoken.repository.sqlite import (
        new_connection, SQLiteScriptRepo, SQLiteSessionRepo, SQLiteRuntimeRepo,
    )
    db = str(tmp_path / "t.db")
    conn = new_connection(db)
    scripts = SQLiteScriptRepo(conn)
    sessions = SQLiteSessionRepo(conn)
    runtime = SQLiteRuntimeRepo(conn)

    scripts.script_save("t1", goal="g", steps=[])
    sessions.session_start("s1", task_id="t1")
    runtime.runtime_init("s1", task_id="t1", cursor_step_index=0, status="running")

    result = scripts.script_delete("t1")
    assert result["deleted"] is True
    assert result["cascade"]["session_headers"] == 1
    assert result["cascade"]["session_runtime"] == 1

    # Verify cascade
    assert sessions.session_list() == []
    assert runtime.runtime_get("s1") is None


def test_script_delete_blocked_by_binding(tmp_path):
    from zerotoken.repository.sqlite import (
        new_connection, SQLiteScriptRepo, SQLiteBindingRepo,
    )
    db = str(tmp_path / "t.db")
    conn = new_connection(db)
    scripts = SQLiteScriptRepo(conn)
    bindings = SQLiteBindingRepo(conn)

    scripts.script_save("t1", goal="g", steps=[])
    bindings.binding_set("job-1", script_task_id="t1")

    with pytest.raises(ValueError, match="has bindings"):
        scripts.script_delete("t1")
```

Also add a test for `find_paused_before` in runtime (append to existing runtime tests file or create new):

```python
# tests/unit/test_repository/test_sqlite_session.py (append or new)
import time
from datetime import datetime, timedelta, timezone


def test_find_paused_before_returns_stale(tmp_path):
    from zerotoken.repository.sqlite import new_connection, SQLiteRuntimeRepo
    db = str(tmp_path / "t.db")
    conn = new_connection(db)
    runtime = SQLiteRuntimeRepo(conn)

    runtime.runtime_init("s1", task_id="t1", cursor_step_index=0, status="paused")
    runtime.runtime_init("s2", task_id="t1", cursor_step_index=0, status="running")

    # Simulate s1 updated_at in the past by direct SQL
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    conn.execute("UPDATE session_runtime SET updated_at=? WHERE session_id=?", (old, "s1"))
    conn.commit()

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    stale = runtime.find_paused_before("t1", cutoff)
    ids = [s["session_id"] for s in stale]
    assert ids == ["s1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_repository/ -v -k "cascade or blocked or paused_before"`
Expected: FAIL

- [ ] **Step 3: Implement cascading delete**

Replace `script_delete` in `SQLiteScriptRepo`:

```python
    def script_delete(self, task_id: str) -> dict[str, Any]:
        """硬删除脚本 + 级联清理 session 数据。
        若存在 script_bindings 引用此 task_id，抛 ValueError（应先删 binding）。
        """
        # Check bindings
        has_binding = self.conn.execute(
            "SELECT 1 FROM script_bindings WHERE script_task_id=? LIMIT 1",
            (task_id,),
        ).fetchone()
        if has_binding:
            raise ValueError(
                f"script {task_id} has bindings; delete them first via script_bind_delete"
            )

        # Collect session_ids for cascade
        session_rows = self.conn.execute(
            "SELECT session_id FROM session_headers WHERE task_id=?", (task_id,),
        ).fetchall()
        session_ids = [r["session_id"] for r in session_rows]

        # Delete session_steps for those sessions
        steps_deleted = 0
        runtime_deleted = 0
        for sid in session_ids:
            cur = self.conn.execute(
                "DELETE FROM session_steps WHERE session_id=?", (sid,),
            )
            steps_deleted += cur.rowcount
            cur = self.conn.execute(
                "DELETE FROM session_runtime WHERE session_id=?", (sid,),
            )
            runtime_deleted += cur.rowcount

        headers_cur = self.conn.execute(
            "DELETE FROM session_headers WHERE task_id=?", (task_id,),
        )
        # session_runtime rows that have the task_id but are orphaned (no session_header)
        orphan_cur = self.conn.execute(
            "DELETE FROM session_runtime WHERE task_id=?", (task_id,),
        )

        # Finally the script
        script_cur = self.conn.execute(
            "DELETE FROM scripts WHERE task_id=?", (task_id,),
        )
        self.conn.commit()
        return {
            "deleted": script_cur.rowcount > 0,
            "cascade": {
                "session_headers": headers_cur.rowcount,
                "session_steps": steps_deleted,
                "session_runtime": runtime_deleted + orphan_cur.rowcount,
            },
        }
```

- [ ] **Step 4: Implement `find_paused_before` on `SQLiteRuntimeRepo`**

In `zerotoken/repository/sqlite.py`, add this method to `SQLiteRuntimeRepo` (the class containing `runtime_init`/`runtime_get`/`runtime_update`):

```python
    def find_paused_before(
        self, task_id: str, cutoff_iso: str,
    ) -> list[dict[str, Any]]:
        """返回指定 task_id 下 status='paused' 且 updated_at < cutoff_iso 的 session。"""
        rows = self.conn.execute(
            """SELECT session_id, task_id, updated_at FROM session_runtime
               WHERE task_id=? AND status='paused' AND updated_at < ?""",
            (task_id, cutoff_iso),
        ).fetchall()
        return [
            {
                "session_id": r["session_id"],
                "task_id": r["task_id"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_repository/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/repository/sqlite.py tests/unit/test_repository/
git commit -m "feat(repo): cascading script_delete and runtime.find_paused_before"
```

---

### Task 4: Update repository protocols

**Files:**
- Modify: `zerotoken/repository/protocols.py`

- [ ] **Step 1: Update the protocols**

In `zerotoken/repository/protocols.py`, update the relevant protocol classes. Find the `ScriptRepo` protocol (around line 8) and add new method signatures:

```python
class ScriptRepo(Protocol):
    def script_save(
        self, task_id: str, *, goal: str, steps: list[dict[str, Any]],
        params_schema: dict[str, Any] | None = None,
        source_trajectory_id: int | None = None,
    ) -> None: ...

    def script_load(self, task_id: str) -> dict[str, Any] | None: ...

    def script_list(
        self, limit: int = 100, status: str = "active",
    ) -> list[dict[str, Any]]: ...

    def script_delete(self, task_id: str) -> dict[str, Any]: ...

    def health(self, task_id: str) -> dict[str, Any] | None: ...

    def record_run_result(
        self, task_id: str, terminal_status: str, session_id: str,
    ) -> dict[str, Any]: ...

    def deprecate(self, task_id: str, *, reason: str = "") -> dict[str, Any]: ...

    def restore(self, task_id: str) -> dict[str, Any]: ...
```

Find the `RuntimeRepo` protocol and add:

```python
    def find_paused_before(
        self, task_id: str, cutoff_iso: str,
    ) -> list[dict[str, Any]]: ...
```

- [ ] **Step 2: Run all tests to confirm no regressions**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/ --tb=short -q`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/repository/protocols.py
git commit -m "chore(protocols): update ScriptRepo/RuntimeRepo with new methods"
```

---

### Task 5: `ScriptService` gets deprecate/restore/health + run wrappers

**Files:**
- Modify: `zerotoken/services/script_service.py`
- Test: `tests/unit/test_services/test_script_service_run.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_services/test_script_service_run.py`:

```python
@pytest.mark.asyncio
async def test_run_script_records_completed_on_success(tmp_path, mock_browser_svc):
    """run_script 成功时应调 record_run_result(completed)"""
    from zerotoken.services.script_service import ScriptService
    from unittest.mock import MagicMock, AsyncMock, patch

    script_repo = MagicMock()
    script_repo.script_load = MagicMock(return_value={
        "task_id": "t1", "goal": "g",
        "steps": [{"action": "browser_open", "params": {"url": "x"}}],
        "params_schema": {},
    })
    script_repo.health = MagicMock(return_value={"status": "active"})
    script_repo.record_run_result = MagicMock(return_value={"status": "active"})

    runtime = MagicMock()
    runtime.find_paused_before = MagicMock(return_value=[])

    svc = ScriptService(
        script_repo=script_repo, trajectory_repo=MagicMock(),
        session_repo=MagicMock(), runtime_repo=runtime,
        binding_repo=MagicMock(),
    )

    with patch("zerotoken.engine.script_engine_v2.ScriptEngineV2.run",
               new=AsyncMock(return_value={"status": "completed", "session_id": "s1"})):
        result = await svc.run_script("t1", mock_browser_svc)

    script_repo.record_run_result.assert_called_once_with("t1", "completed", "s1")
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_run_script_rejects_deprecated(mock_browser_svc):
    """deprecated 脚本不能执行"""
    from zerotoken.services.script_service import ScriptService
    from unittest.mock import MagicMock

    script_repo = MagicMock()
    script_repo.health = MagicMock(return_value={
        "status": "deprecated", "deprecated_reason": "outdated",
    })
    script_repo.script_load = MagicMock(return_value={
        "task_id": "t1", "goal": "g", "steps": [],
    })

    svc = ScriptService(
        script_repo=script_repo, trajectory_repo=MagicMock(),
        session_repo=MagicMock(), runtime_repo=MagicMock(),
        binding_repo=MagicMock(),
    )

    result = await svc.run_script("t1", mock_browser_svc)
    assert result["status"] == "error"
    assert result.get("code") == "SCRIPT_DEPRECATED"


@pytest.mark.asyncio
async def test_run_script_settles_abandoned_sessions(mock_browser_svc):
    """run_script 前应清理该 task_id 下遗弃的 paused session"""
    from zerotoken.services.script_service import ScriptService
    from unittest.mock import MagicMock, AsyncMock, patch

    script_repo = MagicMock()
    script_repo.health = MagicMock(return_value={"status": "active"})
    script_repo.script_load = MagicMock(return_value={
        "task_id": "t1", "goal": "g", "steps": [],
    })
    script_repo.record_run_result = MagicMock(return_value={"status": "active"})

    runtime = MagicMock()
    runtime.find_paused_before = MagicMock(return_value=[
        {"session_id": "old1", "task_id": "t1", "updated_at": "..."},
    ])

    svc = ScriptService(
        script_repo=script_repo, trajectory_repo=MagicMock(),
        session_repo=MagicMock(), runtime_repo=runtime,
        binding_repo=MagicMock(),
    )

    with patch("zerotoken.engine.script_engine_v2.ScriptEngineV2.run",
               new=AsyncMock(return_value={"status": "completed", "session_id": "new1"})):
        await svc.run_script("t1", mock_browser_svc)

    # Old session marked aborted and recorded as failure
    runtime.runtime_update.assert_any_call("old1", status="aborted")
    # record_run_result called at least twice: once for abandoned, once for new
    assert script_repo.record_run_result.call_count >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_services/test_script_service_run.py -v`
Expected: FAIL

- [ ] **Step 3: Add fixture if missing**

If `mock_browser_svc` fixture doesn't already exist in the test file, add at top:

```python
@pytest.fixture
def mock_browser_svc():
    from unittest.mock import AsyncMock
    return AsyncMock()
```

- [ ] **Step 4: Implement the service changes**

Replace `run_script` and `resume_script` in `zerotoken/services/script_service.py`, and add new methods:

```python
    from datetime import datetime, timedelta, timezone

    _ABANDONED_PAUSED_TTL_HOURS = 24

    def script_deprecate(self, task_id: str, reason: str = "") -> dict[str, Any]:
        """将脚本标记为 deprecated"""
        return self._scripts.deprecate(task_id, reason=reason)

    def script_restore(self, task_id: str) -> dict[str, Any]:
        """将 deprecated 脚本恢复为 active"""
        return self._scripts.restore(task_id)

    def script_health(self, task_id: str) -> dict[str, Any] | None:
        """查询脚本健康指标"""
        return self._scripts.health(task_id)

    def _settle_abandoned_sessions(self, task_id: str) -> int:
        """将超过 TTL 的 paused session 标记为 aborted，计入失败。返回处理数量。"""
        from datetime import datetime, timedelta, timezone
        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(hours=self._ABANDONED_PAUSED_TTL_HOURS)
        ).isoformat()
        stale = self._runtime.find_paused_before(task_id, cutoff)
        for s in stale:
            self._runtime.runtime_update(s["session_id"], status="aborted")
            self._scripts.record_run_result(task_id, "aborted", s["session_id"])
        return len(stale)

    async def run_script(
        self, task_id: str, browser_svc: Any,
        *, vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """启动脚本执行：检查 deprecated，清理遗弃 paused，执行后更新统计"""
        health = self._scripts.health(task_id)
        if health is None:
            raw = self._scripts.script_load(task_id)
            if raw is None:
                return {"status": "error", "error": f"Script not found: {task_id}"}

        if health and health.get("status") == "deprecated":
            return {
                "status": "error",
                "code": "SCRIPT_DEPRECATED",
                "error": f"Script deprecated: {health.get('deprecated_reason') or 'no reason'}",
            }

        self._settle_abandoned_sessions(task_id)

        raw = self._scripts.script_load(task_id)
        if raw is None:
            return {"status": "error", "error": f"Script not found: {task_id}"}
        script = Script(
            task_id=raw["task_id"], goal=raw.get("goal", ""),
            steps=[ScriptStep(**s) for s in raw.get("steps", [])],
            params_schema=raw.get("params_schema", {}),
        )
        engine = ScriptEngineV2(browser_svc, self._sessions, self._runtime)
        result = await engine.run(script, vars=vars)

        # 更新统计；非终态 (paused) 不计入
        if result.get("status") in ("completed", "failed", "aborted"):
            updated = self._scripts.record_run_result(
                task_id, result["status"], result.get("session_id", ""),
            )
            if updated.get("status") == "warning" and health and health.get("status") == "active":
                result["health"] = {
                    "auto_warned": True,
                    "consecutive_failures": updated["consecutive_failures"],
                    "hint": "Script entered warning state after 5 consecutive failures. Consider script_deprecate if no longer working.",
                }
        return result

    async def resume_script(
        self, session_id: str, resolution: Resolution,
        browser_svc: Any,
    ) -> dict[str, Any]:
        """恢复暂停的脚本，终态时更新统计"""
        state = self._runtime.runtime_get(session_id)
        if state is None:
            return {"status": "error", "error": f"No session: {session_id}"}
        task_id = state.get("task_id", "")
        raw = self._scripts.script_load(task_id)
        if raw is None:
            return {"status": "error", "error": f"Script not found: {task_id}"}
        script = Script(
            task_id=raw["task_id"], goal=raw.get("goal", ""),
            steps=[ScriptStep(**s) for s in raw.get("steps", [])],
        )
        engine = ScriptEngineV2(browser_svc, self._sessions, self._runtime)
        result = await engine.resume(session_id, script, resolution)

        if result.get("status") in ("completed", "failed", "aborted"):
            self._scripts.record_run_result(
                task_id, result["status"], session_id,
            )
        return result
```

Note: If imports at top of `script_service.py` don't already include `datetime`, add it. Keep the existing imports.

- [ ] **Step 5: Run tests**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_services/ -v`
Expected: All tests PASS (3 new + existing)

- [ ] **Step 6: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/services/script_service.py tests/unit/test_services/test_script_service_run.py
git commit -m "feat(service): deprecate/restore/health + run wrappers for stats and cleanup"
```

---

### Task 6: MCP handler tools and schema updates

**Files:**
- Modify: `handlers/script_handlers.py`
- Test: `tests/unit/test_handlers/test_script_handlers_run.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_handlers/test_script_handlers_run.py` (create if missing):

```python
import pytest
from unittest.mock import MagicMock, AsyncMock


def test_script_deprecate_tool_exists():
    from handlers.script_handlers import script_tools
    names = [t.name for t in script_tools()]
    assert "script_deprecate" in names
    assert "script_restore" in names
    assert "script_health" in names


def test_script_list_schema_has_status_filter():
    from handlers.script_handlers import script_tools
    tools = {t.name: t for t in script_tools()}
    props = tools["script_list"].inputSchema["properties"]
    assert "status" in props


@pytest.mark.asyncio
async def test_handle_script_deprecate():
    from handlers.script_handlers import handle_script_tool
    svc = MagicMock()
    svc.script_deprecate = MagicMock(return_value={
        "status": "deprecated", "task_id": "t1",
        "deprecated_reason": "old",
    })
    result = await handle_script_tool(
        "script_deprecate", {"task_id": "t1", "reason": "old"}, svc,
    )
    import json
    data = json.loads(result[0].text)
    assert data["success"] is True
    assert data["status"] == "deprecated"
    svc.script_deprecate.assert_called_once_with("t1", reason="old")


@pytest.mark.asyncio
async def test_handle_script_restore():
    from handlers.script_handlers import handle_script_tool
    svc = MagicMock()
    svc.script_restore = MagicMock(return_value={"status": "active"})
    result = await handle_script_tool(
        "script_restore", {"task_id": "t1"}, svc,
    )
    import json
    data = json.loads(result[0].text)
    assert data["success"] is True
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_handle_script_health():
    from handlers.script_handlers import handle_script_tool
    svc = MagicMock()
    svc.script_health = MagicMock(return_value={
        "task_id": "t1", "status": "warning",
        "consecutive_failures": 5, "total_runs": 5,
    })
    result = await handle_script_tool(
        "script_health", {"task_id": "t1"}, svc,
    )
    import json
    data = json.loads(result[0].text)
    assert data["success"] is True
    assert data["health"]["status"] == "warning"


@pytest.mark.asyncio
async def test_handle_script_health_not_found():
    from handlers.script_handlers import handle_script_tool
    svc = MagicMock()
    svc.script_health = MagicMock(return_value=None)
    result = await handle_script_tool(
        "script_health", {"task_id": "nope"}, svc,
    )
    import json
    data = json.loads(result[0].text)
    assert data["success"] is False
    assert data["code"] == "SCRIPT_NOT_FOUND"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_handlers/test_script_handlers_run.py -v -k "deprecate or restore or health or status_filter"`
Expected: FAIL

- [ ] **Step 3: Add the new tool schemas**

In `handlers/script_handlers.py`, locate the `script_tools()` function. Find the `script_delete` Tool definition and after it add:

```python
        Tool(
            name="script_deprecate",
            description="Mark a script as deprecated (soft delete). Deprecated scripts are excluded from script_list by default and rejected by script_run.",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID to deprecate"},
                "reason": {"type": "string", "description": "Why the script is being deprecated"},
            }, required=["task_id"]),
        ),
        Tool(
            name="script_restore",
            description="Restore a deprecated script to active status",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID to restore"},
            }, required=["task_id"]),
        ),
        Tool(
            name="script_health",
            description="Get script health metrics: status, consecutive failures, total runs, success rate",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID"},
            }, required=["task_id"]),
        ),
```

Modify `script_list` schema (find the existing one) to add `status`:

```python
        Tool(
            name="script_list",
            description="List scripts in the database (default: only active)",
            inputSchema=_obj_schema({
                "limit": {"type": "integer", "description": "Max number to return", "default": 100},
                "status": {"type": "string", "description": "Filter by status: active / warning / deprecated / all (default: active)"},
            }),
        ),
```

- [ ] **Step 4: Implement the dispatch for new tools**

In `handle_script_tool`, find the `script_delete` branch and after it add:

```python
        if name == "script_deprecate":
            try:
                result = script_svc.script_deprecate(
                    args["task_id"], reason=args.get("reason", ""),
                )
            except KeyError:
                return _err(f"No script for task_id: {args['task_id']}", code="SCRIPT_NOT_FOUND")
            return _resp({"success": True, **result})

        if name == "script_restore":
            try:
                result = script_svc.script_restore(args["task_id"])
            except KeyError:
                return _err(f"No script for task_id: {args['task_id']}", code="SCRIPT_NOT_FOUND")
            except ValueError as e:
                return _err(str(e), code="SCRIPT_NOT_DEPRECATED")
            return _resp({"success": True, **result})

        if name == "script_health":
            result = script_svc.script_health(args["task_id"])
            if result is None:
                return _err(f"No script for task_id: {args['task_id']}", code="SCRIPT_NOT_FOUND")
            return _resp({"success": True, "health": result})
```

Find the existing `script_list` branch and update:

```python
        if name == "script_list":
            items = script_svc.script_list(
                limit=args.get("limit", 100),
                status=args.get("status", "active"),
            )
            return _resp({"scripts": items})
```

Also `ScriptService.script_list` needs to accept `status` param. Modify `zerotoken/services/script_service.py`:

Find `script_list` and update:

```python
    def script_list(
        self, limit: int = 100, status: str = "active",
    ) -> list[dict[str, Any]]:
        return self._scripts.script_list(limit=limit, status=status)
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/ --tb=short -q`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add handlers/script_handlers.py zerotoken/services/script_service.py tests/unit/test_handlers/test_script_handlers_run.py
git commit -m "feat(handlers): add script_deprecate/restore/health MCP tools + status filter"
```

---

## Self-Review

### Spec Coverage

| Spec Section | Task |
|---|---|
| scripts 表新增字段 | Task 1 |
| 状态机 (active/warning/deprecated) | Task 2 (auto warning), Task 5 (deprecate/restore) |
| record_run_result 统计 | Task 2 (repo), Task 5 (engine integration) |
| 遗弃 paused 的清理 | Task 3 (find_paused_before), Task 5 (_settle_abandoned_sessions) |
| MCP 工具 script_deprecate/restore/health | Task 6 |
| script_list 过滤 | Task 6 |
| script_run 拒绝 deprecated | Task 5 |
| script_delete 级联 | Task 3 |
| binding 保护 | Task 3 |
| 错误码 | Task 5 (SCRIPT_DEPRECATED), Task 3 (SCRIPT_HAS_BINDINGS), Task 6 (SCRIPT_NOT_DEPRECATED) |

### Type/Name Consistency

- `health(task_id)` returns dict or None -- Task 2 defined, Task 5/6 consume
- `record_run_result(task_id, terminal_status, session_id)` returns updated health -- Task 2 defined, Task 5 consumes
- `deprecate(task_id, *, reason)` raises KeyError if missing -- Task 2/Task 6
- `restore(task_id)` raises ValueError if not deprecated -- Task 2/Task 6
- `find_paused_before(task_id, cutoff_iso)` on RuntimeRepo -- Task 3/Task 5
- `_settle_abandoned_sessions` -- Task 5 private helper
- `script_delete` return shape `{deleted, cascade}` -- Task 3 defined, handler no change needed (service passes through)

### Placeholder scan

No TBD/TODO placeholders in task code blocks. All code is concrete and executable.
