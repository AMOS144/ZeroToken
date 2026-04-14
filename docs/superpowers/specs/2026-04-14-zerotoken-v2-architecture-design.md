# ZeroToken v2 架构升级设计

> 日期: 2026-04-14
> 状态: 已确认，待实施
> 范围: 全面重构，无向后兼容约束

## 1. 背景与动机

ZeroToken 是面向 AI Agent 的浏览器自动化 MCP 引擎，核心场景是**录制 + 回放混合**：先用 AI Agent 交互式录制轨迹，再转脚本做定时回放。

当前代码库（v0.3.0/v0.4.0）存在以下问题：

### 架构臃肿
- `mcp_server.py`（1053行）是巨型 if/elif 分发器，30+ 分支，零测试覆盖
- `controller.py`（1048行）中 click/input/get_text/get_html 有近乎相同的 adaptive 回退逻辑（每个约 120 行 copy-paste）
- `SQLiteStorage`（639行）同时实现 7 个抽象接口，上帝对象
- `_execute_with_stability` 方法存在但从未被调用

### 浏览器能力缺失
- 无多标签页/多页面支持（controller 假设单一 page）
- 无文件上传/下载、键盘快捷键、hover/右键、iframe、拖拽

### 脚本引擎表达力不足
- 无条件分支（if/else）、循环、子程序
- 提取的数据无法传递到后续步骤
- fuzzy_point/DFU 机制过于死板，只有预标记的步骤才暂停

### Token 优化未深入
- 截图始终 base64 存入轨迹，无压缩/裁剪
- get_html 返回原始 DOM，无智能剪枝
- 页面状态无摘要/简化机制

### 录制中的试错污染
- AI Agent 在交互时走错路再退回，错误路径也被录入轨迹
- 转脚本后回放会重现这些错误

### 工程质量
- 版本号不一致（pyproject=0.3.0, \_\_init\_\_=0.4.0, server.json=0.2.0）
- 无结构化日志、无 lint/type-check/覆盖率 CI

## 2. 设计决策

### 选择方案 B：分层架构重写

评估了三种方案：
- **A. 渐进式重构**：风险低但治标不治本，controller 单例绑死一个 page 的问题无法在原结构上解决
- **B. 分层架构重写**（选中）：从根源解决所有问题，无兼容性包袱是最佳时机
- **C. 插件化架构**：当前用户规模不需要插件生态，过度设计

### 关键设计决策总览

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据模型 | Pydantic v2 | 强类型 + 自动序列化，替代手写 dict |
| 浏览器操作 | ActionPipeline 统一管道 | 消除 controller.py 的重复代码 |
| 多标签页 | BrowserContextManager | 支持多 Page + iframe 栈 |
| 脚本引擎 | 可嵌套步骤树 + VarsEnvironment | 支持 if/loop/assign |
| 错误处理 | Step-as-Unit，每步失败都暂停等 AI | 替代死板的 fuzzy_point/DFU |
| 录制优化 | 探索模式（explore mode） | AI 试错时不录入轨迹 |
| Token 优化 | DOM 剪枝 + 截图压缩 + response_mode | 多层次 Token 控制 |
| 存储 | 按职责拆分 Repo + 版本化迁移 | 消除上帝对象 |
| 表达式求值 | 白名单 AST（非 eval） | 安全性 |
| 循环上限 | 1000 次 | 防止死循环 |

## 3. 整体架构

### 分层结构

```
Transport 层        MCP stdio / Streamable HTTP (仅协议适配)
     |
Handler 层          browser_handlers / trajectory_handlers / script_handlers
     |               (工具注册 + 参数校验 + 调度, 每组一个模块)
     |
Service 层          BrowserService / TrajectoryService / ScriptService
     |               (业务编排, 无框架依赖)
     |
Domain 层           Pydantic 模型 (OperationRecord, Trajectory, Script...)
     |               (纯数据 + 校验, 零外部依赖)
     |
Repository 层       Protocol 抽象 + SQLite 实现 (按职责拆分)
     |
Infrastructure 层   browser/ (ActionPipeline, Actions, Stability)
                     engine/ (ScriptEngine v2 + FlowControl)
                     optimizers/ (DOM剪枝, 截图压缩, 状态摘要)
```

依赖方向**单向向下**：Handler -> Service -> Domain/Repository/Infrastructure，绝不反向。

### 目录结构

