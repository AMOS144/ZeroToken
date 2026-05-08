"""BenchmarkRunner 单元测试（mock dispatch，不需要真实浏览器）"""

import json
import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import yaml


def _make_scenario_yaml(tmp_path, name="test_scenario", steps=None):
    """辅助：在 tmp_path 下创建场景 YAML 文件"""
    if steps is None:
        steps = [
            {"action": "browser_init", "params": {"headless": True}},
            {"action": "browser_open", "params": {"url": "https://example.com"}},
            {"action": "browser_close", "params": {}},
        ]
    scenario = {
        "name": name,
        "description": "test scenario",
        "tags": ["test"],
        "timeout_seconds": 60,
        "steps": steps,
    }
    path = str(tmp_path / f"{name}.yaml")
    with open(path, "w") as f:
        yaml.dump(scenario, f)
    return path


def _mock_dispatch_result(success=True):
    """辅助：构造 mock 的 dispatch 返回值（TextContent 列表格式）"""
    text = json.dumps({"success": success})
    item = MagicMock()
    item.text = text
    return [item]


class TestScenarioLoading:
    def test_load_valid_yaml(self, tmp_path):
        from zerotoken.benchmark.runner import BenchmarkRunner

        path = _make_scenario_yaml(tmp_path)
        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        scenario = runner._load_scenario(path)
        assert scenario["name"] == "test_scenario"
        assert len(scenario["steps"]) == 3

    def test_load_nonexistent_yaml(self, tmp_path):
        from zerotoken.benchmark.runner import BenchmarkRunner

        runner = BenchmarkRunner.__new__(BenchmarkRunner)
        with pytest.raises(FileNotFoundError):
            runner._load_scenario(str(tmp_path / "nonexistent.yaml"))


class TestRunScenario:
    @pytest.mark.asyncio
    async def test_all_steps_succeed(self, tmp_path):
        from zerotoken.benchmark.runner import BenchmarkRunner

        output_dir = str(tmp_path / "benchmarks")
        path = _make_scenario_yaml(tmp_path)
        mock_dispatch = AsyncMock(return_value=_mock_dispatch_result(True))
        with (
            patch("zerotoken.benchmark.runner.dispatch", mock_dispatch),
            patch("zerotoken.benchmark.runner.init_services"),
        ):
            runner = BenchmarkRunner(output_dir=output_dir)
            result = await runner.run_scenario(path)
        assert result.scenario_name == "test_scenario"
        assert result.total_steps == 3
        assert result.success_steps == 3
        assert result.failed_steps == 0
        assert result.errors == []
        assert os.path.exists(result.jsonl_path)

    @pytest.mark.asyncio
    async def test_step_failure_continues(self, tmp_path):
        from zerotoken.benchmark.runner import BenchmarkRunner

        output_dir = str(tmp_path / "benchmarks")
        steps = [
            {"action": "browser_init", "params": {}},
            {"action": "browser_click", "params": {"selector": "#bad"}},
            {"action": "browser_close", "params": {}},
        ]
        path = _make_scenario_yaml(tmp_path, steps=steps)
        call_count = 0

        async def mock_dispatch_fn(name, args):
            nonlocal call_count
            call_count += 1
            if name == "browser_click":
                raise RuntimeError("element not found")
            return _mock_dispatch_result(True)

        with (
            patch("zerotoken.benchmark.runner.dispatch", side_effect=mock_dispatch_fn),
            patch("zerotoken.benchmark.runner.init_services"),
        ):
            runner = BenchmarkRunner(output_dir=output_dir)
            result = await runner.run_scenario(path)
        assert result.total_steps == 3
        assert result.success_steps == 2
        assert result.failed_steps == 1
        assert len(result.errors) == 1
        assert "element not found" in result.errors[0].error

    @pytest.mark.asyncio
    async def test_jsonl_records_written(self, tmp_path):
        from zerotoken.benchmark.runner import BenchmarkRunner

        output_dir = str(tmp_path / "benchmarks")
        path = _make_scenario_yaml(tmp_path)
        mock_dispatch = AsyncMock(return_value=_mock_dispatch_result(True))
        with (
            patch("zerotoken.benchmark.runner.dispatch", mock_dispatch),
            patch("zerotoken.benchmark.runner.init_services"),
        ):
            runner = BenchmarkRunner(output_dir=output_dir)
            result = await runner.run_scenario(path)
        with open(result.jsonl_path) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 3
        assert lines[0]["tool_name"] == "browser_init"
        assert lines[2]["tool_name"] == "browser_close"
