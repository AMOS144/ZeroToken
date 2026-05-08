"""FlowExecutor 测试：if/loop/assign + 动作步骤执行"""

import pytest
from unittest.mock import AsyncMock
from zerotoken.models.script import ScriptStep
from zerotoken.models.operation import OperationRecord, OperationResult, PageState, ActionType


def _ok_record(step: int = 1, action: str = "click", data: dict | None = None) -> OperationRecord:
    return OperationRecord(
        step=step,
        action=ActionType.CLICK,
        params={},
        result=OperationResult(success=True, data=data or {}),
        page_state=PageState(url="https://example.com"),
    )


def _fail_record(step: int = 1, error: str = "not found") -> OperationRecord:
    return OperationRecord(
        step=step,
        action=ActionType.CLICK,
        params={"selector": "#btn"},
        result=OperationResult(success=False, error=error),
        page_state=PageState(url="https://example.com"),
    )


@pytest.fixture
def mock_action_runner():
    """模拟执行单个浏览器动作的回调"""
    runner = AsyncMock(return_value=_ok_record())
    return runner


@pytest.mark.asyncio
async def test_execute_simple_steps(mock_action_runner):
    from zerotoken.engine.flow_control import FlowExecutor
    from zerotoken.engine.data_flow import VarsEnvironment

    steps = [
        ScriptStep(action="browser_open", params={"url": "https://example.com"}),
        ScriptStep(action="browser_click", params={"selector": "#btn"}),
    ]
    env = VarsEnvironment()
    executor = FlowExecutor(env, mock_action_runner)
    result = await executor.execute_steps(steps)
    assert result.completed is True
    assert result.paused is False
    assert mock_action_runner.await_count == 2


@pytest.mark.asyncio
async def test_if_true_branch(mock_action_runner):
    from zerotoken.engine.flow_control import FlowExecutor
    from zerotoken.engine.data_flow import VarsEnvironment

    steps = [
        ScriptStep(
            action="if",
            condition="x > 5",
            body=[ScriptStep(action="browser_click", params={"selector": "#yes"})],
            else_body=[ScriptStep(action="browser_click", params={"selector": "#no"})],
        ),
    ]
    env = VarsEnvironment({"x": 10})
    executor = FlowExecutor(env, mock_action_runner)
    result = await executor.execute_steps(steps)
    assert result.completed is True
    assert mock_action_runner.await_count == 1
    call_step = mock_action_runner.call_args[0][0]
    assert call_step.params["selector"] == "#yes"


@pytest.mark.asyncio
async def test_if_false_branch(mock_action_runner):
    from zerotoken.engine.flow_control import FlowExecutor
    from zerotoken.engine.data_flow import VarsEnvironment

    steps = [
        ScriptStep(
            action="if",
            condition="x > 5",
            body=[ScriptStep(action="browser_click", params={"selector": "#yes"})],
            else_body=[ScriptStep(action="browser_click", params={"selector": "#no"})],
        ),
    ]
    env = VarsEnvironment({"x": 2})
    executor = FlowExecutor(env, mock_action_runner)
    result = await executor.execute_steps(steps)
    assert result.completed is True
    call_step = mock_action_runner.call_args[0][0]
    assert call_step.params["selector"] == "#no"


@pytest.mark.asyncio
async def test_loop_executes_body(mock_action_runner):
    from zerotoken.engine.flow_control import FlowExecutor
    from zerotoken.engine.data_flow import VarsEnvironment

    steps = [
        ScriptStep(
            action="loop",
            condition="i < 3",
            body=[
                ScriptStep(action="browser_click", params={"selector": "#item"}),
                ScriptStep(action="assign", params={"name": "i", "expr": "i + 1"}),
            ],
        ),
    ]
    env = VarsEnvironment({"i": 0})
    executor = FlowExecutor(env, mock_action_runner)
    result = await executor.execute_steps(steps)
    assert result.completed is True
    assert mock_action_runner.await_count == 3
    assert env.get("i") == 3


@pytest.mark.asyncio
async def test_assign_sets_variable():
    from zerotoken.engine.flow_control import FlowExecutor
    from zerotoken.engine.data_flow import VarsEnvironment

    runner = AsyncMock()
    steps = [
        ScriptStep(action="assign", params={"name": "result", "expr": "40 + 2"}),
    ]
    env = VarsEnvironment()
    executor = FlowExecutor(env, runner)
    result = await executor.execute_steps(steps)
    assert result.completed is True
    assert env.get("result") == 42
    runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_assign_to_captures_action_result():
    from zerotoken.engine.flow_control import FlowExecutor
    from zerotoken.engine.data_flow import VarsEnvironment

    record = _ok_record(data={"value": "42.50"})
    runner = AsyncMock(return_value=record)

    steps = [
        ScriptStep(
            action="browser_get_text",
            params={"selector": ".price"},
            assign_to="current_price",
        ),
    ]
    env = VarsEnvironment()
    executor = FlowExecutor(env, runner)
    result = await executor.execute_steps(steps)
    assert result.completed is True
    assert env.get("current_price") == {"value": "42.50"}


@pytest.mark.asyncio
async def test_step_failure_pauses():
    from zerotoken.engine.flow_control import FlowExecutor
    from zerotoken.engine.data_flow import VarsEnvironment

    fail = _fail_record(error="selector not found")
    runner = AsyncMock(return_value=fail)

    steps = [
        ScriptStep(action="browser_click", params={"selector": "#missing"}),
    ]
    env = VarsEnvironment()
    executor = FlowExecutor(env, runner)
    result = await executor.execute_steps(steps)
    assert result.paused is True
    assert result.completed is False
    assert result.failed_step is not None
    assert result.error == "selector not found"


@pytest.mark.asyncio
async def test_loop_max_iterations():
    from zerotoken.engine.flow_control import FlowExecutor
    from zerotoken.engine.data_flow import VarsEnvironment

    runner = AsyncMock(return_value=_ok_record())
    steps = [
        ScriptStep(
            action="loop",
            condition="True",
            body=[
                ScriptStep(action="browser_click", params={"selector": "#x"}),
            ],
        ),
    ]
    env = VarsEnvironment()
    executor = FlowExecutor(env, runner, max_loop_iterations=10)
    result = await executor.execute_steps(steps)
    assert result.failed is True
    assert "max" in result.error.lower()