```
zerotoken/
  __init__.py

  models/                          # Domain 层 - 纯数据模型
    __init__.py
    operation.py                   # OperationRecord, PageState, SelectorCandidate
    trajectory.py                  # Trajectory, TrajectoryMetadata
    script.py                      # Script, ScriptStep, StepHint
    session.py                     # Session, PauseEvent, Resolution, RuntimeState

  repository/                      # Repository 层
    __init__.py
    protocols.py                   # ScriptRepo, TrajectoryRepo, SessionRepo... (Protocol)
    sqlite.py                      # 各 Repo 的 SQLite 实现
    migrations.py                  # 版本化数据库迁移

  browser/                         # Infrastructure - 浏览器控制
    __init__.py
    context.py                     # BrowserContextManager (多标签页/多实例)
    pipeline.py                    # ActionPipeline: 定位->等待->执行->截图->记录
    actions/
      __init__.py
      navigate.py                  # open, wait_for
      interact.py                  # click, input, hover, keyboard, drag_drop, scroll
      extract.py                   # get_text, get_html, extract_data, screenshot, evaluate
      page_mgmt.py                 # new_tab, switch_tab, close_tab, list_tabs
      iframe.py                    # enter_iframe, exit_iframe
      file_ops.py                  # upload, download
    stability/
      __init__.py
      middleware.py                # StabilityMiddleware (统一入口)
      selector.py                  # SmartSelector
      wait.py                      # SmartWait
      recovery.py                  # ErrorRecovery
      adaptive.py                  # 自适应定位
    stealth.py                     # 反检测

  engine/                          # Infrastructure - 脚本引擎
    __init__.py
    script_engine.py               # ScriptEngine v2: 执行器
    flow_control.py                # FlowExecutor: if/loop/assign
    data_flow.py                   # VarsEnvironment: 变量环境 + 安全表达式求值
    generator.py                   # 轨迹转脚本

  optimizers/                      # Infrastructure - Token 优化
    __init__.py
    dom_pruner.py                  # DOM 智能剪枝
    screenshot_opt.py              # 截图压缩/裁剪/降质
    state_summary.py               # 页面状态摘要生成

  services/                        # Service 层
    __init__.py
    browser_service.py             # 浏览器操作编排
    trajectory_service.py          # 轨迹录制/导出/管理 (含探索模式)
    script_service.py              # 脚本管理/执行/绑定

handlers/                          # Handler 层 (顶层)
  __init__.py
  browser_handlers.py              # browser_* 工具注册
  trajectory_handlers.py           # trajectory_* 工具注册
  script_handlers.py               # script_*/run_*/session_* 工具注册

mcp_server.py                     # 入口 (~50行): 启动 + transport + 依赖注入
mcp_server_http.py                # HTTP transport

tests/
  unit/
    test_models/
    test_repository/
    test_browser_actions/
    test_engine/
    test_optimizers/
    test_services/
  integration/
    test_browser_integration.py
    test_full_pipeline.py
  test_handlers/
```

## 4. Domain 模型 (Pydantic v2)

### models/operation.py

```python
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class ActionType(str, Enum):
    OPEN = "open"
    CLICK = "click"
    INPUT = "input"
    GET_TEXT = "get_text"
    GET_HTML = "get_html"
    SCREENSHOT = "screenshot"
    WAIT_FOR = "wait_for"
    EXTRACT_DATA = "extract_data"
    HOVER = "hover"
    KEYBOARD = "keyboard"
    RIGHT_CLICK = "right_click"
    DOUBLE_CLICK = "double_click"
    DRAG_DROP = "drag_drop"
    SCROLL = "scroll"
    NEW_TAB = "new_tab"
    SWITCH_TAB = "switch_tab"
    CLOSE_TAB = "close_tab"
    LIST_TABS = "list_tabs"
    ENTER_IFRAME = "enter_iframe"
    EXIT_IFRAME = "exit_iframe"
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    EVALUATE = "evaluate"


class PageState(BaseModel):
    url: str = ""
    title: str = ""
    tab_id: int = 0
    tab_count: int = 1
    timestamp: datetime = Field(default_factory=datetime.now)


class SelectorCandidate(BaseModel):
    type: str                    # css, id, aria, xpath, text
    value: str
    stability_score: float = 0.0


class OperationResult(BaseModel):
    success: bool
    data: dict[str, Any] = {}
    error: Optional[str] = None


class OperationRecord(BaseModel):
    step: int
    action: ActionType
    params: dict[str, Any] = {}
    result: OperationResult
    page_state: PageState
    screenshot: Optional[str] = None
    selector_candidates: list[SelectorCandidate] = []
    timestamp: datetime = Field(default_factory=datetime.now)
```

