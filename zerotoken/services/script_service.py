"""脚本服务：脚本管理/执行/绑定（含 ScriptEngineV2 执行与恢复）"""
from __future__ import annotations

from typing import Any

from zerotoken.engine.script_engine_v2 import ScriptEngineV2
from zerotoken.models.script import Script, ScriptStep
from zerotoken.models.session import Resolution


class ScriptService:
    """脚本管理服务"""

    def __init__(self, script_repo: Any, trajectory_repo: Any,
                 session_repo: Any, runtime_repo: Any, binding_repo: Any):
        self._scripts = script_repo
        self._trajectories = trajectory_repo
        self._sessions = session_repo
        self._runtime = runtime_repo
        self._bindings = binding_repo

    def script_save(self, task_id: str, goal: str,
                    steps: list[dict[str, Any]], **kw: Any) -> None:
        self._scripts.script_save(task_id, goal=goal, steps=steps, **kw)

    def script_load(self, task_id: str) -> dict[str, Any] | None:
        return self._scripts.script_load(task_id)

    def script_list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._scripts.script_list(limit=limit)

    def script_delete(self, task_id: str) -> bool:
        return self._scripts.script_delete(task_id)

    def trajectory_to_script(self, task_id: str, **kw: Any) -> str:
        """从轨迹生成脚本（复用现有 generator 逻辑）"""
        from zerotoken.engine.script_generator import save_script_from_trajectory
        traj_data = self._trajectories.trajectory_load_by_task_id(task_id)
        if traj_data is None:
            raise ValueError(f"No trajectory for task_id: {task_id}")
        return save_script_from_trajectory(
            traj_data, self._scripts,
            task_id=kw.get("script_task_id", task_id),
            prepend_init=kw.get("prepend_init", True),
            stealth=kw.get("stealth", False),
        )

    def binding_set(self, binding_key: str, script_task_id: str,
                    **kw: Any) -> None:
        self._bindings.binding_set(binding_key, script_task_id=script_task_id, **kw)

    def binding_get(self, binding_key: str) -> dict[str, Any] | None:
        return self._bindings.binding_get(binding_key)

    def binding_list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._bindings.binding_list(limit=limit)

    def binding_delete(self, binding_key: str) -> bool:
        return self._bindings.binding_delete(binding_key)

    def session_list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._sessions.session_list(limit=limit)

    def session_get(self, session_id: str) -> list[dict[str, Any]]:
        return self._sessions.session_get(session_id)

    async def run_script(
        self, task_id: str, browser_svc: Any,
        *, vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """启动脚本执行"""
        raw = self._scripts.script_load(task_id)
        if raw is None:
            return {"status": "error", "error": f"Script not found: {task_id}"}
        script = Script(
            task_id=raw["task_id"],
            goal=raw.get("goal", ""),
            steps=[ScriptStep(**s) for s in raw.get("steps", [])],
            params_schema=raw.get("params_schema", {}),
        )
        engine = ScriptEngineV2(browser_svc, self._sessions, self._runtime)
        return await engine.run(script, vars=vars)

    async def resume_script(
        self, session_id: str, resolution: Resolution,
        browser_svc: Any,
    ) -> dict[str, Any]:
        """恢复暂停的脚本"""
        state = self._runtime.runtime_get(session_id)
        if state is None:
            return {"status": "error", "error": f"No session: {session_id}"}
        task_id = state.get("task_id", "")
        raw = self._scripts.script_load(task_id)
        if raw is None:
            return {"status": "error", "error": f"Script not found: {task_id}"}
        script = Script(
            task_id=raw["task_id"],
            goal=raw.get("goal", ""),
            steps=[ScriptStep(**s) for s in raw.get("steps", [])],
        )
        engine = ScriptEngineV2(browser_svc, self._sessions, self._runtime)
        return await engine.resume(session_id, script, resolution)

    async def run_script_by_binding(
        self, binding_key: str, browser_svc: Any,
        *, vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """按绑定 key 执行脚本（合并 default_vars + 传入 vars）"""
        binding = self._bindings.binding_get(binding_key)
        if binding is None:
            return {"status": "error", "error": f"Binding not found: {binding_key}"}
        task_id = binding["script_task_id"]
        merged_vars = dict(binding.get("default_vars") or {})
        if vars:
            merged_vars.update(vars)
        return await self.run_script(task_id, browser_svc, vars=merged_vars)
