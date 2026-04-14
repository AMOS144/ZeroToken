"""扩展交互动作测试：hover, right_click, double_click, drag_drop, scroll, keyboard, type_text"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_frame():
    return MagicMock()


@pytest.fixture
def mock_element():
    el = AsyncMock()
    el.scroll_into_view_if_needed = AsyncMock()
    el.hover = AsyncMock()
    el.click = AsyncMock()
    el.dblclick = AsyncMock()
    el.bounding_box = AsyncMock(return_value={"x": 10, "y": 10, "width": 50, "height": 50})
    el.evaluate = AsyncMock()
    return el


@pytest.mark.asyncio
async def test_hover_action(mock_frame, mock_element):
    from zerotoken.browser.actions.interact import hover_action
    result = await hover_action(mock_frame, mock_element, {})
    mock_element.hover.assert_awaited_once()
    assert result == {}


@pytest.mark.asyncio
async def test_right_click_action(mock_frame, mock_element):
    from zerotoken.browser.actions.interact import right_click_action
    result = await right_click_action(mock_frame, mock_element, {})
    mock_element.click.assert_awaited_once_with(button="right")
    assert result == {}


@pytest.mark.asyncio
async def test_double_click_action(mock_frame, mock_element):
    from zerotoken.browser.actions.interact import double_click_action
    result = await double_click_action(mock_frame, mock_element, {})
    mock_element.dblclick.assert_awaited_once()
    assert result == {}


@pytest.mark.asyncio
async def test_drag_drop_action(mock_frame, mock_element):
    from zerotoken.browser.actions.interact import drag_drop_action

    target_el = AsyncMock()
    target_el.bounding_box = AsyncMock(return_value={"x": 200, "y": 200, "width": 50, "height": 50})
    mock_frame.wait_for_selector = AsyncMock(return_value=target_el)
    mock_frame.mouse = AsyncMock()
    mock_frame.mouse.move = AsyncMock()
    mock_frame.mouse.down = AsyncMock()
    mock_frame.mouse.up = AsyncMock()

    result = await drag_drop_action(mock_frame, mock_element, {"target": "#drop-zone"})
    assert result["target"] == "#drop-zone"
    mock_frame.mouse.down.assert_awaited_once()
    mock_frame.mouse.up.assert_awaited_once()


@pytest.mark.asyncio
async def test_scroll_action_down(mock_frame, mock_element):
    from zerotoken.browser.actions.interact import scroll_action

    mock_frame.evaluate = AsyncMock()
    result = await scroll_action(mock_frame, None, {"direction": "down", "amount": 300})
    assert result["direction"] == "down"
    assert result["amount"] == 300
    mock_frame.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_scroll_action_element(mock_frame, mock_element):
    from zerotoken.browser.actions.interact import scroll_action

    mock_element.evaluate = AsyncMock()
    result = await scroll_action(mock_frame, mock_element, {"direction": "up", "amount": 200})
    assert result["direction"] == "up"
    mock_element.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_keyboard_action(mock_frame, mock_element):
    from zerotoken.browser.actions.interact import keyboard_action

    mock_frame.keyboard = AsyncMock()
    mock_frame.keyboard.press = AsyncMock()
    result = await keyboard_action(mock_frame, None, {"key": "Enter"})
    assert result["key"] == "Enter"
    mock_frame.keyboard.press.assert_awaited_once_with("Enter")


@pytest.mark.asyncio
async def test_keyboard_action_combo(mock_frame, mock_element):
    from zerotoken.browser.actions.interact import keyboard_action

    mock_frame.keyboard = AsyncMock()
    mock_frame.keyboard.press = AsyncMock()
    result = await keyboard_action(mock_frame, None, {"key": "Control+A"})
    assert result["key"] == "Control+A"


@pytest.mark.asyncio
async def test_type_text_action(mock_frame, mock_element):
    from zerotoken.browser.actions.interact import type_text_action

    mock_frame.keyboard = AsyncMock()
    mock_frame.keyboard.type = AsyncMock()
    result = await type_text_action(mock_frame, None, {"text": "hello", "delay": 30})
    assert result["text"] == "hello"
    mock_frame.keyboard.type.assert_awaited_once_with("hello", delay=30)