### models/trajectory.py

```python
class TrajectoryMetadata(BaseModel):
    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    duration_seconds: Optional[float] = None


class Trajectory(BaseModel):
    task_id: str
    goal: str
    operations: list[OperationRecord] = []
    metadata: TrajectoryMetadata = Field(default_factory=TrajectoryMetadata)
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def add_operation(self, record: OperationRecord) -> None:
        self.operations.append(record)
        self.metadata.total_steps = len(self.operations)
        if record.result.success:
            self.metadata.successful_steps += 1
        else:
            self.metadata.failed_steps += 1

    def to_ai_prompt(self) -> str:
        """导出 AI 友好的文本格式"""
        lines = [f"Task Goal: {self.goal}", "", "Operation History:"]
        for op in self.operations:
            param_str = ", ".join(f"{k}={repr(v)}" for k, v in op.params.items())
            lines.append(f"[Step {op.step}] {op.action.value}({param_str})")
        return "\n".join(lines)
```

### models/script.py

```python
class ScriptStep(BaseModel):
    action: str
    params: dict[str, Any] = {}
    selector_candidates: list[SelectorCandidate] = []
    # 流程控制
    condition: Optional[str] = None
    body: list["ScriptStep"] = []
    else_body: list["ScriptStep"] = []
    # 数据流
    assign_to: Optional[str] = None
    # 可选提示（供 AI 仲裁时参考）
    hint: Optional[str] = None


class Script(BaseModel):
    task_id: str
    goal: str
    steps: list[ScriptStep]
    params_schema: dict[str, Any] = {}
    source_trajectory_id: Optional[int] = None


class StepHint(BaseModel):
    """可选的步骤提示模板（原 DFU 简化版）"""
    hint_id: str
    match_rules: list[dict[str, Any]]
    hint_text: str
```

### models/session.py

```python
class PauseReason(str, Enum):
    STEP_FAILED = "step_failed"
    PRE_STEP_HINT = "pre_step_hint"


class PauseEvent(BaseModel):
    reason: PauseReason
    session_id: str
    task_id: str
    step_index: int
    step_path: list[int | str] = []
    action: str
    params: dict[str, Any]
    selector_candidates: list[SelectorCandidate] = []
    error: Optional[str] = None
    page_state: Optional[PageState] = None
    screenshot: Optional[str] = None
    hint: Optional[str] = None
    allowed_resolutions: list[str] = [
        "retry", "patch_step", "skip", "abort"
    ]


class Resolution(BaseModel):
    type: str                  # retry / patch_step / skip / abort
    patch: dict[str, Any] = {}
    vars: dict[str, Any] = {}
    note: str = ""


class RuntimeState(BaseModel):
    session_id: str
    task_id: str
    cursor_step_index: int
    step_path: list[int | str] = []
    status: str                # running / paused / success / failed
    pause_event: Optional[PauseEvent] = None
    vars: dict[str, Any] = {}
```

## 5. ActionPipeline（统一执行管道）

所有浏览器操作经过同一管道，消除 controller.py 中的重复代码。

### 当前问题

click/input/get_text/get_html 每个方法都有 ~120 行几乎相同的逻辑：
1. 获取 step 计数
2. try: 等待选择器 -> 生成 selector_candidates -> auto_save 指纹
3. 执行核心操作
4. 截图 -> 获取 page_state -> 构建 result
5. except: adaptive 回退 -> 再次 try -> 或报错
6. 构建 OperationRecord -> 加入 history -> 返回

4 个方法 x ~120 行 = ~480 行几乎相同的代码。

### 解决方案

