"""evaluate 动作测试"""
import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_frame():
    frame = AsyncMock()
    frame.evaluate = AsyncMock(return_value=42)
    return frame


@pytest.mark.asyncio
async def test_evaluate_action_basic(mock_frame):
    from zerotoken.browser.actions.extract import evaluate_action
    result = await evaluate_action(mock_frame, None, {"expression": "1 + 1"})
    assert result["value"] == 42
    mock_frame.evaluate.assert_awaited_once_with("1 + 1")


@pytest.mark.asyncio
async def test_evaluate_action_no_return(mock_frame):
    from zerotoken.browser.actions.extract import evaluate_action
    mock_frame.evaluate = AsyncMock(return_value=None)
    result = await evaluate_action(mock_frame, None, {
        "expression": "document.title = 'test'",
        "return_value": False,
    })
    assert result["value"] is None
