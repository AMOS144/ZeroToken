"""浏览器 handler 扩展分发测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_record():
    r = MagicMock()
    r.model_dump = MagicMock(return_value={
        "step": 1, "action": "test", "params": {},
        "result": {"success": True, "data": {}},
        "page_state": {"url": "https://example.com", "title": "Test"},
        "screenshot": None,
    })
    return r


@pytest.fixture
def mock_svc():
    svc = AsyncMock()
    record = _make_record()
    for method_name in [
        "hover", "right_click", "double_click", "drag_drop", "scroll",
        "keyboard", "type_text", "new_tab", "switch_tab", "close_tab",
        "list_tabs", "enter_iframe", "exit_iframe", "upload", "download", "evaluate",
    ]:
        setattr(svc, method_name, AsyncMock(return_value=record))
    return svc


@pytest.fixture
def mock_traj():
    t = MagicMock()
    t.record_operation = MagicMock()
    return t


@pytest.mark.asyncio
async def test_dispatch_hover(mock_svc, mock_traj):
    from handlers.browser_handlers import handle_browser_tool
    await handle_browser_tool("browser_hover", {"selector": "#btn"}, mock_svc, mock_traj)
    mock_svc.hover.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_keyboard(mock_svc, mock_traj):
    from handlers.browser_handlers import handle_browser_tool
    await handle_browser_tool("browser_keyboard", {"key": "Enter"}, mock_svc, mock_traj)
    mock_svc.keyboard.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_scroll(mock_svc, mock_traj):
    from handlers.browser_handlers import handle_browser_tool
    await handle_browser_tool("browser_scroll", {"direction": "down"}, mock_svc, mock_traj)
    mock_svc.scroll.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_new_tab(mock_svc, mock_traj):
    from handlers.browser_handlers import handle_browser_tool
    await handle_browser_tool("browser_new_tab", {}, mock_svc, mock_traj)
    mock_svc.new_tab.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_enter_iframe(mock_svc, mock_traj):
    from handlers.browser_handlers import handle_browser_tool
    await handle_browser_tool("browser_enter_iframe", {"selector": "#frame"}, mock_svc, mock_traj)
    mock_svc.enter_iframe.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_upload(mock_svc, mock_traj):
    from handlers.browser_handlers import handle_browser_tool
    await handle_browser_tool("browser_upload", {"selector": "#file", "path": "/tmp/f.txt"}, mock_svc, mock_traj)
    mock_svc.upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_evaluate(mock_svc, mock_traj):
    from handlers.browser_handlers import handle_browser_tool
    await handle_browser_tool("browser_evaluate", {"expression": "1+1"}, mock_svc, mock_traj)
    mock_svc.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_download(mock_svc, mock_traj):
    from handlers.browser_handlers import handle_browser_tool
    await handle_browser_tool("browser_download", {"selector": "#dl"}, mock_svc, mock_traj)
    mock_svc.download.assert_awaited_once()
