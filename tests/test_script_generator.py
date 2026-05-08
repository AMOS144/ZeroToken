"""Tests for generating script from trajectory and saving to ScriptStore."""

import os
import tempfile

import pytest

from zerotoken.engine.script_generator import trajectory_to_script, save_script_from_trajectory
from zerotoken.storage_sqlite import SQLiteStorage


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_trajectory_to_script_includes_selector_candidates():
    """trajectory_to_script produces steps with selector_candidates from operations."""
    trajectory_data = {
        "task_id": "gen_1",
        "goal": "Test",
        "operations": [
            {"step": 1, "action": "open", "params": {"url": "https://a.com"}},
            {
                "step": 2,
                "action": "click",
                "params": {"selector": "#btn"},
                "selector_candidates": [
                    {"type": "css", "value": "#btn"},
                    {"type": "test_id", "value": "[data-testid=submit]"},
                ],
            },
        ],
    }
    script = trajectory_to_script(trajectory_data, prepend_init=True)
    assert script["task_id"] == "gen_1"
    assert script["goal"] == "Test"
    # browser_init, trajectory_start, browser_open, browser_click
    assert len(script["steps"]) == 4
    assert script["steps"][2]["action"] == "browser_open"
    assert script["steps"][3]["action"] == "browser_click"
    assert script["steps"][3].get("selector_candidates") == [
        {"type": "css", "value": "#btn"},
        {"type": "test_id", "value": "[data-testid=submit]"},
    ]


def test_save_script_from_trajectory_then_load_has_selector_candidates(db_path):
    """Save trajectory to DB, generate script to ScriptStore, script_load returns steps with selector_candidates."""
    store = SQLiteStorage(db_path)
    # Save trajectory with selector_candidates
    traj_id = store.trajectory_save(
        task_id="task_script_1",
        goal="Goal",
        operations=[
            {"step": 1, "action": "open", "params": {"url": "https://x.com"}},
            {
                "step": 2,
                "action": "click",
                "params": {"selector": "#ok"},
                "selector_candidates": [{"type": "css", "value": "#ok"}],
            },
        ],
        metadata={},
    )
    loaded_traj = store.trajectory_load(traj_id)
    assert loaded_traj is not None
    save_script_from_trajectory(loaded_traj, store, prepend_init=False)
    script = store.script_load("task_script_1")
    assert script is not None
    assert script["source_trajectory_id"] == traj_id
    assert len(script["steps"]) == 2
    assert script["steps"][1]["selector_candidates"] == [{"type": "css", "value": "#ok"}]


def test_trajectory_to_script_with_stealth_includes_stealth_in_browser_init():
    """trajectory_to_script(stealth=True) produces browser_init with stealth: true."""
    trajectory_data = {
        "task_id": "stealth_1",
        "goal": "Stealth test",
        "operations": [{"step": 1, "action": "open", "params": {"url": "https://a.com"}}],
    }
    script = trajectory_to_script(trajectory_data, prepend_init=True, stealth=True)
    assert script["steps"][0]["action"] == "browser_init"
    assert script["steps"][0]["params"].get("stealth") is True
    assert script["steps"][0]["params"].get("headless") is True


def test_trajectory_to_script_without_stealth_omits_stealth_in_browser_init():
    """trajectory_to_script(stealth=False) produces browser_init without stealth."""
    trajectory_data = {
        "task_id": "no_stealth_1",
        "goal": "No stealth",
        "operations": [{"step": 1, "action": "open", "params": {"url": "https://a.com"}}],
    }
    script = trajectory_to_script(trajectory_data, prepend_init=True, stealth=False)
    assert script["steps"][0]["action"] == "browser_init"
    assert "stealth" not in script["steps"][0]["params"]


def test_manual_script_save_has_no_source_trajectory_id(db_path):
    store = SQLiteStorage(db_path)
    store.script_save(
        "manual_1",
        goal="Manual",
        steps=[{"action": "browser_open", "params": {"url": "https://example.com"}}],
        params_schema={},
    )
    loaded = store.script_load("manual_1")
    assert loaded is not None
    assert loaded.get("source_trajectory_id") is None
