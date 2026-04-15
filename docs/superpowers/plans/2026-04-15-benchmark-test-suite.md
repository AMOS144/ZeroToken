# Benchmark Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a batch scenario runner, JSONL analyzer, and CLI tool to generate and validate BenchmarkRecorder output using real-site scenarios and trajectory replay.

**Architecture:** BenchmarkRunner executes predefined YAML scenarios or replayed trajectories by calling `mcp_server.dispatch()` in-process (full handler -> service -> pipeline path). BenchmarkAnalyzer reads the resulting JSONL files to run automated assertions and generate summary reports. A CLI wraps both for interactive use; pytest integration provides CI-friendly testing.

**Tech Stack:** Python 3.11+, PyYAML, argparse, pytest, asyncio

---

## File Structure

| File | Responsibility |
|------|----------------|
| `zerotoken/benchmark/recorder.py` | [Modify] Add `force_enable` parameter |
| `zerotoken/benchmark/__init__.py` | [Modify] Re-export `BenchmarkAnalyzer` |
| `zerotoken/benchmark/analyzer.py` | [Create] JSONL analysis + assertions + report |
| `zerotoken/benchmark/runner.py` | [Create] Batch scenario execution |
| `mcp_server.py` | [Modify] Expose `init_services`, `dispatch`, `get_recorder` |
| `benchmark_cli.py` | [Create] CLI entry point |
| `benchmark_scenarios/bilibili_browse.yaml` | [Create] B站浏览场景 |
| `benchmark_scenarios/baidu_search.yaml` | [Create] 百度搜索场景 |
| `benchmark_scenarios/github_explore.yaml` | [Create] GitHub Trending 场景 |
| `tests/unit/test_benchmark/test_recorder.py` | [Modify] Add force_enable tests |
| `tests/unit/test_benchmark/test_analyzer.py` | [Create] Analyzer unit tests |
| `tests/unit/test_benchmark/test_runner.py` | [Create] Runner unit tests (mocked dispatch) |
| `tests/integration/__init__.py` | [Create] Integration test package |
| `tests/integration/test_benchmark_e2e.py` | [Create] E2E integration tests |
| `pytest.ini` or `pyproject.toml` | [Modify] Register `integration` marker |

---

### Task 1: BenchmarkRecorder `force_enable` 参数

**Files:**
- Modify: `zerotoken/benchmark/recorder.py:21-24`
- Test: `tests/unit/test_benchmark/test_recorder.py`

- [ ] **Step 1: Write failing tests for force_enable**

在 `tests/unit/test_benchmark/test_recorder.py` 末尾追加：

```python
def test_force_enable_overrides_env(monkeypatch):
    """force_enable=True 时即使未设置环境变量也应启用"""
    monkeypatch.delenv("ZEROTOKEN_BENCHMARK", raising=False)
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    rec = BenchmarkRecorder(output_dir=tempfile.mkdtemp(), force_enable=True)
    assert rec.enabled is True


def test_force_enable_false_respects_env(monkeypatch):
    """force_enable=False（默认）时仍通过环境变量控制"""
    monkeypatch.delenv("ZEROTOKEN_BENCHMARK", raising=False)
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    rec = BenchmarkRecorder(output_dir=tempfile.mkdtemp(), force_enable=False)
    assert rec.enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/test_benchmark/test_recorder.py::test_force_enable_overrides_env tests/unit/test_benchmark/test_recorder.py::test_force_enable_false_respects_env -v`
Expected: FAIL with `TypeError: BenchmarkRecorder.__init__() got an unexpected keyword argument 'force_enable'`

- [ ] **Step 3: Implement force_enable parameter**

修改 `zerotoken/benchmark/recorder.py` 的 `__init__` 方法：

```python
def __init__(self, output_dir: str = "benchmarks", force_enable: bool = False):
    self._output_dir = output_dir
    if force_enable:
        self.enabled = True
    else:
        env_val = os.environ.get("ZEROTOKEN_BENCHMARK", "").strip().lower()
        self.enabled = env_val in ("1", "true")
    self.session_id = self._make_session_id()
    self._seq = 0
    self._lock = threading.Lock()
    self._file: IO | None = None
    if self.enabled:
        atexit.register(self._close_file)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/test_benchmark/test_recorder.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/benchmark/recorder.py tests/unit/test_benchmark/test_recorder.py
git commit -m "feat(benchmark): add force_enable parameter to BenchmarkRecorder"
```

---

### Task 2: mcp_server.py 接口暴露

