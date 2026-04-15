"""Benchmark JSONL 分析器

读取 BenchmarkRecorder 输出的 JSONL 文件，提供自动断言和汇总报告。
"""
from __future__ import annotations

import json
import statistics
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
            entry = by_tool.setdefault(
                name,
                {
                    "count": 0,
                    "success_count": 0,
                    "durations": [],
                    "max_duration_ms": 0.0,
                },
            )
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
                errors.append(
                    {
                        "seq": r.get("seq"),
                        "tool_name": r.get("tool_name"),
                        "error": r["error"],
                        "duration_ms": r.get("duration_ms", 0),
                    }
                )

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
        s = self.summary()
        sid = s["session_id"] or "unknown"
        print(f"\n=== Benchmark Report: {sid} ===")
        print(f"Total calls:  {s['total_calls']}")
        rate_pct = s["success_rate"] * 100
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
        """在已排序样本上用线性插值计算分位数（如 p50、p95）。"""
        if not sorted_values:
            return 0.0
        k = (len(sorted_values) - 1) * (pct / 100)
        f = int(k)
        c = f + 1
        if c >= len(sorted_values):
            return sorted_values[-1]
        d = k - f
        return sorted_values[f] + d * (sorted_values[c] - sorted_values[f])

    def validate_all(self) -> dict[str, list[str]]:
        return {
            "completeness": self.assert_completeness(),
            "sequence": self.assert_sequence(),
            "timing": self.assert_timing(),
            "errors": self.assert_no_unhandled_errors(),
        }
