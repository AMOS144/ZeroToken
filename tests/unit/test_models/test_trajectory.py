"""Trajectory 模型单元测试"""
import pytest
from datetime import datetime


def test_trajectory_metadata_defaults():
    from zerotoken.models.trajectory import TrajectoryMetadata
    m = TrajectoryMetadata()
    assert m.total_steps == 0
    assert m.successful_steps == 0
    assert m.failed_steps == 0
    assert m.duration_seconds is None


def test_trajectory_add_operation():
    """add_operation 正确递增计数"""
    from zerotoken.models.trajectory import Trajectory
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult
    )
    t = Trajectory(task_id="test", goal="test goal")
    record_ok = OperationRecord(
        step=1, action=ActionType.CLICK,
        params={}, result=OperationResult(success=True),
        page_state=PageState(),
    )
    record_fail = OperationRecord(
        step=2, action=ActionType.CLICK,
        params={}, result=OperationResult(success=False, error="nope"),
        page_state=PageState(),
    )
    t.add_operation(record_ok)
    assert t.metadata.total_steps == 1
    assert t.metadata.successful_steps == 1
    t.add_operation(record_fail)
    assert t.metadata.total_steps == 2
    assert t.metadata.failed_steps == 1


def test_trajectory_to_ai_prompt():
    """to_ai_prompt 生成正确的文本格式"""
    from zerotoken.models.trajectory import Trajectory
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult
    )
    t = Trajectory(task_id="login", goal="Login to system")
    t.add_operation(OperationRecord(
        step=1, action=ActionType.OPEN,
        params={"url": "https://example.com"},
        result=OperationResult(success=True),
        page_state=PageState(),
    ))
    t.add_operation(OperationRecord(
        step=2, action=ActionType.CLICK,
        params={"selector": "#btn"},
        result=OperationResult(success=True),
        page_state=PageState(),
    ))
    prompt = t.to_ai_prompt()
    assert "Task Goal: Login to system" in prompt
    assert "[Step 1] open(" in prompt
    assert "[Step 2] click(" in prompt


def test_trajectory_json_roundtrip():
    from zerotoken.models.trajectory import Trajectory
    t = Trajectory(task_id="t1", goal="goal1")
    json_str = t.model_dump_json()
    t2 = Trajectory.model_validate_json(json_str)
    assert t2.task_id == "t1"
    assert t2.goal == "goal1"


def test_trajectory_complete():
    """complete() 设置 end_time 并写入 metadata.duration_seconds"""
    from zerotoken.models.trajectory import Trajectory
    t = Trajectory(task_id="t_complete", goal="finish")
    t.complete()
    assert t.end_time is not None
    assert isinstance(t.metadata.duration_seconds, (int, float))
    assert t.metadata.duration_seconds >= 0
