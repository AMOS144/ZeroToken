"""脚本 MCP 工具定义 & 分发"""
from __future__ import annotations

import json
from typing import Any

from mcp.types import Tool, TextContent


def _obj_schema(
    props: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    s: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        s["required"] = required
    return s


def script_tools() -> list[Tool]:
    """返回所有脚本相关 MCP 工具定义"""
    return [
        # -- 脚本 CRUD --
        Tool(
            name="script_save",
            description="Save a script to the database (overwrites if task_id exists)",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID (script key)"},
                "goal": {"type": "string", "description": "Goal description"},
                "steps": {"type": "array", "description": "List of steps: {action, params, ...}"},
            }, required=["task_id", "goal", "steps"]),
        ),
        Tool(
            name="script_load",
            description="Load a script by task_id",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID"},
            }, required=["task_id"]),
        ),
        Tool(
            name="script_list",
            description="List scripts in the database (default: only active)",
            inputSchema=_obj_schema({
                "limit": {"type": "integer", "description": "Max number to return", "default": 100},
                "status": {"type": "string", "description": "Filter by status: active / warning / deprecated / all (default: active)"},
            }),
        ),
        Tool(
            name="script_delete",
            description="Delete a script by task_id",
            inputSchema=_obj_schema({
                "task_id": {"type": "string"},
            }, required=["task_id"]),
        ),
        Tool(
            name="script_deprecate",
            description="Mark a script as deprecated (soft delete). Deprecated scripts are excluded from script_list by default and rejected by script_run.",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID to deprecate"},
                "reason": {"type": "string", "description": "Why the script is being deprecated"},
            }, required=["task_id"]),
        ),
        Tool(
            name="script_restore",
            description="Restore a deprecated script to active status",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID to restore"},
            }, required=["task_id"]),
        ),
        Tool(
            name="script_health",
            description="Get script health metrics: status, consecutive failures, total runs, success rate",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID"},
            }, required=["task_id"]),
        ),
        # -- 脚本生成 --
        Tool(
            name="script_generate",
            description="Generate a script from a saved trajectory",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID of the trajectory to convert"},
                "script_task_id": {"type": "string", "description": "Optional output script task_id (default: same as task_id)"},
                "prepend_init": {"type": "boolean", "description": "Prepend browser_init + trajectory_start", "default": True},
                "stealth": {"type": "boolean", "description": "Include stealth in browser_init", "default": False},
            }, required=["task_id"]),
        ),
        # -- 绑定 CRUD --
        Tool(
            name="script_bind",
            description="Bind an external job_id to a script task_id with optional default vars",
            inputSchema=_obj_schema({
                "binding_key": {"type": "string", "description": "External job identifier"},
                "script_task_id": {"type": "string", "description": "ZeroToken script task_id"},
                "description": {"type": "string", "description": "Optional description"},
                "default_vars": {"type": "object", "description": "Optional default vars"},
            }, required=["binding_key", "script_task_id"]),
        ),
        Tool(
            name="script_bind_get",
            description="Get a script binding by binding_key",
            inputSchema=_obj_schema({
                "binding_key": {"type": "string"},
            }, required=["binding_key"]),
        ),
        Tool(
            name="script_bind_list",
            description="List script bindings",
            inputSchema=_obj_schema({
                "limit": {"type": "integer", "default": 100},
            }),
        ),
        Tool(
            name="script_bind_delete",
            description="Delete a script binding by binding_key",
            inputSchema=_obj_schema({
                "binding_key": {"type": "string"},
            }, required=["binding_key"]),
        ),
        # -- Session --
        Tool(
            name="script_session_list",
            description="List sessions from the database",
            inputSchema=_obj_schema({
                "limit": {"type": "integer", "default": 100},
            }),
        ),
        Tool(
            name="script_session_get",
            description="Get session steps by session_id",
            inputSchema=_obj_schema({
                "session_id": {"type": "string"},
            }, required=["session_id"]),
        ),
        # -- 优化 --
        Tool(
            name="script_optimize",
            description="Analyze a script/trajectory and return optimization suggestions for AI to apply (pruning, parameterization, branching)",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Task ID of script or trajectory to optimize"},
                "source": {"type": "string", "description": "Source type: script or trajectory (default: script)"},
                "hints": {"type": "string", "description": "Optional optimization hints from user (e.g. 'parameterize the search keyword')"},
            }, required=["task_id"]),
        ),
        # -- 执行 --
        Tool(
            name="script_run",
            description="Start running a script (provide task_id) or resume a paused session (provide session_id)",
            inputSchema=_obj_schema({
                "task_id": {"type": "string", "description": "Start mode: task_id of script"},
                "vars": {"type": "object", "description": "Start mode: {{varname}} replacements"},
                "session_id": {"type": "string", "description": "Resume mode: session_id to resume"},
                "resolution": {"type": "object", "description": "Resume mode: resolution object"},
            }),
        ),
        Tool(
            name="script_resume",
            description="Resume a paused script session with a resolution",
            inputSchema=_obj_schema({
                "session_id": {"type": "string", "description": "Session ID to resume"},
                "resolution": {"type": "object", "description": "Resolution object {type, note?, patch?}"},
            }, required=["session_id", "resolution"]),
        ),
    ]


