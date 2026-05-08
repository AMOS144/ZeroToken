"""Tests for trajectory save to DB and selector_candidates in operations."""

import os
import tempfile

import pytest

from zerotoken.controller import OperationRecord, PageState
from zerotoken.trajectory import TrajectoryRecorder
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


def test_trajectory_save_to_db_includes_selector_candidates(db_path):
    """After completing a trajectory with selector_candidates, DB has one record with selector_candidates in operations."""
    store = SQLiteStorage(db_path)
    recorder = TrajectoryRecorder(trajectory_store=store, auto_save=False)
    traj = recorder.start_trajectory("task_db_1", "Test goal")
    record = OperationRecord(
        step=1,
        action="click",
        params={"selector": "#btn"},
        result={"success": True},
        page_state=PageState(url="https://example.com", title="Example"),
        selector_candidates=[
            {"type": "css", "value": "#btn"},
            {"type": "test_id", "value": "[data-testid=submit]"},
        ],
    )
    traj.add_operation(record)
    traj.complete()
    recorder.save_trajectory(traj)
    # Load from DB
    listed = store.trajectory_list(limit=1)
    assert len(listed) == 1
    traj_id = listed[0]["id"]
    loaded = store.trajectory_load(traj_id)
    assert loaded is not None
    assert len(loaded["operations"]) == 1
    assert loaded["operations"][0].get("selector_candidates") == [
        {"type": "css", "value": "#btn"},
        {"type": "test_id", "value": "[data-testid=submit]"},
    ]
