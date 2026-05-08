"""
Trajectory Recorder - Records complete operation trajectories.
Stores and manages operation records for replay and analysis.
All persistence uses TrajectoryStore (database); no file storage.
"""

from datetime import datetime
from typing import Dict, List, Any, Optional, TYPE_CHECKING

from .controller import OperationRecord, BrowserController

if TYPE_CHECKING:
    from .storage import TrajectoryStore


class Trajectory:
    """Represents a complete operation trajectory."""

    def __init__(self, task_id: str, goal: str):
        self.task_id = task_id
        self.goal = goal
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.operations: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {
            "browser_info": None,
            "total_steps": 0,
            "successful_steps": 0,
            "failed_steps": 0,
        }

    def add_operation(self, record: OperationRecord) -> None:
        """Add an operation record to trajectory."""
        self.operations.append(record.to_dict())
        self.metadata["total_steps"] = len(self.operations)
        if record.result.get("success"):
            self.metadata["successful_steps"] += 1
        else:
            self.metadata["failed_steps"] += 1

    def complete(self) -> None:
        """Mark trajectory as complete."""
        self.end_time = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": (self.end_time - self.start_time).total_seconds()
            if self.end_time
            else None,
            "metadata": self.metadata,
            "operations": self.operations,
        }

    def to_ai_prompt_format(self) -> str:
        """
        Export trajectory as AI-friendly text format.
        Steps with fuzzy_point are marked with [需判断: {reason}].
        """
        lines = [f"Task Goal: {self.goal}", "", "Operation History:"]
        for op in self.operations:
            step = op.get("step", 0)
            action = op.get("action", "")
            params = op.get("params", {})
            param_str = ", ".join(f"{k}={repr(v)}" for k, v in params.items())
            line = f"[Step {step}] {action}({param_str})"
            fp = op.get("fuzzy_point")
            if fp and fp.get("requires_judgment"):
                reason = fp.get("reason", "需AI/人判断")
                hint = fp.get("hint", "")
                if hint:
                    line += f" [需判断: {reason}; 提示: {hint}]"
                else:
                    line += f" [需判断: {reason}]"
            lines.append(line)
        return "\n".join(lines)


class TrajectoryRecorder:
    """
    Records and manages operation trajectories.
    Integrates with BrowserController to capture all operations.
    All persistence uses TrajectoryStore (database); trajectory_store is required.
    """

    def __init__(
        self,
        trajectory_store: "TrajectoryStore",
        auto_save: bool = True,
    ):
        self.trajectory_store = trajectory_store
        self.auto_save = auto_save
        self._current_trajectory: Optional[Trajectory] = None
        self._controller: Optional[BrowserController] = None

    def bind_controller(self, controller: BrowserController) -> None:
        """Bind to a BrowserController for automatic recording."""
        self._controller = controller

    def start_trajectory(self, task_id: str, goal: str) -> Trajectory:
        """
        Start a new trajectory recording.

        Args:
            task_id: Unique task identifier
            goal: Natural language description of the task goal

        Returns:
            The new Trajectory object
        """
        if self._current_trajectory is not None and self._current_trajectory.task_id.startswith(
            "_implicit_"
        ):
            self.complete_trajectory()
        self._current_trajectory = Trajectory(task_id, goal)

        # Clear controller history if bound
        if self._controller:
            self._controller.clear_history()

        return self._current_trajectory

    def ensure_current_trajectory(self) -> None:
        """若无当前轨迹则创建隐式轨迹（不清理 controller history）。"""
        if self._current_trajectory is not None:
            return
        task_id = "_implicit_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current_trajectory = Trajectory(task_id, "未命名会话")

    def record_operation(self, record: OperationRecord) -> None:
        """Record an operation to current trajectory."""
        if self._current_trajectory:
            self._current_trajectory.add_operation(record)

            if self.auto_save:
                self.save_trajectory()

    def get_current_trajectory(self) -> Optional[Trajectory]:
        """Get the current trajectory."""
        return self._current_trajectory

    def complete_trajectory(self) -> Optional[Trajectory]:
        """Complete the current trajectory and return it."""
        if self._current_trajectory:
            self._current_trajectory.complete()

            # Sync with controller history
            if self._controller:
                for op_dict in self._controller.get_operation_history():
                    # Check if already recorded
                    already_recorded = any(
                        op["step"] == op_dict["step"] for op in self._current_trajectory.operations
                    )
                    if not already_recorded:
                        # Create OperationRecord from dict
                        record = self._dict_to_record(op_dict)
                        self._current_trajectory.add_operation(record)

            # Persistence on complete is handled by MCP (trajectory_complete) to avoid double-save

        trajectory = self._current_trajectory
        self._current_trajectory = None
        return trajectory

    def _dict_to_record(self, data: Dict[str, Any]) -> OperationRecord:
        """Convert dictionary back to OperationRecord."""
        from .controller import PageState

        ps = data.get("page_state") or {}
        page_state = PageState(
            url=ps.get("url", ""),
            title=ps.get("title", ""),
        )

        return OperationRecord(
            step=data.get("step", 0),
            action=data.get("action", ""),
            params=data.get("params") or {},
            result=data.get("result") or {},
            page_state=page_state,
            screenshot=data.get("screenshot"),
            error=data.get("error"),
            fuzzy_point=data.get("fuzzy_point"),
            selector_candidates=data.get("selector_candidates"),
        )

    def save_trajectory(self, trajectory: Optional[Trajectory] = None) -> int:
        """
        Save trajectory to TrajectoryStore (database); no file storage.

        Returns:
            Trajectory id from database
        """
        traj = trajectory or self._current_trajectory
        if not traj:
            raise ValueError("No trajectory to save")

        trajectory_id = self.trajectory_store.trajectory_save(
            task_id=traj.task_id,
            goal=traj.goal,
            operations=traj.operations,
            metadata=traj.metadata,
        )
        return trajectory_id

    def load_trajectory_by_task_id(self, task_id: str) -> Optional[Trajectory]:
        """Load the most recently saved trajectory for the given task_id from DB. Returns None if none found."""
        data = self.trajectory_store.trajectory_load_by_task_id(task_id)
        if data is None:
            return None
        trajectory = Trajectory(data["task_id"], data["goal"])
        trajectory.operations = data.get("operations", [])
        trajectory.metadata = data.get("metadata") or {}
        return trajectory

    def list_trajectories(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List saved trajectories from database."""
        items = self.trajectory_store.trajectory_list(limit=limit)
        return [
            {
                "id": r["id"],
                "task_id": r["task_id"],
                "goal": r["goal"],
                "created_at": r["created_at"],
            }
            for r in items
        ]

    def delete_trajectory(self, task_id: str) -> int:
        """Delete trajectories by task_id from database. Returns number deleted."""
        return self.trajectory_store.trajectory_delete_by_task_id(task_id)

    def export_for_ai(self, task_id: str) -> str:
        """Load trajectory by task_id from DB and return AI prompt format."""
        trajectory = self.load_trajectory_by_task_id(task_id)
        if trajectory is None:
            raise ValueError(f"No trajectory found for task_id: {task_id}")
        return trajectory.to_ai_prompt_format()
