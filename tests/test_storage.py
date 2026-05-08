"""Tests for zerotoken storage (ScriptStore, TrajectoryStore, SessionStore)."""

import os
import tempfile

import pytest

from zerotoken.storage_sqlite import SQLiteStorage


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def storage(db_path):
    return SQLiteStorage(db_path)


def test_script_save_and_load(storage):
    """Save a script and load it by task_id."""
    task_id = "test_task_1"
    goal = "Test goal"
    steps = [
        {"action": "browser_open", "params": {"url": "https://example.com"}},
        {"action": "browser_click", "params": {"selector": "#btn"}},
    ]
    params_schema = {"username": "string"}
    storage.script_save(task_id, goal=goal, steps=steps, params_schema=params_schema)
    loaded = storage.script_load(task_id)
    assert loaded is not None
    assert loaded["task_id"] == task_id
    assert loaded["goal"] == goal
    assert loaded["steps"] == steps
    assert loaded["params_schema"] == params_schema
    assert "created_at" in loaded
    assert "updated_at" in loaded


def test_script_load_missing_returns_none(storage):
    """script_load for missing task_id returns None."""
    assert storage.script_load("nonexistent") is None


def test_trajectory_save_and_load(storage):
    """Save a trajectory and load it by id."""
    task_id = "traj_task_1"
    goal = "Recorded flow"
    operations = [
        {"step": 1, "action": "open", "params": {"url": "https://a.com"}},
        {"step": 2, "action": "click", "params": {"selector": "#x"}},
    ]
    metadata = {"total_steps": 2}
    traj_id = storage.trajectory_save(
        task_id=task_id, goal=goal, operations=operations, metadata=metadata
    )
    assert traj_id is not None
    loaded = storage.trajectory_load(traj_id)
    assert loaded is not None
    assert loaded["task_id"] == task_id
    assert loaded["goal"] == goal
    assert loaded["operations"] == operations
    assert loaded["metadata"] == metadata
    assert "created_at" in loaded


def test_trajectory_load_missing_returns_none(storage):
    """trajectory_load for missing id returns None."""
    assert storage.trajectory_load(99999) is None


def test_session_append_and_get(storage):
    """Append session steps and get by session_id."""
    session_id = "sess_001"
    task_id = "task_1"
    session_type = "replay"
    storage.session_start(session_id, task_id=task_id, session_type=session_type)
    storage.session_append(
        session_id,
        step_index=0,
        action="open",
        selector=None,
        url="https://example.com",
        payload={"url": "https://example.com"},
    )
    storage.session_append(
        session_id,
        step_index=1,
        action="click",
        selector="#btn",
        url="https://example.com/page",
        payload={},
    )
    steps = storage.session_get(session_id)
    assert len(steps) == 2
    assert steps[0]["action"] == "open"
    assert steps[0]["url"] == "https://example.com"
    assert steps[1]["action"] == "click"
    assert steps[1]["selector"] == "#btn"


def test_session_get_missing_returns_empty(storage):
    """session_get for missing session_id returns empty list."""
    assert storage.session_get("no_such_session") == []