```python
# browser/pipeline.py

class ActionPipeline:
    """统一执行管道"""

    def __init__(self, context: BrowserContextManager, stability: StabilityMiddleware):
        self.context = context
        self.stability = stability
        self._step_counter = 0

    async def execute(
        self,
        action: ActionType,
        params: dict,
        *,
        action_fn: ActionFn,
        needs_selector: bool = True,
        take_screenshot: bool = True,
        auto_save: bool = False,
        adaptive: bool = False,
        identifier: str | None = None,
        screenshot_strategy: str = "compressed",
    ) -> OperationRecord:
        step = self._next_step()
        page = self.context.active_page

        # 阶段1: 元素定位 + 稳定性
        element = None
        selector_candidates = []
        if needs_selector and params.get("selector"):
            element, selector_candidates = await self.stability.locate(
                page, params["selector"],
                auto_save=auto_save,
                adaptive=adaptive,
                identifier=identifier,
            )

        # 阶段2: 执行核心操作
        result_data = await action_fn(page, element, params)

        # 阶段3: 状态捕获
        page_state = await self._capture_state(page)
        screenshot = await self._take_screenshot(page, screenshot_strategy) if take_screenshot else None

        # 阶段4: 构建记录
        return OperationRecord(
            step=step,
            action=action,
            params=params,
            result=OperationResult(success=True, data=result_data),
            page_state=page_state,
            screenshot=screenshot,
            selector_candidates=[
                SelectorCandidate(**c) for c in selector_candidates
            ],
        )

    async def capture_state_safe(self) -> PageState | None:
        """安全获取页面状态（异常时返回 None）"""
        try:
            return await self._capture_state(self.context.active_page)
        except Exception:
            return None

    async def take_screenshot_safe(self) -> str | None:
        """安全截图（异常时返回 None）"""
        try:
            return await self._take_screenshot(self.context.active_page, "compressed")
        except Exception:
            return None
```

具体动作变为纯函数（每个 ~5-15 行）：

```python
# browser/actions/interact.py

async def click_action(page, element, params) -> dict:
    if params.get("scroll_into_view", True):
        await element.scroll_into_view_if_needed()
    await element.click()
    await asyncio.sleep(params.get("wait_after", 0.5))
    old_url = params.get("_old_url", page.url)
    navigated = page.url != old_url
    return {"navigated": navigated, "new_url": page.url if navigated else None}

async def hover_action(page, element, params) -> dict:
    await element.hover()
    return {}

async def keyboard_action(page, element, params) -> dict:
    await page.keyboard.press(params["key"])
    return {"key": params["key"]}

async def drag_drop_action(page, element, params) -> dict:
    target = await page.wait_for_selector(params["target"])
    src = await element.bounding_box()
    dst = await target.bounding_box()
    await page.mouse.move(src["x"] + src["width"]/2, src["y"] + src["height"]/2)
    await page.mouse.down()
    await page.mouse.move(dst["x"] + dst["width"]/2, dst["y"] + dst["height"]/2)
    await page.mouse.up()
    return {"target": params["target"]}
```

### StabilityMiddleware

```python
# browser/stability/middleware.py

class StabilityMiddleware:
    """统一封装：智能选择器 + 自适应定位 + 错误恢复 + 重试"""

    def __init__(self, selector_gen, adaptive_storage, retry_config):
        ...

    async def locate(self, page, selector, *, auto_save, adaptive, identifier):
        """
        统一定位流程:
        1. 直接用 selector 定位
        2. 失败 + adaptive=True 时，用指纹重定位
        3. 成功时生成 selector_candidates
        4. auto_save=True 时保存指纹
        返回 (element, selector_candidates)
        """
        ...
```

## 6. BrowserContextManager（多标签页/iframe）

```python
# browser/context.py

class ManagedPage:
    """一个受管理的标签页"""
    page: Page
    tab_id: int
    iframe_stack: list[FrameLocator]

    @property
    def active_frame(self) -> Page | FrameLocator:
        return self.iframe_stack[-1] if self.iframe_stack else self.page


class BrowserContextManager:
    """管理浏览器生命周期 + 多标签页 + iframe 栈"""

    async def start(self, *, headless, viewport, stealth) -> None: ...
    async def stop(self) -> None: ...

    @property
    def active_page(self) -> ManagedPage: ...

    async def new_tab(self, url: str | None = None) -> ManagedPage: ...
    async def switch_tab(self, tab_id: int) -> ManagedPage: ...
    async def close_tab(self, tab_id: int | None = None) -> None: ...
    async def list_tabs(self) -> list[dict]: ...

    async def enter_iframe(self, selector: str) -> None: ...
    async def exit_iframe(self, all: bool = False) -> None: ...

    def get_page_state(self) -> PageState: ...
```

## 7. 新增浏览器动作

### 多标签页 + iframe

| MCP 工具 | 参数 |
|----------|------|
| `browser_new_tab` | `url?` |
| `browser_switch_tab` | `tab_id` |
| `browser_close_tab` | `tab_id?` |
| `browser_list_tabs` | 无 |
| `browser_enter_iframe` | `selector` |
| `browser_exit_iframe` | `all?`(默认 false) |

