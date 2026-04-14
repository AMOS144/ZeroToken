"""文件操作动作测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_frame():
    return AsyncMock()


@pytest.fixture
def mock_element():
    el = AsyncMock()
    el.set_input_files = AsyncMock()
    return el


@pytest.mark.asyncio
async def test_upload_action(mock_frame, mock_element):
    from zerotoken.browser.actions.file_ops import upload_action
    result = await upload_action(mock_frame, mock_element, {"path": "/tmp/test.txt"})
    assert result["uploaded"] == ["/tmp/test.txt"]
    mock_element.set_input_files.assert_awaited_once_with("/tmp/test.txt")


@pytest.mark.asyncio
async def test_upload_action_multiple(mock_frame, mock_element):
    from zerotoken.browser.actions.file_ops import upload_action
    result = await upload_action(mock_frame, mock_element, {"path": ["/tmp/a.txt", "/tmp/b.txt"]})
    assert result["uploaded"] == ["/tmp/a.txt", "/tmp/b.txt"]
    mock_element.set_input_files.assert_awaited_once_with(["/tmp/a.txt", "/tmp/b.txt"])


@pytest.mark.asyncio
async def test_download_action(mock_frame, mock_element):
    from zerotoken.browser.actions.file_ops import download_action

    mock_download = AsyncMock()
    mock_download.path = AsyncMock(return_value="/tmp/downloads/file.pdf")
    mock_download.suggested_filename = "file.pdf"
    mock_download.url = "https://example.com/file.pdf"

    mock_page = AsyncMock()

    class FakeCtxManager:
        async def __aenter__(self):
            # Playwright：下载在 download_info.value 协程中
            info = MagicMock()

            async def _value():
                return mock_download

            info.value = _value()
            return info

        async def __aexit__(self, *args):
            pass

    mock_page.expect_download = MagicMock(return_value=FakeCtxManager())

    result = await download_action(mock_page, mock_element, {"selector": "#download-btn"})
    assert result["filename"] == "file.pdf"
    assert result["url"] == "https://example.com/file.pdf"
