"""轨迹 MCP 工具定义 & 分发"""

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


def trajectory_tools() -> list[Tool]:
    """返回所有轨迹相关 MCP 工具定义"""
    return [
        Tool(
            name="trajectory_start",
            description="Start a new trajectory recording for a task",
            inputSchema=_obj_schema(
                {
                    "task_id": {"type": "string", "description": "Unique task identifier"},
                    "goal": {
                        "type": "string",
                        "description": "Natural language description of the task goal",
                    },
                },
                required=["task_id", "goal"],
            ),
        ),
        Tool(
            name="trajectory_complete",
            description="Complete the current trajectory and get AI-ready prompt",
            inputSchema=_obj_schema(
                {
                    "export_for_ai": {
                        "type": "boolean",
                        "description": "Export in AI-optimized format",
                        "default": True,
                    },
                }
            ),
        ),
        Tool(
            name="trajectory_get",
            description="Get the current (in-progress) trajectory",
            inputSchema=_obj_schema(
                {
                    "format": {
                        "type": "string",
                        "description": "Output format (json | ai_prompt)",
                        "default": "json",
                    },
                }
            ),
        ),
        Tool(
            name="trajectory_list",
            description="List saved trajectories",
            inputSchema=_obj_schema(
                {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of trajectories",
                        "default": 20,
                    },
                    "since": {"type": "number", "description": "Unix timestamp filter"},
                }
            ),
        ),
        Tool(
            name="trajectory_load",
            description="Load a saved trajectory by task_id",
            inputSchema=_obj_schema(
                {
                    "task_id": {"type": "string", "description": "Task ID of the saved trajectory"},
                    "format": {
                        "type": "string",
                        "description": "Output format: ai_prompt | json",
                        "default": "ai_prompt",
                        "enum": ["ai_prompt", "json"],
                    },
                },
                required=["task_id"],
            ),
        ),
        Tool(
            name="trajectory_delete",
            description="Delete saved trajectories by task_id",
            inputSchema=_obj_schema(
                {
                    "task_id": {"type": "string", "description": "Task ID to delete"},
                },
                required=["task_id"],
            ),
        ),
        Tool(
            name="trajectory_explore_start",
            description="Enter explore mode: pause trajectory recording temporarily",
            inputSchema=_obj_schema(
                {
                    "reason": {"type": "string", "description": "Why entering explore mode"},
                }
            ),
        ),
        Tool(
            name="trajectory_explore_stop",
            description="Exit explore mode and resume recording. keep: none=discard all, last=keep last step, all=keep all explore steps",
            inputSchema=_obj_schema(
                {
                    "keep": {
                        "type": "string",
                        "description": "Which explore steps to keep: none / last / all (default: none)",
                    },
                }
            ),
        ),
        Tool(
            name="trajectory_status",
            description="Get current trajectory recording status",
            inputSchema=_obj_schema({}),
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


async def handle_trajectory_tool(
    name: str,
    args: dict[str, Any],
    trajectory_svc: Any,
) -> list[TextContent]:
    """轨迹工具分发"""
    try:
        if name == "trajectory_start":
            traj = trajectory_svc.start_trajectory(args["task_id"], args["goal"])
            return _resp(
                {
                    "success": True,
                    "task_id": traj.task_id,
                    "goal": traj.goal,
                    "message": "Trajectory recording started",
                }
            )

        if name == "trajectory_complete":
            traj = trajectory_svc.complete_trajectory()
            if traj is None:
                return _err("No active trajectory", code="NO_ACTIVE_TRAJECTORY")
            export_for_ai = args.get("export_for_ai", True)
            result: dict[str, Any] = {
                "success": True,
                "task_id": traj.task_id,
                "operations_count": len(traj.operations),
            }
            if export_for_ai:
                result["ai_prompt"] = traj.to_ai_prompt()
            else:
                result["trajectory"] = traj.model_dump()
            return _resp(result)

        if name == "trajectory_get":
            traj = trajectory_svc.get_current_trajectory()
            if traj is None:
                return _err("No active trajectory", code="NO_ACTIVE_TRAJECTORY")
            fmt = args.get("format", "json")
            if fmt == "ai_prompt":
                return _resp({"success": True, "ai_prompt": traj.to_ai_prompt()})
            return _resp({"success": True, "trajectory": traj.model_dump()})

        if name == "trajectory_list":
            items = trajectory_svc._repo.trajectory_list(
                limit=args.get("limit", 20),
                since=args.get("since"),
            )
            return _resp({"trajectories": items})

        if name == "trajectory_load":
            task_id = args["task_id"]
            traj_data = trajectory_svc._repo.trajectory_load_by_task_id(task_id)
            if traj_data is None:
                return _err(
                    f"No saved trajectory for task_id: {task_id}", code="TRAJECTORY_NOT_FOUND"
                )
            fmt = args.get("format", "ai_prompt")
            if fmt == "ai_prompt":
                from zerotoken.models.trajectory import Trajectory

                t = Trajectory(task_id=traj_data["task_id"], goal=traj_data["goal"])
                return _resp({"success": True, "ai_prompt": t.to_ai_prompt()})
            return _resp({"success": True, "trajectory": traj_data})

        if name == "trajectory_delete":
            deleted = trajectory_svc._repo.trajectory_delete_by_task_id(args["task_id"])
            return _resp({"success": True, "deleted": deleted})

        if name == "trajectory_explore_start":
            result = trajectory_svc.start_explore(reason=args.get("reason", ""))
            return _resp({"success": True, **result})

        if name == "trajectory_explore_stop":
            result = trajectory_svc.stop_explore(keep=args.get("keep", "none"))
            return _resp({"success": True, **result})

        if name == "trajectory_status":
            return _resp(trajectory_svc.get_status())

        return _err(f"Unknown trajectory tool: {name}", code="UNKNOWN_TOOL")

    except Exception as e:
        return _err(str(e), code="INTERNAL_ERROR")
