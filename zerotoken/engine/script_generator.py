"""
Generate script (v2) from trajectory and save to ScriptStore.
Maps trajectory operations to script steps with selector_candidates and fuzzy_point.
"""
from typing import Any, Dict, List, Optional

# Trajectory action -> script/MCP action
ACTION_MAP = {
    "open": "browser_open",
    "click": "browser_click",
    "input": "browser_input",
    "get_text": "browser_get_text",
    "get_html": "browser_get_html",
    "screenshot": "browser_screenshot",
    "wait_for": "browser_wait_for",
    "extract_data": "browser_extract_data",
    "hover": "browser_hover",
    "right_click": "browser_right_click",
    "double_click": "browser_double_click",
    "keyboard": "browser_keyboard",
    "type_text": "browser_type_text",
    "drag_drop": "browser_drag_drop",
    "scroll": "browser_scroll",
    "evaluate": "browser_evaluate",
    "new_tab": "browser_new_tab",
    "switch_tab": "browser_switch_tab",
    "close_tab": "browser_close_tab",
    "list_tabs": "browser_list_tabs",
    "enter_iframe": "browser_enter_iframe",
    "exit_iframe": "browser_exit_iframe",
    "file_upload": "browser_upload",
    "file_download": "browser_download",
}


def trajectory_to_script(
    trajectory_data: Dict[str, Any],
    task_id: Optional[str] = None,
    prepend_init: bool = True,
    stealth: bool = False,
) -> Dict[str, Any]:
    """
    Convert trajectory (from trajectory_load) to script v2 format.
    trajectory_data: dict with task_id, goal, operations (list of op dicts).
    Returns script dict: task_id, goal, steps (with action mapped, selector_candidates, fuzzy_point).
    """
    task_id = task_id or trajectory_data.get("task_id", "unknown")
    goal = trajectory_data.get("goal", "")
    operations = trajectory_data.get("operations") or []
    steps: List[Dict[str, Any]] = []
    if prepend_init:
        init_params: Dict[str, Any] = {"headless": True}
        if stealth:
            init_params["stealth"] = True
        steps.append({"action": "browser_init", "params": init_params})
        steps.append({"action": "trajectory_start", "params": {"task_id": task_id, "goal": goal}})
    for op in operations:
        action = op.get("action", "")
        mapped = ACTION_MAP.get(action, f"browser_{action}" if action else "browser_open")
        params = dict(op.get("params") or {})
        step: Dict[str, Any] = {"action": mapped, "params": params}
        if op.get("selector_candidates"):
            step["selector_candidates"] = op["selector_candidates"]
        if op.get("fuzzy_point"):
            step["fuzzy_point"] = op["fuzzy_point"]
        steps.append(step)
    return {"task_id": task_id, "goal": goal, "steps": steps}


def save_script_from_trajectory(
    trajectory_data: Dict[str, Any],
    script_store: Any,
    task_id: Optional[str] = None,
    prepend_init: bool = True,
    stealth: bool = False,
) -> str:
    """
    Generate script from trajectory and save to ScriptStore.
    Returns task_id.
    """
    script = trajectory_to_script(
        trajectory_data, task_id=task_id, prepend_init=prepend_init, stealth=stealth
    )
    source_trajectory_id = trajectory_data.get("id")
    script_store.script_save(
        script["task_id"],
        goal=script["goal"],
        steps=script["steps"],
        params_schema={},
        source_trajectory_id=source_trajectory_id,
    )
    return script["task_id"]
