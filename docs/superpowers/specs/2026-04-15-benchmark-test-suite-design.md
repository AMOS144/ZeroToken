# Benchmark Test Suite 设计

## 概述

为 ZeroToken 的 BenchmarkRecorder 构建完整的测试 + 分析体系。通过批量执行真实网站场景和已有轨迹回放，生成 benchmark JSONL 记录，再由 BenchmarkAnalyzer 自动断言 + 汇总报告。

### 目标

1. **生成真实数据** -- 用预定义的真实网站场景和已录制轨迹的回放，批量产出 benchmark JSONL
2. **自动验证** -- 对 JSONL 做字段完整性、序号连续性、耗时合理性等断言
3. **汇总分析** -- 生成成功率、耗时分布（avg/p50/p95）、按工具分组统计、失败明细的结构化报告

### 不做

- 不做 AI 侧数据采集（仅 MCP Server 端）
- 不做性能基准回归（仅做正确性验证和现状报告）
- 不做并发/压力测试

---

## 架构

```
benchmark_scenarios/              # 测试场景 YAML 文件
  bilibili_browse.yaml
  baidu_search.yaml
  github_explore.yaml

zerotoken/benchmark/
  recorder.py                     # [已有] JSONL 记录器
  runner.py                       # [新增] 批量场景执行器
  analyzer.py                     # [新增] JSONL 分析 + 断言

benchmark_cli.py                  # [新增] CLI 入口

tests/integration/
  test_benchmark_e2e.py           # [新增] pytest 集成测试

mcp_server.py                     # [微调] 暴露 init_services / dispatch
```

### 数据流

```
场景 YAML / 轨迹 task_id
       |
       v
  BenchmarkRunner
    -> 解析场景为 MCP call 序列
    -> 初始化 services（复用 mcp_server.init_services）
    -> 依次调 dispatch(action, params) + recorder.record()
    -> 真实浏览器执行
       |
       v
  benchmarks/{session_id}.jsonl    # BenchmarkRecorder 输出
       |
       v
  BenchmarkAnalyzer
    -> 自动断言（字段完整性、耗时范围）
    -> 汇总报告（成功率、耗时分布、失败分析）
```

### 关键决策

1. **进程内模拟 call_tool 链路**：BenchmarkRunner 直接调用 `mcp_server.dispatch()`（经 handler -> service -> pipeline 完整路径），在前后计时并调 `recorder.record()`。不启动 MCP 子进程，不走 stdio 传输。benchmark JSONL 的数据与 Cursor 真实使用时完全一致。

2. **mcp_server.py 接口暴露**：将 `_init_services()` -> `init_services()`、`_dispatch()` -> `dispatch()`、新增 `get_recorder()` 返回模块级 recorder 实例。改动纯粹是命名去掉下划线前缀，逻辑不变。

3. **步骤失败不中断**：场景执行中某步失败时记录错误但继续执行后续步骤，最后统一报告。每个场景结束后无论成败都执行 `browser_close` 清理。

---

## 场景定义格式

场景文件为 YAML，放在 `benchmark_scenarios/` 目录：

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
      selector: ".recommended-card"
      timeout: 10000

  - action: browser_get_text
    params:
      selector: ".recommended-card:first-child"

  - action: browser_screenshot
    params: {}

  - action: browser_close
    params: {}
