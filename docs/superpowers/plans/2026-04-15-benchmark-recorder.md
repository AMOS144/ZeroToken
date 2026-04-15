# Benchmark Recorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JSONL-based MCP tool call tracing to ZeroToken v2, recording every `call_tool` invocation's name, args, result summary, duration, and errors.

**Architecture:** A single `BenchmarkRecorder` class wraps the existing `call_tool` dispatch in `mcp_server.py`. It writes one JSONL line per tool call, with large data (screenshots) truncated. Controlled by `ZEROTOKEN_BENCHMARK` env var, default off.

**Tech Stack:** Python 3.12, stdlib only (json, uuid, time, threading, os, atexit, datetime)

**Spec:** `docs/superpowers/specs/2026-04-15-benchmark-recorder-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `zerotoken/benchmark/__init__.py` | Create | Re-export `BenchmarkRecorder` |
| `zerotoken/benchmark/recorder.py` | Create | `BenchmarkRecorder` 实现 |
| `tests/unit/test_benchmark/test_recorder.py` | Create | BenchmarkRecorder 单元测试 |
| `tests/unit/test_benchmark/__init__.py` | Create | 测试包 |
| `mcp_server.py` | Modify | 集成 benchmark 包装 |

---

### Task 1: BenchmarkRecorder 核心 -- 开关 + 惰性文件 + record 写入

**Files:**
- Create: `zerotoken/benchmark/__init__.py`
- Create: `zerotoken/benchmark/recorder.py`
- Create: `tests/unit/test_benchmark/__init__.py`
- Create: `tests/unit/test_benchmark/test_recorder.py`

- [ ] **Step 1: Write the failing tests**

```python
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
    rec.record("browser_click", {"selector": "#btn"}, [{"type": "text", "text": '{"success": true}'}], 42.5, None)
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
```

- [ ] **Step 2: Create empty module so imports work, run tests to verify they fail**

```python
# zerotoken/benchmark/__init__.py
"""Benchmark 模块"""
from .recorder import BenchmarkRecorder

__all__ = ["BenchmarkRecorder"]
```

```python
# zerotoken/benchmark/recorder.py
"""BenchmarkRecorder 占位"""
class BenchmarkRecorder:
    pass
```

```python
# tests/unit/test_benchmark/__init__.py
```

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_benchmark/test_recorder.py -v`
Expected: FAIL (missing attributes/methods)

- [ ] **Step 3: Implement BenchmarkRecorder**

```python
# zerotoken/benchmark/recorder.py
"""MCP 工具调用 Benchmark 记录器

在 call_tool 入口处包装，记录每次调用的名称、参数、结果摘要、耗时、异常。
输出 JSONL 文件，按 session（进程生命周期）分文件。
通过 ZEROTOKEN_BENCHMARK 环境变量控制开关。
"""
from __future__ import annotations

import atexit
import json
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Any, IO


class BenchmarkRecorder:
    """MCP 工具调用的 JSONL 记录器"""

    def __init__(self, output_dir: str = "benchmarks"):
        self._output_dir = output_dir
        env_val = os.environ.get("ZEROTOKEN_BENCHMARK", "").strip().lower()
        self.enabled = env_val in ("1", "true")
        self.session_id = self._make_session_id()
        self._seq = 0
        self._lock = threading.Lock()
        self._file: IO | None = None
        if self.enabled:
            atexit.register(self._close_file)

    def record(
        self,
        name: str,
        args: dict[str, Any],
        result: Any,
        duration_ms: float,
        error: Exception | None,
    ) -> None:
        """记录一次工具调用。内部异常静默处理，不影响正常调用。"""
        if not self.enabled:
            return
        try:
            self._write_record(name, args, result, duration_ms, error)
        except Exception:
            pass

    def _write_record(
        self,
        name: str,
        args: dict[str, Any],
        result: Any,
        duration_ms: float,
        error: Exception | None,
    ) -> None:
        with self._lock:
            self._seq += 1
            seq = self._seq

        result_summary, result_size, error_code = self._summarize_result(result)

        record = {
            "session_id": self.session_id,
            "call_id": str(uuid.uuid4()),
            "seq": seq,
            "timestamp": datetime.now().isoformat(),
            "tool_name": name,
            "args": args,
            "duration_ms": round(duration_ms, 2),
            "success": error is None and self._is_success(result_summary),
            "result_summary": result_summary,
            "error": str(error) if error else None,
            "error_code": error_code,
            "result_size_bytes": result_size,
        }

        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            f = self._ensure_file()
            f.write(line)
            f.flush()

    def _summarize_result(self, result: Any) -> tuple[dict, int, str | None]:
        """从 TextContent 列表提取结果摘要，截断大体积数据。
        返回 (摘要 dict, 原始字节数, 错误码)。
        """
        if result is None:
            return {}, 0, None

        raw_texts = []
        for item in result:
            text = getattr(item, "text", None) or (item.get("text") if isinstance(item, dict) else None)
            if text:
                raw_texts.append(text)

        raw_json = "".join(raw_texts)
        result_size = len(raw_json.encode("utf-8"))

        try:
            parsed = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            return {"_raw_preview": raw_json[:500]}, result_size, None

        if not isinstance(parsed, dict):
            return {"_value": str(parsed)[:500]}, result_size, None

        summary = {}
        error_code = parsed.get("code")
        for k, v in parsed.items():
            if k == "screenshot" and isinstance(v, str):
                summary[k] = f"<{len(v)} bytes>"
            elif isinstance(v, str) and len(v) > 1024:
                summary[k] = v[:200] + f"... <{len(v)} chars>"
            else:
                summary[k] = v
        return summary, result_size, error_code

    @staticmethod
    def _is_success(summary: dict) -> bool:
        """从结果摘要判断是否成功"""
        if "success" in summary:
            return bool(summary["success"])
        if "error" in summary and summary["error"]:
            return False
        return True

    def _ensure_file(self) -> IO:
        """惰性创建输出目录和文件"""
        if self._file is None:
            os.makedirs(self._output_dir, exist_ok=True)
            path = os.path.join(self._output_dir, f"{self.session_id}.jsonl")
            self._file = open(path, "a", encoding="utf-8")
        return self._file

    def _close_file(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    @staticmethod
    def _make_session_id() -> str:
        now = datetime.now()
        short_uuid = uuid.uuid4().hex[:6]
        return f"{now.strftime('%Y%m%d_%H%M%S')}_{short_uuid}"
```

