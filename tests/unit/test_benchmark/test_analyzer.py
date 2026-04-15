"""BenchmarkAnalyzer 单元测试"""
import json


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