**Files:**
- Modify: `mcp_server.py:31-64`

- [ ] **Step 1: Rename _init_services -> init_services and _dispatch -> dispatch**

修改 `mcp_server.py`：

1. 将 `def _init_services():` 改为 `def init_services():`
2. 将 `async def _dispatch(name: str, arguments: dict):` 改为 `async def dispatch(name: str, arguments: dict):`
3. 新增 `get_recorder` 函数
4. 更新 `call_tool` 内部调用

完整修改后的相关代码：

```python
def init_services():
    global _db_conn, _browser_svc, _trajectory_svc, _script_svc
    if _db_conn is not None:
        return
    db_path = os.environ.get("ZEROTOKEN_DB") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "zerotoken.db"
    )
    _db_conn = new_connection(db_path)
    fp_repo = SQLiteFingerprintRepo(_db_conn)
    traj_repo = SQLiteTrajectoryRepo(_db_conn)
    _browser_svc = BrowserService(fingerprint_repo=fp_repo)
    _trajectory_svc = TrajectoryService(trajectory_repo=traj_repo)
    _script_svc = ScriptService(
        script_repo=SQLiteScriptRepo(_db_conn),
        trajectory_repo=traj_repo,
        session_repo=SQLiteSessionRepo(_db_conn),
        runtime_repo=SQLiteRuntimeRepo(_db_conn),
        binding_repo=SQLiteBindingRepo(_db_conn),
    )


def get_recorder() -> BenchmarkRecorder:
    """返回模块级 BenchmarkRecorder 实例"""
    return _recorder


@server.list_tools()
async def list_tools():
    return browser_tools() + trajectory_tools() + script_tools()


async def dispatch(name: str, arguments: dict):
    """工具分发（经 handler -> service -> pipeline 完整路径）"""
    if name.startswith("browser_"):
        return await handle_browser_tool(name, arguments, _browser_svc, _trajectory_svc)
    elif name.startswith("trajectory_"):
        return await handle_trajectory_tool(name, arguments, _trajectory_svc)
    else:
        return await handle_script_tool(name, arguments, _script_svc, browser_svc=_browser_svc)


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    init_services()
    start = time.monotonic()
    result = None
    error = None
    try:
        result = await dispatch(name, arguments)
        return result
    except Exception as e:
        error = e
        raise
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        _recorder.record(name, arguments, result, duration_ms, error)
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/ -v --tb=short -q`
Expected: All existing tests PASS（mcp_server 的 `_init_services` / `_dispatch` 仅被 `call_tool` 内部调用，单元测试不直接依赖它们）

- [ ] **Step 3: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add mcp_server.py
git commit -m "refactor(mcp): expose init_services, dispatch, get_recorder for benchmark runner"
```

---

### Task 3: BenchmarkAnalyzer -- 断言功能

**Files:**
- Create: `zerotoken/benchmark/analyzer.py`
- Create: `tests/unit/test_benchmark/test_analyzer.py`
- Modify: `zerotoken/benchmark/__init__.py`

- [ ] **Step 1: Write failing tests for load + assert_completeness + assert_sequence**

创建 `tests/unit/test_benchmark/test_analyzer.py`：

```python
"""BenchmarkAnalyzer 单元测试"""
import json
import os
import tempfile

import pytest


def _write_jsonl(records: list[dict], path: str) -> str:
    """辅助：写入 JSONL 文件"""
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def _make_record(seq: int, **overrides) -> dict:
    """辅助：生成一条合法的 benchmark record"""
    base = {
        "session_id": "20260415_120000_abc123",
        "call_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "seq": seq,
        "timestamp": "2026-04-15T12:00:00",
        "tool_name": "browser_click",
        "args": {"selector": "#btn"},
        "duration_ms": 100.0,
        "success": True,
        "result_summary": {"success": True},
        "error": None,
        "error_code": None,
        "result_size_bytes": 50,
    }
    base.update(overrides)
    return base


