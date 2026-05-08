"""Extract actions 单元测试"""

import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_get_text_action():
    from zerotoken.browser.actions.extract import get_text_action

    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value="  Hello World  ")
    result = await get_text_action(AsyncMock(), mock_element, {"attribute": "text"})
    assert result["value"] == "Hello World"


@pytest.mark.asyncio
async def test_get_html_action_with_selector():
    from zerotoken.browser.actions.extract import get_html_action

    mock_element = AsyncMock()
    mock_element.inner_html = AsyncMock(return_value="<span>hi</span>")
    result = await get_html_action(AsyncMock(), mock_element, {"selector": "#box"})
    assert result["html"] == "<span>hi</span>"


@pytest.mark.asyncio
async def test_get_html_action_full_page():
    from zerotoken.browser.actions.extract import get_html_action

    mock_frame = AsyncMock()
    mock_frame.content = AsyncMock(return_value="<html>full</html>")
    result = await get_html_action(mock_frame, None, {})
    assert result["html"] == "<html>full</html>"


@pytest.mark.asyncio
async def test_screenshot_action_cdp_default():
    """默认截图应走 CDP，返回 base64 数据"""
    import base64
    from zerotoken.browser.actions.extract import screenshot_action

    fake_b64 = base64.b64encode(b"cdp-png").decode()
    mock_cdp = AsyncMock()
    mock_cdp.send = AsyncMock(return_value={"data": fake_b64})
    mock_cdp.detach = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    mock_frame = AsyncMock()
    mock_frame.context = mock_context

    result = await screenshot_action(mock_frame, None, {})
    assert result["screenshot"] == fake_b64
    mock_cdp.send.assert_called_once()


@pytest.mark.asyncio
async def test_screenshot_action_element_uses_playwright():
    """元素截图应走 Playwright 而非 CDP"""
    from zerotoken.browser.actions.extract import screenshot_action

    mock_element = AsyncMock()
    mock_element.screenshot = AsyncMock(return_value=b"element-png")

    result = await screenshot_action(AsyncMock(), mock_element, {})
    assert result["screenshot"] is not None
    mock_element.screenshot.assert_called_once()


@pytest.mark.asyncio
async def test_screenshot_action_all_fail_returns_none():
    """CDP 也失败时应返回 None 而不是抛异常"""
    from zerotoken.browser.actions.extract import screenshot_action

    mock_frame = AsyncMock()
    mock_frame.context = AsyncMock()
    mock_frame.context.new_cdp_session = AsyncMock(side_effect=Exception("no cdp"))

    result = await screenshot_action(mock_frame, None, {"timeout": 50})
    assert result["screenshot"] is None
    assert result["degraded"] is True
    assert "error" in result
