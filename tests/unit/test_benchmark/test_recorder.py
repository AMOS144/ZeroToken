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


def test_screenshot_truncated_in_summary(monkeypatch):
    """screenshot base64 应被截断为 '<N bytes>' 格式"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "1")
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    d = tempfile.mkdtemp()
    rec = BenchmarkRecorder(output_dir=d)
    big_screenshot = "x" * 200000
    result = [{"type": "text", "text": json.dumps({"success": True, "screenshot": big_screenshot})}]
    rec.record("browser_click", {}, result, 100.0, None)
    with open(os.path.join(d, os.listdir(d)[0])) as f:
        data = json.loads(f.readline())
    assert "200000 bytes" in data["result_summary"]["screenshot"]
    assert len(data["result_summary"]["screenshot"]) < 100


def test_large_string_truncated(monkeypatch):
    """超过 1024 字节的字符串值应被截断"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "1")
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    d = tempfile.mkdtemp()
    rec = BenchmarkRecorder(output_dir=d)
    big_html = "a" * 5000
    result = [{"type": "text", "text": json.dumps({"success": True, "html": big_html})}]
    rec.record("browser_get_html", {}, result, 50.0, None)
    with open(os.path.join(d, os.listdir(d)[0])) as f:
        data = json.loads(f.readline())
    assert data["result_summary"]["html"].endswith("... <5000 chars>")
    assert len(data["result_summary"]["html"]) < 300


def test_result_size_bytes_correct(monkeypatch):
    """result_size_bytes 应反映原始 JSON 的字节大小"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "1")
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    d = tempfile.mkdtemp()
    rec = BenchmarkRecorder(output_dir=d)
    payload = json.dumps({"success": True, "data": "hello"})
    result = [{"type": "text", "text": payload}]
    rec.record("browser_evaluate", {}, result, 10.0, None)
    with open(os.path.join(d, os.listdir(d)[0])) as f:
        data = json.loads(f.readline())
    assert data["result_size_bytes"] == len(payload.encode("utf-8"))


def test_recorder_exception_does_not_propagate(monkeypatch):
    """recorder 内部 IO 异常不应向外传播"""
    monkeypatch.setenv("ZEROTOKEN_BENCHMARK", "1")
    from zerotoken.benchmark.recorder import BenchmarkRecorder

    rec = BenchmarkRecorder(output_dir="/nonexistent/path/that/should/fail")
    # 不应抛出异常
    rec.record("browser_click", {}, None, 10.0, None)


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
