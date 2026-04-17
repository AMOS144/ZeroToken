# 脚本生命周期 -- 报废与清理设计

## 背景

当前 `script_delete` 是硬删除，`scripts` 表无任何状态或健康指标。一旦目标网站改版，脚本持续失败，但系统没有任何机制提示 AI 这些脚本已经报废。用户/AI 也不知道哪些脚本能用、哪些需要重建。

## 目标

- 自动识别失效脚本：连续 5 次执行失败时自动打 `warning` 标签
- AI 确认报废机制：AI 根据健康指标判断并调用 `script_deprecate`
- 软删除 + 硬删除两级清理：deprecated 不删数据；`script_delete` 才硬删并级联清理
- 遗弃 session 自愈：永久 paused 的 session 在下次执行时被识别并计入失败

### 不做

- 不做定时后台任务（复杂度过高）
- 不做 API 级 Web 监控面板（ZeroToken 是 MCP 工具，AI 才是消费者）
- 不收集详细执行历史（只保留最近结果 + 聚合计数）

---

## 数据模型

### scripts 表新增字段

```sql
ALTER TABLE scripts ADD COLUMN status TEXT DEFAULT 'active';
ALTER TABLE scripts ADD COLUMN consecutive_failures INTEGER DEFAULT 0;
ALTER TABLE scripts ADD COLUMN total_runs INTEGER DEFAULT 0;
ALTER TABLE scripts ADD COLUMN total_completed INTEGER DEFAULT 0;
ALTER TABLE scripts ADD COLUMN last_run_at TEXT;
ALTER TABLE scripts ADD COLUMN last_run_status TEXT;
ALTER TABLE scripts ADD COLUMN last_session_id TEXT;
ALTER TABLE scripts ADD COLUMN deprecated_at TEXT;
ALTER TABLE scripts ADD COLUMN deprecated_reason TEXT;
```

### 状态机

```
  [active]
    |
    | 连续 5 次失败 (非 completed 的终态)
    v
  [warning]
    |    \
    |     \ AI 调 script_deprecate
    |      v
    |   [deprecated]
    |      |
    |      | script_delete (硬删除 + 级联)
    |      v
    |   [从 DB 移除]
    |
    | 一次 completed
    v
  [active]  <-- warning 状态一次成功即恢复
```

### 状态语义

| 状态 | 语义 | `script_run` 是否允许 | 默认是否在 `script_list` |
|------|------|------|------|
| `active` | 健康 | 允许 | 是 |
| `warning` | 系统预警，AI 应关注 | 允许（AI 可能在尝试修复） | 是 |
| `deprecated` | 已报废 | 拒绝，返回 `SCRIPT_DEPRECATED` | 否 |

### "失败"定义

终态 (terminal status) 中 `!= completed` 的都算失败：
- `failed` -- 非步骤级错误
- `aborted` -- AI 主动放弃
- **被遗弃的 `paused`** -- session 超过 24h 未恢复，下次 `script_run` 同 task_id 时被识别并标记为 `aborted`，计入失败

---

## 失败统计更新

### 触发点：`ScriptEngineV2` 终态位置

现有代码中 `runtime_update` 有 4 处：
1. `paused` -- 非终态，不触发统计
2. `failed` -- 触发
3. `completed` -- 触发
4. `resume` 内 `aborted` -- 触发

每次终态时追加调用：

```python
self._scripts.record_run_result(
    task_id=script.task_id,
    terminal_status=status,   # completed / failed / aborted
    session_id=session_id,
)
```

### `script_repo.record_run_result` 实现

```python
def record_run_result(
    self, task_id: str, terminal_status: str, session_id: str,
) -> dict:
    """更新脚本的执行统计和 status。返回更新后的健康快照。"""
    is_success = (terminal_status == "completed")
    now = datetime.now().isoformat()

    if is_success:
        sql = """
            UPDATE scripts SET
                consecutive_failures = 0,
                total_runs = total_runs + 1,
                total_completed = total_completed + 1,
                last_run_at = ?,
                last_run_status = ?,
                last_session_id = ?,
                status = CASE
                    WHEN status = 'warning' THEN 'active'
                    ELSE status
                END,
                updated_at = ?
            WHERE task_id = ?
        """
    else:
        sql = """
            UPDATE scripts SET
                consecutive_failures = consecutive_failures + 1,
                total_runs = total_runs + 1,
                last_run_at = ?,
                last_run_status = ?,
                last_session_id = ?,
                status = CASE
                    WHEN status = 'active' AND consecutive_failures + 1 >= 5
                    THEN 'warning'
                    ELSE status
                END,
                updated_at = ?
            WHERE task_id = ?
        """
    # 执行，返回新快照
```

返回更新后的快照让引擎把 `auto_warned` 信号带到响应中。

### 遗弃 paused 的清理

新增 `_settle_abandoned_sessions` 在 `script_run` 之前调用：

```python
def _settle_abandoned_sessions(self, task_id: str, ttl_hours: int = 24):
    """查找该脚本超过 ttl 的 paused session，标为 aborted 并计入失败"""
    cutoff = (datetime.now() - timedelta(hours=ttl_hours)).isoformat()
    rows = self._runtime.find_paused_before(task_id, cutoff)
    for row in rows:
        self._runtime.runtime_update(row.session_id, status='aborted')
        self._scripts.record_run_result(task_id, 'aborted', row.session_id)
```

**懒检测策略**：不做后台任务，在 `script_run(task_id)` 被调用时顺手清理该 `task_id` 的遗弃 session。

---