# --------------- 辅助 ---------------

def _resp(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, default=str))]


def _err(error: str, code: str | None = None, retryable: bool = False) -> list[TextContent]:
    out: dict[str, Any] = {"success": False, "error": error}
    if code:
        out["code"] = code
    out["retryable"] = retryable
    return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False, default=str))]


# --------------- 优化提示词生成 ---------------

# 传给 AI 的优化指令模板（正文部分，与具体脚本无关）
_OPTIMIZE_INSTRUCTIONS = """\
### 请从三个方面优化此脚本

**1. 智能剪枝** -- 找出冗余步骤（如滚动后又滚回来、重复获取相同内容、失败后重试成功但两步都保留等），建议删除哪些步骤。

**2. 参数泛化** -- 找出应该变成参数的硬编码值（如搜索关键词、URL 中的查询参数、特定的文本内容等），建议改为 `{{param_name}}` 占位符，并给出 `params_schema`。

**3. 条件分支** -- 如果有步骤可能因页面状态不同而需要走不同路径（如登录弹窗检测、元素不存在时的替代方案等），建议添加 `if` 条件步骤。
"""

# 步骤格式说明
_STEP_FORMAT_REFERENCE = """\
步骤格式支持：
- 普通步骤: `{"action": "browser_click", "params": {"selector": "#btn"}}`
- 带参数: `{"action": "browser_input", "params": {"selector": "#kw", "text": "{{search_keyword}}"}}`
- 条件分支: `{"action": "if", "condition": "page_state.url.includes('login')", "then": [...steps], "else": [...steps]}`
- 循环: `{"action": "loop", "condition": "...", "max_iterations": 10, "body": [...steps]}`
- 赋值: `{"action": "assign", "var": "result", "expr": "..."}`
"""


def _format_operations_for_ai(operations: list[dict]) -> str:
    """将轨迹操作格式化为 AI 可读文本"""
    lines = []
    for i, op in enumerate(operations, 1):
        action = op.get("action", "?")
        params = op.get("params", {})
        result = op.get("result", {})
        status = "OK" if result.get("success", True) else "FAIL"
        params_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in params.items())
        line = f"[{i}] [{status}] {action}({params_str})"
        result_data = result.get("data", {})
        if result_data:
            line += f"  -> {str(result_data)[:100]}"
        lines.append(line)
    return "\n".join(lines)


def _format_steps_for_ai(steps: list[dict]) -> str:
    """将脚本步骤格式化为 AI 可读文本"""
    lines = []
    for i, step in enumerate(steps, 1):
        action = step.get("action", "?")
        params = step.get("params", {})
        params_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in params.items())
        line = f"[{i}] {action}({params_str})"
        if step.get("assign_to"):
            line += f"  -> {step['assign_to']}"
        lines.append(line)
    return "\n".join(lines)


def _load_optimize_source(
    task_id: str, source: str, script_svc: Any,
) -> tuple[str, str] | tuple[None, str]:
    """加载优化源数据，返回 (goal, steps_text)，失败返回 (None, error_code)"""
    if source == "trajectory":
        traj = script_svc.trajectory_load(task_id)
        if traj is None:
            return None, "TRAJECTORY_NOT_FOUND"
        return traj.get("goal", ""), _format_operations_for_ai(traj.get("operations", []))
    script = script_svc.script_load(task_id)
    if script is None:
        return None, "SCRIPT_NOT_FOUND"
    return script.get("goal", ""), _format_steps_for_ai(script.get("steps", []))


def _build_optimize_prompt(args: dict[str, Any], script_svc: Any) -> list[TextContent]:
    """构建脚本优化提示词，返回给 AI 分析"""
    task_id = args["task_id"]
    source = args.get("source", "script")
    hints = args.get("hints", "")

    goal_or_none, steps_text_or_code = _load_optimize_source(task_id, source, script_svc)
    if goal_or_none is None:
        code = steps_text_or_code
        kind = "trajectory" if source == "trajectory" else "script"
        return _err(f"No {kind} for task_id: {task_id}", code=code)
    goal, steps_text = goal_or_none, steps_text_or_code

    sections = [
        "## 脚本优化分析",
        "",
        f"**Task ID:** `{task_id}`",
        f"**Goal:** {goal}",
        "",
        "### 当前步骤",
        "",
        steps_text,
        "",
        _OPTIMIZE_INSTRUCTIONS,
    ]
    if hints:
        sections.extend(["### 用户额外提示", "", hints, ""])
    sections.extend([
        "### 输出要求",
        "",
        "分析完成后，请调用 `script_save` 保存优化后的脚本：",
        f'- `task_id`: `"{task_id}_optimized"` (或用户指定的名称)',
        "- `goal`: 保持不变",
        "- `steps`: 优化后的步骤数组",
        "",
        _STEP_FORMAT_REFERENCE,
    ])

    return _resp({
        "success": True,
        "task_id": task_id,
        "optimization_prompt": "\n".join(sections),
    })


