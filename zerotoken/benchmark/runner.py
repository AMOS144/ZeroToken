"""Benchmark 场景批量执行器

加载 YAML 场景或已录制轨迹，通过 mcp_server.dispatch() 完整链路执行，
用 BenchmarkRecorder 记录每步调用。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import yaml

from mcp_server import dispatch, init_services
from zerotoken.benchmark.recorder import BenchmarkRecorder


@dataclass
class StepError:
    """单步执行失败详情"""
    seq: int
    action: str
    error: str
    duration_ms: float


@dataclass
class RunResult:
    """单个场景的执行结果"""
    scenario_name: str
    session_id: str
    total_steps: int
    success_steps: int
    failed_steps: int
    total_duration_ms: float
    errors: list[StepError] = field(default_factory=list)
    jsonl_path: str = ""


@dataclass
class BatchResult:
    """批量执行结果"""
    results: list[RunResult] = field(default_factory=list)
    total_scenarios: int = 0
    passed_scenarios: int = 0
    total_duration_ms: float = 0.0


class BenchmarkRunner:
    """批量执行 benchmark 场景"""

    def __init__(self, output_dir: str = "benchmarks"):
        self._output_dir = output_dir
        init_services()

    async def run_scenario(self, scenario_path: str) -> RunResult:
        """执行单个场景 YAML"""
        scenario = self._load_scenario(scenario_path)
        name = scenario.get("name", "unknown")
        steps = scenario.get("steps", [])

        recorder = BenchmarkRecorder(output_dir=self._output_dir, force_enable=True)
        result = RunResult(
            scenario_name=name,
            session_id=recorder.session_id,
            total_steps=len(steps),
            success_steps=0,
            failed_steps=0,
            total_duration_ms=0.0,
        )

        total_start = time.monotonic()
        for seq, step in enumerate(steps, 1):
            action = step["action"]
            params = step.get("params", {})
            start = time.monotonic()
            error: Exception | None = None
            step_result: Any = None
            try:
                step_result = await dispatch(action, params)
                result.success_steps += 1
            except Exception as e:
                error = e
                result.failed_steps += 1
                result.errors.append(StepError(
                    seq=seq, action=action,
                    error=str(e), duration_ms=0.0,
                ))
            finally:
                duration_ms = (time.monotonic() - start) * 1000
                if result.errors and result.errors[-1].seq == seq:
                    result.errors[-1].duration_ms = duration_ms
                recorder.record(action, params, step_result, duration_ms, error)

        result.total_duration_ms = (time.monotonic() - total_start) * 1000
        recorder._close_file()
        result.jsonl_path = self._jsonl_path(recorder)
        return result

    async def run_replay(self, task_id: str, **kw: Any) -> RunResult:
        """从轨迹 task_id 回放"""
        from zerotoken.engine.script_generator import trajectory_to_script
        from zerotoken.repository.sqlite import new_connection, SQLiteTrajectoryRepo
        import os

        db_path = os.environ.get("ZEROTOKEN_DB") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "zerotoken.db"
        )
        conn = new_connection(db_path)
        repo = SQLiteTrajectoryRepo(conn)
        traj_data = repo.trajectory_load_by_task_id(task_id)
        if traj_data is None:
            raise ValueError(f"No trajectory for task_id: {task_id}")

        script = trajectory_to_script(
            traj_data, task_id=task_id,
            prepend_init=True,
            stealth=kw.get("stealth", False),
        )
        steps = script.get("steps", [])

        recorder = BenchmarkRecorder(output_dir=self._output_dir, force_enable=True)
        result = RunResult(
            scenario_name=f"replay:{task_id}",
            session_id=recorder.session_id,
            total_steps=len(steps),
            success_steps=0,
            failed_steps=0,
            total_duration_ms=0.0,
        )

        total_start = time.monotonic()
        for seq, step in enumerate(steps, 1):
            action = step["action"]
            params = step.get("params", {})
            start = time.monotonic()
            error: Exception | None = None
            step_result: Any = None
            try:
                step_result = await dispatch(action, params)
                result.success_steps += 1
            except Exception as e:
                error = e
                result.failed_steps += 1
                result.errors.append(StepError(
                    seq=seq, action=action,
                    error=str(e), duration_ms=0.0,
                ))
            finally:
                duration_ms = (time.monotonic() - start) * 1000
                if result.errors and result.errors[-1].seq == seq:
                    result.errors[-1].duration_ms = duration_ms
                recorder.record(action, params, step_result, duration_ms, error)

        result.total_duration_ms = (time.monotonic() - total_start) * 1000
        recorder._close_file()
        result.jsonl_path = self._jsonl_path(recorder)
        return result

    async def run_batch(
        self, scenario_paths: list[str], tags: list[str] | None = None,
    ) -> BatchResult:
        """批量执行多个场景"""
        filtered = scenario_paths
        if tags:
            filtered = []
            for p in scenario_paths:
                scenario = self._load_scenario(p)
                scenario_tags = scenario.get("tags", [])
                if any(t in scenario_tags for t in tags):
                    filtered.append(p)

        batch = BatchResult(total_scenarios=len(filtered))
        total_start = time.monotonic()
        for path in filtered:
            r = await self.run_scenario(path)
            batch.results.append(r)
            if r.failed_steps == 0:
                batch.passed_scenarios += 1
        batch.total_duration_ms = (time.monotonic() - total_start) * 1000
        return batch

    async def cleanup(self) -> None:
        """清理资源"""
        pass

    def _load_scenario(self, path: str) -> dict:
        """加载场景 YAML 文件"""
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def _jsonl_path(recorder: BenchmarkRecorder) -> str:
        """获取 recorder 对应的 JSONL 文件路径"""
        import os
        return os.path.join(recorder._output_dir, f"{recorder.session_id}.jsonl")
