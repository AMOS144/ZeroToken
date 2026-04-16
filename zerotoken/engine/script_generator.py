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


def _build_tab_id_mapping(operations: List[Dict[str, Any]]) -> Dict[Any, str]:
    """扫描操作序列，为所有出现过的 tab_id 建立变量名映射。
    包括首次 open 创建的初始 tab 和 new_tab 创建的新 tab。
    返回: {录制时的 tab_id -> 变量名} 如 {0: "_init_tab", 3: "_new_tab_0"}
    """
    mapping: Dict[Any, str] = {}
    new_tab_counter = 0

    for op in operations:
        action = op.get("action", "")
        page_state = op.get("page_state") or {}
        ps_tab_id = page_state.get("tab_id")

        # 首次出现的 tab_id 来自 open 操作，记为 _init_tab
        if action == "open" and ps_tab_id is not None and not mapping:
            mapping[ps_tab_id] = "_init_tab"

        # new_tab 创建的 tab，从 result.data 里取
        if action == "new_tab":
            result_data = (op.get("result") or {}).get("data") or {}
            tab_id = result_data.get("tab_id")
            if tab_id is not None and tab_id not in mapping:
                mapping[tab_id] = f"_new_tab_{new_tab_counter}"
                new_tab_counter += 1

    return mapping


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

    自动处理 tab_id 变量化：new_tab 步骤添加 assign_to，
    后续 close_tab/switch_tab 的硬编码 tab_id 替换为 {{var.tab_id}} 引用。
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

    tab_id_map = _build_tab_id_mapping(operations)

    # 是否已为首次 open 添加 assign_to
    init_tab_assigned = False

    for op in operations:
        action = op.get("action", "")
        mapped = ACTION_MAP.get(action, f"browser_{action}" if action else "browser_open")
        params = dict(op.get("params") or {})
        step: Dict[str, Any] = {"action": mapped, "params": params}

        # 首次 open: 捕获初始 tab_id 到 _init_tab 变量
        if action == "open" and not init_tab_assigned:
            page_state = op.get("page_state") or {}
            ps_tab_id = page_state.get("tab_id")
            if ps_tab_id is not None and ps_tab_id in tab_id_map:
                step["assign_to"] = tab_id_map[ps_tab_id]
                init_tab_assigned = True

        # new_tab: 添加 assign_to 以捕获返回的 tab_id
        if action == "new_tab":
            result_data = (op.get("result") or {}).get("data") or {}
            recorded_tab_id = result_data.get("tab_id")
            var_name = tab_id_map.get(recorded_tab_id)
            if var_name:
                step["assign_to"] = var_name

        # close_tab / switch_tab: 将硬编码 tab_id 替换为变量引用
        if action in ("close_tab", "switch_tab"):
            raw_tab_id = params.get("tab_id")
            var_name = tab_id_map.get(raw_tab_id)
            if var_name:
                params["tab_id"] = "{{" + var_name + ".tab_id}}"

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
