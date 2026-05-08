"""脚本服务：脚本管理/执行/绑定（含 ScriptEngineV2 执行与恢复）"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from zerotoken.engine.script_engine_v2 import ScriptEngineV2
from zerotoken.models.script import Script, ScriptStep
from zerotoken.models.session import Resolution


class ScriptService:
    """脚本管理服务"""

    _ABANDONED_PAUSED_TTL_HOURS = 24

    def __init__(
        self,
        script_repo: Any,
        trajectory_repo: Any,
        session_repo: Any,
        runtime_repo: Any,
        binding_repo: Any,
    ):
        self._scripts = script_repo
        self._trajectories = trajectory_repo
        self._sessions = session_repo
        self._runtime = runtime_repo
        self._bindings = binding_repo

    def script_save(self, task_id: str, goal: str, steps: list[dict[str, Any]], **kw: Any) -> None:
        self._scripts.script_save(task_id, goal=goal, steps=steps, **kw)

    def script_load(self, task_id: str) -> dict[str, Any] | None:
        return self._scripts.script_load(task_id)

    def script_list(
        self,
        limit: int = 100,
        status: str = "active",
    ) -> list[dict[str, Any]]:
        return self._scripts.script_list(limit=limit, status=status)

    def script_delete(self, task_id: str) -> dict[str, Any]:
        return self._scripts.script_delete(task_id)

    def script_deprecate(self, task_id: str, reason: str = "") -> dict[str, Any]:
        """将脚本标记为 deprecated"""
        return self._scripts.deprecate(task_id, reason=reason)

    def script_restore(self, task_id: str) -> dict[str, Any]:
        """将 deprecated 脚本恢复为 active"""
        return self._scripts.restore(task_id)

    def script_health(self, task_id: str) -> dict[str, Any] | None:
        """查询脚本健康指标"""
        return self._scripts.health(task_id)

    def _settle_abandoned_sessions(self, task_id: str) -> int:
        """将超过 TTL 的 paused session 标记为 aborted，计入失败。返回处理数量。"""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=self._ABANDONED_PAUSED_TTL_HOURS)
        ).isoformat()
        stale = self._runtime.find_paused_before(task_id, cutoff)
        for s in stale:
            self._runtime.runtime_update(s["session_id"], status="aborted")
            self._scripts.record_run_result(task_id, "aborted", s["session_id"])
        return len(stale)

    def trajectory_load(self, task_id: str) -> dict[str, Any] | None:
        """加载已保存的轨迹数据（供优化、分析等场景使用）"""
        return self._trajectories.trajectory_load_by_task_id(task_id)

    def trajectory_to_script(self, task_id: str, **kw: Any) -> str:
        """从轨迹生成脚本（复用现有 generator 逻辑）"""
        from zerotoken.engine.script_generator import save_script_from_trajectory

        traj_data = self.trajectory_load(task_id)
        if traj_data is None:
            raise ValueError(f"No trajectory for task_id: {task_id}")
        return save_script_from_trajectory(
            traj_data,
            self._scripts,
            task_id=kw.get("script_task_id", task_id),
            prepend_init=kw.get("prepend_init", True),
            stealth=kw.get("stealth", False),
        )

    def binding_set(self, binding_key: str, script_task_id: str, **kw: Any) -> None:
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
        self,
        task_id: str,
        browser_svc: Any,
        *,
        vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """启动脚本执行：检查 deprecated，清理遗弃 paused，执行后更新统计"""
        health = self._scripts.health(task_id)

        if health and health.get("status") == "deprecated":
            reason = health.get("deprecated_reason") or "no reason"
            return {
                "status": "error",
                "code": "SCRIPT_DEPRECATED",
                "error": f"Script deprecated: {reason}",
            }

        self._settle_abandoned_sessions(task_id)

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
        result = await engine.run(script, vars=vars)

        # 终态时更新统计（paused 是中间态，不计入）
        if result.get("status") in ("completed", "failed", "aborted"):
            updated = self._scripts.record_run_result(
                task_id,
                result["status"],
                result.get("session_id", ""),
            )
            # 若本次执行刚把 active 升级为 warning，在响应中带 hint
            was_active = bool(health and health.get("status") == "active")
            if updated.get("status") == "warning" and was_active:
                result["health"] = {
                    "auto_warned": True,
                    "consecutive_failures": updated.get("consecutive_failures", 0),
                    "hint": (
                        "Script entered warning state after 5 consecutive failures. "
                        "Consider script_deprecate if no longer working."
                    ),
                }
        return result

    async def resume_script(
        self,
        session_id: str,
        resolution: Resolution,
        browser_svc: Any,
    ) -> dict[str, Any]:
        """恢复暂停的脚本，终态时更新统计"""
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
        result = await engine.resume(session_id, script, resolution)

        if result.get("status") in ("completed", "failed", "aborted"):
            self._scripts.record_run_result(
                task_id,
                result["status"],
                session_id,
            )
        return result

    async def run_script_by_binding(
        self,
        binding_key: str,
        browser_svc: Any,
        *,
        vars: dict[str, Any] | None = None,
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
