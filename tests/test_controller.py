"""
Test BrowserController - Test browser operation capabilities.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from zerotoken.controller import BrowserController, PageState, OperationRecord


class TestPageState:
    """Test PageState class."""

    def test_create_page_state(self):
        """Test creating PageState."""
        state = PageState(url="https://example.com", title="Example")
        assert state.url == "https://example.com"
        assert state.title == "Example"
        assert state.html is None
        assert state.timestamp is not None

    def test_create_page_state_with_html(self):
        """Test creating PageState with HTML."""
        state = PageState(
            url="https://example.com", title="Example", html="<html><body>Test</body></html>"
        )
        assert state.html == "<html><body>Test</body></html>"

    def test_to_dict(self):
        """Test converting PageState to dict."""
        state = PageState(url="https://example.com", title="Example")
        result = state.to_dict()
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"
        assert "timestamp" in result


class TestOperationRecord:
    """Test OperationRecord class."""

    def test_create_operation_record(self):
        """Test creating OperationRecord."""
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="click",
            params={"selector": "#button"},
            result={"success": True},
            page_state=page_state,
        )
        assert record.step == 1
        assert record.action == "click"
        assert record.params == {"selector": "#button"}
        assert record.result == {"success": True}
        assert record.error is None

    def test_create_operation_record_with_screenshot(self):
        """Test creating OperationRecord with screenshot."""
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="click",
            params={"selector": "#button"},
            result={"success": True},
            page_state=page_state,
            screenshot="base64_data",
        )
        assert record.screenshot == "base64_data"

    def test_create_operation_record_with_error(self):
        """Test creating OperationRecord with error."""
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="click",
            params={"selector": "#button"},
            result={"success": False},
            page_state=page_state,
            error="Element not found",
        )
        assert record.error == "Element not found"

    def test_to_dict(self):
        """Test converting OperationRecord to dict."""
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="click",
            params={"selector": "#button"},
            result={"success": True},
            page_state=page_state,
            screenshot="base64_data",
        )
        result = record.to_dict()
        assert result["step"] == 1
        assert result["action"] == "click"
        assert result["params"] == {"selector": "#button"}
        assert result["page_state"]["url"] == "https://example.com"
        assert result["screenshot"] == "base64_data"

    def test_to_dict_without_screenshot(self):
        """Test converting OperationRecord without screenshot."""
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="click",
            params={"selector": "#button"},
            result={"success": True},
            page_state=page_state,
        )
        result = record.to_dict()
        assert "screenshot" not in result


class TestBrowserController:
    """Test BrowserController class."""

    @pytest.fixture
    def controller(self):
        """Create controller instance."""
        # Reset singleton
        BrowserController._instance = None
        BrowserController._browser = None
        BrowserController._context = None
        BrowserController._page = None
        return BrowserController()

    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """Test singleton pattern."""
        BrowserController._instance = None
        c1 = BrowserController()
        c2 = BrowserController()
        assert c1 is c2

    @pytest.mark.asyncio
    async def test_start(self, controller):
        """Test starting browser."""
        # Mock async_playwright function
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        mock_chromium = AsyncMock()
        mock_playwright = AsyncMock()

        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_playwright.chromium = mock_chromium

        async def mock_start():
            return mock_playwright

        with patch("zerotoken.controller.async_playwright") as mock_cls:
            mock_cls.return_value.start = mock_start

            await controller.start(headless=True)

            assert controller._page is mock_page
            assert controller._browser is mock_browser

    @pytest.mark.asyncio
    async def test_start_stealth_mode(self, controller):
        """Test start with stealth=True uses stealth args and adds init script."""
        from zerotoken.stealth import STEALTH_LAUNCH_ARGS, STEALTH_INIT_SCRIPT

        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.add_init_script = AsyncMock()
        mock_browser = AsyncMock()
        mock_chromium = AsyncMock()
        mock_playwright = AsyncMock()

        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_playwright.chromium = mock_chromium

        async def mock_start():
            return mock_playwright

        with patch("zerotoken.controller.async_playwright") as mock_cls:
            mock_cls.return_value.start = mock_start

            await controller.start(headless=True, stealth=True)

            assert controller._page is mock_page
            assert controller._browser is mock_browser
            mock_chromium.launch.assert_called_once()
            call_kw = mock_chromium.launch.call_args[1]
            assert call_kw.get("args") == STEALTH_LAUNCH_ARGS
            mock_context.add_init_script.assert_called_once_with(STEALTH_INIT_SCRIPT)

    @pytest.mark.asyncio
    async def test_stop(self, controller):
        """Test stopping browser."""
        controller._page = AsyncMock()
        controller._context = AsyncMock()
        controller._browser = AsyncMock()
        page_mock = controller._page
        context_mock = controller._context
        browser_mock = controller._browser

        await controller.stop()

        page_mock.close.assert_called_once()
        context_mock.close.assert_called_once()
        browser_mock.close.assert_called_once()
        assert controller._page is None
        assert controller._context is None
        assert controller._browser is None

    def test_page_property(self, controller):
        """Test page property raises if not started."""
        controller._page = None
        with pytest.raises(RuntimeError, match="Browser not started"):
            _ = controller.page

    def test_page_property_returns_page(self, controller):
        """Test page property returns page."""
        mock_page = MagicMock()
        controller._page = mock_page
        assert controller.page is mock_page

    @pytest.mark.asyncio
    async def test_open_success(self, controller):
        """Test open URL success."""
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title = AsyncMock(return_value="Example")
        controller._page.goto = AsyncMock(return_value=None)
        controller._page.wait_for_load_state = AsyncMock(return_value=None)
        controller._page.screenshot = AsyncMock(return_value=b"screenshot")

        record = await controller.open("https://example.com")

        assert isinstance(record, OperationRecord)
        assert record.action == "open"
        assert record.params["url"] == "https://example.com"
        assert record.result["success"] is True

    @pytest.mark.asyncio
    async def test_open_error(self, controller):
        """Test open URL error."""
        controller._page = AsyncMock()
        controller._page.goto.side_effect = Exception("Network error")
        controller._page.url = "about:blank"
        controller._page.title.return_value = ""

        record = await controller.open("https://invalid-url")

        assert isinstance(record, OperationRecord)
        assert record.action == "open"
        assert record.result["success"] is False
        assert record.error is not None

    @pytest.mark.asyncio
    async def test_click_success(self, controller):
        """Test click element success."""
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title = AsyncMock(return_value="Example")
        controller._page.wait_for_selector = AsyncMock(return_value=True)
        controller._page.click = AsyncMock(return_value=None)
        controller._page.wait_for_load_state = AsyncMock(return_value=None)
        controller._page.screenshot = AsyncMock(return_value=b"screenshot")

        mock_locator = AsyncMock()
        mock_locator.scroll_into_view_if_needed = AsyncMock(return_value=None)
        # locator() 应该返回 mock_locator，无论传入什么 selector
        controller._page.locator = MagicMock(return_value=mock_locator)

        # Mock _take_screenshot and _get_page_state
        controller._take_screenshot = AsyncMock(return_value="base64_data")
        controller._get_page_state = AsyncMock(
            return_value=PageState(url="https://example.com", title="Example")
        )
        controller._wait_for_stable_state = AsyncMock(return_value=None)

        record = await controller.click("#button")

        assert isinstance(record, OperationRecord)
        assert record.action == "click"
        assert record.params["selector"] == "#button"
        assert record.result["success"] is True

    @pytest.mark.asyncio
    async def test_click_error(self, controller):
        """Test click element error."""
        controller._page = AsyncMock()
        controller._page.wait_for_selector.side_effect = Exception("Timeout")
        controller._page.url = "https://example.com"
        controller._page.title.return_value = "Example"

        record = await controller.click("#nonexistent")

        assert isinstance(record, OperationRecord)
        assert record.action == "click"
        assert record.result["success"] is False
        assert record.error is not None

    @pytest.mark.asyncio
    async def test_input_success(self, controller):
        """Test input text success."""
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title = AsyncMock(return_value="Example")
        controller._page.wait_for_selector = AsyncMock(return_value=True)
        controller._page.type = AsyncMock(return_value=None)
        controller._page.input_value = AsyncMock(return_value="test input")
        controller._page.wait_for_load_state = AsyncMock(return_value=None)
        controller._page.screenshot = AsyncMock(return_value=b"screenshot")

        mock_locator = AsyncMock()
        mock_locator.clear = AsyncMock(return_value=None)
        # locator() 应该返回 mock_locator，无论传入什么 selector
        controller._page.locator = MagicMock(return_value=mock_locator)

        # Mock _take_screenshot and _get_page_state
        controller._take_screenshot = AsyncMock(return_value="base64_data")
        controller._get_page_state = AsyncMock(
            return_value=PageState(url="https://example.com", title="Example")
        )
        controller._wait_for_stable_state = AsyncMock(return_value=None)

        record = await controller.input("#input", "test input")

        assert isinstance(record, OperationRecord)
        assert record.action == "input"
        assert record.params["selector"] == "#input"
        assert record.params["text"] == "test input"
        assert record.result["success"] is True

    @pytest.mark.asyncio
    async def test_get_text_success(self, controller):
        """Test get text success."""
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title.return_value = "Example"

        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Hello World"
        controller._page.wait_for_selector.return_value = mock_element

        record = await controller.get_text("#element")

        assert isinstance(record, OperationRecord)
        assert record.action == "get_text"
        assert record.result["success"] is True
        assert record.result["value"] == "Hello World"

    @pytest.mark.asyncio
    async def test_get_html_success(self, controller):
        """Test get HTML success."""
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title.return_value = "Example"
        controller._page.content.return_value = "<html><body>Test</body></html>"

        record = await controller.get_html()

        assert isinstance(record, OperationRecord)
        assert record.action == "get_html"
        assert record.result["success"] is True
        assert "<html>" in record.result["html"]

    @pytest.mark.asyncio
    async def test_screenshot_success(self, controller):
        """Test screenshot success."""
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title.return_value = "Example"
        controller._page.screenshot.return_value = b"image_data"

        record = await controller.screenshot()

        assert isinstance(record, OperationRecord)
        assert record.action == "screenshot"
        assert record.result["success"] is True
        assert record.screenshot is not None

    @pytest.mark.asyncio
    async def test_wait_for_selector(self, controller):
        """Test wait for selector."""
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title.return_value = "Example"
        controller._page.wait_for_selector.return_value = True
        controller._page.screenshot.return_value = b"image"

        record = await controller.wait_for("selector", "#element")

        assert isinstance(record, OperationRecord)
        assert record.action == "wait_for"
        assert record.params["condition"] == "selector"
        assert record.result["success"] is True

    @pytest.mark.asyncio
    async def test_wait_for_url(self, controller):
        """Test wait for URL."""
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title.return_value = "Example"
        controller._page.wait_for_url.return_value = None
        controller._page.screenshot.return_value = b"image"

        record = await controller.wait_for("url", "https://example.com")

        assert isinstance(record, OperationRecord)
        assert record.action == "wait_for"
        assert record.params["condition"] == "url"
        assert record.result["success"] is True

    @pytest.mark.asyncio
    async def test_extract_data(self, controller):
        """Test extract structured data."""
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title.return_value = "Example"
        controller._page.screenshot.return_value = b"image"

        mock_element = AsyncMock()
        mock_element.text_content.return_value = "$100.00"
        controller._page.wait_for_selector.return_value = mock_element

        schema = {"fields": [{"name": "price", "selector": ".price", "type": "float"}]}

        record = await controller.extract_data(schema)

        assert isinstance(record, OperationRecord)
        assert record.action == "extract_data"
        assert record.result["success"] is True
        assert "price" in record.result["data"]
        assert record.fuzzy_point is not None
        assert record.fuzzy_point["requires_judgment"] is True
        assert "提取" in record.fuzzy_point["reason"]

    def test_get_operation_history(self, controller):
        """Test getting operation history."""
        controller._operation_history = []

        # Add mock records
        page_state = PageState(url="https://example.com", title="Example")
        record1 = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        controller._operation_history.append(record1)

        history = controller.get_operation_history()

        assert len(history) == 1
        assert history[0]["action"] == "open"

    def test_get_last_operation(self, controller):
        """Test getting last operation."""
        controller._operation_history = []

        page_state = PageState(url="https://example.com", title="Example")
        record1 = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        controller._operation_history.append(record1)

        last = controller.get_last_operation()

        assert last["action"] == "open"

    def test_clear_history(self, controller):
        """Test clearing history."""
        controller._operation_history = [{"step": 1, "action": "open"}]
        controller._step_counter = 5

        controller.clear_history()

        assert len(controller._operation_history) == 0
        assert controller._step_counter == 0

    def test_set_config(self, controller):
        """Test setting config."""
        controller.set_config(timeout=60000, auto_screenshot=False)

        assert controller._config["timeout"] == 60000
        assert controller._config["auto_screenshot"] is False

    def test_get_config(self, controller):
        """Test getting config."""
        config = controller.get_config()

        assert isinstance(config, dict)
        assert "timeout" in config
        assert "auto_screenshot" in config
