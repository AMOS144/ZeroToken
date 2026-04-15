"""ScriptEngineV2 测试：启动/暂停/恢复 + Step-as-Unit"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from zerotoken.models.script import ScriptStep, Script
from zerotoken.models.session import Resolution
from zerotoken.models.operation import (
    OperationRecord, OperationResult, PageState, ActionType,
)


def _ok_record(**data) -> OperationRecord:
    return OperationRecord(
        step=1, action=ActionType.CLICK, params={},
        result=OperationResult(success=True, data=data or {}),
        page_state=PageState(url="https://example.com"),
    )


def _fail_record(error: str = "not found") -> OperationRecord:
    return OperationRecord(
        step=1, action=ActionType.CLICK,
        params={"selector": "#btn"},
        result=OperationResult(success=False, error=error),
        page_state=PageState(url="https://example.com"),
    )


@pytest.fixture
def mock_browser_svc():
    """模拟 BrowserService"""
    svc = AsyncMock()
    svc.click = AsyncMock(return_value=_ok_record())
    svc.open = AsyncMock(return_value=_ok_record())
    svc.get_text = AsyncMock(return_value=_ok_record(value="hello"))
    return svc


@pytest.fixture
def mock_session_repo():
    repo = MagicMock()
    repo.session_start = MagicMock()
    repo.session_append = MagicMock()
    return repo


@pytest.fixture
def mock_runtime_repo():
    repo = MagicMock()
    repo.runtime_init = MagicMock()
    repo.runtime_update = MagicMock()
    repo.runtime_get = MagicMock(return_value=None)
    return repo


@pytest.mark.asyncio
async def test_run_simple_script(mock_browser_svc, mock_session_repo, mock_runtime_repo):
    from zerotoken.engine.script_engine_v2 import ScriptEngineV2

    script = Script(
        task_id="test", goal="test goal",
        steps=[
            ScriptStep(action="browser_open", params={"url": "https://example.com"}),
            ScriptStep(action="browser_click", params={"selector": "#btn"}),
        ],
    )
    engine = ScriptEngineV2(mock_browser_svc, mock_session_repo, mock_runtime_repo)
    result = await engine.run(script)
    assert result["status"] == "completed"
    assert "session_id" in result
    mock_session_repo.session_start.assert_called_once()


@pytest.mark.asyncio
async def test_run_pauses_on_failure(mock_browser_svc, mock_session_repo, mock_runtime_repo):
    from zerotoken.engine.script_engine_v2 import ScriptEngineV2

    mock_browser_svc.click = AsyncMock(return_value=_fail_record("element not found"))

    script = Script(
        task_id="test", goal="test",
        steps=[ScriptStep(action="browser_click", params={"selector": "#missing"})],
    )
    engine = ScriptEngineV2(mock_browser_svc, mock_session_repo, mock_runtime_repo)
    result = await engine.run(script)
    assert result["status"] == "paused"
    assert result["pause_event"]["reason"] == "step_failed"
    assert "element not found" in result["pause_event"]["error"]
    mock_runtime_repo.runtime_update.assert_called()


@pytest.mark.asyncio
async def test_run_with_vars(mock_browser_svc, mock_session_repo, mock_runtime_repo):
    from zerotoken.engine.script_engine_v2 import ScriptEngineV2

    script = Script(
        task_id="test", goal="test",
        steps=[ScriptStep(action="browser_open", params={"url": "{{target_url}}"})],
    )
    engine = ScriptEngineV2(mock_browser_svc, mock_session_repo, mock_runtime_repo)
    result = await engine.run(script, vars={"target_url": "https://example.com"})
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_with_retry(mock_browser_svc, mock_session_repo, mock_runtime_repo):
    from zerotoken.engine.script_engine_v2 import ScriptEngineV2

    mock_browser_svc.click = AsyncMock(return_value=_fail_record("not found"))
    script = Script(
        task_id="test", goal="test",
        steps=[ScriptStep(action="browser_click", params={"selector": "#btn"})],
    )
    engine = ScriptEngineV2(mock_browser_svc, mock_session_repo, mock_runtime_repo)
    run_result = await engine.run(script)
    assert run_result["status"] == "paused"
    session_id = run_result["session_id"]

    mock_browser_svc.click = AsyncMock(return_value=_ok_record())
    mock_runtime_repo.runtime_get = MagicMock(return_value={
        "session_id": session_id,
        "task_id": "test",
        "cursor_step_index": 0,
        "status": "paused",
        "vars": {},
    })
    resolution = Resolution(type="retry")
    resume_result = await engine.resume(session_id, script, resolution)
    assert resume_result["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_with_skip(mock_browser_svc, mock_session_repo, mock_runtime_repo):
    from zerotoken.engine.script_engine_v2 import ScriptEngineV2

    mock_browser_svc.click = AsyncMock(return_value=_fail_record("not found"))
    script = Script(
        task_id="test", goal="test",
        steps=[
            ScriptStep(action="browser_click", params={"selector": "#btn"}),
            ScriptStep(action="browser_open", params={"url": "https://next.com"}),
        ],
    )
    engine = ScriptEngineV2(mock_browser_svc, mock_session_repo, mock_runtime_repo)
    run_result = await engine.run(script)
    session_id = run_result["session_id"]

    mock_browser_svc.open = AsyncMock(return_value=_ok_record())
    mock_runtime_repo.runtime_get = MagicMock(return_value={
        "session_id": session_id,
        "task_id": "test",
        "cursor_step_index": 0,
        "status": "paused",
        "vars": {},
    })
    resolution = Resolution(type="skip")
    resume_result = await engine.resume(session_id, script, resolution)
    assert resume_result["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_with_patch_step(mock_browser_svc, mock_session_repo, mock_runtime_repo):
    from zerotoken.engine.script_engine_v2 import ScriptEngineV2

    mock_browser_svc.click = AsyncMock(return_value=_fail_record("not found"))
    script = Script(
        task_id="test", goal="test",
        steps=[ScriptStep(action="browser_click", params={"selector": "#old-btn"})],
    )
    engine = ScriptEngineV2(mock_browser_svc, mock_session_repo, mock_runtime_repo)
    run_result = await engine.run(script)
    session_id = run_result["session_id"]

    mock_browser_svc.click = AsyncMock(return_value=_ok_record())
    mock_runtime_repo.runtime_get = MagicMock(return_value={
        "session_id": session_id,
        "task_id": "test",
        "cursor_step_index": 0,
        "status": "paused",
        "vars": {},
    })
    resolution = Resolution(type="patch_step", patch={"params": {"selector": "#new-btn"}})
    resume_result = await engine.resume(session_id, script, resolution)
    assert resume_result["status"] == "completed"
    patched_call = mock_browser_svc.click.call_args
    assert patched_call.args[0] == "#new-btn" or patched_call.kwargs.get("selector") == "#new-btn"
