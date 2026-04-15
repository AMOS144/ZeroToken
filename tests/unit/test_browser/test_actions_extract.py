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
async def test_screenshot_action_success():
    """正常截图应返回 base64 数据"""
    from zerotoken.browser.actions.extract import screenshot_action

    mock_frame = AsyncMock()
    mock_frame.screenshot = AsyncMock(return_value=b"fake-png-data")
    result = await screenshot_action(mock_frame, None, {})
    assert result["screenshot"] is not None
    assert result.get("degraded") is not True


@pytest.mark.asyncio
async def test_screenshot_action_timeout_degrades():
    """正常截图超时应降级为 animations=disabled"""
    import asyncio
    from zerotoken.browser.actions.extract import screenshot_action

    call_args_list = []

    async def slow_then_fast(**kwargs):
        call_args_list.append(kwargs)
        if "animations" not in kwargs:
            await asyncio.sleep(100)
        return b"degraded-png-data"

    mock_frame = AsyncMock()
    mock_frame.screenshot = slow_then_fast

    result = await screenshot_action(mock_frame, None, {"timeout": 100})
    assert result["degraded"] is True
    assert result["screenshot"] is not None


@pytest.mark.asyncio
async def test_screenshot_action_all_fail_returns_none():
    """正常和降级截图都失败时应返回 None 而不是抛异常"""
    import asyncio
    from zerotoken.browser.actions.extract import screenshot_action

    async def always_slow(**kwargs):
        await asyncio.sleep(100)
        return b"data"

    mock_frame = AsyncMock()
    mock_frame.screenshot = always_slow

    result = await screenshot_action(mock_frame, None, {"timeout": 50})
    assert result["screenshot"] is None
    assert result["degraded"] is True
    assert "error" in result
