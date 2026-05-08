"""Tests for ScriptEngine run_script with mock controller and SessionStore."""

import os
import tempfile
from typing import Any, Dict, Optional

import pytest

from zerotoken.engine.script_engine import ScriptEngine
from zerotoken.storage_sqlite import SQLiteStorage
from zerotoken.controller import OperationRecord, PageState


class MockController:
    """Minimal controller that records calls and returns success."""

    def __init__(self):
        self.calls = []
        self._page_url = "about:blank"

    async def start(self, headless: bool = True, **kwargs) -> None:
        self.calls.append(("start", {"headless": headless, **kwargs}))

    async def open(self, url: str, **kwargs) -> OperationRecord:
        self.calls.append(("open", {"url": url}))
        self._page_url = url
        return OperationRecord(
            step=1,
            action="open",
            params={"url": url},
            result={"success": True},
            page_state=PageState(url=url, title=""),
        )

    async def click(self, selector: str, **kwargs) -> OperationRecord:
        self.calls.append(("click", {"selector": selector}))
        return OperationRecord(
            step=2,
            action="click",
            params={"selector": selector},
            result={"success": True},
            page_state=PageState(url=self._page_url, title=""),
        )

    async def get_text(self, selector: str, attr: str = "text", **kwargs) -> OperationRecord:
        self.calls.append(("get_text", {"selector": selector, "attr": attr}))
        return OperationRecord(
            step=3,
            action="get_text",
            params={"selector": selector, "attribute": attr},
            result={"success": True, "value": "mock text"},
            page_state=PageState(url=self._page_url, title=""),
        )

    async def get_html(self, selector: Optional[str] = None, **kwargs) -> OperationRecord:
        self.calls.append(("get_html", {"selector": selector}))
        return OperationRecord(
            step=4,
            action="get_html",
            params={"selector": selector},
            result={"success": True, "value": "<html>mock</html>"},
            page_state=PageState(url=self._page_url, title=""),
        )

    async def screenshot(
        self,
        path: Optional[str] = None,
        full_page: bool = False,
        selector: Optional[str] = None,
        **kwargs,
    ) -> OperationRecord:
        self.calls.append(
            ("screenshot", {"path": path, "full_page": full_page, "selector": selector})
        )
        return OperationRecord(
            step=5,
            action="screenshot",
            params={"path": path, "full_page": full_page, "selector": selector},
            result={"success": True},
            page_state=PageState(url=self._page_url, title=""),
        )

    async def wait_for(
        self, condition: str, value: Optional[str] = None, timeout: Optional[int] = None, **kwargs
    ) -> OperationRecord:
        self.calls.append(("wait_for", {"condition": condition, "value": value}))
        return OperationRecord(
            step=6,
            action="wait_for",
            params={"condition": condition, "value": value},
            result={"success": True},
            page_state=PageState(url=self._page_url, title=""),
        )

    async def extract_data(self, schema: Dict[str, Any], **kwargs) -> OperationRecord:
        self.calls.append(("extract_data", {"schema": schema}))
        return OperationRecord(
            step=7,
            action="extract_data",
            params={"schema": schema},
            result={"success": True, "value": {}},
            page_state=PageState(url=self._page_url, title=""),
        )


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def session_store(db_path):
    return SQLiteStorage(db_path)


@pytest.mark.asyncio
async def test_run_script_executes_open_and_click_writes_session(session_store):
    """Script with browser_open + browser_click runs and writes steps to SessionStore."""
    script = {
        "task_id": "test_run_1",
        "goal": "Open and click",
        "steps": [
            {"action": "browser_open", "params": {"url": "https://example.com"}},
            {"action": "browser_click", "params": {"selector": "#submit"}},
        ],
    }
    controller = MockController()
    engine = ScriptEngine(vars_map={})
    result = await engine.run_script(script, controller, session_store)
    assert result["success"] is True
    assert "session_id" in result
    session_id = result["session_id"]
    steps = session_store.session_get(session_id)
    assert len(steps) == 2
    assert steps[0]["action"] == "open"
    assert steps[0]["url"] == "https://example.com"
    assert steps[1]["action"] == "click"
    assert steps[1]["selector"] == "#submit"
    assert len(controller.calls) == 2
    assert controller.calls[0][0] == "open"
    assert controller.calls[1][0] == "click"


@pytest.mark.asyncio
async def test_run_script_executes_get_text_screenshot_wait_for_extract_data(session_store):
    """Script with browser_get_text, browser_screenshot, browser_wait_for, browser_extract_data runs."""
    script = {
        "task_id": "test_run_2",
        "goal": "Get text, screenshot, wait, extract",
        "steps": [
            {"action": "browser_open", "params": {"url": "https://example.com"}},
            {"action": "browser_get_text", "params": {"selector": "h1"}},
            {"action": "browser_screenshot", "params": {"full_page": True}},
            {"action": "browser_wait_for", "params": {"condition": "navigation"}},
            {
                "action": "browser_extract_data",
                "params": {
                    "schema": {"fields": [{"name": "title", "selector": "h1", "type": "text"}]}
                },
            },
        ],
    }
    controller = MockController()
    engine = ScriptEngine(vars_map={})
    result = await engine.run_script(script, controller, session_store)
    assert result["success"] is True
    assert len(controller.calls) == 5
    assert controller.calls[1][0] == "get_text"
    assert controller.calls[2][0] == "screenshot"
    assert controller.calls[3][0] == "wait_for"
    assert controller.calls[4][0] == "extract_data"


@pytest.mark.asyncio
async def test_run_script_browser_init_passes_stealth(session_store):
    """Script with browser_init(stealth=true) passes stealth to controller.start."""
    script = {
        "task_id": "test_stealth",
        "goal": "Stealth init",
        "steps": [
            {"action": "browser_init", "params": {"headless": True, "stealth": True}},
            {"action": "browser_open", "params": {"url": "https://example.com"}},
        ],
    }
    controller = MockController()
    engine = ScriptEngine(vars_map={})
    result = await engine.run_script(script, controller, session_store)
    assert result["success"] is True
    assert len(controller.calls) >= 1
    start_call = controller.calls[0]
    assert start_call[0] == "start"
    assert start_call[1].get("stealth") is True
    assert start_call[1].get("headless") is True
