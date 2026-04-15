# Benchmark Recorder 设计文档

## 概述

为 ZeroToken v2 MCP Server 添加全链路 benchmark 记录能力，记录每次 MCP 工具调用的完整上下文（工具名、参数、返回摘要、耗时、成功/失败），输出为 JSONL 文件，供开发阶段排查问题和优化使用。

## 目标与非目标

**目标**：
- 记录 MCP Server 侧每次 `call_tool` 的输入、输出摘要、耗时、异常
- JSONL 文件存储，一次进程生命周期一个文件
- 环境变量开关，默认关闭，零运行时开销
- 对现有代码侵入最小

**非目标**：
- 不采集 AI 客户端侧的 prompt/response/token 用量
- 不做 pipeline 内部分阶段耗时（可后续增量添加）
- 不做自动清理/归档
- 不提供 MCP 查询工具（JSONL 直接用 grep/jq 查看）

## 数据结构

### ToolCallRecord

每次工具调用记录一条，对应 JSONL 中的一行：

```json
{
  "session_id": "20260414_153201_a1b2c3",
  "call_id": "uuid-v4",
  "seq": 1,
  "timestamp": "2026-04-14T15:32:01.234567",
  "tool_name": "browser_click",
  "args": {"selector": "#btn", "include_screenshot": false},
  "duration_ms": 342.5,
  "success": true,
  "result_summary": {"action": "click", "page_url": "https://example.com"},
  "error": null,
  "error_code": null,
  "result_size_bytes": 1523
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | str | 进程级唯一，格式 `{YYYYMMDD}_{HHMMSS}_{6位uuid}` |
| `call_id` | str | 单次调用唯一标识（UUID v4） |
| `seq` | int | 同一 session 内的调用序号（从 1 自增） |
| `timestamp` | str | ISO 格式调用开始时间 |
| `tool_name` | str | MCP 工具名，如 `browser_click` |
| `args` | dict | 原始调用参数，完整保留 |
| `duration_ms` | float | 总耗时（毫秒），从进入 call_tool 到返回 |
| `success` | bool | 工具调用是否成功 |
| `result_summary` | dict | 返回值摘要（大体积数据已截断） |
| `error` | str/null | 异常信息 |
| `error_code` | str/null | 错误码（从返回的 JSON 提取） |
| `result_size_bytes` | int | 原始返回值的 JSON 序列化字节数 |

### 结果摘要规则

`result_summary` 从 `TextContent[]` 返回值中提取 JSON，然后按以下规则处理：

- `screenshot` 字段：替换为 `"<{len} bytes>"`
- 超过 1024 字节的字符串值：截断为前 200 字符 + `"... <{total} chars>"`
- `success`、`error`、`url`、`action` 等常规字段：原样保留

## 架构

### 新增文件

```
zerotoken/benchmark/
├── __init__.py          # re-export BenchmarkRecorder
└── recorder.py          # BenchmarkRecorder 实现
```

### 修改文件

```
mcp_server.py            # call_tool 中添加 benchmark 包装（~15 行）
```

### 不修改的文件

- handler 层、service 层、pipeline 层 -- 零改动
- trajectory 系统 -- 完全独立
- SQLite 数据库 -- 不涉及

### 组件设计

```
BenchmarkRecorder
├── __init__(output_dir="benchmarks")
│   ├── 读取 ZEROTOKEN_BENCHMARK 环境变量
│   ├── enabled=False 时所有方法为 no-op
│   ├── 生成 session_id
│   └── seq = 0
├── record(name, args, result, duration_ms, error)
│   ├── seq += 1
│   ├── 构建 ToolCallRecord dict
│   ├── _summarize_result(result) 提取摘要
│   ├── json.dumps + '\n' 写入文件
│   └── 内部异常静默处理（不影响正常工具调用）
├── _summarize_result(result: list[TextContent]) -> dict
│   ├── 解析 TextContent.text 为 JSON
│   ├── 截断 screenshot 和大字符串
│   └── 计算 result_size_bytes
└── _ensure_file() -> IO
    └── 惰性创建输出目录和文件
```

### call_tool 集成方式

```python
# mcp_server.py

_recorder = BenchmarkRecorder()

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
```

原有 handler dispatch 逻辑提取为 `_dispatch(name, arguments)` 内部函数，逻辑不变。

## 开关机制

环境变量 `ZEROTOKEN_BENCHMARK`：

- `= "1"` 或 `= "true"`：启用记录
- 不设置或为空：不记录（`BenchmarkRecorder.record` 立即返回）

在 Cursor MCP 配置中启用：

```json
{
  "mcpServers": {
    "zerotoken-v2": {
      "command": "uv",
      "args": ["run", ...],
      "env": {"ZEROTOKEN_BENCHMARK": "1"}
    }
  }
}
```

## 文件管理

- **路径**：`{mcp_server.py 所在目录}/benchmarks/{session_id}.jsonl`
- **session_id 格式**：`{YYYYMMDD}_{HHMMSS}_{6位uuid}`，如 `20260414_153201_a1b2c3`
- **创建时机**：首次 `record()` 调用时惰性创建目录和文件
- **关闭时机**：进程退出时通过 `atexit` 注册关闭文件句柄
- **并发安全**：`threading.Lock` 保护写入
- **不做自动清理**：文件通常很小，用户手动管理

## 典型输出示例

一次 "打开 B 站 + 点击三个视频 + 关闭" 的会话（约 20 次调用，< 40KB）：

```jsonl
{"session_id":"20260414_153201_a1b2c3","call_id":"...","seq":1,"timestamp":"...","tool_name":"browser_init","args":{"headless":false,"stealth":true},"duration_ms":1523.4,"success":true,"result_summary":{"success":true,"message":"Browser initialized"},"error":null,"error_code":null,"result_size_bytes":52}
{"session_id":"20260414_153201_a1b2c3","call_id":"...","seq":2,"timestamp":"...","tool_name":"browser_open","args":{"url":"https://bilibili.com"},"duration_ms":3842.1,"success":true,"result_summary":{"action":"open","page_url":"https://www.bilibili.com/","screenshot":"<245832 bytes>"},"error":null,"error_code":null,"result_size_bytes":245901}
```

## 测试策略

- `BenchmarkRecorder` 单元测试：启用/禁用开关、record 写入格式、result 摘要截断规则、异常隔离
- `mcp_server.py` 集成：mock `_dispatch`，验证 benchmark record 被正确调用
- 不需要端到端测试（benchmark 本身是被动观测，不影响功能正确性）
