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
            description="List scripts in the database",
            inputSchema=_obj_schema({
                "limit": {"type": "integer", "description": "Max number to return", "default": 100},
            }),
        ),
        Tool(
            name="script_delete",
            description="Delete a script by task_id",
            inputSchema=_obj_schema({
                "task_id": {"type": "string"},
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
            items = script_svc.script_list(limit=args.get("limit", 100))
            return _resp({"scripts": items})

        if name == "script_delete":
            ok = script_svc.script_delete(args["task_id"])
            return _resp({"success": True, "deleted": ok})

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
