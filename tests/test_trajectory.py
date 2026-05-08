"""
Test TrajectoryRecorder - Test trajectory recording capabilities.
"""

import pytest
from zerotoken.trajectory import Trajectory, TrajectoryRecorder
from zerotoken.controller import OperationRecord, PageState, BrowserController
from zerotoken.storage_sqlite import SQLiteStorage


class TestTrajectory:
    """Test Trajectory class."""

    def test_create_trajectory(self):
        """Test creating trajectory."""
        traj = Trajectory(task_id="test_001", goal="Test goal")
        assert traj.task_id == "test_001"
        assert traj.goal == "Test goal"
        assert traj.operations == []
        assert traj.metadata["total_steps"] == 0

    def test_add_operation(self):
        """Test adding operation to trajectory."""
        traj = Trajectory(task_id="test_001", goal="Test goal")

        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )

        traj.add_operation(record)

        assert len(traj.operations) == 1
        assert traj.metadata["total_steps"] == 1
        assert traj.metadata["successful_steps"] == 1

    def test_add_failed_operation(self):
        """Test adding failed operation to trajectory."""
        traj = Trajectory(task_id="test_001", goal="Test goal")

        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="click",
            params={"selector": "#button"},
            result={"success": False},
            page_state=page_state,
            error="Element not found",
        )

        traj.add_operation(record)

        assert len(traj.operations) == 1
        assert traj.metadata["failed_steps"] == 1

    def test_complete_trajectory(self):
        """Test completing trajectory."""
        traj = Trajectory(task_id="test_001", goal="Test goal")
        assert traj.end_time is None

        traj.complete()

        assert traj.end_time is not None

    def test_to_ai_prompt_includes_fuzzy_point(self):
        """Test to_ai_prompt_format includes fuzzy point marker."""
        traj = Trajectory(task_id="t", goal="goal")
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="extract_data",
            params={"schema": {"fields": []}},
            result={"success": True, "value": {}},
            page_state=page_state,
            fuzzy_point={
                "requires_judgment": True,
                "reason": "需根据 schema 提取可变内容",
                "hint": "AI 视觉",
            },
        )
        traj.add_operation(record)
        s = traj.to_ai_prompt_format()
        assert "需判断" in s
        assert "需根据 schema 提取可变内容" in s
        assert "AI 视觉" in s

    def test_to_ai_prompt_without_fuzzy_point(self):
        """Test to_ai_prompt_format for steps without fuzzy point."""
        traj = Trajectory(task_id="t", goal="click button")
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="click",
            params={"selector": "#btn"},
            result={"success": True},
            page_state=page_state,
        )
        traj.add_operation(record)
        s = traj.to_ai_prompt_format()
        assert "Task Goal: click button" in s
        assert "[Step 1]" in s
        assert "需判断" not in s

    def test_to_dict(self):
        """Test converting trajectory to dict."""
        traj = Trajectory(task_id="test_001", goal="Test goal")

        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        traj.add_operation(record)
        traj.complete()

        result = traj.to_dict()

        assert result["task_id"] == "test_001"
        assert result["goal"] == "Test goal"
        assert result["operations"] is not None
        assert result["metadata"]["total_steps"] == 1
        assert result["duration_seconds"] is not None


