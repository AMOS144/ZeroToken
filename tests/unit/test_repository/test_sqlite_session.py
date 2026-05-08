"""SQLiteSessionRepo + SQLiteRuntimeRepo 测试"""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def session_repo():
    from zerotoken.repository.sqlite import SQLiteSessionRepo, new_connection

    conn = new_connection(":memory:")
    return SQLiteSessionRepo(conn)


@pytest.fixture
def runtime_repo():
    from zerotoken.repository.sqlite import SQLiteRuntimeRepo, new_connection

    conn = new_connection(":memory:")
    return SQLiteRuntimeRepo(conn)


def test_session_start_and_append(session_repo):
    session_repo.session_start("s1", task_id="t1")
    session_repo.session_append("s1", step_index=0, action="open", url="https://x.com")
    session_repo.session_append("s1", step_index=1, action="click", selector="#btn")
    steps = session_repo.session_get("s1")
    assert len(steps) == 2
    assert steps[0]["action"] == "open"
    assert steps[1]["selector"] == "#btn"


def test_session_list(session_repo):
    session_repo.session_start("s1", task_id="t1")
    session_repo.session_start("s2", task_id="t2")
    items = session_repo.session_list()
    assert len(items) == 2


def test_runtime_init_and_get(runtime_repo):
    runtime_repo.runtime_init("s1", task_id="t1", cursor_step_index=0, status="running")
    rt = runtime_repo.runtime_get("s1")
    assert rt is not None
    assert rt["status"] == "running"
    assert rt["cursor_step_index"] == 0


def test_runtime_update(runtime_repo):
    runtime_repo.runtime_init("s1", task_id="t1", cursor_step_index=0, status="running")
    runtime_repo.runtime_update("s1", cursor_step_index=3, status="paused")
    rt = runtime_repo.runtime_get("s1")
    assert rt["cursor_step_index"] == 3
    assert rt["status"] == "paused"


def test_runtime_get_not_found(runtime_repo):
    assert runtime_repo.runtime_get("nope") is None


def test_runtime_update_not_found(runtime_repo):
    with pytest.raises(KeyError):
        runtime_repo.runtime_update("nope", status="x")


def test_find_paused_before_returns_stale(tmp_path):
    """paused 且 updated_at 早于 cutoff 的会话应被找出"""
    from zerotoken.repository.sqlite import SQLiteRuntimeRepo, new_connection

    db = str(tmp_path / "t.db")
    conn = new_connection(db)
    runtime = SQLiteRuntimeRepo(conn)

    runtime.runtime_init("s1", task_id="t1", cursor_step_index=0, status="paused")
    runtime.runtime_init("s2", task_id="t1", cursor_step_index=0, status="running")

    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    conn.execute("UPDATE session_runtime SET updated_at=? WHERE session_id=?", (old, "s1"))
    conn.commit()

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    stale = runtime.find_paused_before("t1", cutoff)
    ids = [s["session_id"] for s in stale]
    assert ids == ["s1"]


def test_find_paused_before_ignores_running(tmp_path):
    """running 状态不应被视为遗弃，即使时间很久"""
    from zerotoken.repository.sqlite import SQLiteRuntimeRepo, new_connection

    db = str(tmp_path / "t.db")
    conn = new_connection(db)
    runtime = SQLiteRuntimeRepo(conn)

    runtime.runtime_init("s1", task_id="t1", cursor_step_index=0, status="running")
    old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
    conn.execute("UPDATE session_runtime SET updated_at=? WHERE session_id=?", (old, "s1"))
    conn.commit()

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    stale = runtime.find_paused_before("t1", cutoff)
    assert stale == []


def test_find_paused_before_filters_by_task_id(tmp_path):
    from zerotoken.repository.sqlite import SQLiteRuntimeRepo, new_connection

    db = str(tmp_path / "t.db")
    conn = new_connection(db)
    runtime = SQLiteRuntimeRepo(conn)

    runtime.runtime_init("s1", task_id="t1", cursor_step_index=0, status="paused")
    runtime.runtime_init("s2", task_id="t2", cursor_step_index=0, status="paused")
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    conn.execute("UPDATE session_runtime SET updated_at=?", (old,))
    conn.commit()

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    stale = runtime.find_paused_before("t1", cutoff)
    ids = [s["session_id"] for s in stale]
    assert ids == ["s1"]
