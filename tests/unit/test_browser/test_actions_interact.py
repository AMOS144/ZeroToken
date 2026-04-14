"""Interact actions 单元测试"""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_click_action():
    from zerotoken.browser.actions.interact import click_action

    mock_frame = AsyncMock()
    mock_frame.url = "https://example.com"
    mock_element = AsyncMock()
    result = await click_action(mock_frame, mock_element, {"scroll_into_view": True, "wait_after": 0})
    mock_element.scroll_into_view_if_needed.assert_called_once()
    mock_element.click.assert_called_once()
    assert "navigated" in result


@pytest.mark.asyncio
async def test_input_action():
    from zerotoken.browser.actions.interact import input_action

    mock_frame = AsyncMock()
    mock_element = AsyncMock()
    mock_element.evaluate = AsyncMock(return_value="hello")
    result = await input_action(mock_frame, mock_element, {"text": "hello", "delay": 50, "clear_first": True})
    mock_element.fill.assert_called_once_with("")
    mock_element.type.assert_called_once_with("hello", delay=50)
    assert result["text"] == "hello"
    assert result["actual_value"] == "hello"