```

字段说明：
- `name`: 场景唯一标识
- `description`: 人可读描述
- `tags`: 用于 CLI 按标签筛选
- `timeout_seconds`: 整个场景的总超时
- `steps[].action`: MCP 工具名，直接传给 `dispatch(action, params)`
- `steps[].params`: 工具参数 dict

轨迹回放模式不需要 YAML。Runner 从数据库加载 trajectory，用 `trajectory_to_script` 转为 steps，过滤掉 setup 类动作（`browser_init`/`browser_close`/`trajectory_*`），由 Runner 自行管理浏览器生命周期。

---

## BenchmarkRunner

```python
class BenchmarkRunner:
    """批量执行 benchmark 场景"""

    def __init__(self, output_dir: str = "benchmarks"):
        """初始化 services 和 BenchmarkRecorder"""

    async def run_scenario(self, scenario_path: str) -> RunResult:
        """执行单个场景 YAML
        1. 解析 YAML -> steps 列表
        2. 依次执行：dispatch(step.action, step.params)
        3. 前后计时 + recorder.record()
        4. 步骤失败记录错误但继续
        5. 最后 browser_close 清理
        """

    async def run_replay(self, task_id: str) -> RunResult:
        """从轨迹 task_id 回放
        1. 加载 trajectory
        2. trajectory_to_script 转 steps
        3. 过滤 setup 动作
        4. 自动包裹 browser_init + browser_close
        5. 执行流程同 run_scenario
        """

    async def run_batch(
        self, scenarios: list[str], tags: list[str] | None = None
    ) -> BatchResult:
        """批量执行（按 tags 筛选 -> 依次执行 -> 汇总）"""

    async def cleanup(self):
        """关闭浏览器和数据库连接"""
```

### 数据结构

```python
@dataclass
class StepError:
    seq: int              # 步骤序号
    action: str           # 工具名
    error: str            # 错误信息
    duration_ms: float    # 耗时

@dataclass
class RunResult:
    scenario_name: str
    session_id: str       # 对应 JSONL 文件的 session_id
    total_steps: int
    success_steps: int
    failed_steps: int
    total_duration_ms: float
    errors: list[StepError]
    jsonl_path: str       # 生成的 JSONL 文件路径

@dataclass
class BatchResult:
    results: list[RunResult]
    total_scenarios: int
    passed_scenarios: int  # 全部步骤成功的场景数
    total_duration_ms: float
```

### 场景隔离

每个场景独立执行：
- 每个场景创建一个新的 `BenchmarkRecorder` 实例（独立 `session_id`，独立 JSONL 文件）
- 每个场景开始前确保浏览器是干净状态（run_scenario 自行管理 init/close）
- Runner 创建 `BenchmarkRecorder` 时使用 `force_enable=True` 跳过环境变量检查（Runner 场景下始终启用记录）

### BenchmarkRecorder 小改动

为支持 Runner 场景，`BenchmarkRecorder.__init__` 新增可选参数 `force_enable: bool = False`。当 `force_enable=True` 时跳过 `ZEROTOKEN_BENCHMARK` 环境变量检查，直接启用。现有逻辑（默认通过环境变量控制）不受影响。

---

## BenchmarkAnalyzer

```python
class BenchmarkAnalyzer:
    """分析 benchmark JSONL 记录"""

    def __init__(self, jsonl_path: str):
        self.records: list[dict] = []

    def load(self) -> None:
        """加载并解析 JSONL 文件"""

    # --- 自动断言 ---
    def assert_completeness(self) -> list[str]:
        """检查必填字段: session_id, call_id, seq, timestamp,
        tool_name, args, duration_ms, success, result_summary"""

    def assert_sequence(self) -> list[str]:
        """seq 连续递增，无断号"""

    def assert_timing(self, max_ms: float = 60000) -> list[str]:
        """每步耗时不超过 max_ms"""

    def assert_no_unhandled_errors(self) -> list[str]:
        """无未预期的 error"""

    def validate_all(self) -> dict[str, list[str]]:
        """运行全部断言，返回 {断言名: 违规列表}"""

    # --- 汇总报告 ---
    def summary(self) -> dict:
        """生成结构化汇总报告
        包含: session_id, total_calls, success_count, fail_count,
        success_rate, total_duration_ms, avg_duration_ms,
        p50_duration_ms, p95_duration_ms, by_tool, errors
        """

    def print_report(self) -> None:
        """格式化输出到终端"""
```

### 报告输出格式

```
=== Benchmark Report: 20260415_143022_a1b2c3 ===
Total calls:  12
Success:      11 (91.7%)
Failed:       1

Duration: total=8432ms, avg=702ms, p50=320ms, p95=3200ms

