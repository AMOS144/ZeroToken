"""SQLiteScriptRepo 单元测试"""
import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import SQLiteScriptRepo, new_connection

    conn = new_connection(":memory:")
    return SQLiteScriptRepo(conn)


def test_save_and_load(repo):
    repo.script_save(
        "t1",
        goal="test",
        steps=[{"action": "browser_open", "params": {"url": "https://x.com"}}],
    )
    script = repo.script_load("t1")
    assert script is not None
    assert script["task_id"] == "t1"
    assert script["goal"] == "test"
    assert len(script["steps"]) == 1
    assert script["steps"][0]["action"] == "browser_open"


def test_load_not_found(repo):
    assert repo.script_load("nonexistent") is None


def test_save_overwrites(repo):
    repo.script_save("t1", goal="v1", steps=[])
    repo.script_save("t1", goal="v2", steps=[{"action": "browser_click", "params": {}}])
    script = repo.script_load("t1")
    assert script["goal"] == "v2"
    assert len(script["steps"]) == 1


def test_list(repo):
    repo.script_save("a", goal="ga", steps=[])
    repo.script_save("b", goal="gb", steps=[])
    items = repo.script_list(limit=10)
    assert len(items) == 2
    task_ids = {it["task_id"] for it in items}
    assert task_ids == {"a", "b"}


def test_delete(repo):
    repo.script_save("t1", goal="g", steps=[])
    assert repo.script_delete("t1") is True
    assert repo.script_load("t1") is None
    assert repo.script_delete("t1") is False


def test_save_with_source_trajectory_id(repo):
    repo.script_save("t1", goal="g", steps=[], source_trajectory_id=42)
    script = repo.script_load("t1")
    assert script["source_trajectory_id"] == 42