- [ ] **Step 4: Run tests to verify they all pass**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_benchmark/test_recorder.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/benchmark/__init__.py zerotoken/benchmark/recorder.py \
       tests/unit/test_benchmark/__init__.py tests/unit/test_benchmark/test_recorder.py
git commit -m "feat: add BenchmarkRecorder with JSONL output and env-var toggle"
```

---

### Task 2: 结果摘要截断测试

**Files:**
- Modify: `tests/unit/test_benchmark/test_recorder.py`

- [ ] **Step 1: Write the failing tests for result summarization**

在 `tests/unit/test_benchmark/test_recorder.py` 末尾追加：

```python
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
```

- [ ] **Step 2: Run tests to verify they pass (implementation already handles these)**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_benchmark/test_recorder.py -v`
Expected: 12 passed

- [ ] **Step 3: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add tests/unit/test_benchmark/test_recorder.py
git commit -m "test: add result summarization and error isolation tests for BenchmarkRecorder"
```

---

### Task 3: 集成到 mcp_server.py

**Files:**
- Modify: `mcp_server.py:1-85`

- [ ] **Step 1: Modify mcp_server.py to integrate BenchmarkRecorder**

将 `mcp_server.py` 的 `call_tool` 函数改为：

```python
"""ZeroToken MCP Server - 入口点"""
import asyncio
import os
import time

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from zerotoken.repository.sqlite import (
    new_connection, SQLiteScriptRepo, SQLiteTrajectoryRepo,
    SQLiteSessionRepo, SQLiteRuntimeRepo, SQLiteFingerprintRepo, SQLiteBindingRepo,
)
from zerotoken.services import BrowserService, TrajectoryService, ScriptService
from zerotoken.benchmark import BenchmarkRecorder
from handlers.browser_handlers import browser_tools, handle_browser_tool
from handlers.trajectory_handlers import trajectory_tools, handle_trajectory_tool
from handlers.script_handlers import script_tools, handle_script_tool

server = Server("zerotoken")

_db_conn = None
_browser_svc = None
_trajectory_svc = None
_script_svc = None

_benchmark_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmarks")
_recorder = BenchmarkRecorder(output_dir=_benchmark_dir)


def _init_services():
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


@server.list_tools()
async def list_tools():
    return browser_tools() + trajectory_tools() + script_tools()


async def _dispatch(name: str, arguments: dict):
    """工具分发（从 call_tool 提取，供 benchmark 包装）"""
    if name.startswith("browser_"):
        return await handle_browser_tool(name, arguments, _browser_svc, _trajectory_svc)
    elif name.startswith("trajectory_"):
        return await handle_trajectory_tool(name, arguments, _trajectory_svc)
    else:
        return await handle_script_tool(name, arguments, _script_svc, browser_svc=_browser_svc)


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    _init_services()
    start = time.monotonic()
    result = None
    error = None
    try:
        result = await _dispatch(name, arguments)
        return result
    except Exception as e:
        error = e
        raise
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        _recorder.record(name, arguments, result, duration_ms, error)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run(transport: str = "stdio"):
    """入口：支持 stdio 和 streamable-http 两种传输"""
    if transport == "streamable-http":
        from mcp_server_http import run as run_http
        run_http()
    else:
        asyncio.run(main())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ZeroToken MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "streamable-http"],
        default=os.environ.get("ZEROTOKEN_MCP_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()
    run(transport=args.transport)
```

- [ ] **Step 2: Run full test suite to verify no regression**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/ -v --tb=short`
Expected: All tests pass (371+ tests)

- [ ] **Step 3: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add mcp_server.py
git commit -m "feat: integrate BenchmarkRecorder into mcp_server call_tool dispatch"
```

---

### Task 4: 将 benchmarks/ 加入 .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append benchmarks/ to .gitignore**

在 `.gitignore` 末尾追加：

```
# Benchmark JSONL 输出
benchmarks/
```

- [ ] **Step 2: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add .gitignore
git commit -m "chore: add benchmarks/ to .gitignore"
```