class TestLoad:
    def test_load_valid_jsonl(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "test.jsonl")
        _write_jsonl([_make_record(1), _make_record(2)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        assert len(analyzer.records) == 2

    def test_load_empty_file(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "empty.jsonl")
        open(path, "w").close()
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        assert len(analyzer.records) == 0


class TestAssertCompleteness:
    def test_complete_records(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "ok.jsonl")
        _write_jsonl([_make_record(1)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        assert analyzer.assert_completeness() == []

    def test_missing_field(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        record = _make_record(1)
        del record["tool_name"]
        path = str(tmp_path / "bad.jsonl")
        _write_jsonl([record], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        violations = analyzer.assert_completeness()
        assert len(violations) == 1
        assert "tool_name" in violations[0]


class TestAssertSequence:
    def test_sequential(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "seq.jsonl")
        _write_jsonl([_make_record(1), _make_record(2), _make_record(3)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        assert analyzer.assert_sequence() == []

    def test_gap_in_sequence(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "gap.jsonl")
        _write_jsonl([_make_record(1), _make_record(3)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        violations = analyzer.assert_sequence()
        assert len(violations) == 1

    def test_single_record(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "one.jsonl")
        _write_jsonl([_make_record(1)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        assert analyzer.assert_sequence() == []


class TestAssertTiming:
    def test_within_limit(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "fast.jsonl")
        _write_jsonl([_make_record(1, duration_ms=500.0)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        assert analyzer.assert_timing(max_ms=1000) == []

    def test_exceeds_limit(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "slow.jsonl")
        _write_jsonl([_make_record(1, duration_ms=90000.0)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        violations = analyzer.assert_timing(max_ms=60000)
        assert len(violations) == 1


class TestAssertNoUnhandledErrors:
    def test_no_errors(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "clean.jsonl")
        _write_jsonl([_make_record(1)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        assert analyzer.assert_no_unhandled_errors() == []

    def test_has_error(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "err.jsonl")
        _write_jsonl([_make_record(1, success=False, error="timeout")], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        violations = analyzer.assert_no_unhandled_errors()
        assert len(violations) == 1
        assert "timeout" in violations[0]


class TestValidateAll:
    def test_all_pass(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "all_ok.jsonl")
        _write_jsonl([_make_record(1), _make_record(2)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        result = analyzer.validate_all()
        assert all(len(v) == 0 for v in result.values())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/test_benchmark/test_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'zerotoken.benchmark.analyzer'`

- [ ] **Step 3: Implement BenchmarkAnalyzer (断言部分)**

创建 `zerotoken/benchmark/analyzer.py`：

```python
"""Benchmark JSONL 分析器

读取 BenchmarkRecorder 输出的 JSONL 文件，提供自动断言和汇总报告。
"""
from __future__ import annotations

import json
import statistics
from typing import Any

# JSONL 记录必填字段
_REQUIRED_FIELDS = (
    "session_id", "call_id", "seq", "timestamp",
    "tool_name", "args", "duration_ms", "success", "result_summary",
)


class BenchmarkAnalyzer:
    """分析 benchmark JSONL 记录"""

    def __init__(self, jsonl_path: str):
        self._path = jsonl_path
        self.records: list[dict[str, Any]] = []

    def load(self) -> None:
        """加载并解析 JSONL 文件"""
        self.records = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.records.append(json.loads(line))

    # ---- 自动断言 ----

    def assert_completeness(self) -> list[str]:
        """检查每条记录的必填字段完整性，返回违规描述列表"""
        violations: list[str] = []
        for r in self.records:
            seq = r.get("seq", "?")
            for field in _REQUIRED_FIELDS:
                if field not in r:
                    violations.append(f"seq={seq}: missing field '{field}'")
        return violations

    def assert_sequence(self) -> list[str]:
        """检查 seq 是否连续递增"""
        violations: list[str] = []
        seqs = [r.get("seq", 0) for r in self.records]
        for i in range(1, len(seqs)):
            if seqs[i] != seqs[i - 1] + 1:
                violations.append(
                    f"seq gap: {seqs[i - 1]} -> {seqs[i]} (expected {seqs[i - 1] + 1})"
                )
        return violations

    def assert_timing(self, max_ms: float = 60000) -> list[str]:
        """检查每步耗时不超过 max_ms"""
        violations: list[str] = []
        for r in self.records:
            d = r.get("duration_ms", 0)
            if d > max_ms:
                violations.append(
                    f"seq={r.get('seq', '?')}: {r.get('tool_name', '?')} "
                    f"took {d:.0f}ms (max={max_ms:.0f}ms)"
                )
        return violations

    def assert_no_unhandled_errors(self) -> list[str]:
        """检查是否有 error 记录"""
        violations: list[str] = []
        for r in self.records:
            if r.get("error"):
                violations.append(
                    f"seq={r.get('seq', '?')}: {r.get('tool_name', '?')} "
                    f"error: {r['error']}"
                )
        return violations

    def validate_all(self) -> dict[str, list[str]]:
        """运行全部断言"""
        return {
            "completeness": self.assert_completeness(),
            "sequence": self.assert_sequence(),
            "timing": self.assert_timing(),
            "errors": self.assert_no_unhandled_errors(),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/test_benchmark/test_analyzer.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/benchmark/analyzer.py tests/unit/test_benchmark/test_analyzer.py
git commit -m "feat(benchmark): add BenchmarkAnalyzer with assertion methods"
```

---

### Task 4: BenchmarkAnalyzer -- 汇总报告

**Files:**
- Modify: `zerotoken/benchmark/analyzer.py`
- Modify: `tests/unit/test_benchmark/test_analyzer.py`
- Modify: `zerotoken/benchmark/__init__.py`

- [ ] **Step 1: Write failing tests for summary + print_report**

在 `tests/unit/test_benchmark/test_analyzer.py` 末尾追加：

```python
class TestSummary:
    def test_basic_summary(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "sum.jsonl")
        records = [
            _make_record(1, tool_name="browser_open", duration_ms=1000.0),
            _make_record(2, tool_name="browser_click", duration_ms=200.0),
            _make_record(3, tool_name="browser_click", duration_ms=300.0),
            _make_record(4, tool_name="browser_close", duration_ms=50.0, success=False, error="fail"),
        ]
        _write_jsonl(records, path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        s = analyzer.summary()
        assert s["total_calls"] == 4
        assert s["success_count"] == 3
        assert s["fail_count"] == 1
        assert 0.74 < s["success_rate"] < 0.76
        assert s["total_duration_ms"] == 1550.0
        assert "browser_click" in s["by_tool"]
        assert s["by_tool"]["browser_click"]["count"] == 2
        assert s["by_tool"]["browser_click"]["avg_duration_ms"] == 250.0
        assert len(s["errors"]) == 1

    def test_empty_summary(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "empty.jsonl")
        open(path, "w").close()
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        s = analyzer.summary()
        assert s["total_calls"] == 0
        assert s["success_rate"] == 0.0

    def test_percentiles(self, tmp_path):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "perc.jsonl")
        durations = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        records = [_make_record(i + 1, duration_ms=float(d)) for i, d in enumerate(durations)]
        _write_jsonl(records, path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        s = analyzer.summary()
        assert s["avg_duration_ms"] == 550.0
        assert "p50_duration_ms" in s
        assert "p95_duration_ms" in s


class TestPrintReport:
    def test_print_does_not_crash(self, tmp_path, capsys):
        from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

        path = str(tmp_path / "print.jsonl")
        _write_jsonl([_make_record(1), _make_record(2)], path)
        analyzer = BenchmarkAnalyzer(path)
        analyzer.load()
        analyzer.print_report()
        captured = capsys.readouterr()
        assert "Benchmark Report" in captured.out
        assert "browser_click" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/test_benchmark/test_analyzer.py::TestSummary tests/unit/test_benchmark/test_analyzer.py::TestPrintReport -v`
Expected: FAIL with `AttributeError: 'BenchmarkAnalyzer' object has no attribute 'summary'`

- [ ] **Step 3: Implement summary + print_report**

在 `zerotoken/benchmark/analyzer.py` 的 `BenchmarkAnalyzer` 类末尾追加：

```python
    # ---- 汇总报告 ----

    def summary(self) -> dict[str, Any]:
        """生成结构化汇总报告"""
        total = len(self.records)
        if total == 0:
            return {
                "session_id": None,
                "total_calls": 0,
                "success_count": 0,
                "fail_count": 0,
                "success_rate": 0.0,
                "total_duration_ms": 0.0,
                "avg_duration_ms": 0.0,
                "p50_duration_ms": 0.0,
                "p95_duration_ms": 0.0,
                "by_tool": {},
                "errors": [],
            }

        durations = [r.get("duration_ms", 0) for r in self.records]
        success_count = sum(1 for r in self.records if r.get("success"))
        fail_count = total - success_count
        sorted_d = sorted(durations)

        by_tool: dict[str, dict[str, Any]] = {}
        for r in self.records:
            name = r.get("tool_name", "unknown")
            entry = by_tool.setdefault(name, {
                "count": 0, "success_count": 0,
                "durations": [], "max_duration_ms": 0.0,
            })
            entry["count"] += 1
            if r.get("success"):
                entry["success_count"] += 1
            d = r.get("duration_ms", 0)
            entry["durations"].append(d)
            if d > entry["max_duration_ms"]:
                entry["max_duration_ms"] = d

        by_tool_clean: dict[str, dict[str, Any]] = {}
        for name, entry in by_tool.items():
            by_tool_clean[name] = {
                "count": entry["count"],
                "success_count": entry["success_count"],
                "avg_duration_ms": round(statistics.mean(entry["durations"]), 2),
                "max_duration_ms": entry["max_duration_ms"],
            }

        errors = []
        for r in self.records:
            if r.get("error"):
                errors.append({
                    "seq": r.get("seq"),
                    "tool_name": r.get("tool_name"),
                    "error": r["error"],
                    "duration_ms": r.get("duration_ms", 0),
                })

        return {
            "session_id": self.records[0].get("session_id") if self.records else None,
            "total_calls": total,
            "success_count": success_count,
            "fail_count": fail_count,
            "success_rate": round(success_count / total, 4) if total else 0.0,
            "total_duration_ms": round(sum(durations), 2),
            "avg_duration_ms": round(statistics.mean(durations), 2),
            "p50_duration_ms": round(self._percentile(sorted_d, 50), 2),
            "p95_duration_ms": round(self._percentile(sorted_d, 95), 2),
            "by_tool": by_tool_clean,
            "errors": errors,
        }

    def print_report(self) -> None:
        """格式化输出到终端"""
        s = self.summary()
        sid = s["session_id"] or "unknown"
        print(f"\n=== Benchmark Report: {sid} ===")
        print(f"Total calls:  {s['total_calls']}")
        rate_pct = s['success_rate'] * 100
        print(f"Success:      {s['success_count']} ({rate_pct:.1f}%)")
        print(f"Failed:       {s['fail_count']}")
        print()
        print(
            f"Duration: total={s['total_duration_ms']:.0f}ms, "
            f"avg={s['avg_duration_ms']:.0f}ms, "
            f"p50={s['p50_duration_ms']:.0f}ms, "
            f"p95={s['p95_duration_ms']:.0f}ms"
        )
        print()
        if s["by_tool"]:
            print("By Tool:")
            for name, info in s["by_tool"].items():
                unit = "call" if info["count"] == 1 else "calls"
                ok_pct = (info["success_count"] / info["count"] * 100) if info["count"] else 0
                print(
                    f"  {name:<22} {info['count']} {unit:<5} "
                    f"avg={info['avg_duration_ms']:.0f}ms  "
                    f"max={info['max_duration_ms']:.0f}ms  "
                    f"{ok_pct:.0f}% ok"
                )
            print()
        if s["errors"]:
            print("Errors:")
            for e in s["errors"]:
                print(f"  #{e['seq']} {e['tool_name']}: {e['error']}")
            print()

    @staticmethod
    def _percentile(sorted_values: list[float], pct: float) -> float:
        """计算百分位数"""
        if not sorted_values:
            return 0.0
        k = (len(sorted_values) - 1) * (pct / 100)
        f = int(k)
        c = f + 1
        if c >= len(sorted_values):
            return sorted_values[-1]
        d = k - f
        return sorted_values[f] + d * (sorted_values[c] - sorted_values[f])
```

- [ ] **Step 4: Update __init__.py to export BenchmarkAnalyzer**

修改 `zerotoken/benchmark/__init__.py`：

```python
"""Benchmark 模块"""
from .recorder import BenchmarkRecorder
from .analyzer import BenchmarkAnalyzer

__all__ = ["BenchmarkRecorder", "BenchmarkAnalyzer"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/test_benchmark/test_analyzer.py -v`
Expected: All 16 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/benchmark/analyzer.py zerotoken/benchmark/__init__.py tests/unit/test_benchmark/test_analyzer.py
git commit -m "feat(benchmark): add summary and print_report to BenchmarkAnalyzer"
```

---

### Task 5: BenchmarkRunner -- 场景执行

**Files:**
- Create: `zerotoken/benchmark/runner.py`
- Create: `tests/unit/test_benchmark/test_runner.py`

Runner 的单元测试需要 mock `dispatch`，不需要真实浏览器。

- [ ] **Step 1: Write failing tests for RunResult/StepError dataclasses and YAML loading**

创建 `tests/unit/test_benchmark/test_runner.py`：

```python
"""BenchmarkRunner 单元测试（mock dispatch，不需要真实浏览器）"""
import json
import os
import tempfile
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

        with patch("zerotoken.benchmark.runner.dispatch", mock_dispatch), \
             patch("zerotoken.benchmark.runner.init_services"):
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

        with patch("zerotoken.benchmark.runner.dispatch", side_effect=mock_dispatch_fn), \
             patch("zerotoken.benchmark.runner.init_services"):
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

        with patch("zerotoken.benchmark.runner.dispatch", mock_dispatch), \
             patch("zerotoken.benchmark.runner.init_services"):
            runner = BenchmarkRunner(output_dir=output_dir)
            result = await runner.run_scenario(path)

        with open(result.jsonl_path) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 3
        assert lines[0]["tool_name"] == "browser_init"
        assert lines[2]["tool_name"] == "browser_close"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/test_benchmark/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'zerotoken.benchmark.runner'`

- [ ] **Step 3: Implement BenchmarkRunner**

创建 `zerotoken/benchmark/runner.py`：

```python
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
        from zerotoken.repository.sqlite import (
            new_connection, SQLiteTrajectoryRepo,
        )
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/test_benchmark/test_runner.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/benchmark/runner.py tests/unit/test_benchmark/test_runner.py
git commit -m "feat(benchmark): add BenchmarkRunner for scenario execution"
```

---

### Task 6: CLI 工具

**Files:**
- Create: `benchmark_cli.py`

- [ ] **Step 1: Implement benchmark_cli.py**

创建 `benchmark_cli.py`（项目根目录）：

```python
"""Benchmark CLI -- 批量场景执行 + JSONL 分析

用法:
    python benchmark_cli.py run <scenario.yaml>           # 运行单个场景
    python benchmark_cli.py run-all <dir/> [--tag <tag>]  # 批量运行
    python benchmark_cli.py replay <task_id>              # 回放轨迹
    python benchmark_cli.py analyze <file.jsonl>          # 分析 JSONL
    python benchmark_cli.py analyze --latest              # 分析最新 JSONL
    python benchmark_cli.py analyze-all <dir/>            # 批量分析
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import os
import sys


def _find_latest_jsonl(directory: str) -> str | None:
    """在目录中找到最新的 JSONL 文件"""
    pattern = os.path.join(directory, "*.jsonl")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def _analyze_file(path: str) -> None:
    """分析单个 JSONL 文件"""
    from zerotoken.benchmark.analyzer import BenchmarkAnalyzer

    analyzer = BenchmarkAnalyzer(path)
    analyzer.load()
    violations = analyzer.validate_all()
    has_issues = False
    for name, issues in violations.items():
        if issues:
            has_issues = True
            print(f"\n[WARN] {name}:")
            for issue in issues:
                print(f"  - {issue}")
    if not has_issues:
        print("[OK] All assertions passed")
    analyzer.print_report()


async def cmd_run(args: argparse.Namespace) -> None:
    """执行单个场景"""
    from zerotoken.benchmark.runner import BenchmarkRunner

    runner = BenchmarkRunner(output_dir=args.output_dir)
    try:
        result = await runner.run_scenario(args.scenario)
        print(f"\nScenario: {result.scenario_name}")
        print(f"Steps: {result.success_steps}/{result.total_steps} passed")
        print(f"Duration: {result.total_duration_ms:.0f}ms")
        print(f"JSONL: {result.jsonl_path}")
        if result.errors:
            print("\nErrors:")
            for e in result.errors:
                print(f"  #{e.seq} {e.action}: {e.error}")
        _analyze_file(result.jsonl_path)
    finally:
        await runner.cleanup()


async def cmd_run_all(args: argparse.Namespace) -> None:
    """批量执行场景"""
    from zerotoken.benchmark.runner import BenchmarkRunner

    pattern = os.path.join(args.directory, "*.yaml")
    scenario_paths = sorted(glob.glob(pattern))
    if not scenario_paths:
        print(f"No YAML scenarios found in {args.directory}")
        return

    runner = BenchmarkRunner(output_dir=args.output_dir)
    try:
        tags = [args.tag] if args.tag else None
        batch = await runner.run_batch(scenario_paths, tags=tags)
        print(f"\n=== Batch Result ===")
        print(f"Scenarios: {batch.passed_scenarios}/{batch.total_scenarios} passed")
        print(f"Total duration: {batch.total_duration_ms:.0f}ms")
        for r in batch.results:
            status = "PASS" if r.failed_steps == 0 else "FAIL"
            print(f"  [{status}] {r.scenario_name} ({r.success_steps}/{r.total_steps})")
            _analyze_file(r.jsonl_path)
    finally:
        await runner.cleanup()


async def cmd_replay(args: argparse.Namespace) -> None:
    """回放轨迹"""
    from zerotoken.benchmark.runner import BenchmarkRunner

    runner = BenchmarkRunner(output_dir=args.output_dir)
    try:
        result = await runner.run_replay(args.task_id)
        print(f"\nReplay: {result.scenario_name}")
        print(f"Steps: {result.success_steps}/{result.total_steps} passed")
        print(f"Duration: {result.total_duration_ms:.0f}ms")
        print(f"JSONL: {result.jsonl_path}")
        _analyze_file(result.jsonl_path)
    finally:
        await runner.cleanup()


def cmd_analyze(args: argparse.Namespace) -> None:
    """分析 JSONL"""
    if args.latest:
        path = _find_latest_jsonl(args.output_dir)
        if not path:
            print(f"No JSONL files found in {args.output_dir}")
            return
    else:
        path = args.file
        if not path:
            print("Please specify a JSONL file or use --latest")
            return

    print(f"Analyzing: {path}")
    _analyze_file(path)


def cmd_analyze_all(args: argparse.Namespace) -> None:
    """批量分析"""
    pattern = os.path.join(args.directory, "*.jsonl")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No JSONL files found in {args.directory}")
        return

    for path in files:
        print(f"\n--- {os.path.basename(path)} ---")
        _analyze_file(path)


def main():
    parser = argparse.ArgumentParser(description="Benchmark CLI")
    parser.add_argument(
        "--output-dir", default="benchmarks",
        help="benchmark JSONL 输出目录（默认 benchmarks/）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="运行单个场景")
    p_run.add_argument("scenario", help="场景 YAML 文件路径")

    p_run_all = sub.add_parser("run-all", help="批量运行场景")
    p_run_all.add_argument("directory", help="场景 YAML 目录")
    p_run_all.add_argument("--tag", help="按标签筛选")

    p_replay = sub.add_parser("replay", help="回放轨迹")
    p_replay.add_argument("task_id", help="轨迹 task_id")

    p_analyze = sub.add_parser("analyze", help="分析 JSONL 文件")
    p_analyze.add_argument("file", nargs="?", help="JSONL 文件路径")
    p_analyze.add_argument("--latest", action="store_true", help="分析最新的 JSONL")

    p_analyze_all = sub.add_parser("analyze-all", help="批量分析 JSONL")
    p_analyze_all.add_argument("directory", help="JSONL 目录")

    args = parser.parse_args()
    if args.command in ("run", "run-all", "replay"):
        asyncio.run({"run": cmd_run, "run-all": cmd_run_all, "replay": cmd_replay}[args.command](args))
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "analyze-all":
        cmd_analyze_all(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI help works**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python benchmark_cli.py --help`
Expected: 输出帮助信息，显示 run / run-all / replay / analyze / analyze-all 子命令

- [ ] **Step 3: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add benchmark_cli.py
git commit -m "feat(benchmark): add CLI tool for scenario execution and JSONL analysis"
```

---

### Task 7: 预置测试场景

**Files:**
- Create: `benchmark_scenarios/bilibili_browse.yaml`
- Create: `benchmark_scenarios/baidu_search.yaml`
- Create: `benchmark_scenarios/github_explore.yaml`

- [ ] **Step 1: Create bilibili_browse.yaml**

```yaml
name: "bilibili_browse"
description: "打开B站首页，获取推荐视频文本，截图，关闭"
tags: ["bilibili", "basic"]
timeout_seconds: 120

steps:
  - action: browser_init
    params:
      headless: false
      stealth: true

  - action: browser_open
    params:
      url: "https://www.bilibili.com"

  - action: browser_wait_for
    params:
      selector: ".bili-video-card"
      timeout: 15000

  - action: browser_get_text
    params:
      selector: ".bili-video-card:first-child"
      include_screenshot: false

  - action: browser_screenshot
    params: {}

  - action: browser_close
    params: {}
```

- [ ] **Step 2: Create baidu_search.yaml**

```yaml
name: "baidu_search"
description: "打开百度，搜索关键词，获取结果文本，截图，关闭"
tags: ["baidu", "search"]
timeout_seconds: 120

steps:
  - action: browser_init
    params:
      headless: false

  - action: browser_open
    params:
      url: "https://www.baidu.com"

  - action: browser_wait_for
    params:
      selector: "#kw"
      timeout: 10000

  - action: browser_input
    params:
      selector: "#kw"
      text: "ZeroToken MCP"

  - action: browser_click
    params:
      selector: "#su"

  - action: browser_wait_for
    params:
      selector: "#content_left"
      timeout: 10000

  - action: browser_get_text
    params:
      selector: "#content_left"
      include_screenshot: false

  - action: browser_screenshot
    params: {}

  - action: browser_close
    params: {}
```

- [ ] **Step 3: Create github_explore.yaml**

```yaml
name: "github_explore"
description: "打开 GitHub Trending 页面，获取仓库列表，截图，关闭"
tags: ["github", "explore"]
timeout_seconds: 120

steps:
  - action: browser_init
    params:
      headless: false

  - action: browser_open
    params:
      url: "https://github.com/trending"

  - action: browser_wait_for
    params:
      selector: "article.Box-row"
      timeout: 15000

  - action: browser_get_text
    params:
      selector: "article.Box-row:first-child"
      include_screenshot: false

  - action: browser_screenshot
    params: {}

  - action: browser_close
    params: {}
```

- [ ] **Step 4: Verify YAML files are valid**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -c "import yaml; [yaml.safe_load(open(f)) for f in ['benchmark_scenarios/bilibili_browse.yaml', 'benchmark_scenarios/baidu_search.yaml', 'benchmark_scenarios/github_explore.yaml']]; print('All valid')"` Expected: `All valid`

- [ ] **Step 5: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add benchmark_scenarios/
git commit -m "feat(benchmark): add 3 real-site test scenarios (bilibili, baidu, github)"
```

---

### Task 8: pytest 集成测试 + marker 注册

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_benchmark_e2e.py`
- Modify: `pyproject.toml`（或 `pytest.ini`）添加 `integration` marker

- [ ] **Step 1: Check existing pytest config**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && cat pyproject.toml 2>/dev/null || cat pytest.ini 2>/dev/null || echo "no config found"`

查看现有的 pytest 配置位置以决定在哪里注册 marker。

- [ ] **Step 2: Register integration marker**

如果用 `pyproject.toml`，在 `[tool.pytest.ini_options]` 下添加：

```toml
[tool.pytest.ini_options]
markers = [
    "integration: E2E integration tests requiring real browser (deselect by default)",
]
```

如果用 `pytest.ini`，添加：

```ini
[pytest]
markers =
    integration: E2E integration tests requiring real browser (deselect by default)
```

- [ ] **Step 3: Create integration test package and E2E tests**

创建 `tests/integration/__init__.py`（空文件）。

创建 `tests/integration/test_benchmark_e2e.py`：

```python
"""Benchmark E2E 集成测试

需要真实浏览器环境，使用 @pytest.mark.integration 标记。
运行: pytest -m integration tests/integration/
"""
import os

import pytest

from zerotoken.benchmark.analyzer import BenchmarkAnalyzer
from zerotoken.benchmark.runner import BenchmarkRunner

_SCENARIOS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "benchmark_scenarios"
)


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
```

- [ ] **Step 4: Verify unit tests still pass (integration tests excluded by default)**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest tests/unit/ -v --tb=short -q`
Expected: All unit tests PASS

- [ ] **Step 5: Verify integration marker is recognized**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && python -m pytest --markers | grep integration`
Expected: 显示 `integration: E2E integration tests requiring real browser`

- [ ] **Step 6: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add tests/integration/ pyproject.toml
git commit -m "feat(benchmark): add E2E integration tests with real-site scenarios"
```

---

## Self-Review

### Spec Coverage

| Spec Section | Task |
|---|---|
| BenchmarkRecorder.force_enable | Task 1 |
| mcp_server 接口暴露 | Task 2 |
| BenchmarkAnalyzer 断言 | Task 3 |
| BenchmarkAnalyzer 汇总报告 | Task 4 |
| BenchmarkRunner 场景执行 + 轨迹回放 | Task 5 |
| CLI 工具 | Task 6 |
| 预置场景 YAML | Task 7 |
| pytest 集成测试 | Task 8 |

### Type/Name Consistency

- `BenchmarkRecorder(output_dir, force_enable)` -- Task 1 定义，Task 5 使用
- `init_services()`, `dispatch()`, `get_recorder()` -- Task 2 定义，Task 5 导入
- `BenchmarkAnalyzer(jsonl_path)` + `.load()` + `.validate_all()` + `.summary()` + `.print_report()` -- Task 3/4 定义，Task 6/8 使用
- `BenchmarkRunner(output_dir)` + `.run_scenario()` + `.run_replay()` + `.run_batch()` + `.cleanup()` -- Task 5 定义，Task 6/8 使用
- `RunResult`, `BatchResult`, `StepError` -- Task 5 定义，Task 6 使用
