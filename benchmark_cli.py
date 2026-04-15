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
