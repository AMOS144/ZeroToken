"""Session 模型单元测试"""
import pytest


def test_pause_event():
    from zerotoken.models.session import PauseEvent, PauseReason
    pe = PauseEvent(
        reason=PauseReason.STEP_FAILED,
        session_id="s1",
        task_id="t1",
        step_index=3,
        action="browser_click",
        params={"selector": "#btn"},
        error="not found",
    )
    assert pe.reason == "step_failed"
    assert pe.step_index == 3
    assert "retry" in pe.allowed_resolutions
    assert "patch_step" in pe.allowed_resolutions
    assert "skip" in pe.allowed_resolutions
    assert "abort" in pe.allowed_resolutions


def test_resolution():
    from zerotoken.models.session import Resolution
    r = Resolution(type="patch_step", patch={"params": {"selector": ".new"}}, note="changed selector")
    assert r.type == "patch_step"
    assert r.patch["params"]["selector"] == ".new"


def test_runtime_state():
    from zerotoken.models.session import RuntimeState
    rs = RuntimeState(
        session_id="s1", task_id="t1",
        cursor_step_index=5, status="running",
    )
    assert rs.cursor_step_index == 5
    assert rs.status == "running"
    assert rs.pause_event is None
    assert rs.vars == {}


def test_runtime_state_json_roundtrip():
    from zerotoken.models.session import RuntimeState, PauseEvent, PauseReason
    rs = RuntimeState(
        session_id="s1", task_id="t1",
        cursor_step_index=3, status="paused",
        pause_event=PauseEvent(
            reason=PauseReason.STEP_FAILED,
            session_id="s1", task_id="t1", step_index=3,
            action="browser_click", params={"selector": "#x"},
            error="timeout",
        ),
        vars={"user": "test"},
    )
    json_str = rs.model_dump_json()
    rs2 = RuntimeState.model_validate_json(json_str)
    assert rs2.status == "paused"
    assert rs2.pause_event.error == "timeout"
    assert rs2.vars["user"] == "test"