class TestTrajectoryRecorder:
    """Test TrajectoryRecorder class."""

    @pytest.fixture
    def recorder(self, tmp_path):
        """Create recorder with SQLite storage."""
        db_path = str(tmp_path / "test.db")
        store = SQLiteStorage(db_path)
        return TrajectoryRecorder(trajectory_store=store, auto_save=False)

    @pytest.fixture
    def controller(self):
        """Create controller instance."""
        BrowserController._instance = None
        BrowserController._browser = None
        BrowserController._context = None
        BrowserController._page = None
        return BrowserController()

    def test_create_recorder(self, recorder):
        """Test creating recorder."""
        assert recorder.trajectory_store is not None
        assert recorder._current_trajectory is None

    def test_bind_controller(self, recorder, controller):
        """Test binding controller."""
        recorder.bind_controller(controller)
        assert recorder._controller is controller

    def test_start_trajectory(self, recorder):
        """Test starting trajectory."""
        traj = recorder.start_trajectory(task_id="test_001", goal="Login to system")

        assert traj is not None
        assert traj.task_id == "test_001"
        assert traj.goal == "Login to system"
        assert recorder._current_trajectory is traj

    def test_ensure_current_trajectory_creates_implicit(self, recorder):
        """ensure_current_trajectory 在无当前轨迹时创建隐式轨迹"""
        assert recorder.get_current_trajectory() is None
        recorder.ensure_current_trajectory()
        traj = recorder.get_current_trajectory()
        assert traj is not None
        assert traj.task_id.startswith("_implicit_")
        assert traj.goal == "未命名会话"

    def test_ensure_current_trajectory_idempotent(self, recorder):
        """已有当前轨迹时 ensure_current_trajectory 不新建"""
        recorder.start_trajectory("t1", "g1")
        first = recorder.get_current_trajectory()
        recorder.ensure_current_trajectory()
        second = recorder.get_current_trajectory()
        assert first is second
        assert second.task_id == "t1"

    def test_start_trajectory_completes_implicit_first(self, recorder):
        """调用 start_trajectory 时若当前为隐式轨迹则先 complete 再开新轨迹"""
        recorder.ensure_current_trajectory()
        page_state = PageState(url="https://x.com", title="X")
        record = OperationRecord(
            step=1, action="open", params={}, result={"success": True}, page_state=page_state
        )
        recorder.record_operation(record)
        recorder.start_trajectory("named", "named goal")
        current = recorder.get_current_trajectory()
        assert current is not None
        assert current.task_id == "named"
        assert current.goal == "named goal"
        assert len(current.operations) == 0

    def test_start_trajectory_clears_controller_history(self, recorder, controller):
        """Test starting trajectory clears controller history."""
        recorder.bind_controller(controller)

        # Add some history
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        controller._operation_history.append(record)

        # Start new trajectory
        recorder.start_trajectory(task_id="test_001", goal="Test")

        assert controller._step_counter == 0
        assert len(controller._operation_history) == 0

    def test_record_operation(self, recorder):
        """Test recording operation."""
        traj = recorder.start_trajectory(task_id="test_001", goal="Test goal")

        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )

        recorder.record_operation(record)

        assert len(traj.operations) == 1

    def test_get_current_trajectory(self, recorder):
        """Test getting current trajectory."""
        recorder.start_trajectory(task_id="test_001", goal="Test goal")

        current = recorder.get_current_trajectory()

        assert current is not None
        assert current.task_id == "test_001"

    def test_get_current_trajectory_none(self, recorder):
        """Test getting current trajectory when none exists."""
        current = recorder.get_current_trajectory()
        assert current is None

    def test_complete_trajectory(self, recorder):
        """Test completing trajectory."""
        recorder.start_trajectory(task_id="test_001", goal="Test goal")

        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        recorder.record_operation(record)

        completed = recorder.complete_trajectory()

        assert completed is not None
        assert completed.end_time is not None
        assert recorder._current_trajectory is None

    def test_complete_trajectory_syncs_controller_history(self, recorder, controller):
        """Test completing trajectory syncs controller history."""
        recorder.bind_controller(controller)
        recorder.start_trajectory(task_id="test_001", goal="Test goal")

        # Add operation directly to controller
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        controller._operation_history.append(record)

        # Complete trajectory
        completed = recorder.complete_trajectory()

        assert len(completed.operations) == 1

    def test_save_trajectory(self, recorder, tmp_path):
        """Test saving trajectory to database."""
        traj = recorder.start_trajectory(task_id="test_001", goal="Test goal")

        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        recorder.record_operation(record)

        trajectory_id = recorder.save_trajectory(traj)

        assert trajectory_id is not None
        assert trajectory_id > 0

    def test_save_trajectory_no_trajectory(self, recorder):
        """Test saving without trajectory raises error."""
        with pytest.raises(ValueError, match="No trajectory to save"):
            recorder.save_trajectory()

    def test_save_trajectory_persists_to_db(self, recorder, tmp_path):
        """Test saving trajectory persists to database."""
        traj = recorder.start_trajectory(task_id="test_001", goal="Test goal")
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        recorder.record_operation(record)
        recorder.save_trajectory(traj)

        items = recorder.list_trajectories()
        assert len(items) == 1
        assert items[0]["task_id"] == "test_001"
        assert items[0]["goal"] == "Test goal"

    def test_list_trajectories_empty(self, recorder):
        """Test listing trajectories when empty."""
        trajectories = recorder.list_trajectories()
        assert trajectories == []

    def test_list_trajectories(self, recorder, tmp_path):
        """Test listing trajectories from database."""
        recorder.start_trajectory(task_id="test_001", goal="Test goal 1")
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        recorder.record_operation(record)
        recorder.save_trajectory()

        trajectories = recorder.list_trajectories()

        assert len(trajectories) == 1
        assert trajectories[0]["task_id"] == "test_001"
        assert trajectories[0]["goal"] == "Test goal 1"

    def test_delete_trajectory(self, recorder, tmp_path):
        """Test deleting trajectory from database."""
        recorder.start_trajectory(task_id="test_001", goal="Test goal")
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        recorder.record_operation(record)
        recorder.save_trajectory()

        deleted = recorder.delete_trajectory("test_001")

        assert deleted >= 1
        assert recorder.load_trajectory_by_task_id("test_001") is None

    def test_load_trajectory_by_task_id_nonexistent(self, recorder):
        """load_trajectory_by_task_id 对不存在的 task_id 返回 None"""
        assert recorder.load_trajectory_by_task_id("nonexistent_id") is None

    def test_load_trajectory_by_task_id_success(self, recorder, tmp_path):
        """load_trajectory_by_task_id loads saved trajectory from DB and returns Trajectory."""
        recorder.start_trajectory(task_id="task_abc", goal="Test goal")
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        recorder.record_operation(record)
        recorder.save_trajectory()

        loaded = recorder.load_trajectory_by_task_id("task_abc")
        assert loaded is not None
        assert loaded.task_id == "task_abc"
        assert loaded.goal == "Test goal"
        assert len(loaded.operations) == 1
        assert "Task Goal" in loaded.to_ai_prompt_format()

    def test_export_for_ai(self, recorder, tmp_path):
        """export_for_ai loads from DB and returns AI prompt format."""
        recorder.start_trajectory(task_id="export_test", goal="Export goal")
        page_state = PageState(url="https://example.com", title="Example")
        record = OperationRecord(
            step=1,
            action="open",
            params={"url": "https://example.com"},
            result={"success": True},
            page_state=page_state,
        )
        recorder.record_operation(record)
        recorder.save_trajectory()

        ai_prompt = recorder.export_for_ai("export_test")
        assert "Task Goal: Export goal" in ai_prompt
        assert "[Step 1]" in ai_prompt

    def test_dict_to_record(self, recorder):
        """Test converting dict to OperationRecord."""
        data = {
            "step": 1,
            "action": "open",
            "params": {"url": "https://example.com"},
            "result": {"success": True},
            "page_state": {"url": "https://example.com", "title": "Example"},
            "screenshot": None,
            "error": None,
        }

        record = recorder._dict_to_record(data)

        assert isinstance(record, OperationRecord)
        assert record.step == 1
        assert record.action == "open"
        assert record.params == {"url": "https://example.com"}
