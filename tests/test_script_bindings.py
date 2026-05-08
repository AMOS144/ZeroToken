"""Tests for script bindings (job_id -> script_task_id) in SQLiteStorage."""

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


def test_script_binding_set_get_list_delete(storage: SQLiteStorage):
    key = "job_daily_comment"
    storage.script_binding_set(
        key,
        script_task_id="task_script_1",
        description="每日评论脚本",
        default_vars={"channel": "bilibili", "video_id": "abc"},
    )

    binding = storage.script_binding_get(key)
    assert binding is not None
    assert binding["binding_key"] == key
    assert binding["script_task_id"] == "task_script_1"
    assert binding["description"] == "每日评论脚本"
    assert binding["default_vars"]["channel"] == "bilibili"

    items = storage.script_binding_list()
    assert any(it["binding_key"] == key for it in items)

    assert storage.script_binding_delete(key) is True
    assert storage.script_binding_get(key) is None