## MCP 工具变更

### 新增工具

#### `script_deprecate`

```
Input:
  task_id: string (required)
  reason: string (optional) -- AI 判断的报废原因

Behavior:
  - 将 scripts.status 设为 'deprecated'
  - 记录 deprecated_at, deprecated_reason
  - 不删除任何数据

Output:
  {success: true, task_id, status: "deprecated", reason}
```

#### `script_restore`

```
Input:
  task_id: string (required)

Behavior:
  - 将 status 从 'deprecated' 恢复为 'active'
  - consecutive_failures = 0
  - deprecated_at = null, deprecated_reason = null
  - 如果脚本不是 deprecated 状态，返回错误

Output:
  {success: true, task_id, status: "active"}
```

#### `script_health`

```
Input:
  task_id: string (required)

Output:
  {
    success: true,
    task_id,
    status: "active" | "warning" | "deprecated",
    consecutive_failures: int,
    total_runs: int,
    total_completed: int,
    success_rate: float (0.0-1.0),
    last_run_at: iso string | null,
    last_run_status: "completed" | "failed" | "aborted" | null,
    last_session_id: string | null,
    deprecated_at: iso string | null,
    deprecated_reason: string | null
  }
```

### 修改工具

#### `script_list`

新增过滤参数：

```
Input:
  limit: int (default 100)
  status: "active" | "warning" | "deprecated" | "all" (default "active")

Behavior:
  - 默认只返回 active 状态
  - 每项输出扩展: 增加 status, consecutive_failures, last_run_status

Output:
  {
    scripts: [
      {task_id, goal, status, consecutive_failures, last_run_status, created_at},
      ...
    ]
  }
```

#### `script_run`

```
修改点:
  1. 执行前先调 _settle_abandoned_sessions(task_id) 清理遗弃 session
  2. 若 status == 'deprecated', 返回 SCRIPT_DEPRECATED 错误
  3. 执行结束（完成/失败/aborted）时调 record_run_result
  4. 若此次执行导致 active -> warning, 响应中附加 health.auto_warned

Output (含 auto_warned 示例):
  {
    status: "failed",
    session_id: "...",
    health: {
      auto_warned: true,
      consecutive_failures: 5,
      hint: "Script entered warning state. Consider script_deprecate."
    }
  }

Output (deprecated 示例):
  {
    success: false,
    error: "Script deprecated: outdated selectors",
    code: "SCRIPT_DEPRECATED"
  }
```

#### `script_delete`

硬删除行为增强：

```
Behavior:
  1. 检查 script_bindings 是否有引用此 task_id
     - 有引用则返回错误 SCRIPT_HAS_BINDINGS，要求先 script_bind_delete
  2. DELETE FROM scripts WHERE task_id=?
  3. 级联清理:
     - 查询 session_headers WHERE task_id=? 得到 session_id 列表
     - DELETE FROM session_steps WHERE session_id IN (...)
     - DELETE FROM session_runtime WHERE session_id IN (...)
     - DELETE FROM session_headers WHERE task_id=?

Output:
  {
    success: true,
    task_id,
    deleted: true,
    cascade: {session_headers: N, session_steps: M, session_runtime: K}
  }
```

---

## 错误码

| 代码 | 含义 |
|------|------|
| `SCRIPT_DEPRECATED` | 尝试执行已报废的脚本 |
| `SCRIPT_HAS_BINDINGS` | 硬删除时发现有 binding 引用，需先删 binding |
| `SCRIPT_NOT_DEPRECATED` | `script_restore` 作用于非 deprecated 脚本 |

---

## 涉及的文件

| 文件 | 改动 |
|------|------|
| `zerotoken/repository/migrations.py` | 新增 migration，ALTER TABLE scripts |
| `zerotoken/repository/sqlite.py` | `SQLiteScriptRepo` 新增 `record_run_result`, `deprecate`, `restore`, `health`, 更新 `script_list`, `script_delete` 级联 |
| `zerotoken/repository/sqlite.py` | `SQLiteRuntimeRepo` 新增 `find_paused_before` |
| `zerotoken/repository/protocols.py` | 协议增加对应方法 |
| `zerotoken/services/script_service.py` | 新增 `script_deprecate`, `script_restore`, `script_health`；`run_script` / `resume_script` 前后包装统计调用 + 遗弃清理 |
| `zerotoken/engine/script_engine_v2.py` | 终态位置增加 `record_run_result` 调用 |
| `handlers/script_handlers.py` | 新增 3 个 MCP 工具 + 更新 `script_list`/`script_run`/`script_delete` schema 和分发 |
| `tests/unit/test_repository/test_sqlite_scripts.py` | 新增 record_run_result/deprecate/restore 测试 |
| `tests/unit/test_services/test_script_service_run.py` | 扩展：验证连续失败触发 warning、warning 成功恢复 active、deprecated 拒绝执行 |
| `tests/unit/test_handlers/` | 新增 script_deprecate/restore/health handler 测试 |

---

## 测试关注点

- **统计正确性**：5 次失败后 status 升级；一次成功后清零
- **warning 允许执行**：warning 状态下 script_run 正常执行（AI 需要尝试修复）
- **deprecated 拒绝执行**：返回 SCRIPT_DEPRECATED
- **遗弃 session 处理**：模拟 25h 前的 paused session，下次 run 应被标为 aborted
- **级联清理**：script_delete 后对应 session_headers/steps/runtime 全部清空
- **binding 保护**：script_delete 存在 binding 时返回 SCRIPT_HAS_BINDINGS
