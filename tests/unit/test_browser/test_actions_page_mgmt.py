"""页面管理动作测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_context():
    ctx = AsyncMock()
    mp = MagicMock()
    mp.tab_id = 1
    mp.page = MagicMock()
    mp.page.url = "https://example.com"
    ctx.new_tab = AsyncMock(return_value=mp)
    ctx.switch_tab = AsyncMock(return_value=mp)
    ctx.close_tab = AsyncMock()
    ctx.list_tabs_sync = MagicMock(return_value=[
        {"tab_id": 0, "url": "about:blank", "active": False},
        {"tab_id": 1, "url": "https://example.com", "active": True},
    ])
    return ctx


@pytest.mark.asyncio
async def test_new_tab_action(mock_context):
    from zerotoken.browser.actions.page_mgmt import new_tab_action
    result = await new_tab_action(mock_context, None, {"url": "https://example.com"})
    assert result["tab_id"] == 1
    mock_context.new_tab.assert_awaited_once_with(url="https://example.com")


@pytest.mark.asyncio
async def test_switch_tab_action(mock_context):
    from zerotoken.browser.actions.page_mgmt import switch_tab_action
    result = await switch_tab_action(mock_context, None, {"tab_id": 1})
    assert result["tab_id"] == 1
    mock_context.switch_tab.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_close_tab_action(mock_context):
    from zerotoken.browser.actions.page_mgmt import close_tab_action
    result = await close_tab_action(mock_context, None, {"tab_id": 0})
    assert result["closed_tab_id"] == 0
    mock_context.close_tab.assert_awaited_once_with(0)


@pytest.mark.asyncio
async def test_list_tabs_action(mock_context):
    from zerotoken.browser.actions.page_mgmt import list_tabs_action
    result = await list_tabs_action(mock_context, None, {})
    assert len(result["tabs"]) == 2
    assert result["tabs"][1]["url"] == "https://example.com"
