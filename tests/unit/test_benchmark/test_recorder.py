# tests/unit/test_benchmark/test_recorder.py
"""BenchmarkRecorder 单元测试"""
import json
import os
import tempfile

import pytest


def test_disabled_by_default(monkeypatch):
    """未设置 ZEROTOKEN_BENCHMARK 时，recorder 应处于禁用状态"""
    monkeypatch.delenv("ZEROTOKEN_BENCHMARK", raising=False)
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    rec = BenchmarkRecorder(output_dir=tempfile.mkdtemp())
    assert rec.enabled is False


def test_enabled_by_env(monkeypatch):
    """ZEROTOKEN_BENCHMARK=1 时应启用"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "1")
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    rec = BenchmarkRecorder(output_dir=tempfile.mkdtemp())
    assert rec.enabled is True


def test_enabled_by_env_true(monkeypatch):
    """ZEROTOKEN_BENCHMARK=true 时也应启用"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "true")
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    rec = BenchmarkRecorder(output_dir=tempfile.mkdtemp())
    assert rec.enabled is True


def test_disabled_no_file_created(monkeypatch):
    """禁用时 record() 不应创建任何文件"""
    monkeypatch.delenv("ZEROTOKEN_BENCHMARK", raising=False)
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    d = tempfile.mkdtemp()
    rec = BenchmarkRecorder(output_dir=d)
    rec.record("browser_click", {"selector": "#btn"}, None, 100.0, None)
    assert len(os.listdir(d)) == 0


def test_record_writes_jsonl(monkeypatch):
    """启用时 record() 应写入一条合法的 JSONL"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "1")
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    d = tempfile.mkdtemp()
    rec = BenchmarkRecorder(output_dir=d)
    rec.record(
        "browser_click",
        {"selector": "#btn"},
        [{"type": "text", "text": '{"success": true}'}],
        42.5,
        None,
    )
    files = os.listdir(d)
    assert len(files) == 1
    assert files[0].endswith(".jsonl")
    with open(os.path.join(d, files[0])) as f:
        line = f.readline()
    data = json.loads(line)
    assert data["tool_name"] == "browser_click"
    assert data["args"] == {"selector": "#btn"}
    assert data["duration_ms"] == 42.5
    assert data["success"] is True
    assert data["seq"] == 1


def test_record_seq_increments(monkeypatch):
    """seq 应自增"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "1")
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    d = tempfile.mkdtemp()
    rec = BenchmarkRecorder(output_dir=d)
    rec.record("browser_init", {}, None, 10.0, None)
    rec.record("browser_click", {}, None, 20.0, None)
    files = os.listdir(d)
    with open(os.path.join(d, files[0])) as f:
        lines = f.readlines()
    assert json.loads(lines[0])["seq"] == 1
    assert json.loads(lines[1])["seq"] == 2


def test_record_captures_error(monkeypatch):
    """异常时应记录 error 字段"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "1")
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    d = tempfile.mkdtemp()
    rec = BenchmarkRecorder(output_dir=d)
    rec.record("browser_click", {"selector": "#x"}, None, 50.0, RuntimeError("timeout"))
    files = os.listdir(d)
    with open(os.path.join(d, files[0])) as f:
        data = json.loads(f.readline())
    assert data["success"] is False
    assert "timeout" in data["error"]


def test_session_id_format(monkeypatch):
    """session_id 应为 YYYYMMDD_HHMMSS_6hex 格式"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "1")
    import re

    from zerotoken.benchmark.recorder import BenchmarkRecorder

    rec = BenchmarkRecorder(output_dir=tempfile.mkdtemp())
    assert re.match(r"\d{8}_\d{6}_[a-f0-9]{6}$", rec.session_id)
