"""ScriptEngine v2：脚本编排、暂停/恢复、Step-as-Unit 错误模型

核心流程：
1. run(script, vars) -> 从头执行脚本
2. 任何步骤失败 -> 构建 PauseEvent -> 持久化 RuntimeState -> 返回暂停状态
3. resume(session_id, script, resolution) -> 根据 AI 仲裁决议恢复执行
"""
from __future__ import annotations

import uuid
from typing import Any

from zerotoken.models.script import Script, ScriptStep
from zerotoken.models.session import PauseEvent, PauseReason, Resolution
from zerotoken.models.operation import (
    ActionType, OperationRecord, OperationResult, PageState,
)
from .data_flow import VarsEnvironment
from .flow_control import FlowExecutor


def _make_placeholder_record(
    params: dict[str, Any], *, success: bool = True, error: str | None = None,
) -> OperationRecord:
    """构造 setup/skip 类步骤或错误的占位 OperationRecord"""
    return OperationRecord(
        step=0, action=ActionType.EVALUATE, params=params,
        result=OperationResult(success=success, error=error),
        page_state=PageState(),
    )

# BrowserService 动作方法映射（action 名 -> 方法名）
_ACTION_METHOD_MAP = {
    "browser_open": "open",
    "browser_click": "click",
    "browser_input": "input",
    "browser_get_text": "get_text",
    "browser_get_html": "get_html",
    "browser_screenshot": "screenshot",
    "browser_wait_for": "wait_for",
    "browser_extract_data": "extract_data",
    "browser_hover": "hover",
    "browser_right_click": "right_click",
    "browser_double_click": "double_click",
    "browser_keyboard": "keyboard",
    "browser_type_text": "type_text",
    "browser_drag_drop": "drag_drop",
    "browser_scroll": "scroll",
    "browser_evaluate": "evaluate",
    "browser_new_tab": "new_tab",
    "browser_switch_tab": "switch_tab",
    "browser_close_tab": "close_tab",
    "browser_list_tabs": "list_tabs",
    "browser_enter_iframe": "enter_iframe",
    "browser_exit_iframe": "exit_iframe",
    "browser_upload": "upload",
    "browser_download": "download",
}

# 轨迹控制步骤，引擎自动跳过（这些不是浏览器操作）
_SKIP_ACTIONS = {
    "trajectory_start", "trajectory_complete", "trajectory_get",
}

# 生命周期步骤，引擎直接调 BrowserService.init() / .close()
_LIFECYCLE_ACTIONS = {
    "browser_init", "browser_close",
}

# 第一个位置参数为 selector 的动作
_SELECTOR_ACTIONS = {
    "click", "input", "hover", "right_click", "double_click",
    "get_text", "get_html", "upload", "download", "drag_drop",
}


