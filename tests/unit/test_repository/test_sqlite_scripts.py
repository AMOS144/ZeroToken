"""SQLiteScriptRepo 健康指标 / 报废测试"""
import os
import tempfile

import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import SQLiteScriptRepo, new_connection

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
    assert h["status"] == "active"


def test_auto_warning_at_5_failures(repo):
    result = None
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

    items = repo.script_list()
    ids = {i["task_id"] for i in items}
    assert "t1" in ids and "t2" in ids and "t3" not in ids

    items = repo.script_list(status="all")
    ids = {i["task_id"] for i in items}
    assert "t3" in ids

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


def test_script_delete_cascades_sessions(tmp_path):
    """删除脚本时应级联清理 session_headers / session_runtime"""
    from zerotoken.repository.sqlite import (
        SQLiteRuntimeRepo,
        SQLiteScriptRepo,
        SQLiteSessionRepo,
        new_connection,
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

    assert sessions.session_list() == []
    assert runtime.runtime_get("s1") is None


def test_script_delete_blocked_by_binding(tmp_path):
    """存在 script_bindings 引用时不允许删除脚本"""
    from zerotoken.repository.sqlite import (
        SQLiteBindingRepo,
        SQLiteScriptRepo,
        new_connection,
    )

    db = str(tmp_path / "t.db")
    conn = new_connection(db)
    scripts = SQLiteScriptRepo(conn)
    bindings = SQLiteBindingRepo(conn)

    scripts.script_save("t1", goal="g", steps=[])
    bindings.binding_set("job-1", script_task_id="t1")

    with pytest.raises(ValueError, match="has bindings"):
        scripts.script_delete("t1")
