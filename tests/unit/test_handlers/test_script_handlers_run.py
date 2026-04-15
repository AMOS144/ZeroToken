"""script_run / script_resume handler 测试"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_script_svc():
    svc = MagicMock()
    svc.run_script = AsyncMock(return_value={"status": "completed", "session_id": "sess-1"})
    svc.resume_script = AsyncMock(return_value={"status": "completed", "session_id": "sess-1"})
    svc.run_script_by_binding = AsyncMock(return_value={"status": "completed", "session_id": "sess-1"})
    return svc


@pytest.fixture
def mock_browser_svc():
    return AsyncMock()


@pytest.mark.asyncio
async def test_script_run_start(mock_script_svc, mock_browser_svc):
    from handlers.script_handlers import handle_script_tool
    result = await handle_script_tool(
        "script_run",
        {"task_id": "test_task", "vars": {"x": 1}},
        mock_script_svc,
        browser_svc=mock_browser_svc,
    )
    text = json.loads(result[0].text)
    assert text["status"] == "completed"
    mock_script_svc.run_script.assert_awaited_once()


@pytest.mark.asyncio
async def test_script_resume(mock_script_svc, mock_browser_svc):
    from handlers.script_handlers import handle_script_tool
    result = await handle_script_tool(
        "script_resume",
        {"session_id": "sess-1", "resolution": {"type": "retry"}},
        mock_script_svc,
        browser_svc=mock_browser_svc,
    )
    text = json.loads(result[0].text)
    assert text["status"] == "completed"
    mock_script_svc.resume_script.assert_awaited_once()
