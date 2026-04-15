"""ScriptService run/resume 测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_repos():
    scripts = MagicMock()
    scripts.script_load = MagicMock(return_value={
        "task_id": "test_task",
        "goal": "test",
        "steps": [{"action": "browser_open", "params": {"url": "https://example.com"}}],
    })
    trajs = MagicMock()
    sessions = MagicMock()
    sessions.session_start = MagicMock()
    sessions.session_append = MagicMock()
    runtime = MagicMock()
    runtime.runtime_init = MagicMock()
    runtime.runtime_update = MagicMock()
    runtime.runtime_get = MagicMock(return_value=None)
    bindings = MagicMock()
    return scripts, trajs, sessions, runtime, bindings


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
