"""BrowserService 扩展方法测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_pipeline():
    pipeline = AsyncMock()
    record = MagicMock()
    record.result = MagicMock()
    record.result.success = True
    pipeline.execute = AsyncMock(return_value=record)
    return pipeline


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    mp = MagicMock()
    mp.page = MagicMock()
    mp.page.url = "https://example.com"
    mp.active_frame = MagicMock()
    mp.tab_id = 0
    ctx.active_page = mp
    ctx._pages = {0: mp}
    ctx.new_tab = AsyncMock(return_value=MagicMock(tab_id=1, page=MagicMock(url="about:blank")))
    ctx.switch_tab = AsyncMock(return_value=mp)
    ctx.close_tab = AsyncMock()
    ctx.list_tabs_sync = MagicMock(return_value=[{"tab_id": 0}])
    ctx.enter_iframe = MagicMock()
    ctx.exit_iframe = MagicMock()
    return ctx


@pytest.fixture
def browser_service(mock_pipeline, mock_context):
    from zerotoken.services.browser_service import BrowserService
    svc = BrowserService.__new__(BrowserService)
    svc._context = mock_context
    svc._stability = MagicMock()
    svc._pipeline = mock_pipeline
    return svc


@pytest.mark.asyncio
async def test_hover(browser_service, mock_pipeline):
    await browser_service.hover("#btn")
    call_args = mock_pipeline.execute.call_args
    assert call_args.args[0].value == "hover"


@pytest.mark.asyncio
async def test_right_click(browser_service, mock_pipeline):
    await browser_service.right_click("#menu")
    assert mock_pipeline.execute.call_args.args[0].value == "right_click"


@pytest.mark.asyncio
async def test_double_click(browser_service, mock_pipeline):
    await browser_service.double_click("#item")
    assert mock_pipeline.execute.call_args.args[0].value == "double_click"


@pytest.mark.asyncio
async def test_keyboard(browser_service, mock_pipeline):
    await browser_service.keyboard("Enter")
    call_args = mock_pipeline.execute.call_args
    assert call_args.args[0].value == "keyboard"
    assert call_args.args[1]["key"] == "Enter"


@pytest.mark.asyncio
async def test_type_text(browser_service, mock_pipeline):
    await browser_service.type_text("hello")
    assert mock_pipeline.execute.call_args.args[0].value == "type_text"


@pytest.mark.asyncio
async def test_drag_drop(browser_service, mock_pipeline):
    await browser_service.drag_drop("#src", "#dst")
    assert mock_pipeline.execute.call_args.args[0].value == "drag_drop"


@pytest.mark.asyncio
async def test_scroll(browser_service, mock_pipeline):
    await browser_service.scroll(direction="down", amount=500)
    assert mock_pipeline.execute.call_args.args[0].value == "scroll"


@pytest.mark.asyncio
async def test_new_tab(browser_service, mock_pipeline):
    await browser_service.new_tab(url="https://example.com")
    assert mock_pipeline.execute.call_args.args[0].value == "new_tab"


@pytest.mark.asyncio
async def test_switch_tab(browser_service, mock_pipeline):
    await browser_service.switch_tab(1)
    assert mock_pipeline.execute.call_args.args[0].value == "switch_tab"


@pytest.mark.asyncio
async def test_close_tab(browser_service, mock_pipeline):
    await browser_service.close_tab(0)
    assert mock_pipeline.execute.call_args.args[0].value == "close_tab"


@pytest.mark.asyncio
async def test_list_tabs(browser_service, mock_pipeline):
    await browser_service.list_tabs()
    assert mock_pipeline.execute.call_args.args[0].value == "list_tabs"


@pytest.mark.asyncio
async def test_enter_iframe(browser_service, mock_pipeline):
    await browser_service.enter_iframe("#frame")
    assert mock_pipeline.execute.call_args.args[0].value == "enter_iframe"


@pytest.mark.asyncio
async def test_exit_iframe(browser_service, mock_pipeline):
    await browser_service.exit_iframe()
    assert mock_pipeline.execute.call_args.args[0].value == "exit_iframe"


@pytest.mark.asyncio
async def test_upload(browser_service, mock_pipeline):
    await browser_service.upload("#file-input", "/tmp/test.txt")
    assert mock_pipeline.execute.call_args.args[0].value == "file_upload"


@pytest.mark.asyncio
async def test_download(browser_service, mock_pipeline):
    await browser_service.download("#dl-btn")
    assert mock_pipeline.execute.call_args.args[0].value == "file_download"


@pytest.mark.asyncio
async def test_evaluate(browser_service, mock_pipeline):
    await browser_service.evaluate("document.title")
    assert mock_pipeline.execute.call_args.args[0].value == "evaluate"
