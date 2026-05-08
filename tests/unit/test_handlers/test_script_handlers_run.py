"""script_run / script_resume handler 测试"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_script_svc():
    svc = MagicMock()
    svc.run_script = AsyncMock(return_value={"status": "completed", "session_id": "sess-1"})
    svc.resume_script = AsyncMock(return_value={"status": "completed", "session_id": "sess-1"})
    svc.run_script_by_binding = AsyncMock(
        return_value={"status": "completed", "session_id": "sess-1"}
    )
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


# ---------- script_deprecate / script_restore / script_health / script_list(status) ----------


def test_script_deprecate_tool_exists():
    from handlers.script_handlers import script_tools

    names = [t.name for t in script_tools()]
    assert "script_deprecate" in names
    assert "script_restore" in names
    assert "script_health" in names


def test_script_list_schema_has_status_filter():
    from handlers.script_handlers import script_tools

    tools = {t.name: t for t in script_tools()}
    props = tools["script_list"].inputSchema["properties"]
    assert "status" in props


def test_script_deprecate_schema_requires_task_id():
    from handlers.script_handlers import script_tools

    tools = {t.name: t for t in script_tools()}
    schema = tools["script_deprecate"].inputSchema
    assert "task_id" in schema.get("required", [])


@pytest.mark.asyncio
async def test_handle_script_deprecate_success():
    from handlers.script_handlers import handle_script_tool

    svc = MagicMock()
    svc.script_deprecate = MagicMock(
        return_value={
            "status": "deprecated",
            "task_id": "t1",
            "deprecated_reason": "old",
        }
    )
    result = await handle_script_tool(
        "script_deprecate",
        {"task_id": "t1", "reason": "old"},
        svc,
    )
    data = json.loads(result[0].text)
    assert data["success"] is True
    assert data["status"] == "deprecated"
    svc.script_deprecate.assert_called_once_with("t1", reason="old")


@pytest.mark.asyncio
async def test_handle_script_deprecate_not_found():
    from handlers.script_handlers import handle_script_tool

    svc = MagicMock()
    svc.script_deprecate = MagicMock(side_effect=KeyError("nope"))
    result = await handle_script_tool(
        "script_deprecate",
        {"task_id": "nope"},
        svc,
    )
    data = json.loads(result[0].text)
    assert data["success"] is False
    assert data["code"] == "SCRIPT_NOT_FOUND"


@pytest.mark.asyncio
async def test_handle_script_restore_success():
    from handlers.script_handlers import handle_script_tool

    svc = MagicMock()
    svc.script_restore = MagicMock(
        return_value={
            "task_id": "t1",
            "status": "active",
        }
    )
    result = await handle_script_tool(
        "script_restore",
        {"task_id": "t1"},
        svc,
    )
    data = json.loads(result[0].text)
    assert data["success"] is True
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_handle_script_restore_not_deprecated():
    from handlers.script_handlers import handle_script_tool

    svc = MagicMock()
    svc.script_restore = MagicMock(side_effect=ValueError("script t1 is not deprecated"))
    result = await handle_script_tool(
        "script_restore",
        {"task_id": "t1"},
        svc,
    )
    data = json.loads(result[0].text)
    assert data["success"] is False
    assert data["code"] == "SCRIPT_NOT_DEPRECATED"


@pytest.mark.asyncio
async def test_handle_script_restore_missing():
    from handlers.script_handlers import handle_script_tool

    svc = MagicMock()
    svc.script_restore = MagicMock(side_effect=KeyError("no"))
    result = await handle_script_tool(
        "script_restore",
        {"task_id": "nope"},
        svc,
    )
    data = json.loads(result[0].text)
    assert data["code"] == "SCRIPT_NOT_FOUND"


@pytest.mark.asyncio
async def test_handle_script_health_success():
    from handlers.script_handlers import handle_script_tool

    svc = MagicMock()
    svc.script_health = MagicMock(
        return_value={
            "task_id": "t1",
            "status": "warning",
            "consecutive_failures": 5,
            "total_runs": 5,
        }
    )
    result = await handle_script_tool(
        "script_health",
        {"task_id": "t1"},
        svc,
    )
    data = json.loads(result[0].text)
    assert data["success"] is True
    assert data["health"]["status"] == "warning"
    assert data["health"]["consecutive_failures"] == 5


@pytest.mark.asyncio
async def test_handle_script_health_not_found():
    from handlers.script_handlers import handle_script_tool

    svc = MagicMock()
    svc.script_health = MagicMock(return_value=None)
    result = await handle_script_tool(
        "script_health",
        {"task_id": "nope"},
        svc,
    )
    data = json.loads(result[0].text)
    assert data["success"] is False
    assert data["code"] == "SCRIPT_NOT_FOUND"


@pytest.mark.asyncio
async def test_handle_script_list_passes_status():
    """script_list 处理器应透传 status 参数到 service"""
    from handlers.script_handlers import handle_script_tool

    svc = MagicMock()
    svc.script_list = MagicMock(return_value=[])
    await handle_script_tool(
        "script_list",
        {"limit": 50, "status": "deprecated"},
        svc,
    )
    svc.script_list.assert_called_once_with(limit=50, status="deprecated")