class ScriptEngineV2:
    """v2 脚本引擎"""

    def __init__(
        self,
        browser_svc: Any,
        session_repo: Any,
        runtime_repo: Any,
    ):
        self._browser = browser_svc
        self._sessions = session_repo
        self._runtime = runtime_repo

    async def run(
        self,
        script: Script,
        *,
        vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """从头执行脚本"""
        session_id = str(uuid.uuid4())
        env = VarsEnvironment(vars)

        self._sessions.session_start(session_id, task_id=script.task_id)
        self._runtime.runtime_init(
            session_id, task_id=script.task_id,
            cursor_step_index=0, status="running",
            vars=env.snapshot(),
        )

        return await self._execute(session_id, script, env, start_index=0)

    async def resume(
        self,
        session_id: str,
        script: Script,
        resolution: Resolution,
    ) -> dict[str, Any]:
        """恢复暂停的脚本执行"""
        state = self._runtime.runtime_get(session_id)
        if state is None:
            return {"status": "error", "error": f"No runtime state for session {session_id}"}

        cursor = state.get("cursor_step_index", 0)
        env = VarsEnvironment(state.get("vars") or {})

        if resolution.vars:
            for k, v in resolution.vars.items():
                env.set(k, v)

        if resolution.type == "abort":
            self._runtime.runtime_update(session_id, status="aborted")
            return {"status": "aborted", "session_id": session_id}

        if resolution.type == "skip":
            cursor += 1
            if cursor >= len(script.steps):
                self._runtime.runtime_update(session_id, status="completed", cursor_step_index=cursor)
                return {"status": "completed", "session_id": session_id}

        if resolution.type == "patch_step" and resolution.patch:
            step = script.steps[cursor]
            patched = self._apply_patch(step, resolution.patch)
            script = script.model_copy(
                update={"steps": script.steps[:cursor] + [patched] + script.steps[cursor + 1:]}
            )

        self._runtime.runtime_update(
            session_id, status="running",
            cursor_step_index=cursor, vars=env.snapshot(),
        )
        return await self._execute(session_id, script, env, start_index=cursor)

    async def _execute(
        self,
        session_id: str,
        script: Script,
        env: VarsEnvironment,
        start_index: int,
    ) -> dict[str, Any]:
        """从 start_index 开始执行脚本步骤"""
        remaining_steps = script.steps[start_index:]

        async def action_runner(step: ScriptStep) -> OperationRecord:
            return await self._run_browser_action(step)

        executor = FlowExecutor(env, action_runner)
        result = await executor.execute_steps(remaining_steps)

        if result.paused and result.failed_step:
            batch_off = result.failed_batch_offset or 0
            abs_step_index = start_index + batch_off
            pause_event = self._build_pause_event(
                session_id, script.task_id, abs_step_index,
                result.failed_step, result.failed_record, result.error,
            )
            self._runtime.runtime_update(
                session_id, status="paused",
                cursor_step_index=abs_step_index,
                pause_event=pause_event.model_dump(),
                vars=env.snapshot(),
            )
            return {
                "status": "paused",
                "session_id": session_id,
                "pause_event": pause_event.model_dump(),
            }

        if result.failed:
            self._runtime.runtime_update(session_id, status="failed")
            return {"status": "failed", "session_id": session_id, "error": result.error}

        self._runtime.runtime_update(
            session_id, status="completed",
            cursor_step_index=len(script.steps),
            vars=env.snapshot(),
        )
        return {"status": "completed", "session_id": session_id}

    async def _run_browser_action(self, step: ScriptStep) -> OperationRecord:
        """调用 BrowserService 执行一个动作步骤"""
        # 轨迹控制步骤自动跳过，返回成功 record
        if step.action in _SKIP_ACTIONS:
            return _make_placeholder_record(step.params, success=True)

        # 浏览器生命周期步骤，真正执行 init/close
        if step.action in _LIFECYCLE_ACTIONS:
            try:
                if step.action == "browser_init":
                    params = dict(step.params)
                    await self._browser.init(
                        headless=params.get("headless", True),
                        stealth=params.get("stealth", False),
                    )
                elif step.action == "browser_close":
                    await self._browser.close()
                return _make_placeholder_record(step.params, success=True)
            except Exception as e:
                return _make_placeholder_record(step.params, success=False, error=str(e))

        method_name = _ACTION_METHOD_MAP.get(step.action)
        if method_name is None:
            return _make_placeholder_record(
                step.params, success=False, error=f"Unknown action: {step.action}",
            )

        method = getattr(self._browser, method_name, None)
        if method is None:
            return _make_placeholder_record(
                step.params, success=False,
                error=f"BrowserService missing method: {method_name}",
            )

        try:
            params = dict(step.params)
            if method_name in _SELECTOR_ACTIONS and "selector" in params:
                selector = params.pop("selector")
                if method_name == "input" and "text" in params:
                    text = params.pop("text")
                    return await method(selector, text, **params)
                elif method_name == "drag_drop" and "target" in params:
                    target = params.pop("target")
                    return await method(selector, target, **params)
                elif method_name == "upload" and "path" in params:
                    path = params.pop("path")
                    return await method(selector, path, **params)
                else:
                    return await method(selector, **params)
            elif method_name == "open" and "url" in params:
                url = params.pop("url")
                record = await method(url, **params)
                # 注入 tab_id 到 result.data，使 assign_to 能捕获
                if record.result.success and record.page_state:
                    if record.result.data is None:
                        record.result.data = {}
                    record.result.data.setdefault("tab_id", record.page_state.tab_id)
                return record
            elif method_name == "wait_for" and "condition" in params:
                condition = params.pop("condition")
                value = params.pop("value", None)
                return await method(condition, value, **params)
            elif method_name == "keyboard" and "key" in params:
                key = params.pop("key")
                return await method(key, **params)
            elif method_name == "type_text" and "text" in params:
                text = params.pop("text")
                return await method(text, **params)
            elif method_name == "evaluate" and "expression" in params:
                expr = params.pop("expression")
                return await method(expr, **params)
            elif method_name == "extract_data" and "schema" in params:
                schema = params.pop("schema")
                return await method(schema, **params)
            elif method_name == "switch_tab" and "tab_id" in params:
                tab_id = params.pop("tab_id")
                return await method(tab_id, **params)
            elif method_name == "new_tab":
                return await method(url=params.get("url"), **{k: v for k, v in params.items() if k != "url"})
            else:
                return await method(**params)
        except Exception as e:
            # 尽量捕获当前页面状态附到错误记录上
            page_state = PageState()
            try:
                pipeline = getattr(self._browser, "_pipeline", None)
                if pipeline is not None:
                    ps = await pipeline.capture_state_safe()
                    if ps:
                        page_state = ps
            except Exception:
                pass
            return OperationRecord(
                step=0,
                action=ActionType.EVALUATE,
                params=step.params,
                result=OperationResult(success=False, error=str(e)),
                page_state=page_state,
            )

    def _build_pause_event(
        self,
        session_id: str,
        task_id: str,
        step_index: int,
        step: ScriptStep,
        record: OperationRecord | None,
        error: str,
    ) -> PauseEvent:
        """构建暂停事件"""
        return PauseEvent(
            reason=PauseReason.STEP_FAILED,
            session_id=session_id,
            task_id=task_id,
            step_index=step_index,
            action=step.action,
            params=step.params,
            selector_candidates=list(record.selector_candidates) if record else [],
            error=error or (record.result.error if record and record.result else None),
            page_state=record.page_state if record else None,
            screenshot=record.screenshot if record else None,
            hint=step.hint,
        )

    def _apply_patch(self, step: ScriptStep, patch: dict[str, Any]) -> ScriptStep:
        """应用 patch 到 step（shallow merge params 等字段）"""
        update: dict[str, Any] = {}
        if "params" in patch:
            merged = {**step.params, **patch["params"]}
            update["params"] = merged
        if "action" in patch:
            update["action"] = patch["action"]
        return step.model_copy(update=update)
