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
    mock_frame.wait_for_selector.assert_called_once_with("#btn", state="visible", timeout=5000)
    assert result["condition"] == "selector"


@pytest.mark.asyncio
async def test_wait_for_action_passes_state():
    """state 参数应透传给 wait_for_selector"""
    from zerotoken.browser.actions.navigate import wait_for_action

    mock_frame = AsyncMock()
    result = await wait_for_action(mock_frame, None, {
        "condition": "selector", "value": "#box",
        "timeout": 5000, "state": "attached",
    })
    mock_frame.wait_for_selector.assert_called_once_with(
        "#box", state="attached", timeout=5000,
    )
    assert result["state"] == "attached"


@pytest.mark.asyncio
async def test_wait_for_action_degrades_visible_to_attached():
    """visible 超时但 attached 成功时应降级并标记 degraded"""
    from playwright.async_api import TimeoutError as PwTimeout
    from zerotoken.browser.actions.navigate import wait_for_action

    mock_frame = AsyncMock()
    call_count = 0

    async def side_effect(selector, state="visible", timeout=30000):
        nonlocal call_count
        call_count += 1
        if state == "visible":
            raise PwTimeout("timeout")

    mock_frame.wait_for_selector = AsyncMock(side_effect=side_effect)
    result = await wait_for_action(mock_frame, None, {
        "condition": "selector", "value": ".card", "timeout": 10000,
    })
    assert result["degraded"] is True
    assert result["state"] == "attached"
    assert call_count == 2


@pytest.mark.asyncio
async def test_wait_for_action_no_degrade_if_attached_also_fails():
    """visible 和 attached 都超时时应抛原始异常"""
    from playwright.async_api import TimeoutError as PwTimeout
    from zerotoken.browser.actions.navigate import wait_for_action

    mock_frame = AsyncMock()
    mock_frame.wait_for_selector = AsyncMock(side_effect=PwTimeout("timeout"))

    with pytest.raises(PwTimeout):
        await wait_for_action(mock_frame, None, {
            "condition": "selector", "value": ".gone", "timeout": 4000,
        })


@pytest.mark.asyncio
async def test_wait_for_action_no_degrade_when_state_explicit():
    """显式传 state=attached 超时时不做二次降级"""
    from playwright.async_api import TimeoutError as PwTimeout
    from zerotoken.browser.actions.navigate import wait_for_action

    mock_frame = AsyncMock()
    mock_frame.wait_for_selector = AsyncMock(side_effect=PwTimeout("timeout"))

    with pytest.raises(PwTimeout):
        await wait_for_action(mock_frame, None, {
            "condition": "selector", "value": ".x",
            "timeout": 4000, "state": "attached",
        })
