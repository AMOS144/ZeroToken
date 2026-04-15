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
import uuid
from datetime import datetime
from typing import IO, Any


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
