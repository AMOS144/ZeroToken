"""SQLiteTrajectoryRepo 单元测试"""
import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import SQLiteTrajectoryRepo, new_connection

    conn = new_connection(":memory:")
    return SQLiteTrajectoryRepo(conn)


def test_save_and_load(repo):
    tid = repo.trajectory_save(
        task_id="login",
        goal="login test",
        operations=[{"step": 1, "action": "open", "params": {"url": "https://x.com"}}],
        metadata={"total_steps": 1},
    )
    assert isinstance(tid, int)
    traj = repo.trajectory_load(tid)
    assert traj is not None
    assert traj["task_id"] == "login"
    assert len(traj["operations"]) == 1


def test_load_by_task_id(repo):
    repo.trajectory_save(task_id="t1", goal="g1", operations=[])
    repo.trajectory_save(task_id="t1", goal="g1 v2", operations=[{"step": 1}])
    traj = repo.trajectory_load_by_task_id("t1")
    assert traj is not None
    assert traj["goal"] == "g1 v2"


def test_load_by_task_id_not_found(repo):
    assert repo.trajectory_load_by_task_id("nope") is None


def test_list(repo):
    repo.trajectory_save(task_id="a", goal="ga", operations=[])
    repo.trajectory_save(task_id="b", goal="gb", operations=[])
    items = repo.trajectory_list(limit=10)
    assert len(items) == 2


def test_delete_by_task_id(repo):
    repo.trajectory_save(task_id="t1", goal="g", operations=[])
    repo.trajectory_save(task_id="t1", goal="g", operations=[])
    deleted = repo.trajectory_delete_by_task_id("t1")
    assert deleted == 2
    assert repo.trajectory_load_by_task_id("t1") is None