### 键盘

| MCP 工具 | 参数 |
|----------|------|
| `browser_keyboard` | `key`("Enter"/"Control+A"/"Escape") |
| `browser_type_text` | `text`, `delay?` |

### 鼠标

| MCP 工具 | 参数 |
|----------|------|
| `browser_hover` | `selector` |
| `browser_right_click` | `selector` |
| `browser_double_click` | `selector` |
| `browser_drag_drop` | `source_selector`, `target_selector` |
| `browser_scroll` | `direction`, `amount?`, `selector?` |

### 文件

| MCP 工具 | 参数 |
|----------|------|
| `browser_upload` | `selector`, `file_paths` |
| `browser_download` | `trigger_selector?`, `save_dir?`, `timeout?` |

### JavaScript

| MCP 工具 | 参数 |
|----------|------|
| `browser_evaluate` | `expression`, `return_value?` |

## 8. ScriptEngine v2

### 流程控制

脚本步骤从平铺列表升级为可嵌套指令树，支持 if/loop/assign：

```json
{
  "task_id": "monitor_price",
  "steps": [
    {"action": "browser_open", "params": {"url": "{{target_url}}"}},
    {
      "action": "browser_get_text",
      "params": {"selector": ".price"},
      "assign_to": "current_price"
    },
    {
      "action": "if",
      "condition": "float(current_price) < float(threshold)",
      "body": [
        {"action": "browser_click", "params": {"selector": "#buy-btn"}}
      ],
      "else_body": [
        {"action": "browser_screenshot", "params": {}}
      ]
    },
    {
      "action": "loop",
      "condition": "page_num <= max_pages",
      "body": [
        {"action": "browser_extract_data", "params": {...}, "assign_to": "page_data"},
        {"action": "browser_click", "params": {"selector": ".next-page"}},
        {"action": "assign", "params": {"name": "page_num", "expr": "page_num + 1"}}
      ]
    }
  ]
}
```

### VarsEnvironment（变量环境）

```python
class VarsEnvironment:
    def get(self, name: str) -> Any: ...
    def set(self, name: str, value: Any) -> None: ...
    def resolve_params(self, params: dict) -> dict:
        """替换 {{varname}} 占位符"""
    def eval_condition(self, expr: str) -> bool:
        """白名单 AST 安全求值条件表达式"""
    def eval_expr(self, expr: str) -> Any:
        """白名单 AST 安全求值赋值表达式"""
    def snapshot(self) -> dict:
        """快照变量（用于 pause/resume 持久化）"""
```

表达式求值使用白名单 AST 解析，支持比较运算、算术、字符串操作、变量引用，禁止危险操作。

### FlowExecutor（流程执行器）

```python
class FlowExecutor:
    """递归执行脚本步骤树"""

    async def execute_steps(self, steps, store, session_id) -> FlowResult:
        for step in steps:
            match step.action:
                case "if":
                    cond = self.vars_env.eval_condition(step.condition)
                    body = step.body if cond else step.else_body
                    result = await self.execute_steps(body, store, session_id)
                    if result.paused or result.failed:
                        return result
                case "loop":
                    iteration = 0
                    while self.vars_env.eval_condition(step.condition):
                        if iteration >= 1000:
                            return FlowResult(failed=True, error="loop exceeded max")
                        result = await self.execute_steps(step.body, ...)
                        if result.paused or result.failed:
                            return result
                        iteration += 1
                case "assign":
                    value = self.vars_env.eval_expr(step.params["expr"])
                    self.vars_env.set(step.params["name"], value)
                case _:
                    result = await self._execute_action_step(step, ...)
                    if result.paused:
                        return result
```

循环上限硬编码 1000 次，防止死循环。

## 9. 统一步骤执行模型（Step-as-Unit）

### 核心理念

废弃 fuzzy_point/DFU 机制。每一步都是独立执行单元，任何一步失败都暂停等 AI 仲裁。

| 旧模型 | 新模型 |
|--------|--------|
| 普通步骤硬报错，fuzzy_point 才暂停 | 每步失败都暂停等 AI |
| DFU 触发器匹配到就强制暂停 | 废弃 DFU，改用可选 hint |
| fuzzy_point 区分确定性/模糊步骤 | 所有步骤一视同仁 |

### 执行循环

