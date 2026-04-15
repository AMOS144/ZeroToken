"""Benchmark JSONL 分析器

读取 BenchmarkRecorder 输出的 JSONL 文件，提供自动断言和汇总报告。
"""
from __future__ import annotations

import json
from typing import Any

_REQUIRED_FIELDS = (
    "session_id",
    "call_id",
    "seq",
    "timestamp",
    "tool_name",
    "args",
    "duration_ms",
    "success",
    "result_summary",
)


class BenchmarkAnalyzer:
    """分析 benchmark JSONL 记录"""

    def __init__(self, jsonl_path: str):
        self._path = jsonl_path
        self.records: list[dict[str, Any]] = []

    def load(self) -> None:
        self.records = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.records.append(json.loads(line))

    def assert_completeness(self) -> list[str]:
        violations: list[str] = []
        for r in self.records:
            seq = r.get("seq", "?")
            for field in _REQUIRED_FIELDS:
                if field not in r:
                    violations.append(f"seq={seq}: missing field '{field}'")
        return violations

    def assert_sequence(self) -> list[str]:
        violations: list[str] = []
        seqs = [r.get("seq", 0) for r in self.records]
        for i in range(1, len(seqs)):
            if seqs[i] != seqs[i - 1] + 1:
                violations.append(
                    f"seq gap: {seqs[i - 1]} -> {seqs[i]} (expected {seqs[i - 1] + 1})"
                )
        return violations

    def assert_timing(self, max_ms: float = 60000) -> list[str]:
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
        violations: list[str] = []
        for r in self.records:
            if r.get("error"):
                violations.append(
                    f"seq={r.get('seq', '?')}: {r.get('tool_name', '?')} "
                    f"error: {r['error']}"
                )
        return violations

    def validate_all(self) -> dict[str, list[str]]:
        return {
            "completeness": self.assert_completeness(),
            "sequence": self.assert_sequence(),
            "timing": self.assert_timing(),
            "errors": self.assert_no_unhandled_errors(),
        }
