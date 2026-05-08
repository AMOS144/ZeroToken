"""Tests for ScriptEngine pause/resume with DFUs and session runtime cursor."""

import os
import tempfile

import pytest

from zerotoken.engine.script_engine import ScriptEngine
from zerotoken.storage_sqlite import SQLiteStorage
from zerotoken.controller import OperationRecord, PageState


class MockController:
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

    async def input(self, selector: str, text: str, **kwargs) -> OperationRecord:
        self.calls.append(("input", {"selector": selector, "text": text}))
        return OperationRecord(
            step=3,
            action="input",
            params={"selector": selector, "text": text},
            result={"success": True},
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
def storage(db_path):
    return SQLiteStorage(db_path)


@pytest.mark.asyncio
async def test_pause_on_dfu_then_resume_human_done_advances(storage: SQLiteStorage):
    # DFU pauses on clicking #captcha
    storage.dfu_save(
        "captcha_v1",
        name="Captcha pause",
        triggers=[{"action_is": "browser_click", "selector_is": "#captcha"}],
        prompt="Solve captcha",
        allowed_resolutions=["human_done", "abort", "retry_step", "patch_step", "skip_step"],
    )

    script = {
        "task_id": "task_pause_1",
        "goal": "Flow with captcha",
        "steps": [
            {"action": "browser_open", "params": {"url": "https://example.com"}},
            {"action": "browser_click", "params": {"selector": "#captcha"}},
            {"action": "browser_click", "params": {"selector": "#after"}},
        ],
    }
    storage.script_save(
        script["task_id"], goal=script["goal"], steps=script["steps"], params_schema={}
    )

    controller = MockController()
    engine = ScriptEngine(vars_map={})

    res1 = await engine.run_script_start(script, controller, storage)
    assert res1["success"] is False
    assert res1["status"] == "paused"
    assert res1["pause_event"]["kind"] == "dfu_pause"
    assert res1["pause_event"]["dfu_id"] == "captcha_v1"

    session_id = res1["session_id"]
    rt = storage.runtime_get(session_id)
    assert rt is not None
    assert rt["status"] == "paused"
    assert rt["cursor_step_index"] == 1

    # Resume with human_done should advance to next step (H1)
    res2 = await engine.run_script_resume(
        session_id, {"type": "human_done", "note": "done"}, controller, storage
    )
    assert res2["success"] is True
    assert res2["status"] == "success"

    rt2 = storage.runtime_get(session_id)
    assert rt2 is not None
    assert rt2["status"] == "success"

    # Ensure we did open + after-click; captcha click was skipped by human_done semantics
    call_names = [c[0] for c in controller.calls]
    assert call_names == ["open", "click"]
    assert controller.calls[1][1]["selector"] == "#after"


@pytest.mark.asyncio
async def test_resume_patch_step_retries_current_step_with_patch(storage: SQLiteStorage):
    script = {
        "task_id": "task_patch_1",
        "goal": "Patch selector",
        "steps": [
            {"action": "browser_open", "params": {"url": "https://example.com"}},
            {"action": "browser_click", "params": {"selector": "#old"}},
        ],
    }
    storage.script_save(
        script["task_id"], goal=script["goal"], steps=script["steps"], params_schema={}
    )

    # Pause on the old selector
    storage.dfu_save(
        "pause_old",
        name="Pause old selector",
        triggers=[{"action_is": "browser_click", "selector_is": "#old"}],
        prompt="Update selector",
        allowed_resolutions=["patch_step"],
    )

    controller = MockController()
    engine = ScriptEngine(vars_map={})

    res1 = await engine.run_script_start(script, controller, storage)
    assert res1["status"] == "paused"
    session_id = res1["session_id"]

    res2 = await engine.run_script_resume(
        session_id,
        {"type": "patch_step", "patch": {"params": {"selector": "#new"}}},
        controller,
        storage,
    )
    assert res2["status"] == "success"
    assert [c[0] for c in controller.calls] == ["open", "click"]
    assert controller.calls[1][1]["selector"] == "#new"


@pytest.mark.asyncio
async def test_resume_vars_persist_and_substitute_placeholders(storage: SQLiteStorage):
    # Pause on an execution point, then resume with vars used by a later input step.
    script = {
        "task_id": "task_vars_1",
        "goal": "Generate comment text",
        "steps": [
            {"action": "browser_open", "params": {"url": "https://example.com"}},
            {"action": "browser_click", "params": {"selector": "#need_comment"}},
            {
                "action": "browser_input",
                "params": {"selector": "#comment", "text": "{{comment_text}}"},
            },
        ],
    }
    storage.script_save(
        script["task_id"], goal=script["goal"], steps=script["steps"], params_schema={}
    )

    storage.dfu_save(
        "exec_point_comment",
        name="Execution point: comment",
        triggers=[{"action_is": "browser_click", "selector_is": "#need_comment"}],
        prompt="Please generate comment_text",
        allowed_resolutions=["human_done"],
    )

    controller = MockController()
    engine = ScriptEngine(vars_map={})

    res1 = await engine.run_script_start(script, controller, storage)
    assert res1["status"] == "paused"
    session_id = res1["session_id"]

    res2 = await engine.run_script_resume(
        session_id,
        {"type": "human_done", "vars": {"comment_text": "hello world"}},
        controller,
        storage,
    )
    assert res2["status"] == "success"
    # Ensure placeholder was substituted when calling input
    assert [c[0] for c in controller.calls] == ["open", "input"]
    assert controller.calls[1][1]["text"] == "hello world"

    rt = storage.runtime_get(session_id)
    assert rt is not None
    assert rt["vars"]["comment_text"] == "hello world"
