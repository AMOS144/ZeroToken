"""页面状态摘要测试"""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_summarize_page_basic():
    from zerotoken.optimizers.state_summary import summarize_page

    mock_page = AsyncMock()
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Example Page")
    mock_page.evaluate = AsyncMock(side_effect=[
        [{"tag": "form", "id": "login", "fields": ["username", "password"]}],
        [{"text": "Home", "href": "/"}],
        [{"text": "Submit", "tag": "button"}],
        "This is the main content of the page.",
        42,
    ])
    result = await summarize_page(mock_page)
    assert result["url"] == "https://example.com"
    assert result["title"] == "Example Page"
    assert isinstance(result["forms"], list)
    assert isinstance(result["links"], list)
    assert isinstance(result["buttons"], list)
    assert result["interactive_elements"] == 42


@pytest.mark.asyncio
async def test_summarize_page_empty():
    from zerotoken.optimizers.state_summary import summarize_page

    mock_page = AsyncMock()
    mock_page.url = "about:blank"
    mock_page.title = AsyncMock(return_value="")
    mock_page.evaluate = AsyncMock(side_effect=[[], [], [], "", 0])
    result = await summarize_page(mock_page)
    assert result["url"] == "about:blank"
    assert result["forms"] == []


@pytest.mark.asyncio
async def test_summarize_page_error_resilient():
    from zerotoken.optimizers.state_summary import summarize_page

    mock_page = AsyncMock()
    mock_page.url = "https://error.com"
    mock_page.title = AsyncMock(side_effect=Exception("timeout"))
    mock_page.evaluate = AsyncMock(side_effect=Exception("timeout"))
    result = await summarize_page(mock_page)
    assert result["url"] == "https://error.com"
    assert result["title"] == ""
    assert result["forms"] == []
