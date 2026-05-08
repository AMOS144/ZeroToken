"""Benchmark E2E 集成测试

需要真实浏览器环境，使用 @pytest.mark.integration 标记。
运行: pytest -m integration tests/integration/
"""

import os

import pytest

from zerotoken.benchmark.analyzer import BenchmarkAnalyzer
from zerotoken.benchmark.runner import BenchmarkRunner

_SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "benchmark_scenarios")


@pytest.fixture
async def runner(tmp_path):
    r = BenchmarkRunner(output_dir=str(tmp_path))
    yield r
    await r.cleanup()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_bilibili_scenario(runner):
    """B站浏览场景应完整执行且 benchmark 记录正确"""
    path = os.path.join(_SCENARIOS_DIR, "bilibili_browse.yaml")
    if not os.path.exists(path):
        pytest.skip("bilibili_browse.yaml not found")
    result = await runner.run_scenario(path)

    analyzer = BenchmarkAnalyzer(result.jsonl_path)
    analyzer.load()
    assert len(analyzer.assert_completeness()) == 0, "JSONL records incomplete"
    assert len(analyzer.assert_sequence()) == 0, "seq not sequential"
    analyzer.print_report()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_baidu_scenario(runner):
    """百度搜索场景应完整执行"""
    path = os.path.join(_SCENARIOS_DIR, "baidu_search.yaml")
    if not os.path.exists(path):
        pytest.skip("baidu_search.yaml not found")
    result = await runner.run_scenario(path)

    analyzer = BenchmarkAnalyzer(result.jsonl_path)
    analyzer.load()
    assert len(analyzer.assert_completeness()) == 0
    assert len(analyzer.assert_sequence()) == 0
    analyzer.print_report()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_github_scenario(runner):
    """GitHub Trending 场景应完整执行"""
    path = os.path.join(_SCENARIOS_DIR, "github_explore.yaml")
    if not os.path.exists(path):
        pytest.skip("github_explore.yaml not found")
    result = await runner.run_scenario(path)

    analyzer = BenchmarkAnalyzer(result.jsonl_path)
    analyzer.load()
    assert len(analyzer.assert_completeness()) == 0
    assert len(analyzer.assert_sequence()) == 0
    analyzer.print_report()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_batch_execution(runner):
    """批量执行所有场景"""
    import glob

    pattern = os.path.join(_SCENARIOS_DIR, "*.yaml")
    scenarios = glob.glob(pattern)
    if not scenarios:
        pytest.skip("No scenario files found")

    batch = await runner.run_batch(scenarios)
    assert batch.total_scenarios > 0

    for r in batch.results:
        analyzer = BenchmarkAnalyzer(r.jsonl_path)
        analyzer.load()
        assert len(analyzer.assert_completeness()) == 0, f"{r.scenario_name}: incomplete"
        assert len(analyzer.assert_sequence()) == 0, f"{r.scenario_name}: seq gap"
