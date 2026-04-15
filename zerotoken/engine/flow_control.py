"""流程执行器：递归执行脚本步骤树

支持 if / loop / assign 流程控制和浏览器动作步骤。
动作步骤失败时构建暂停结果（Step-as-Unit 模型）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from zerotoken.models.script import ScriptStep
from zerotoken.models.operation import OperationRecord
from .data_flow import VarsEnvironment

ActionRunner = Callable[[ScriptStep], Awaitable[OperationRecord]]


@dataclass
class FlowResult:
    """流程执行结果"""
    completed: bool = False
    paused: bool = False
    failed: bool = False
    error: str = ""
    failed_step: Optional[ScriptStep] = None
    failed_record: Optional[OperationRecord] = None
    steps_executed: int = 0
    # 当前 execute_steps 批次中失败步骤的下标（用于顶层脚本绝对 step_index）
    failed_batch_offset: Optional[int] = None


class FlowExecutor:
    """递归执行脚本步骤树"""

    def __init__(
        self,
        vars_env: VarsEnvironment,
        action_runner: ActionRunner,
        *,
        max_loop_iterations: int = 1000,
    ):
        self.vars_env = vars_env
        self.action_runner = action_runner
        self.max_loop_iterations = max_loop_iterations
        self._total_steps = 0

    async def execute_steps(self, steps: list[ScriptStep]) -> FlowResult:
        """按顺序递归执行步骤列表"""
        for i, step in enumerate(steps):
            result = await self._execute_one(step)
            if result.paused or result.failed:
                # 嵌套 execute_steps 已设置 failed_batch_offset 时不覆盖
                if result.paused and result.failed_batch_offset is None:
                    result.failed_batch_offset = i
                return result
        return FlowResult(completed=True, steps_executed=self._total_steps)

    async def _execute_one(self, step: ScriptStep) -> FlowResult:
        """执行单个步骤（可能是流程控制或浏览器动作）"""
        action = step.action

        if action == "if":
            return await self._handle_if(step)
        elif action == "loop":
            return await self._handle_loop(step)
        elif action == "assign":
            return self._handle_assign(step)
        else:
            return await self._handle_action(step)

    async def _handle_if(self, step: ScriptStep) -> FlowResult:
        """处理 if 分支"""
        cond = self.vars_env.eval_condition(step.condition or "False")
        body = step.body if cond else step.else_body
        if body:
            return await self.execute_steps(body)
        return FlowResult(completed=True, steps_executed=self._total_steps)

    async def _handle_loop(self, step: ScriptStep) -> FlowResult:
        """处理 loop 循环"""
        iteration = 0
        while self.vars_env.eval_condition(step.condition or "False"):
            if iteration >= self.max_loop_iterations:
                return FlowResult(
                    failed=True,
                    error=f"Loop exceeded max iterations ({self.max_loop_iterations})",
                )
            if step.body:
                result = await self.execute_steps(step.body)
                if result.paused or result.failed:
                    return result
            iteration += 1
        return FlowResult(completed=True, steps_executed=self._total_steps)

    def _handle_assign(self, step: ScriptStep) -> FlowResult:
        """处理 assign 赋值"""
        name = step.params.get("name", "")
        expr = step.params.get("expr", "")
        value = self.vars_env.eval_expr(expr)
        self.vars_env.set(name, value)
        self._total_steps += 1
        return FlowResult(completed=True, steps_executed=self._total_steps)

    async def _handle_action(self, step: ScriptStep) -> FlowResult:
        """执行浏览器动作步骤，失败时暂停"""
        resolved_params = self.vars_env.resolve_params(step.params)
        resolved_step = step.model_copy(update={"params": resolved_params})

        record = await self.action_runner(resolved_step)
        self._total_steps += 1

        if record.result.success:
            if step.assign_to:
                self.vars_env.set(step.assign_to, record.result.data)
            return FlowResult(completed=True, steps_executed=self._total_steps)
        else:
            return FlowResult(
                paused=True,
                failed_step=step,
                failed_record=record,
                error=record.result.error or "Step failed",
                steps_executed=self._total_steps,
            )