```
对每一步:
  1. 解析参数 (变量替换)
  2. 执行浏览器动作
  3. 检查结果
     +-- 成功 -> 记录, 推进下一步
     +-- 失败 -> 构建 PauseEvent (含完整上下文), 暂停, 返回给 AI
                  AI 收到: 步骤信息 + 错误 + 页面状态 + 截图 + hint
                  AI 决定: retry / patch_step / skip / abort
```

### PauseEvent 包含 AI 决策所需的全部上下文

- 哪一步失败（step_index, step_path）
- 执行了什么（action, params, selector_candidates）
- 为什么失败（error）
- 当前页面什么状态（page_state, screenshot）
- 预置提示（hint，可选）
- 可选的操作（allowed_resolutions）

### AI 仲裁示例

```json
// AI 收到暂停事件
{
  "status": "paused",
  "pause_event": {
    "reason": "step_failed",
    "step_index": 3,
    "action": "browser_click",
    "params": {"selector": "#submit-btn"},
    "selector_candidates": [
      {"type": "css", "value": "#submit-btn"},
      {"type": "aria", "value": "[aria-label='Submit']"}
    ],
    "error": "selector '#submit-btn' not found",
    "page_state": {"url": "https://example.com/login"},
    "screenshot": "base64...",
    "hint": "登录按钮位置可能因 A/B 测试而变化"
  }
}

// AI 决定换选择器重试
{
  "session_id": "...",
  "resolution": {
    "type": "patch_step",
    "patch": {"params": {"selector": "[aria-label='Submit']"}},
    "note": "原选择器失效，改用 aria-label"
  }
}
```

### 废弃的 MCP 工具

移除 `dfu_save`、`dfu_load`、`dfu_list`、`dfu_delete` 四个工具。hint 直接写在 ScriptStep 中。

## 10. 探索模式（Explore Mode）

### 问题

AI Agent 交互操作时可能走错路再退回，当前代码把试错步骤也录入轨迹，导致转脚本后回放重现错误。

### 解决方案

轨迹录制器新增两种状态：

```
[录制模式 recording]  <-->  [探索模式 exploring]
     |                            |
  操作记入轨迹                操作不记入轨迹
  正常截图                    自动降级为 minimal response_mode
  步骤计数递增                步骤计数冻结
```

### MCP 工具

| 工具 | 作用 | 参数 |
|------|------|------|
| `trajectory_explore_start` | 进入探索模式 | `reason?` |
| `trajectory_explore_stop` | 退出，回到录制 | `keep_last?`(默认 false) |
| `trajectory_status` | 查看当前状态 | 无 |

### 典型流程

```
AI: "我需要找到登录按钮在哪"
1. trajectory_explore_start(reason="寻找登录入口")
2. browser_click("#menu")          -- 不录入轨迹
3. browser_get_text(".nav-items")  -- 不录入轨迹
4. browser_click(".back")          -- 不录入轨迹
5. "找到了，登录按钮在 #header-login"
6. trajectory_explore_stop()
7. browser_click("#header-login")  -- 录入轨迹
```

生成的脚本只有第 7 步。

### TrajectoryService 实现

```python
class RecordingMode(str, Enum):
    RECORDING = "recording"
    EXPLORING = "exploring"

class TrajectoryService:
    def __init__(self):
        self._mode = RecordingMode.RECORDING
        self._explore_depth = 0

    def start_explore(self, reason="") -> dict: ...
    def stop_explore(self, keep_last=False) -> dict: ...
    def should_record(self) -> bool:
        return self._mode == RecordingMode.RECORDING
    def record_operation(self, record):
        if self._mode == RecordingMode.EXPLORING:
            self._explore_depth += 1
            return
        ...
```

## 11. Token 优化层

### DOM 智能剪枝 (`optimizers/dom_pruner.py`)

将原始 HTML 精简为 AI 可理解的语义骨架（典型 200KB -> < 5KB）。

剪枝规则：
1. 移除 `<script>`, `<style>`, `<svg>`, `<noscript>`
2. 移除纯装饰属性（CSS Module hash, style, data-v-*）
3. 保留语义属性（id, name, aria-*, role, href, src, type, placeholder, value）
4. 折叠空白文本节点
5. 超长列表只保留前 N 项 + "...共 M 项"
6. 超深嵌套截断（>10 层折叠为 [...]）

### 截图优化 (`optimizers/screenshot_opt.py`)

