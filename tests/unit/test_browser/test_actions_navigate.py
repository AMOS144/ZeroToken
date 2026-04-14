"""Navigate actions 单元测试"""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_open_action():
    from zerotoken.browser.actions.navigate import open_action

    mock_frame = AsyncMock()
    result = await open_action(mock_frame, None, {"url": "https://example.com", "wait_until": "networkidle"})
    mock_frame.goto.assert_called_once_with("https://example.com", wait_until="networkidle", timeout=30000)
    assert result["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_wait_for_action_selector():
    from zerotoken.browser.actions.navigate import wait_for_action

    mock_frame = AsyncMock()
    result = await wait_for_action(mock_frame, None, {"condition": "selector", "value": "#btn", "timeout": 5000})
    mock_frame.wait_for_selector.assert_called_once_with("#btn", timeout=5000)
    assert result["condition"] == "selector"
