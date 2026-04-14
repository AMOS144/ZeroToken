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