| 策略 | 行为 |
|------|------|
| `none` | 不截图 |
| `compressed` | JPEG 压缩 + 降分辨率（quality=50, max_width=800） |
| `thumbnail` | 极小缩略图（200px 宽, quality=30） |
| `region` | 只截取目标元素周围区域 |

### 页面状态摘要 (`optimizers/state_summary.py`)

将页面精简为结构化摘要：

```python
{
    "url": "...",
    "title": "...",
    "forms": [...],        # 表单字段列表
    "links": [...],        # 关键链接 (limit=20)
    "buttons": [...],      # 可点击按钮
    "text_summary": "...", # 主要文本 (limit=500 chars)
    "interactive_elements": 42
}
```

### response_mode 参数

每个 browser_* 工具支持 `response_mode` 参数：

| response_mode | 行为 | 适用场景 |
|---------------|------|----------|
| `full` | 完整返回（原始截图 + HTML + 状态） | 调试 |
| `standard`(默认) | 压缩截图 + 剪枝 DOM | 正常使用 |
| `minimal` | 只返回操作结果 + URL/title | Token 敏感 |
| `summary` | 操作结果 + 页面摘要 | AI Agent 推理 |

探索模式下自动降级为 `minimal`。

## 12. Repository 层

### Protocol 定义

用 Protocol 替代 ABC，按职责拆分为 7 个独立协议：

- `ScriptRepo` -- 脚本 CRUD
- `TrajectoryRepo` -- 轨迹 CRUD
- `SessionRepo` -- 会话 CRUD
- `RuntimeRepo` -- 运行时状态
- `FingerprintRepo` -- 元素指纹
- `BindingRepo` -- 脚本绑定
- `HintRepo` -- 步骤提示模板（可选，替代 DFU）

### SQLite 实现

共享 `SQLiteConnection`（连接 + 迁移管理），每个 Repo 独立实现：

```python
class SQLiteConnection:
    def __init__(self, db_path: str): ...
    def _run_migrations(self) -> None: ...

class SQLiteScriptRepo:      # ~60 行
class SQLiteTrajectoryRepo:  # ~80 行
class SQLiteSessionRepo:     # ~60 行
class SQLiteRuntimeRepo:     # ~50 行
class SQLiteFingerprintRepo: # ~40 行
class SQLiteBindingRepo:     # ~50 行
```

### 版本化迁移

```python
MIGRATIONS = [
    ("001_initial", "CREATE TABLE IF NOT EXISTS scripts (...);\n..."),
    ("002_add_step_path", "ALTER TABLE session_runtime ADD COLUMN step_path TEXT;"),
]

class MigrationRunner:
    """跟踪已执行的迁移版本，只跑增量"""
    ...
```

## 13. Handler 层

### 拆分方式

| 模块 | 负责工具 |
|------|----------|
| `browser_handlers.py` | browser_init/close + 所有 browser_* 动作 |
| `trajectory_handlers.py` | trajectory_start/complete/get/list/load/delete + explore_start/stop/status |
| `script_handlers.py` | script_save/list/load/delete + run_script + session_list/get + binding_* |

### mcp_server.py 精简为 ~50 行

```python
server = Server("zerotoken")

db = SQLiteConnection(db_path)
browser_service = BrowserService(...)
trajectory_service = TrajectoryService(...)
script_service = ScriptService(...)

@server.list_tools()
async def list_tools():
    return browser_tools() + trajectory_tools() + script_tools()

@server.call_tool()
async def call_tool(name, arguments):
    if name.startswith("browser_"):
        return await handle_browser_tool(name, arguments, browser_service, trajectory_service)
    elif name.startswith("trajectory_"):
        return await handle_trajectory_tool(name, arguments, trajectory_service)
    else:
        return await handle_script_tool(name, arguments, script_service)
```

## 14. 测试策略

### 分层覆盖

| 层级 | 范围 | 依赖 | 目标覆盖率 |
|------|------|------|-----------|
| unit/models | Pydantic 模型序列化/校验 | 无 | 100% |
| unit/repository | 每个 SQLiteRepo CRUD | 内存 SQLite | 100% |
| unit/actions | 每个 action 纯函数 | Mock Page/Element | 90%+ |
| unit/engine | FlowExecutor if/loop/assign + Step-as-Unit 暂停 | Mock Pipeline | 90%+ |
| unit/optimizers | DOM 剪枝、截图压缩 | 静态 HTML | 90%+ |
| unit/services | Service 层编排 + 探索模式 | Mock Repo + Mock Browser | 85%+ |
| unit/handlers | 参数解析 + 响应格式 | Mock Service | 85%+ |
| integration | ActionPipeline + 真实 Playwright | Chromium | 关键路径 |
| e2e | MCP 工具端到端 | 完整启动 | 冒烟测试 |

