"""ScriptService run/resume 统计和报废测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_repos():
    scripts = MagicMock()
    scripts.script_load = MagicMock(return_value={
        "task_id": "test_task",
        "goal": "test",
        "steps": [{"action": "browser_open", "params": {"url": "https://example.com"}}],
    })
    scripts.health = MagicMock(return_value=None)
    trajs = MagicMock()
    sessions = MagicMock()
    sessions.session_start = MagicMock()
    sessions.session_append = MagicMock()
    runtime = MagicMock()
    runtime.runtime_init = MagicMock()
    runtime.runtime_update = MagicMock()
    runtime.runtime_get = MagicMock(return_value=None)
    runtime.find_paused_before = MagicMock(return_value=[])
    bindings = MagicMock()
    return scripts, trajs, sessions, runtime, bindings


@pytest.fixture
def mock_browser_svc_for_stats():
    return AsyncMock()


def _make_service(script_repo=None, runtime_repo=None):
    """构造 ScriptService，各 repo 默认 MagicMock"""
    from zerotoken.services.script_service import ScriptService
    return ScriptService(
        script_repo or MagicMock(),
        MagicMock(),
        MagicMock(),
        runtime_repo or MagicMock(),
        MagicMock(),
    )


@pytest.fixture
def mock_browser_svc():
    from zerotoken.models.operation import OperationRecord, OperationResult, PageState, ActionType
    record = OperationRecord(
        step=1, action=ActionType.OPEN, params={},
        result=OperationResult(success=True, data={}),
        page_state=PageState(url="https://example.com"),
    )
    svc = AsyncMock()
    svc.open = AsyncMock(return_value=record)
    svc.click = AsyncMock(return_value=record)
    svc._pipeline = MagicMock()
    svc._pipeline.capture_state_safe = AsyncMock(return_value=None)
    return svc


@pytest.mark.asyncio
async def test_run_script(mock_repos, mock_browser_svc):
    from zerotoken.services.script_service import ScriptService
    scripts, trajs, sessions, runtime, bindings = mock_repos
    svc = ScriptService(scripts, trajs, sessions, runtime, bindings)
    result = await svc.run_script("test_task", mock_browser_svc, vars={})
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_run_script_not_found(mock_repos, mock_browser_svc):
    from zerotoken.services.script_service import ScriptService
    scripts, trajs, sessions, runtime, bindings = mock_repos
    scripts.script_load = MagicMock(return_value=None)
    svc = ScriptService(scripts, trajs, sessions, runtime, bindings)
    result = await svc.run_script("missing", mock_browser_svc)
    assert result["status"] == "error"
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_run_script_by_binding(mock_repos, mock_browser_svc):
    from zerotoken.services.script_service import ScriptService
    scripts, trajs, sessions, runtime, bindings = mock_repos
    bindings.binding_get = MagicMock(return_value={
        "script_task_id": "test_task",
        "default_vars": {"x": 1},
    })
    svc = ScriptService(scripts, trajs, sessions, runtime, bindings)
    result = await svc.run_script_by_binding("job_1", mock_browser_svc)
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_script(mock_repos, mock_browser_svc):
    from zerotoken.services.script_service import ScriptService
    from zerotoken.models.session import Resolution
    scripts, trajs, sessions, runtime, bindings = mock_repos
    runtime.runtime_get = MagicMock(return_value={
        "session_id": "sess-1",
        "task_id": "test_task",
        "cursor_step_index": 0,
        "status": "paused",
        "vars": {},
    })
    svc = ScriptService(scripts, trajs, sessions, runtime, bindings)
    result = await svc.resume_script("sess-1", Resolution(type="retry"), mock_browser_svc)
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_run_script_records_completed_on_success(mock_browser_svc_for_stats):
    """run_script 成功时应调 record_run_result(completed)"""
    script_repo = MagicMock()
    script_repo.script_load.return_value = {
        "task_id": "t1", "goal": "g",
        "steps": [{"action": "browser_open", "params": {"url": "x"}}],
        "params_schema": {},
    }
    script_repo.health.return_value = {"status": "active"}
    script_repo.record_run_result.return_value = {"status": "active"}

    runtime_repo = MagicMock()
    runtime_repo.find_paused_before.return_value = []

    svc = _make_service(script_repo=script_repo, runtime_repo=runtime_repo)

    with patch(
        "zerotoken.engine.script_engine_v2.ScriptEngineV2.run",
        new=AsyncMock(return_value={"status": "completed", "session_id": "s1"}),
    ):
        result = await svc.run_script("t1", mock_browser_svc_for_stats)

    script_repo.record_run_result.assert_called_once_with("t1", "completed", "s1")
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_run_script_rejects_deprecated(mock_browser_svc_for_stats):
    """deprecated 脚本不能执行"""
    script_repo = MagicMock()
    script_repo.health.return_value = {
        "status": "deprecated", "deprecated_reason": "outdated",
    }
    script_repo.script_load.return_value = {
        "task_id": "t1", "goal": "g", "steps": [],
    }

    svc = _make_service(script_repo=script_repo)
    result = await svc.run_script("t1", mock_browser_svc_for_stats)
    assert result["status"] == "error"
    assert result.get("code") == "SCRIPT_DEPRECATED"
    assert "outdated" in result["error"]


@pytest.mark.asyncio
async def test_run_script_settles_abandoned_sessions(mock_browser_svc_for_stats):
    """run_script 前应清理该 task_id 下遗弃的 paused session"""
    script_repo = MagicMock()
    script_repo.health.return_value = {"status": "active"}
    script_repo.script_load.return_value = {
        "task_id": "t1", "goal": "g", "steps": [],
    }
    script_repo.record_run_result.return_value = {"status": "active"}

    runtime_repo = MagicMock()
    runtime_repo.find_paused_before.return_value = [
        {"session_id": "old1", "task_id": "t1", "updated_at": "..."},
    ]

    svc = _make_service(script_repo=script_repo, runtime_repo=runtime_repo)

    with patch(
        "zerotoken.engine.script_engine_v2.ScriptEngineV2.run",
        new=AsyncMock(return_value={"status": "completed", "session_id": "new1"}),
    ):
        await svc.run_script("t1", mock_browser_svc_for_stats)

    runtime_repo.runtime_update.assert_any_call("old1", status="aborted")
    # record_run_result 被至少调用 2 次：遗弃一次 + 新执行终态一次
    assert script_repo.record_run_result.call_count >= 2


@pytest.mark.asyncio
async def test_run_script_adds_auto_warned_hint(mock_browser_svc_for_stats):
    """当 active 因本次执行升级为 warning 时，响应中带 auto_warned hint"""
    script_repo = MagicMock()
    script_repo.health.return_value = {"status": "active"}
    script_repo.script_load.return_value = {
        "task_id": "t1", "goal": "g", "steps": [],
    }
    script_repo.record_run_result.return_value = {
        "status": "warning", "consecutive_failures": 5,
    }
    runtime_repo = MagicMock()
    runtime_repo.find_paused_before.return_value = []

    svc = _make_service(script_repo=script_repo, runtime_repo=runtime_repo)

    with patch(
        "zerotoken.engine.script_engine_v2.ScriptEngineV2.run",
        new=AsyncMock(return_value={"status": "failed", "session_id": "s1"}),
    ):
        result = await svc.run_script("t1", mock_browser_svc_for_stats)

    assert result.get("health", {}).get("auto_warned") is True
    assert result["health"]["consecutive_failures"] == 5


@pytest.mark.asyncio
async def test_run_script_paused_does_not_update_stats(mock_browser_svc_for_stats):
    """paused 不是终态，不应调用 record_run_result"""
    script_repo = MagicMock()
    script_repo.health.return_value = {"status": "active"}
    script_repo.script_load.return_value = {
        "task_id": "t1", "goal": "g", "steps": [],
    }
    runtime_repo = MagicMock()
    runtime_repo.find_paused_before.return_value = []

    svc = _make_service(script_repo=script_repo, runtime_repo=runtime_repo)

    with patch(
        "zerotoken.engine.script_engine_v2.ScriptEngineV2.run",
        new=AsyncMock(return_value={
            "status": "paused", "session_id": "s1", "pause_event": {},
        }),
    ):
        result = await svc.run_script("t1", mock_browser_svc_for_stats)

    # paused 不触发统计更新
    script_repo.record_run_result.assert_not_called()
    assert result["status"] == "paused"


@pytest.mark.asyncio
async def test_resume_script_records_stats_on_terminal(mock_browser_svc_for_stats):
    """resume 终态时应更新统计"""
    script_repo = MagicMock()
    script_repo.script_load.return_value = {
        "task_id": "t1", "goal": "g", "steps": [],
    }
    script_repo.record_run_result.return_value = {"status": "active"}

    runtime_repo = MagicMock()
    runtime_repo.runtime_get.return_value = {"task_id": "t1", "status": "paused"}

    svc = _make_service(script_repo=script_repo, runtime_repo=runtime_repo)

    from zerotoken.models.session import Resolution
    with patch(
        "zerotoken.engine.script_engine_v2.ScriptEngineV2.resume",
        new=AsyncMock(return_value={"status": "completed", "session_id": "s1"}),
    ):
        result = await svc.resume_script(
            "s1", Resolution(type="retry"), mock_browser_svc_for_stats,
        )

    script_repo.record_run_result.assert_called_once_with("t1", "completed", "s1")


def test_script_deprecate_delegates_to_repo():
    script_repo = MagicMock()
    script_repo.deprecate.return_value = {"status": "deprecated"}
    svc = _make_service(script_repo=script_repo)
    result = svc.script_deprecate("t1", reason="old")
    script_repo.deprecate.assert_called_once_with("t1", reason="old")
    assert result["status"] == "deprecated"


def test_script_restore_delegates_to_repo():
    script_repo = MagicMock()
    script_repo.restore.return_value = {"status": "active"}
    svc = _make_service(script_repo=script_repo)
    result = svc.script_restore("t1")
    script_repo.restore.assert_called_once_with("t1")
    assert result["status"] == "active"


def test_script_health_delegates_to_repo():
    script_repo = MagicMock()
    script_repo.health.return_value = {"status": "warning"}
    svc = _make_service(script_repo=script_repo)
    result = svc.script_health("t1")
    script_repo.health.assert_called_once_with("t1")
    assert result["status"] == "warning"
