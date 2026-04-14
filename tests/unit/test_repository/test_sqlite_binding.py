"""SQLiteBindingRepo 测试"""
import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import SQLiteBindingRepo, new_connection
    conn = new_connection(":memory:")
    return SQLiteBindingRepo(conn)


def test_set_and_get(repo):
    repo.binding_set("job1", script_task_id="script1", description="test binding", default_vars={"user": "admin"})
    b = repo.binding_get("job1")
    assert b is not None
    assert b["script_task_id"] == "script1"
    assert b["default_vars"]["user"] == "admin"


def test_get_not_found(repo):
    assert repo.binding_get("nope") is None


def test_list(repo):
    repo.binding_set("j1", script_task_id="s1")
    repo.binding_set("j2", script_task_id="s2")
    items = repo.binding_list()
    assert len(items) == 2


def test_delete(repo):
    repo.binding_set("j1", script_task_id="s1")
    assert repo.binding_delete("j1") is True
    assert repo.binding_get("j1") is None
    assert repo.binding_delete("j1") is False