# --------------- 分发 ---------------

async def handle_script_tool(
    name: str,
    args: dict[str, Any],
    script_svc: Any,
    *,
    browser_svc: Any = None,
) -> list[TextContent]:
    """脚本工具分发"""
    try:
        # -- CRUD --
        if name == "script_save":
            script_svc.script_save(args["task_id"], args["goal"], args["steps"])
            return _resp({"success": True, "task_id": args["task_id"]})

        if name == "script_load":
            script = script_svc.script_load(args["task_id"])
            if script is None:
                return _err(f"No script for task_id: {args['task_id']}", code="SCRIPT_NOT_FOUND")
            return _resp({"success": True, "script": script})

        if name == "script_list":
            items = script_svc.script_list(
                limit=args.get("limit", 100),
                status=args.get("status", "active"),
            )
            return _resp({"scripts": items})

        if name == "script_delete":
            try:
                result = script_svc.script_delete(args["task_id"])
            except ValueError as e:
                return _err(str(e), code="SCRIPT_HAS_BINDINGS")
            return _resp({"success": True, **result})

        if name == "script_deprecate":
            try:
                result = script_svc.script_deprecate(
                    args["task_id"], reason=args.get("reason", ""),
                )
            except KeyError:
                return _err(
                    f"No script for task_id: {args['task_id']}",
                    code="SCRIPT_NOT_FOUND",
                )
            return _resp({"success": True, **result})

        if name == "script_restore":
            try:
                result = script_svc.script_restore(args["task_id"])
            except KeyError:
                return _err(
                    f"No script for task_id: {args['task_id']}",
                    code="SCRIPT_NOT_FOUND",
                )
            except ValueError as e:
                return _err(str(e), code="SCRIPT_NOT_DEPRECATED")
            return _resp({"success": True, **result})

        if name == "script_health":
            result = script_svc.script_health(args["task_id"])
            if result is None:
                return _err(
                    f"No script for task_id: {args['task_id']}",
                    code="SCRIPT_NOT_FOUND",
                )
            return _resp({"success": True, "health": result})

        # -- 生成 --
        if name == "script_generate":
            out_task_id = script_svc.trajectory_to_script(
                args["task_id"],
                script_task_id=args.get("script_task_id"),
                prepend_init=args.get("prepend_init", True),
                stealth=args.get("stealth", False),
            )
            return _resp({"success": True, "task_id": out_task_id, "message": "Script generated from trajectory"})

        # -- 绑定 --
        if name == "script_bind":
            script_svc.binding_set(
                args["binding_key"],
                args["script_task_id"],
                description=args.get("description", ""),
                default_vars=args.get("default_vars") or {},
            )
            return _resp({"success": True, "binding_key": args["binding_key"], "script_task_id": args["script_task_id"]})

        if name == "script_bind_get":
            binding = script_svc.binding_get(args["binding_key"])
            if binding is None:
                return _err(f"No binding for key: {args['binding_key']}", code="SCRIPT_BINDING_NOT_FOUND")
            return _resp({"success": True, "binding": binding})

        if name == "script_bind_list":
            items = script_svc.binding_list(limit=args.get("limit", 100))
            return _resp({"bindings": items})

        if name == "script_bind_delete":
            ok = script_svc.binding_delete(args["binding_key"])
            return _resp({"success": True, "deleted": ok})

        # -- 优化 --
        if name == "script_optimize":
            return _build_optimize_prompt(args, script_svc)

        # -- Session --
        if name == "script_session_list":
            items = script_svc.session_list(limit=args.get("limit", 100))
            return _resp({"sessions": items})

        if name == "script_session_get":
            steps = script_svc.session_get(args["session_id"])
            return _resp({"success": True, "steps": steps})

        # -- 执行 / 恢复 --
        if name == "script_run":
            task_id = args.get("task_id")
            session_id = args.get("session_id")
            if bool(task_id) == bool(session_id):
                return _err("Provide exactly one of task_id or session_id", code="INVALID_PARAMS")
            if browser_svc is None:
                return _err("Browser not initialized", code="BROWSER_NOT_READY")
            if task_id:
                result = await script_svc.run_script(
                    task_id, browser_svc, vars=args.get("vars") or {},
                )
                return _resp(result)
            else:
                from zerotoken.models.session import Resolution
                resolution = Resolution(**(args.get("resolution") or {"type": "retry"}))
                result = await script_svc.resume_script(session_id, resolution, browser_svc)
                return _resp(result)

        if name == "script_resume":
            if browser_svc is None:
                return _err("Browser not initialized", code="BROWSER_NOT_READY")
            from zerotoken.models.session import Resolution
            resolution = Resolution(**args["resolution"])
            result = await script_svc.resume_script(
                args["session_id"], resolution, browser_svc,
            )
            return _resp(result)

        return _err(f"Unknown script tool: {name}", code="UNKNOWN_TOOL")

    except Exception as e:
        return _err(str(e), code="INTERNAL_ERROR")