By Tool:
  browser_open       2 calls  avg=1200ms  max=2100ms  100% ok
  browser_click      3 calls  avg=350ms   max=800ms   100% ok
  browser_wait_for   3 calls  avg=1500ms  max=3200ms  67% ok
  browser_get_text   2 calls  avg=120ms   max=180ms   100% ok
  browser_screenshot 1 call   avg=400ms   max=400ms   100% ok
  browser_close      1 call   avg=50ms    max=50ms    100% ok

Errors:
  #5 browser_wait_for: TimeoutError - selector ".bpx-player" timeout
```

---

## CLI (`benchmark_cli.py`)

基于 `argparse` 的子命令模式：

```bash
# 运行单个场景
python benchmark_cli.py run benchmark_scenarios/bilibili_browse.yaml

# 批量运行目录下所有场景
python benchmark_cli.py run-all benchmark_scenarios/

# 按标签筛选
python benchmark_cli.py run-all benchmark_scenarios/ --tag bilibili

# 回放轨迹
python benchmark_cli.py replay <task_id>

# 分析已有 JSONL
python benchmark_cli.py analyze benchmarks/20260415_143022_a1b2c3.jsonl

# 分析最新 JSONL
python benchmark_cli.py analyze --latest

# 批量分析
python benchmark_cli.py analyze-all benchmarks/
```

所有 `run` / `run-all` / `replay` 命令执行完后自动输出 Analyzer 报告。

---

## pytest 集成

文件: `tests/integration/test_benchmark_e2e.py`

```python
@pytest.fixture
async def runner(tmp_path):
    r = BenchmarkRunner(output_dir=str(tmp_path))
    yield r
    await r.cleanup()

@pytest.mark.asyncio
@pytest.mark.integration
async def test_bilibili_scenario(runner):
    result = await runner.run_scenario("benchmark_scenarios/bilibili_browse.yaml")
    assert result.failed_steps == 0
    analyzer = BenchmarkAnalyzer(result.jsonl_path)
    analyzer.load()
    violations = analyzer.validate_all()
    for name, issues in violations.items():
        assert len(issues) == 0, f"{name}: {issues}"

@pytest.mark.asyncio
@pytest.mark.integration
async def test_trajectory_replay(runner):
    result = await runner.run_replay("login_demo")
    analyzer = BenchmarkAnalyzer(result.jsonl_path)
    analyzer.load()
    assert len(analyzer.assert_completeness()) == 0
    assert len(analyzer.assert_sequence()) == 0
```

标记策略：
- `@pytest.mark.integration` 标记集成测试
- 默认 `pytest` 不运行，需 `pytest -m integration` 显式触发
- `tests/unit/` 下的单元测试不受影响

---

## mcp_server.py 改动

将以下内部函数改为可导入接口：

| 现有 | 改为 | 说明 |
|------|------|------|
| `_init_services()` | `init_services()` | 去掉前缀，逻辑不变 |
| `_dispatch(name, arguments)` | `dispatch(name, arguments)` | 去掉前缀，逻辑不变 |
| (无) | `get_recorder()` | 返回模块级 `_recorder` 实例 |

`call_tool` 内部相应调用改为新名称。其他逻辑不变。

---

## 预置测试场景

首批 3 个真实网站场景：

1. **`bilibili_browse.yaml`** -- 打开B站 -> 等待推荐卡片 -> 获取文本 -> 截图 -> 关闭
   - 覆盖: `browser_init`, `browser_open`, `browser_wait_for`, `browser_get_text`, `browser_screenshot`, `browser_close`

2. **`baidu_search.yaml`** -- 打开百度 -> 输入搜索词 -> 点击搜索 -> 等待结果 -> 获取文本 -> 截图 -> 关闭
   - 覆盖: 上述 + `browser_input`, `browser_click`

3. **`github_explore.yaml`** -- 打开 GitHub trending -> 等待列表 -> 获取仓库名 -> 截图 -> 关闭
   - 覆盖: 基础浏览操作，无需登录
