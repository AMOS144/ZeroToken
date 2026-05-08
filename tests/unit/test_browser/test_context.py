"""BrowserContextManager 单元测试（Mock Playwright）"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_playwright():
    """构建完整的 Playwright mock 链"""
    mock_page = AsyncMock()
    mock_page.url = "about:blank"
    mock_page.title = AsyncMock(return_value="")
    mock_page.close = AsyncMock()
    mock_page.bring_to_front = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.frame_locator = MagicMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_browser.is_connected = MagicMock(return_value=True)

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw = AsyncMock()
    mock_pw.chromium = mock_chromium

    return mock_pw, mock_browser, mock_context, mock_page


@pytest.mark.asyncio
async def test_start_creates_page(mock_playwright):
    """start() 启动浏览器后应创建第一个标签页，tab_id=0"""
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager

        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        assert mgr.active_page is not None
        assert mgr.active_page.tab_id == 0


@pytest.mark.asyncio
async def test_new_tab(mock_playwright):
    """new_tab() 应创建新标签页，tab_id 递增"""
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager

        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        tab = await mgr.new_tab()
        assert tab.tab_id == 1
        assert len(mgr.list_tabs_sync()) == 2


@pytest.mark.asyncio
async def test_switch_tab(mock_playwright):
    """switch_tab() 切换后 active_page 应指向目标标签页"""
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager

        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        await mgr.new_tab()
        assert mgr.active_page.tab_id == 0
        await mgr.switch_tab(1)
        assert mgr.active_page.tab_id == 1


@pytest.mark.asyncio
async def test_switch_tab_invalid(mock_playwright):
    """switch_tab() 传入不存在的 tab_id 应抛出 ValueError，并显示可用 tab 列表"""
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager

        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        with pytest.raises(ValueError, match=r"Tab 99 not found.*Available tabs.*\[0\]"):
            await mgr.switch_tab(99)


@pytest.mark.asyncio
async def test_close_tab_invalid_shows_available(mock_playwright):
    """close_tab() 传入不存在的 tab_id 应在错误信息中列出可用 tab"""
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager

        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        with pytest.raises(ValueError, match=r"Tab 99 not found.*Available tabs.*\[0\]"):
            await mgr.close_tab(99)


@pytest.mark.asyncio
async def test_enter_exit_iframe(mock_playwright):
    """enter_iframe/exit_iframe 应正确管理 iframe 栈"""
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    mock_frame = MagicMock()
    mock_page.frame_locator = MagicMock(return_value=mock_frame)
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager

        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        mp = mgr.active_page
        assert mp.active_frame == mock_page
        mgr.enter_iframe("#myframe")
        assert mp.active_frame == mock_frame
        mgr.exit_iframe()
        assert mp.active_frame == mock_page


@pytest.mark.asyncio
async def test_stop(mock_playwright):
    """stop() 应关闭所有标签页和浏览器"""
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager

        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        await mgr.stop()
        mock_page.close.assert_called()
        mock_browser.close.assert_called()
