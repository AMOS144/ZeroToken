"""iframe 动作测试"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.enter_iframe = MagicMock()
    ctx.exit_iframe = MagicMock()
    return ctx


@pytest.mark.asyncio
async def test_enter_iframe_action(mock_context):
    from zerotoken.browser.actions.iframe import enter_iframe_action
    result = await enter_iframe_action(mock_context, None, {"selector": "#my-iframe"})
    assert result["selector"] == "#my-iframe"
    mock_context.enter_iframe.assert_called_once_with("#my-iframe")


@pytest.mark.asyncio
async def test_exit_iframe_action(mock_context):
    from zerotoken.browser.actions.iframe import exit_iframe_action
    result = await exit_iframe_action(mock_context, None, {})
    assert result["exit_all"] is False
    mock_context.exit_iframe.assert_called_once_with(exit_all=False)


@pytest.mark.asyncio
async def test_exit_iframe_all(mock_context):
    from zerotoken.browser.actions.iframe import exit_iframe_action
    result = await exit_iframe_action(mock_context, None, {"all": True})
    assert result["exit_all"] is True
    mock_context.exit_iframe.assert_called_once_with(exit_all=True)