### CI 升级

```yaml
jobs:
  lint:
    - ruff check .
    - ruff format --check .
  typecheck:
    - mypy zerotoken/ handlers/ --strict
  test:
    - pytest tests/unit/ -v --cov=zerotoken --cov-report=term --cov-fail-under=85
  integration:
    - playwright install chromium --with-deps
    - pytest tests/integration/ -v
```

### 版本统一

所有版本号从 `pyproject.toml` 读取：

```python
# zerotoken/__init__.py
from importlib.metadata import version
__version__ = version("zerotoken")
```

`server.json` 版本在 CI 中自动校验一致性。

### 结构化日志

```python
import logging
logger = logging.getLogger("zerotoken")
logger.info("action_executed", extra={
    "action": "click", "selector": "#btn", "success": True, "duration_ms": 342
})
```

## 15. MCP 工具完整清单

### Browser 工具（26 个）

| 工具 | 描述 |
|------|------|
| `browser_init` | 初始化浏览器 |
| `browser_close` | 关闭浏览器 |
| `browser_open` | 打开 URL |
| `browser_click` | 点击元素 |
| `browser_input` | 输入文本 |
| `browser_get_text` | 提取文本/属性 |
| `browser_get_html` | 获取 HTML（支持剪枝） |
| `browser_screenshot` | 截图 |
| `browser_wait_for` | 等待条件 |
| `browser_extract_data` | 结构化数据提取 |
| `browser_hover` | 悬停 |
| `browser_right_click` | 右键 |
| `browser_double_click` | 双击 |
| `browser_keyboard` | 按键/组合键 |
| `browser_type_text` | 原始键盘输入 |
| `browser_drag_drop` | 拖拽 |
| `browser_scroll` | 滚动 |
| `browser_new_tab` | 新建标签页 |
| `browser_switch_tab` | 切换标签页 |
| `browser_close_tab` | 关闭标签页 |
| `browser_list_tabs` | 列出标签页 |
| `browser_enter_iframe` | 进入 iframe |
| `browser_exit_iframe` | 退出 iframe |
| `browser_upload` | 文件上传 |
| `browser_download` | 文件下载 |
| `browser_evaluate` | 执行 JavaScript |

除 `browser_init`/`browser_close`/`browser_list_tabs` 外，所有返回 OperationRecord 的工具支持 `response_mode`、`include_screenshot`、`auto_save`、`adaptive`、`identifier` 参数。

### 类型定义补充

`ActionFn` 类型别名：`Callable[[Page | FrameLocator, ElementHandle | None, dict], Awaitable[dict]]`。ActionPipeline 在调用 action_fn 时传入 `managed_page.active_frame`（而非 Page 本身），确保 iframe 内操作透明。

### Trajectory 工具（9 个）

| 工具 | 描述 |
|------|------|
| `trajectory_start` | 开始轨迹记录 |
| `trajectory_complete` | 完成轨迹 |
| `trajectory_get` | 获取当前轨迹 |
| `trajectory_list` | 列出已保存轨迹 |
| `trajectory_load` | 加载轨迹 |
| `trajectory_delete` | 删除轨迹 |
| `trajectory_explore_start` | 进入探索模式 |
| `trajectory_explore_stop` | 退出探索模式 |
| `trajectory_status` | 查看录制状态 |

### Script 工具（13 个）

| 工具 | 描述 |
|------|------|
| `trajectory_to_script` | 轨迹转脚本 |
| `script_save` | 保存脚本 |
| `script_list` | 列出脚本 |
| `script_load` | 加载脚本 |
| `script_delete` | 删除脚本 |
| `run_script` | 启动/恢复脚本执行 |
| `run_script_by_job_id` | 按绑定 key 执行脚本 |
| `script_binding_set` | 设置绑定 |
| `script_binding_get` | 获取绑定 |
| `script_binding_list` | 列出绑定 |
| `script_binding_delete` | 删除绑定 |
| `session_list` | 列出会话 |
| `session_get` | 获取会话步骤 |

### 废弃的工具

`dfu_save`、`dfu_load`、`dfu_list`、`dfu_delete` -- 被 ScriptStep.hint 替代。
