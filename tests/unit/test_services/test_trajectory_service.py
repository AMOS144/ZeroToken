"""TrajectoryService 单元测试（含探索模式）"""
import pytest
from unittest.mock import MagicMock
from zerotoken.models.operation import (
    OperationRecord, ActionType, PageState, OperationResult
)


def _make_record(step=1, success=True):
    return OperationRecord(
        step=step, action=ActionType.CLICK,
        params={"selector": "#btn"},
        result=OperationResult(success=success),
        page_state=PageState(url="https://x.com"),
    )


def test_recording_mode_records():
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    svc.start_trajectory("t1", "test goal")
    record = _make_record()
    svc.record_operation(record)
    traj = svc.get_current_trajectory()
    assert traj is not None
    assert len(traj.operations) == 1


def test_explore_mode_default_discards():
    """keep='none'（默认）时探索步骤全部丢弃"""
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    svc.start_trajectory("t1", "test goal")
    svc.start_explore(reason="looking around")
    assert svc.should_record() is False
    svc.record_operation(_make_record(step=1))
    svc.record_operation(_make_record(step=2))
    result = svc.stop_explore()
    assert result["skipped"] == 2
    assert result["kept"] == 0
    assert svc.should_record() is True
    traj = svc.get_current_trajectory()
    assert len(traj.operations) == 0


def test_explore_mode_keep_last():
    """keep='last' 时只保留探索中最后一步到正式轨迹"""
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    svc.start_trajectory("t1", "test goal")
    svc.start_explore(reason="trying selectors")
    svc.record_operation(_make_record(step=1))
    svc.record_operation(_make_record(step=2))
    svc.record_operation(_make_record(step=3))
    result = svc.stop_explore(keep="last")
    assert result["kept"] == 1
    assert result["skipped"] == 2
    traj = svc.get_current_trajectory()
    assert len(traj.operations) == 1
    assert traj.operations[0].step == 3


def test_explore_mode_keep_all():
    """keep='all' 时全部探索步骤追加到正式轨迹"""
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    svc.start_trajectory("t1", "test goal")
    svc.record_operation(_make_record(step=0))
    svc.start_explore(reason="exploring")
    svc.record_operation(_make_record(step=1))
    svc.record_operation(_make_record(step=2))
    result = svc.stop_explore(keep="all")
    assert result["kept"] == 2
    assert result["skipped"] == 0
    traj = svc.get_current_trajectory()
    assert len(traj.operations) == 3


def test_explore_mode_without_trajectory_raises():
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    with pytest.raises(ValueError, match="No active trajectory"):
        svc.start_explore()


def test_complete_trajectory():
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    mock_repo.trajectory_save = MagicMock(return_value=42)
    svc = TrajectoryService(trajectory_repo=mock_repo)
    svc.start_trajectory("t1", "goal")
    svc.record_operation(_make_record())
    traj = svc.complete_trajectory()
    assert traj is not None
    assert traj.end_time is not None
    mock_repo.trajectory_save.assert_called_once()


def test_status():
    from zerotoken.services.trajectory_service import TrajectoryService, RecordingMode
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    status = svc.get_status()
    assert status["mode"] == RecordingMode.RECORDING.value
    assert status["has_trajectory"] is False
    svc.start_trajectory("t1", "g")
    status = svc.get_status()
    assert status["has_trajectory"] is True
