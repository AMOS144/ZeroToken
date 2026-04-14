"""轨迹服务：录制/导出/管理 + 探索模式"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from zerotoken.models.operation import OperationRecord
from zerotoken.models.trajectory import Trajectory


class RecordingMode(str, Enum):
    RECORDING = "recording"
    EXPLORING = "exploring"


class TrajectoryService:
    """轨迹录制与管理"""

    def __init__(self, trajectory_repo: Any):
        self._repo = trajectory_repo
        self._current: Optional[Trajectory] = None
        self._mode = RecordingMode.RECORDING
        self._explore_depth = 0

    def start_trajectory(self, task_id: str, goal: str) -> Trajectory:
        self._current = Trajectory(task_id=task_id, goal=goal)
        self._mode = RecordingMode.RECORDING
        self._explore_depth = 0
        return self._current

    def get_current_trajectory(self) -> Optional[Trajectory]:
        return self._current

    def should_record(self) -> bool:
        return self._mode == RecordingMode.RECORDING

    def record_operation(self, record: OperationRecord) -> None:
        """记录操作；探索模式下只计数不入轨迹"""
        if self._mode == RecordingMode.EXPLORING:
            self._explore_depth += 1
            return
        if self._current:
            self._current.add_operation(record)

    def start_explore(self, reason: str = "") -> dict[str, Any]:
        """进入探索模式，暂停轨迹录制"""
        if self._current is None:
            raise ValueError("No active trajectory")
        self._mode = RecordingMode.EXPLORING
        self._explore_depth = 0
        return {"mode": "exploring", "reason": reason}

    def stop_explore(self, keep_last: bool = False) -> dict[str, Any]:
        """退出探索模式，返回跳过的步数"""
        skipped = self._explore_depth
        self._mode = RecordingMode.RECORDING
        self._explore_depth = 0
        return {"mode": "recording", "skipped_steps": skipped}

    def complete_trajectory(self) -> Optional[Trajectory]:
        """完成当前轨迹，保存到仓库"""
        if self._current is None:
            return None
        self._current.complete()
        traj = self._current
        self._repo.trajectory_save(
            task_id=traj.task_id,
            goal=traj.goal,
            operations=[op.model_dump() for op in traj.operations],
            metadata=traj.metadata.model_dump(),
        )
        self._current = None
        self._mode = RecordingMode.RECORDING
        return traj

    def get_status(self) -> dict[str, Any]:
        """返回当前录制状态"""
        return {
            "mode": self._mode.value,
            "has_trajectory": self._current is not None,
            "task_id": self._current.task_id if self._current else None,
            "operations_count": len(self._current.operations) if self._current else 0,
            "explore_depth": self._explore_depth,
        }
