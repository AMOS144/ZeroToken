"""Tests for DFUStore and SessionRuntimeStore in SQLiteStorage."""

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


def test_dfu_save_load_list_delete(storage: SQLiteStorage):
    storage.dfu_save(
        "captcha_v1",
        name="Captcha handler",
        description="Pause on captcha step",
        triggers=[{"action_is": "browser_click", "selector_is": "#captcha"}],
        prompt="Need human to solve captcha",
        allowed_resolutions=["human_done", "abort"],
    )

    items = storage.dfu_list()
    assert any(it["dfu_id"] == "captcha_v1" for it in items)

    loaded = storage.dfu_load("captcha_v1")
    assert loaded is not None
    assert loaded["dfu_id"] == "captcha_v1"
    assert loaded["name"] == "Captcha handler"
    assert loaded["prompt"] == "Need human to solve captcha"
    assert loaded["triggers"][0]["selector_is"] == "#captcha"
    assert "updated_at" in loaded

    assert storage.dfu_delete("captcha_v1") is True
    assert storage.dfu_load("captcha_v1") is None


def test_runtime_init_get_update(storage: SQLiteStorage):
    session_id = "sess_rt_1"
    storage.runtime_init(
        session_id, task_id="task_x", cursor_step_index=0, status="running", pause_event=None
    )

    rt = storage.runtime_get(session_id)
    assert rt is not None
    assert rt["session_id"] == session_id
    assert rt["cursor_step_index"] == 0
    assert rt["status"] == "running"
    assert rt["pause_event"] is None

    pause_event = {"kind": "dfu_pause", "step_index": 1}
    storage.runtime_update(
        session_id, cursor_step_index=1, status="paused", pause_event=pause_event
    )

    rt2 = storage.runtime_get(session_id)
    assert rt2 is not None
    assert rt2["cursor_step_index"] == 1
    assert rt2["status"] == "paused"
    assert rt2["pause_event"]["kind"] == "dfu_pause"
