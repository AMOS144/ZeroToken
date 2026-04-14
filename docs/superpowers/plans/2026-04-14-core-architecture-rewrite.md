# ZeroToken v2 Core Architecture Rewrite - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite ZeroToken from monolithic controller to layered architecture with Pydantic models, ActionPipeline, and modular handlers -- functionally equivalent to current system, architecturally superior.

**Architecture:** Five-layer design (Transport -> Handler -> Service -> Domain -> Repository/Infrastructure). All browser operations go through a unified ActionPipeline. Storage split into per-responsibility repos behind Protocol interfaces.

**Tech Stack:** Python 3.10+, Pydantic v2, Playwright, MCP SDK, SQLite, pytest + pytest-asyncio

**Design Spec:** `docs/superpowers/specs/2026-04-14-zerotoken-v2-architecture-design.md`

---

## File Structure

```
zerotoken/
  __init__.py                      # MODIFY: version from importlib.metadata
  models/
    __init__.py                    # CREATE
    operation.py                   # CREATE: ActionType, PageState, SelectorCandidate, OperationResult, OperationRecord
    trajectory.py                  # CREATE: TrajectoryMetadata, Trajectory
    script.py                      # CREATE: ScriptStep, Script, StepHint
    session.py                     # CREATE: PauseReason, PauseEvent, Resolution, RuntimeState
  repository/
    __init__.py                    # CREATE
    protocols.py                   # CREATE: ScriptRepo, TrajectoryRepo, SessionRepo, RuntimeRepo, FingerprintRepo, BindingRepo
    migrations.py                  # CREATE: MIGRATIONS list, MigrationRunner
    sqlite.py                      # CREATE: SQLiteConnection, SQLiteScriptRepo, SQLiteTrajectoryRepo, SQLiteSessionRepo, SQLiteRuntimeRepo, SQLiteFingerprintRepo, SQLiteBindingRepo
  browser/
    __init__.py                    # CREATE
    context.py                     # CREATE: ManagedPage, BrowserContextManager
    pipeline.py                    # CREATE: ActionPipeline
    actions/
      __init__.py                  # CREATE
      navigate.py                  # CREATE: open_action, wait_for_action
      interact.py                  # CREATE: click_action, input_action
      extract.py                   # CREATE: get_text_action, get_html_action, screenshot_action, extract_data_action
    stability/
      __init__.py                  # CREATE
      middleware.py                # CREATE: StabilityMiddleware
      selector.py                  # MIGRATE from zerotoken/selector.py
      wait.py                      # MIGRATE from zerotoken/wait_strategy.py
      recovery.py                  # MIGRATE from zerotoken/recovery.py
      adaptive.py                  # MIGRATE from zerotoken/adaptive.py
    stealth.py                     # MIGRATE from zerotoken/stealth.py
  services/
    __init__.py                    # CREATE
    browser_service.py             # CREATE: BrowserService
    trajectory_service.py          # CREATE: TrajectoryService (with RecordingMode)
    script_service.py              # CREATE: ScriptService (basic, no v2 engine)
handlers/
  __init__.py                      # CREATE
  browser_handlers.py              # CREATE: browser_tools(), handle_browser_tool()
  trajectory_handlers.py           # CREATE: trajectory_tools(), handle_trajectory_tool()
  script_handlers.py               # CREATE: script_tools(), handle_script_tool()
mcp_server.py                      # REWRITE: ~50 lines entry point
pyproject.toml                     # MODIFY: version, dependencies (add Pillow for screenshot opt)
tests/
  unit/
    __init__.py                    # CREATE
    test_models/
      __init__.py                  # CREATE
      test_operation.py            # CREATE
      test_trajectory.py           # CREATE
      test_script.py               # CREATE
      test_session.py              # CREATE
    test_repository/
      __init__.py                  # CREATE
      test_sqlite_script.py        # CREATE
      test_sqlite_trajectory.py    # CREATE
      test_sqlite_session.py       # CREATE
      test_sqlite_fingerprint.py   # CREATE
      test_sqlite_binding.py       # CREATE
      test_migrations.py           # CREATE
    test_browser/
      __init__.py                  # CREATE
      test_context.py              # CREATE
      test_pipeline.py             # CREATE
      test_actions_navigate.py     # CREATE
      test_actions_interact.py     # CREATE
      test_actions_extract.py      # CREATE
      test_stability_middleware.py  # CREATE
    test_services/
      __init__.py                  # CREATE
      test_browser_service.py      # CREATE
      test_trajectory_service.py   # CREATE
      test_script_service.py       # CREATE
    test_handlers/
      __init__.py                  # CREATE
      test_browser_handlers.py     # CREATE
      test_trajectory_handlers.py  # CREATE
      test_script_handlers.py      # CREATE
```

---

## Task 1: Domain Models - Operation

**Files:**
- Create: `zerotoken/models/__init__.py`
- Create: `zerotoken/models/operation.py`
- Test: `tests/unit/test_models/__init__.py`
- Test: `tests/unit/test_models/test_operation.py`
- Test: `tests/unit/__init__.py`

- [ ] **Step 1: Create test directory structure and write failing tests**

```bash
mkdir -p tests/unit/test_models
touch tests/unit/__init__.py tests/unit/test_models/__init__.py
```

```python
# tests/unit/test_models/test_operation.py
"""OperationRecord 及相关模型的单元测试"""
import pytest
from datetime import datetime


def test_action_type_values():
    """ActionType 枚举包含所有基础动作"""
    from zerotoken.models.operation import ActionType
    assert ActionType.OPEN == "open"
    assert ActionType.CLICK == "click"
    assert ActionType.INPUT == "input"
    assert ActionType.GET_TEXT == "get_text"
    assert ActionType.GET_HTML == "get_html"
    assert ActionType.SCREENSHOT == "screenshot"
    assert ActionType.WAIT_FOR == "wait_for"
    assert ActionType.EXTRACT_DATA == "extract_data"
    assert ActionType.HOVER == "hover"
    assert ActionType.KEYBOARD == "keyboard"


def test_page_state_defaults():
    """PageState 有合理默认值"""
    from zerotoken.models.operation import PageState
    ps = PageState()
    assert ps.url == ""
    assert ps.title == ""
    assert ps.tab_id == 0
    assert ps.tab_count == 1
    assert isinstance(ps.timestamp, datetime)


def test_page_state_with_values():
    """PageState 可以指定值"""
    from zerotoken.models.operation import PageState
    ps = PageState(url="https://example.com", title="Example", tab_id=2, tab_count=3)
    assert ps.url == "https://example.com"
    assert ps.tab_id == 2


def test_selector_candidate():
    """SelectorCandidate 序列化/反序列化"""
    from zerotoken.models.operation import SelectorCandidate
    sc = SelectorCandidate(type="css", value="#btn", stability_score=0.9)
    d = sc.model_dump()
    assert d == {"type": "css", "value": "#btn", "stability_score": 0.9}
    sc2 = SelectorCandidate.model_validate(d)
    assert sc2.value == "#btn"


def test_operation_result_success():
    """OperationResult 成功场景"""
    from zerotoken.models.operation import OperationResult
    r = OperationResult(success=True, data={"navigated": True})
    assert r.success is True
    assert r.data["navigated"] is True
    assert r.error is None


def test_operation_result_failure():
    """OperationResult 失败场景"""
    from zerotoken.models.operation import OperationResult
    r = OperationResult(success=False, error="element not found")
    assert r.success is False
    assert r.error == "element not found"


def test_operation_record_full():
    """OperationRecord 完整构建和序列化"""
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult, SelectorCandidate
    )
    record = OperationRecord(
        step=1,
        action=ActionType.CLICK,
        params={"selector": "#btn"},
        result=OperationResult(success=True, data={"navigated": False}),
        page_state=PageState(url="https://example.com", title="Test"),
        screenshot="base64data",
        selector_candidates=[
            SelectorCandidate(type="css", value="#btn", stability_score=0.9)
        ],
    )
    d = record.model_dump()
    assert d["step"] == 1
    assert d["action"] == "click"
    assert d["result"]["success"] is True
    assert d["page_state"]["url"] == "https://example.com"
    assert d["screenshot"] == "base64data"
    assert len(d["selector_candidates"]) == 1


def test_operation_record_minimal():
    """OperationRecord 最小构建（无可选字段）"""
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult
    )
    record = OperationRecord(
        step=1,
        action=ActionType.OPEN,
        params={"url": "https://example.com"},
        result=OperationResult(success=True),
        page_state=PageState(),
    )
    d = record.model_dump()
    assert d["screenshot"] is None
    assert d["selector_candidates"] == []


def test_operation_record_json_roundtrip():
    """OperationRecord JSON 序列化 <-> 反序列化"""
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult
    )
    record = OperationRecord(
        step=5,
        action=ActionType.INPUT,
        params={"selector": "#name", "text": "hello"},
        result=OperationResult(success=True, data={"actual_value": "hello"}),
        page_state=PageState(url="https://x.com", title="Form"),
    )
    json_str = record.model_dump_json()
    record2 = OperationRecord.model_validate_json(json_str)
    assert record2.step == 5
    assert record2.action == ActionType.INPUT
    assert record2.result.data["actual_value"] == "hello"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_models/test_operation.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'zerotoken.models'`

- [ ] **Step 3: Implement operation models**

```bash
mkdir -p zerotoken/models
touch zerotoken/models/__init__.py
```

```python
# zerotoken/models/__init__.py
"""ZeroToken Domain Models - Pydantic v2"""
from .operation import (
    ActionType,
    PageState,
    SelectorCandidate,
    OperationResult,
    OperationRecord,
)
from .trajectory import Trajectory, TrajectoryMetadata
from .script import ScriptStep, Script, StepHint
from .session import PauseReason, PauseEvent, Resolution, RuntimeState

__all__ = [
    "ActionType",
    "PageState",
    "SelectorCandidate",
    "OperationResult",
    "OperationRecord",
    "Trajectory",
    "TrajectoryMetadata",
    "ScriptStep",
    "Script",
    "StepHint",
    "PauseReason",
    "PauseEvent",
    "Resolution",
    "RuntimeState",
]
```

```python
# zerotoken/models/operation.py
"""浏览器操作的核心数据模型"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """所有支持的浏览器动作类型"""
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
    TYPE_TEXT = "type_text"


class PageState(BaseModel):
    """页面状态快照"""
    url: str = ""
    title: str = ""
    tab_id: int = 0
    tab_count: int = 1
    timestamp: datetime = Field(default_factory=datetime.now)


class SelectorCandidate(BaseModel):
    """备选选择器（含稳定性评分）"""
    type: str
    value: str
    stability_score: float = 0.0


class OperationResult(BaseModel):
    """操作执行结果"""
    success: bool
    data: dict[str, Any] = {}
    error: Optional[str] = None


class OperationRecord(BaseModel):
    """一次浏览器操作的完整记录"""
    step: int
    action: ActionType
    params: dict[str, Any] = {}
    result: OperationResult
    page_state: PageState
    screenshot: Optional[str] = None
    selector_candidates: list[SelectorCandidate] = []
    timestamp: datetime = Field(default_factory=datetime.now)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_models/test_operation.py -v
```

Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zerotoken/models/ tests/unit/
git commit -m "feat(models): add operation domain models with Pydantic v2"
```

---

## Task 2: Domain Models - Trajectory, Script, Session

**Files:**
- Create: `zerotoken/models/trajectory.py`
- Create: `zerotoken/models/script.py`
- Create: `zerotoken/models/session.py`
- Test: `tests/unit/test_models/test_trajectory.py`
- Test: `tests/unit/test_models/test_script.py`
- Test: `tests/unit/test_models/test_session.py`

- [ ] **Step 1: Write failing tests for all three models**

```python
# tests/unit/test_models/test_trajectory.py
"""Trajectory 模型单元测试"""
import pytest
from datetime import datetime


def test_trajectory_metadata_defaults():
    from zerotoken.models.trajectory import TrajectoryMetadata
    m = TrajectoryMetadata()
    assert m.total_steps == 0
    assert m.successful_steps == 0
    assert m.failed_steps == 0
    assert m.duration_seconds is None


def test_trajectory_add_operation():
    """add_operation 正确递增计数"""
    from zerotoken.models.trajectory import Trajectory
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult
    )
    t = Trajectory(task_id="test", goal="test goal")
    record_ok = OperationRecord(
        step=1, action=ActionType.CLICK,
        params={}, result=OperationResult(success=True),
        page_state=PageState(),
    )
    record_fail = OperationRecord(
        step=2, action=ActionType.CLICK,
        params={}, result=OperationResult(success=False, error="nope"),
        page_state=PageState(),
    )
    t.add_operation(record_ok)
    assert t.metadata.total_steps == 1
    assert t.metadata.successful_steps == 1
    t.add_operation(record_fail)
    assert t.metadata.total_steps == 2
    assert t.metadata.failed_steps == 1


def test_trajectory_to_ai_prompt():
    """to_ai_prompt 生成正确的文本格式"""
    from zerotoken.models.trajectory import Trajectory
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult
    )
    t = Trajectory(task_id="login", goal="Login to system")
    t.add_operation(OperationRecord(
        step=1, action=ActionType.OPEN,
        params={"url": "https://example.com"},
        result=OperationResult(success=True),
        page_state=PageState(),
    ))
    t.add_operation(OperationRecord(
        step=2, action=ActionType.CLICK,
        params={"selector": "#btn"},
        result=OperationResult(success=True),
        page_state=PageState(),
    ))
    prompt = t.to_ai_prompt()
    assert "Task Goal: Login to system" in prompt
    assert "[Step 1] open(" in prompt
    assert "[Step 2] click(" in prompt


def test_trajectory_json_roundtrip():
    from zerotoken.models.trajectory import Trajectory
    t = Trajectory(task_id="t1", goal="goal1")
    json_str = t.model_dump_json()
    t2 = Trajectory.model_validate_json(json_str)
    assert t2.task_id == "t1"
    assert t2.goal == "goal1"
```

```python
# tests/unit/test_models/test_script.py
"""Script 模型单元测试"""
import pytest


def test_script_step_basic():
    from zerotoken.models.script import ScriptStep
    step = ScriptStep(action="browser_click", params={"selector": "#btn"})
    assert step.action == "browser_click"
    assert step.condition is None
    assert step.body == []
    assert step.assign_to is None
    assert step.hint is None


def test_script_step_with_flow_control():
    """ScriptStep 支持嵌套 body/else_body"""
    from zerotoken.models.script import ScriptStep
    step = ScriptStep(
        action="if",
        condition="price < 100",
        body=[
            ScriptStep(action="browser_click", params={"selector": "#buy"}),
        ],
        else_body=[
            ScriptStep(action="browser_screenshot", params={}),
        ],
    )
    assert len(step.body) == 1
    assert len(step.else_body) == 1
    assert step.body[0].action == "browser_click"


def test_script_step_with_assign():
    from zerotoken.models.script import ScriptStep
    step = ScriptStep(
        action="browser_get_text",
        params={"selector": ".price"},
        assign_to="current_price",
    )
    assert step.assign_to == "current_price"


def test_script_full():
    from zerotoken.models.script import Script, ScriptStep
    script = Script(
        task_id="demo",
        goal="demo goal",
        steps=[
            ScriptStep(action="browser_open", params={"url": "https://x.com"}),
            ScriptStep(action="browser_click", params={"selector": "#btn"}),
        ],
    )
    assert len(script.steps) == 2
    d = script.model_dump()
    assert d["task_id"] == "demo"
    assert len(d["steps"]) == 2


def test_script_json_roundtrip():
    from zerotoken.models.script import Script, ScriptStep
    script = Script(
        task_id="rt",
        goal="roundtrip",
        steps=[ScriptStep(action="browser_open", params={"url": "https://x.com"})],
    )
    json_str = script.model_dump_json()
    script2 = Script.model_validate_json(json_str)
    assert script2.task_id == "rt"
    assert script2.steps[0].action == "browser_open"


def test_step_hint():
    from zerotoken.models.script import StepHint
    h = StepHint(hint_id="h1", match_rules=[{"action_is": "browser_click"}], hint_text="may need captcha")
    assert h.hint_id == "h1"
```

```python
# tests/unit/test_models/test_session.py
"""Session 模型单元测试"""
import pytest


def test_pause_event():
    from zerotoken.models.session import PauseEvent, PauseReason
    pe = PauseEvent(
        reason=PauseReason.STEP_FAILED,
        session_id="s1",
        task_id="t1",
        step_index=3,
        action="browser_click",
        params={"selector": "#btn"},
        error="not found",
    )
    assert pe.reason == "step_failed"
    assert pe.step_index == 3
    assert "retry" in pe.allowed_resolutions
    assert "patch_step" in pe.allowed_resolutions
    assert "skip" in pe.allowed_resolutions
    assert "abort" in pe.allowed_resolutions


def test_resolution():
    from zerotoken.models.session import Resolution
    r = Resolution(type="patch_step", patch={"params": {"selector": ".new"}}, note="changed selector")
    assert r.type == "patch_step"
    assert r.patch["params"]["selector"] == ".new"


def test_runtime_state():
    from zerotoken.models.session import RuntimeState
    rs = RuntimeState(
        session_id="s1", task_id="t1",
        cursor_step_index=5, status="running",
    )
    assert rs.cursor_step_index == 5
    assert rs.status == "running"
    assert rs.pause_event is None
    assert rs.vars == {}


def test_runtime_state_json_roundtrip():
    from zerotoken.models.session import RuntimeState, PauseEvent, PauseReason
    rs = RuntimeState(
        session_id="s1", task_id="t1",
        cursor_step_index=3, status="paused",
        pause_event=PauseEvent(
            reason=PauseReason.STEP_FAILED,
            session_id="s1", task_id="t1", step_index=3,
            action="browser_click", params={"selector": "#x"},
            error="timeout",
        ),
        vars={"user": "test"},
    )
    json_str = rs.model_dump_json()
    rs2 = RuntimeState.model_validate_json(json_str)
    assert rs2.status == "paused"
    assert rs2.pause_event.error == "timeout"
    assert rs2.vars["user"] == "test"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_models/ -v
```

Expected: test_operation.py passes (from Task 1), new test files FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement trajectory, script, session models**

```python
# zerotoken/models/trajectory.py
"""轨迹数据模型"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .operation import OperationRecord


class TrajectoryMetadata(BaseModel):
    """轨迹统计元数据"""
    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    duration_seconds: Optional[float] = None


class Trajectory(BaseModel):
    """完整的操作轨迹"""
    task_id: str
    goal: str
    operations: list[OperationRecord] = []
    metadata: TrajectoryMetadata = Field(default_factory=TrajectoryMetadata)
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def add_operation(self, record: OperationRecord) -> None:
        """添加一条操作记录，自动更新统计"""
        self.operations.append(record)
        self.metadata.total_steps = len(self.operations)
        if record.result.success:
            self.metadata.successful_steps += 1
        else:
            self.metadata.failed_steps += 1

    def complete(self) -> None:
        """标记轨迹完成"""
        self.end_time = datetime.now()
        if self.start_time and self.end_time:
            self.metadata.duration_seconds = (
                self.end_time - self.start_time
            ).total_seconds()

    def to_ai_prompt(self) -> str:
        """导出 AI 友好的文本格式"""
        lines = [f"Task Goal: {self.goal}", "", "Operation History:"]
        for op in self.operations:
            param_str = ", ".join(f"{k}={repr(v)}" for k, v in op.params.items())
            lines.append(f"[Step {op.step}] {op.action.value}({param_str})")
        return "\n".join(lines)
```

```python
# zerotoken/models/script.py
"""脚本数据模型（支持嵌套流程控制）"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from .operation import SelectorCandidate


class ScriptStep(BaseModel):
    """脚本步骤（可嵌套：if/loop 的 body 也是 ScriptStep 列表）"""
    action: str
    params: dict[str, Any] = {}
    selector_candidates: list[SelectorCandidate] = []
    condition: Optional[str] = None
    body: list[ScriptStep] = []
    else_body: list[ScriptStep] = []
    assign_to: Optional[str] = None
    hint: Optional[str] = None


class Script(BaseModel):
    """完整脚本"""
    task_id: str
    goal: str
    steps: list[ScriptStep]
    params_schema: dict[str, Any] = {}
    source_trajectory_id: Optional[int] = None


class StepHint(BaseModel):
    """步骤提示模板（可选，替代原 DFU）"""
    hint_id: str
    match_rules: list[dict[str, Any]]
    hint_text: str
```

```python
# zerotoken/models/session.py
"""会话与运行时状态模型"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from .operation import PageState, SelectorCandidate


class PauseReason(str, Enum):
    """暂停原因"""
    STEP_FAILED = "step_failed"
    PRE_STEP_HINT = "pre_step_hint"


class PauseEvent(BaseModel):
    """暂停事件：包含 AI 仲裁所需的全部上下文"""
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
    """AI 仲裁决议"""
    type: str
    patch: dict[str, Any] = {}
    vars: dict[str, Any] = {}
    note: str = ""


class RuntimeState(BaseModel):
    """脚本执行运行时状态（持久化到 DB，支持 pause/resume）"""
    session_id: str
    task_id: str
    cursor_step_index: int
    step_path: list[int | str] = []
    status: str
    pause_event: Optional[PauseEvent] = None
    vars: dict[str, Any] = {}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_models/ -v
```

Expected: All tests PASS (operation + trajectory + script + session)

- [ ] **Step 5: Commit**

```bash
git add zerotoken/models/ tests/unit/test_models/
git commit -m "feat(models): add trajectory, script, session domain models"
```

---

## Task 3: Repository Protocols + SQLite Connection + Migrations

**Files:**
- Create: `zerotoken/repository/__init__.py`
- Create: `zerotoken/repository/protocols.py`
- Create: `zerotoken/repository/migrations.py`
- Test: `tests/unit/test_repository/__init__.py`
- Test: `tests/unit/test_repository/test_migrations.py`

- [ ] **Step 1: Write failing tests**

```bash
mkdir -p tests/unit/test_repository
touch tests/unit/test_repository/__init__.py
```

```python
# tests/unit/test_repository/test_migrations.py
"""数据库迁移测试"""
import sqlite3
import pytest


def test_migration_runner_creates_tables():
    """MigrationRunner 在空数据库上创建所有表"""
    from zerotoken.repository.migrations import MigrationRunner
    conn = sqlite3.connect(":memory:")
    runner = MigrationRunner(conn)
    runner.run()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cursor.fetchall()}
    assert "scripts" in tables
    assert "trajectories" in tables
    assert "session_headers" in tables
    assert "session_steps" in tables
    assert "session_runtime" in tables
    assert "fingerprints" in tables
    assert "script_bindings" in tables
    assert "_migrations" in tables


def test_migration_runner_idempotent():
    """多次调用 run() 不会报错"""
    from zerotoken.repository.migrations import MigrationRunner
    conn = sqlite3.connect(":memory:")
    runner = MigrationRunner(conn)
    runner.run()
    runner.run()
    cursor = conn.execute("SELECT COUNT(*) FROM _migrations")
    count = cursor.fetchone()[0]
    assert count > 0


def test_migration_runner_tracks_versions():
    """已执行的迁移有版本记录"""
    from zerotoken.repository.migrations import MigrationRunner, MIGRATIONS
    conn = sqlite3.connect(":memory:")
    runner = MigrationRunner(conn)
    runner.run()
    cursor = conn.execute("SELECT version FROM _migrations ORDER BY version")
    versions = [row[0] for row in cursor.fetchall()]
    assert versions == [m[0] for m in MIGRATIONS]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_repository/test_migrations.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement protocols and migrations**

```python
# zerotoken/repository/__init__.py
"""ZeroToken Repository Layer"""
from .protocols import (
    ScriptRepo, TrajectoryRepo, SessionRepo,
    RuntimeRepo, FingerprintRepo, BindingRepo,
)

__all__ = [
    "ScriptRepo", "TrajectoryRepo", "SessionRepo",
    "RuntimeRepo", "FingerprintRepo", "BindingRepo",
]
```

```python
# zerotoken/repository/protocols.py
"""存储层协议定义（Protocol，非 ABC）"""
from __future__ import annotations

from typing import Any, Optional, Protocol

from zerotoken.models.script import Script
from zerotoken.models.trajectory import Trajectory


class ScriptRepo(Protocol):
    def script_save(self, task_id: str, *, goal: str, steps: list[dict[str, Any]],
                    params_schema: dict[str, Any] | None = None,
                    source_trajectory_id: int | None = None) -> None: ...
    def script_load(self, task_id: str) -> dict[str, Any] | None: ...
    def script_list(self, limit: int = 100) -> list[dict[str, Any]]: ...
    def script_delete(self, task_id: str) -> bool: ...


class TrajectoryRepo(Protocol):
    def trajectory_save(self, *, task_id: str, goal: str,
                        operations: list[dict[str, Any]],
                        metadata: dict[str, Any] | None = None) -> int: ...
    def trajectory_load(self, trajectory_id: int) -> dict[str, Any] | None: ...
    def trajectory_load_by_task_id(self, task_id: str) -> dict[str, Any] | None: ...
    def trajectory_list(self, limit: int = 100, since: float | None = None) -> list[dict[str, Any]]: ...
    def trajectory_delete_by_task_id(self, task_id: str) -> int: ...


class SessionRepo(Protocol):
    def session_start(self, session_id: str, *, task_id: str | None = None,
                      session_type: str = "replay") -> None: ...
    def session_append(self, session_id: str, *, step_index: int, action: str,
                       selector: str | None = None, url: str | None = None,
                       payload: dict[str, Any] | None = None) -> None: ...
    def session_get(self, session_id: str) -> list[dict[str, Any]]: ...
    def session_list(self, limit: int = 100) -> list[dict[str, Any]]: ...


class RuntimeRepo(Protocol):
    def runtime_init(self, session_id: str, *, task_id: str | None,
                     cursor_step_index: int, status: str,
                     pause_event: dict[str, Any] | None = None,
                     vars: dict[str, Any] | None = None) -> None: ...
    def runtime_get(self, session_id: str) -> dict[str, Any] | None: ...
    def runtime_update(self, session_id: str, **fields: Any) -> None: ...


class FingerprintRepo(Protocol):
    def fingerprint_save(self, domain: str, identifier: str,
                         fingerprint_dict: dict[str, Any]) -> None: ...
    def fingerprint_load(self, domain: str, identifier: str) -> dict[str, Any] | None: ...
    def fingerprint_delete(self, domain: str, identifier: str) -> bool: ...


class BindingRepo(Protocol):
    def binding_set(self, binding_key: str, *, script_task_id: str,
                    description: str = "", default_vars: dict[str, Any] | None = None) -> None: ...
    def binding_get(self, binding_key: str) -> dict[str, Any] | None: ...
    def binding_list(self, limit: int = 100) -> list[dict[str, Any]]: ...
    def binding_delete(self, binding_key: str) -> bool: ...
```

```python
# zerotoken/repository/migrations.py
"""版本化数据库迁移"""
from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[str, str]] = [
    ("001_initial", """
        CREATE TABLE IF NOT EXISTS scripts (
            task_id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            params_schema_json TEXT,
            source_trajectory_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trajectories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            goal TEXT NOT NULL,
            operations_json TEXT NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS session_headers (
            session_id TEXT PRIMARY KEY,
            task_id TEXT,
            session_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS session_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            action TEXT NOT NULL,
            selector TEXT,
            url TEXT,
            timestamp TEXT NOT NULL,
            payload_json TEXT,
            FOREIGN KEY (session_id) REFERENCES session_headers(session_id)
        );
        CREATE TABLE IF NOT EXISTS session_runtime (
            session_id TEXT PRIMARY KEY,
            task_id TEXT,
            cursor_step_index INTEGER NOT NULL,
            step_path_json TEXT,
            status TEXT NOT NULL,
            pause_event_json TEXT,
            vars_json TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fingerprints (
            domain TEXT NOT NULL,
            identifier TEXT NOT NULL,
            fingerprint_json TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (domain, identifier)
        );
        CREATE TABLE IF NOT EXISTS script_bindings (
            binding_key TEXT PRIMARY KEY,
            script_task_id TEXT NOT NULL,
            description TEXT,
            default_vars_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """),
]


class MigrationRunner:
    """跟踪已执行的迁移版本，只跑增量"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def run(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
        self.conn.commit()
        cursor = self.conn.execute("SELECT version FROM _migrations")
        applied = {row[0] for row in cursor.fetchall()}
        for version, sql in MIGRATIONS:
            if version not in applied:
                self.conn.executescript(sql)
                self.conn.execute(
                    "INSERT INTO _migrations (version, applied_at) VALUES (?, datetime('now'))",
                    (version,),
                )
                self.conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_repository/test_migrations.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zerotoken/repository/ tests/unit/test_repository/
git commit -m "feat(repository): add protocols, migrations, and SQLiteConnection foundation"
```

---

## Task 4: SQLite Script + Trajectory Repos

**Files:**
- Create: `zerotoken/repository/sqlite.py`
- Test: `tests/unit/test_repository/test_sqlite_script.py`
- Test: `tests/unit/test_repository/test_sqlite_trajectory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_repository/test_sqlite_script.py
"""SQLiteScriptRepo 单元测试"""
import sqlite3
import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import SQLiteScriptRepo, new_connection
    conn = new_connection(":memory:")
    return SQLiteScriptRepo(conn)


def test_save_and_load(repo):
    repo.script_save("t1", goal="test", steps=[{"action": "browser_open", "params": {"url": "https://x.com"}}])
    script = repo.script_load("t1")
    assert script is not None
    assert script["task_id"] == "t1"
    assert script["goal"] == "test"
    assert len(script["steps"]) == 1
    assert script["steps"][0]["action"] == "browser_open"


def test_load_not_found(repo):
    assert repo.script_load("nonexistent") is None


def test_save_overwrites(repo):
    repo.script_save("t1", goal="v1", steps=[])
    repo.script_save("t1", goal="v2", steps=[{"action": "browser_click", "params": {}}])
    script = repo.script_load("t1")
    assert script["goal"] == "v2"
    assert len(script["steps"]) == 1


def test_list(repo):
    repo.script_save("a", goal="ga", steps=[])
    repo.script_save("b", goal="gb", steps=[])
    items = repo.script_list(limit=10)
    assert len(items) == 2
    task_ids = {it["task_id"] for it in items}
    assert task_ids == {"a", "b"}


def test_delete(repo):
    repo.script_save("t1", goal="g", steps=[])
    assert repo.script_delete("t1") is True
    assert repo.script_load("t1") is None
    assert repo.script_delete("t1") is False


def test_save_with_source_trajectory_id(repo):
    repo.script_save("t1", goal="g", steps=[], source_trajectory_id=42)
    script = repo.script_load("t1")
    assert script["source_trajectory_id"] == 42
```

```python
# tests/unit/test_repository/test_sqlite_trajectory.py
"""SQLiteTrajectoryRepo 单元测试"""
import sqlite3
import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import SQLiteTrajectoryRepo, new_connection
    conn = new_connection(":memory:")
    return SQLiteTrajectoryRepo(conn)


def test_save_and_load(repo):
    tid = repo.trajectory_save(
        task_id="login", goal="login test",
        operations=[{"step": 1, "action": "open", "params": {"url": "https://x.com"}}],
        metadata={"total_steps": 1},
    )
    assert isinstance(tid, int)
    traj = repo.trajectory_load(tid)
    assert traj is not None
    assert traj["task_id"] == "login"
    assert len(traj["operations"]) == 1


def test_load_by_task_id(repo):
    repo.trajectory_save(task_id="t1", goal="g1", operations=[])
    repo.trajectory_save(task_id="t1", goal="g1 v2", operations=[{"step": 1}])
    traj = repo.trajectory_load_by_task_id("t1")
    assert traj is not None
    assert traj["goal"] == "g1 v2"


def test_load_by_task_id_not_found(repo):
    assert repo.trajectory_load_by_task_id("nope") is None


def test_list(repo):
    repo.trajectory_save(task_id="a", goal="ga", operations=[])
    repo.trajectory_save(task_id="b", goal="gb", operations=[])
    items = repo.trajectory_list(limit=10)
    assert len(items) == 2


def test_delete_by_task_id(repo):
    repo.trajectory_save(task_id="t1", goal="g", operations=[])
    repo.trajectory_save(task_id="t1", goal="g", operations=[])
    deleted = repo.trajectory_delete_by_task_id("t1")
    assert deleted == 2
    assert repo.trajectory_load_by_task_id("t1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_repository/test_sqlite_script.py tests/unit/test_repository/test_sqlite_trajectory.py -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement SQLite repos**

```python
# zerotoken/repository/sqlite.py
"""SQLite 存储实现 -- 每个 Repo 只管自己的表"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .migrations import MigrationRunner


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(s: Optional[str]) -> Any:
    if s is None:
        return None
    return json.loads(s)


def new_connection(db_path: str) -> sqlite3.Connection:
    """创建并初始化数据库连接（运行迁移）"""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    MigrationRunner(conn).run()
    return conn


class SQLiteScriptRepo:
    """scripts 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def script_save(
        self, task_id: str, *, goal: str, steps: list[dict[str, Any]],
        params_schema: dict[str, Any] | None = None,
        source_trajectory_id: int | None = None,
    ) -> None:
        now = _now_iso()
        self.conn.execute(
            """INSERT INTO scripts (task_id, goal, steps_json, params_schema_json, source_trajectory_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(task_id) DO UPDATE SET
                 goal=excluded.goal, steps_json=excluded.steps_json,
                 params_schema_json=excluded.params_schema_json,
                 source_trajectory_id=excluded.source_trajectory_id,
                 updated_at=excluded.updated_at""",
            (task_id, goal, _json_dumps(steps), _json_dumps(params_schema or {}),
             source_trajectory_id, now, now),
        )
        self.conn.commit()

    def script_load(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT task_id, goal, steps_json, params_schema_json, source_trajectory_id, created_at, updated_at FROM scripts WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "task_id": row["task_id"], "goal": row["goal"],
            "steps": _json_loads(row["steps_json"]),
            "params_schema": _json_loads(row["params_schema_json"]),
            "source_trajectory_id": row["source_trajectory_id"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def script_list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT task_id, goal, created_at FROM scripts ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"task_id": r["task_id"], "goal": r["goal"], "created_at": r["created_at"]} for r in rows]

    def script_delete(self, task_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM scripts WHERE task_id=?", (task_id,))
        self.conn.commit()
        return cur.rowcount > 0


class SQLiteTrajectoryRepo:
    """trajectories 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def trajectory_save(
        self, *, task_id: str, goal: str,
        operations: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = _now_iso()
        cur = self.conn.execute(
            "INSERT INTO trajectories (task_id, goal, operations_json, metadata_json, created_at) VALUES (?,?,?,?,?)",
            (task_id, goal, _json_dumps(operations), _json_dumps(metadata or {}), now),
        )
        self.conn.commit()
        return cur.lastrowid

    def trajectory_load(self, trajectory_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, task_id, goal, operations_json, metadata_json, created_at FROM trajectories WHERE id=?",
            (trajectory_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"], "task_id": row["task_id"], "goal": row["goal"],
            "operations": _json_loads(row["operations_json"]),
            "metadata": _json_loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def trajectory_load_by_task_id(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, task_id, goal, operations_json, metadata_json, created_at FROM trajectories WHERE task_id=? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"], "task_id": row["task_id"], "goal": row["goal"],
            "operations": _json_loads(row["operations_json"]),
            "metadata": _json_loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def trajectory_list(
        self, limit: int = 100, since: float | None = None,
    ) -> list[dict[str, Any]]:
        if since is not None:
            since_iso = datetime.utcfromtimestamp(since).strftime("%Y-%m-%dT%H:%M:%SZ")
            rows = self.conn.execute(
                "SELECT id, task_id, goal, created_at FROM trajectories WHERE created_at>=? ORDER BY id DESC LIMIT ?",
                (since_iso, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, task_id, goal, created_at FROM trajectories ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"id": r["id"], "task_id": r["task_id"], "goal": r["goal"], "created_at": r["created_at"]} for r in rows]

    def trajectory_delete_by_task_id(self, task_id: str) -> int:
        cur = self.conn.execute("DELETE FROM trajectories WHERE task_id=?", (task_id,))
        self.conn.commit()
        return cur.rowcount


class SQLiteSessionRepo:
    """session_headers + session_steps 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def session_start(self, session_id: str, *, task_id: str | None = None, session_type: str = "replay") -> None:
        now = _now_iso()
        self.conn.execute(
            "INSERT OR REPLACE INTO session_headers (session_id, task_id, session_type, created_at) VALUES (?,?,?,?)",
            (session_id, task_id, session_type, now),
        )
        self.conn.commit()

    def session_append(self, session_id: str, *, step_index: int, action: str,
                       selector: str | None = None, url: str | None = None,
                       payload: dict[str, Any] | None = None) -> None:
        now = _now_iso()
        self.conn.execute(
            "INSERT INTO session_steps (session_id, step_index, action, selector, url, timestamp, payload_json) VALUES (?,?,?,?,?,?,?)",
            (session_id, step_index, action, selector, url, now, _json_dumps(payload or {})),
        )
        self.conn.commit()

    def session_get(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT step_index, action, selector, url, timestamp, payload_json FROM session_steps WHERE session_id=? ORDER BY step_index",
            (session_id,),
        ).fetchall()
        return [{
            "step_index": r["step_index"], "action": r["action"],
            "selector": r["selector"], "url": r["url"],
            "timestamp": r["timestamp"], "payload": _json_loads(r["payload_json"]),
        } for r in rows]

    def session_list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT session_id, task_id, session_type, created_at FROM session_headers ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"session_id": r["session_id"], "task_id": r["task_id"],
                 "session_type": r["session_type"], "created_at": r["created_at"]} for r in rows]


class SQLiteRuntimeRepo:
    """session_runtime 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def runtime_init(self, session_id: str, *, task_id: str | None,
                     cursor_step_index: int, status: str,
                     pause_event: dict[str, Any] | None = None,
                     vars: dict[str, Any] | None = None) -> None:
        now = _now_iso()
        self.conn.execute(
            """INSERT INTO session_runtime (session_id, task_id, cursor_step_index, step_path_json, status, pause_event_json, vars_json, updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
                 task_id=excluded.task_id, cursor_step_index=excluded.cursor_step_index,
                 step_path_json=excluded.step_path_json, status=excluded.status,
                 pause_event_json=excluded.pause_event_json, vars_json=excluded.vars_json,
                 updated_at=excluded.updated_at""",
            (session_id, task_id, cursor_step_index, _json_dumps([]), status,
             _json_dumps(pause_event) if pause_event else None,
             _json_dumps(vars or {}), now),
        )
        self.conn.commit()

    def runtime_get(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT session_id, task_id, cursor_step_index, step_path_json, status, pause_event_json, vars_json, updated_at FROM session_runtime WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"], "task_id": row["task_id"],
            "cursor_step_index": int(row["cursor_step_index"]),
            "step_path": _json_loads(row["step_path_json"]) or [],
            "status": row["status"],
            "pause_event": _json_loads(row["pause_event_json"]),
            "vars": _json_loads(row["vars_json"]) or {},
            "updated_at": row["updated_at"],
        }

    def runtime_update(self, session_id: str, **fields: Any) -> None:
        existing = self.runtime_get(session_id)
        if existing is None:
            raise KeyError(f"runtime not found: {session_id}")
        now = _now_iso()
        new_cursor = fields.get("cursor_step_index", existing["cursor_step_index"])
        new_status = fields.get("status", existing["status"])
        new_step_path = fields.get("step_path", existing["step_path"])
        pe = fields.get("pause_event", existing["pause_event"])
        new_pe_json = _json_dumps(pe) if pe is not None else None
        new_vars = fields.get("vars", existing["vars"])
        self.conn.execute(
            """UPDATE session_runtime SET cursor_step_index=?, step_path_json=?, status=?,
               pause_event_json=?, vars_json=?, updated_at=? WHERE session_id=?""",
            (int(new_cursor), _json_dumps(new_step_path), new_status,
             new_pe_json, _json_dumps(new_vars or {}), now, session_id),
        )
        self.conn.commit()


class SQLiteFingerprintRepo:
    """fingerprints 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def fingerprint_save(self, domain: str, identifier: str, fingerprint_dict: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO fingerprints (domain, identifier, fingerprint_json, updated_at) VALUES (?,?,?,?)",
            (domain, identifier, _json_dumps(fingerprint_dict), time.time()),
        )
        self.conn.commit()

    def fingerprint_load(self, domain: str, identifier: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT fingerprint_json FROM fingerprints WHERE domain=? AND identifier=?",
            (domain, identifier),
        ).fetchone()
        if row is None:
            return None
        return _json_loads(row["fingerprint_json"])

    def fingerprint_delete(self, domain: str, identifier: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM fingerprints WHERE domain=? AND identifier=?",
            (domain, identifier),
        )
        self.conn.commit()
        return cur.rowcount > 0


class SQLiteBindingRepo:
    """script_bindings 表 CRUD"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def binding_set(self, binding_key: str, *, script_task_id: str,
                    description: str = "", default_vars: dict[str, Any] | None = None) -> None:
        now = _now_iso()
        self.conn.execute(
            """INSERT INTO script_bindings (binding_key, script_task_id, description, default_vars_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(binding_key) DO UPDATE SET
                 script_task_id=excluded.script_task_id, description=excluded.description,
                 default_vars_json=excluded.default_vars_json, updated_at=excluded.updated_at""",
            (binding_key, script_task_id, description, _json_dumps(default_vars or {}), now, now),
        )
        self.conn.commit()

    def binding_get(self, binding_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT binding_key, script_task_id, description, default_vars_json, created_at, updated_at FROM script_bindings WHERE binding_key=?",
            (binding_key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "binding_key": row["binding_key"], "script_task_id": row["script_task_id"],
            "description": row["description"] or "",
            "default_vars": _json_loads(row["default_vars_json"]) or {},
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def binding_list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT binding_key, script_task_id, description, updated_at FROM script_bindings ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"binding_key": r["binding_key"], "script_task_id": r["script_task_id"],
                 "description": r["description"] or "", "updated_at": r["updated_at"]} for r in rows]

    def binding_delete(self, binding_key: str) -> bool:
        cur = self.conn.execute("DELETE FROM script_bindings WHERE binding_key=?", (binding_key,))
        self.conn.commit()
        return cur.rowcount > 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_repository/ -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zerotoken/repository/sqlite.py tests/unit/test_repository/
git commit -m "feat(repository): SQLite script and trajectory repos with full CRUD"
```

---

## Task 5: SQLite Session, Runtime, Fingerprint, Binding Repos - Tests

**Files:**
- Test: `tests/unit/test_repository/test_sqlite_session.py`
- Test: `tests/unit/test_repository/test_sqlite_fingerprint.py`
- Test: `tests/unit/test_repository/test_sqlite_binding.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_repository/test_sqlite_session.py
"""SQLiteSessionRepo + SQLiteRuntimeRepo 测试"""
import pytest


@pytest.fixture
def session_repo():
    from zerotoken.repository.sqlite import SQLiteSessionRepo, new_connection
    conn = new_connection(":memory:")
    return SQLiteSessionRepo(conn)


@pytest.fixture
def runtime_repo():
    from zerotoken.repository.sqlite import SQLiteRuntimeRepo, new_connection
    conn = new_connection(":memory:")
    return SQLiteRuntimeRepo(conn)


def test_session_start_and_append(session_repo):
    session_repo.session_start("s1", task_id="t1")
    session_repo.session_append("s1", step_index=0, action="open", url="https://x.com")
    session_repo.session_append("s1", step_index=1, action="click", selector="#btn")
    steps = session_repo.session_get("s1")
    assert len(steps) == 2
    assert steps[0]["action"] == "open"
    assert steps[1]["selector"] == "#btn"


def test_session_list(session_repo):
    session_repo.session_start("s1", task_id="t1")
    session_repo.session_start("s2", task_id="t2")
    items = session_repo.session_list()
    assert len(items) == 2


def test_runtime_init_and_get(runtime_repo):
    runtime_repo.runtime_init("s1", task_id="t1", cursor_step_index=0, status="running")
    rt = runtime_repo.runtime_get("s1")
    assert rt is not None
    assert rt["status"] == "running"
    assert rt["cursor_step_index"] == 0


def test_runtime_update(runtime_repo):
    runtime_repo.runtime_init("s1", task_id="t1", cursor_step_index=0, status="running")
    runtime_repo.runtime_update("s1", cursor_step_index=3, status="paused")
    rt = runtime_repo.runtime_get("s1")
    assert rt["cursor_step_index"] == 3
    assert rt["status"] == "paused"


def test_runtime_get_not_found(runtime_repo):
    assert runtime_repo.runtime_get("nope") is None


def test_runtime_update_not_found(runtime_repo):
    with pytest.raises(KeyError):
        runtime_repo.runtime_update("nope", status="x")
```

```python
# tests/unit/test_repository/test_sqlite_fingerprint.py
"""SQLiteFingerprintRepo 测试"""
import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import SQLiteFingerprintRepo, new_connection
    conn = new_connection(":memory:")
    return SQLiteFingerprintRepo(conn)


def test_save_and_load(repo):
    repo.fingerprint_save("example.com", "#btn", {"tag": "button", "text": "Submit"})
    fp = repo.fingerprint_load("example.com", "#btn")
    assert fp is not None
    assert fp["tag"] == "button"


def test_load_not_found(repo):
    assert repo.fingerprint_load("x.com", "nope") is None


def test_domain_isolation(repo):
    repo.fingerprint_save("a.com", "#btn", {"v": 1})
    repo.fingerprint_save("b.com", "#btn", {"v": 2})
    assert repo.fingerprint_load("a.com", "#btn")["v"] == 1
    assert repo.fingerprint_load("b.com", "#btn")["v"] == 2


def test_delete(repo):
    repo.fingerprint_save("x.com", "#btn", {"v": 1})
    assert repo.fingerprint_delete("x.com", "#btn") is True
    assert repo.fingerprint_load("x.com", "#btn") is None
    assert repo.fingerprint_delete("x.com", "#btn") is False
```

```python
# tests/unit/test_repository/test_sqlite_binding.py
"""SQLiteBindingRepo 测试"""
import pytest


@pytest.fixture
def repo():
    from zerotoken.repository.sqlite import SQLiteBindingRepo, new_connection
    conn = new_connection(":memory:")
    return SQLiteBindingRepo(conn)


def test_set_and_get(repo):
    repo.binding_set("job1", script_task_id="script1", description="test binding", default_vars={"user": "admin"})
    b = repo.binding_get("job1")
    assert b is not None
    assert b["script_task_id"] == "script1"
    assert b["default_vars"]["user"] == "admin"


def test_get_not_found(repo):
    assert repo.binding_get("nope") is None


def test_list(repo):
    repo.binding_set("j1", script_task_id="s1")
    repo.binding_set("j2", script_task_id="s2")
    items = repo.binding_list()
    assert len(items) == 2


def test_delete(repo):
    repo.binding_set("j1", script_task_id="s1")
    assert repo.binding_delete("j1") is True
    assert repo.binding_get("j1") is None
    assert repo.binding_delete("j1") is False
```

- [ ] **Step 2: Run tests to verify they pass** (implementation was in Task 4)

```bash
pytest tests/unit/test_repository/ -v
```

Expected: All tests PASS (repos were implemented in Task 4)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_repository/
git commit -m "test(repository): add session, runtime, fingerprint, binding repo tests"
```

---

## Task 6: BrowserContextManager

**Files:**
- Create: `zerotoken/browser/__init__.py`
- Create: `zerotoken/browser/context.py`
- Create: `zerotoken/browser/stealth.py` (migrate from existing)
- Test: `tests/unit/test_browser/__init__.py`
- Test: `tests/unit/test_browser/test_context.py`

- [ ] **Step 1: Write failing tests**

```bash
mkdir -p tests/unit/test_browser
touch tests/unit/test_browser/__init__.py
```

```python
# tests/unit/test_browser/test_context.py
"""BrowserContextManager 单元测试（Mock Playwright）"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_playwright():
    """构建完整的 Playwright mock 链"""
    mock_page = AsyncMock()
    mock_page.url = "about:blank"
    mock_page.title = AsyncMock(return_value="")
    mock_page.close = AsyncMock()
    mock_page.bring_to_front = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.frame_locator = MagicMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_browser.is_connected = MagicMock(return_value=True)

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw = AsyncMock()
    mock_pw.chromium = mock_chromium

    return mock_pw, mock_browser, mock_context, mock_page


@pytest.mark.asyncio
async def test_start_creates_page(mock_playwright):
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager
        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        assert mgr.active_page is not None
        assert mgr.active_page.tab_id == 0


@pytest.mark.asyncio
async def test_new_tab(mock_playwright):
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager
        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        tab = await mgr.new_tab()
        assert tab.tab_id == 1
        assert len(mgr.list_tabs_sync()) == 2


@pytest.mark.asyncio
async def test_switch_tab(mock_playwright):
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager
        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        await mgr.new_tab()
        assert mgr.active_page.tab_id == 0
        switched = await mgr.switch_tab(1)
        assert mgr.active_page.tab_id == 1


@pytest.mark.asyncio
async def test_switch_tab_invalid(mock_playwright):
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager
        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        with pytest.raises(ValueError, match="Tab 99 not found"):
            await mgr.switch_tab(99)


@pytest.mark.asyncio
async def test_enter_exit_iframe(mock_playwright):
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    mock_frame = MagicMock()
    mock_page.frame_locator = MagicMock(return_value=mock_frame)
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager
        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        mp = mgr.active_page
        assert mp.active_frame == mock_page
        mgr.enter_iframe("#myframe")
        assert mp.active_frame == mock_frame
        mgr.exit_iframe()
        assert mp.active_frame == mock_page


@pytest.mark.asyncio
async def test_stop(mock_playwright):
    mock_pw, mock_browser, mock_context, mock_page = mock_playwright
    with patch("zerotoken.browser.context.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_pw)
        from zerotoken.browser.context import BrowserContextManager
        mgr = BrowserContextManager()
        await mgr.start(headless=True, viewport={"width": 1920, "height": 1080}, stealth=False)
        await mgr.stop()
        mock_page.close.assert_called()
        mock_browser.close.assert_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_browser/test_context.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'zerotoken.browser'`

- [ ] **Step 3: Implement BrowserContextManager**

```bash
mkdir -p zerotoken/browser/actions zerotoken/browser/stability
touch zerotoken/browser/__init__.py zerotoken/browser/actions/__init__.py zerotoken/browser/stability/__init__.py
```

Copy stealth module:
```bash
cp zerotoken/stealth.py zerotoken/browser/stealth.py
```

```python
# zerotoken/browser/context.py
"""浏览器上下文管理：多标签页 + iframe 栈"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .stealth import STEALTH_LAUNCH_ARGS, STEALTH_INIT_SCRIPT, DEFAULT_STEALTH_USER_AGENT


@dataclass
class ManagedPage:
    """一个受管理的标签页"""
    page: Page
    tab_id: int
    iframe_stack: list[Any] = field(default_factory=list)

    @property
    def active_frame(self) -> Any:
        """当前活动帧：iframe 内返回最内层 frame，否则返回 page"""
        return self.iframe_stack[-1] if self.iframe_stack else self.page


class BrowserContextManager:
    """管理浏览器生命周期 + 多标签页 + iframe 栈"""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pages: dict[int, ManagedPage] = {}
        self._active_tab_id: int = 0
        self._next_tab_id: int = 0

    async def start(
        self, *, headless: bool = True,
        viewport: dict[str, int] | None = None,
        stealth: bool = False,
    ) -> None:
        """启动浏览器，创建第一个标签页"""
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        launch_args = (
            STEALTH_LAUNCH_ARGS if stealth
            else ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        self._browser = await self._playwright.chromium.launch(
            headless=headless, args=launch_args,
        )
        vp = viewport or {"width": 1920, "height": 1080}
        if stealth:
            self._context = await self._browser.new_context(
                viewport=vp, user_agent=DEFAULT_STEALTH_USER_AGENT,
                locale="en-US", timezone_id="America/New_York",
            )
            await self._context.add_init_script(STEALTH_INIT_SCRIPT)
        else:
            self._context = await self._browser.new_context(
                viewport=vp,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
        page = await self._context.new_page()
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        self._pages[tab_id] = ManagedPage(page=page, tab_id=tab_id)
        self._active_tab_id = tab_id

    async def stop(self) -> None:
        """关闭所有标签页和浏览器"""
        for mp in self._pages.values():
            try:
                await mp.page.close()
            except Exception:
                pass
        self._pages.clear()
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    @property
    def active_page(self) -> ManagedPage:
        """当前激活的标签页"""
        if self._active_tab_id not in self._pages:
            raise RuntimeError("No active page. Call start() first.")
        return self._pages[self._active_tab_id]

    async def new_tab(self, url: str | None = None) -> ManagedPage:
        """新建标签页"""
        if self._context is None:
            raise RuntimeError("Browser not started")
        page = await self._context.new_page()
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        mp = ManagedPage(page=page, tab_id=tab_id)
        self._pages[tab_id] = mp
        if url:
            await page.goto(url)
        return mp

    async def switch_tab(self, tab_id: int) -> ManagedPage:
        """切换到指定标签页"""
        if tab_id not in self._pages:
            raise ValueError(f"Tab {tab_id} not found")
        self._active_tab_id = tab_id
        await self._pages[tab_id].page.bring_to_front()
        return self._pages[tab_id]

    async def close_tab(self, tab_id: int | None = None) -> None:
        """关闭标签页，自动切到其他存活标签页"""
        tid = tab_id if tab_id is not None else self._active_tab_id
        if tid not in self._pages:
            raise ValueError(f"Tab {tid} not found")
        await self._pages[tid].page.close()
        del self._pages[tid]
        if self._pages and tid == self._active_tab_id:
            self._active_tab_id = next(iter(self._pages))

    def list_tabs_sync(self) -> list[dict[str, Any]]:
        """列出所有标签页（同步，不依赖 await）"""
        return [
            {"tab_id": mp.tab_id, "url": mp.page.url, "active": mp.tab_id == self._active_tab_id}
            for mp in self._pages.values()
        ]

    def enter_iframe(self, selector: str) -> None:
        """进入 iframe（可嵌套）"""
        mp = self.active_page
        parent = mp.active_frame
        frame = parent.frame_locator(selector)
        mp.iframe_stack.append(frame)

    def exit_iframe(self, exit_all: bool = False) -> None:
        """退出 iframe"""
        mp = self.active_page
        if exit_all:
            mp.iframe_stack.clear()
        elif mp.iframe_stack:
            mp.iframe_stack.pop()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_browser/test_context.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zerotoken/browser/ tests/unit/test_browser/
git commit -m "feat(browser): BrowserContextManager with multi-tab and iframe support"
```

---

## Task 7: Stability Middleware + ActionPipeline

**Files:**
- Create: `zerotoken/browser/stability/middleware.py`
- Migrate: `zerotoken/browser/stability/selector.py` (from `zerotoken/selector.py`)
- Migrate: `zerotoken/browser/stability/wait.py` (from `zerotoken/wait_strategy.py`)
- Migrate: `zerotoken/browser/stability/recovery.py` (from `zerotoken/recovery.py`)
- Migrate: `zerotoken/browser/stability/adaptive.py` (from `zerotoken/adaptive.py`)
- Create: `zerotoken/browser/pipeline.py`
- Test: `tests/unit/test_browser/test_stability_middleware.py`
- Test: `tests/unit/test_browser/test_pipeline.py`

- [ ] **Step 1: Migrate existing stability modules**

Copy existing files to new locations, update imports:

```bash
cp zerotoken/selector.py zerotoken/browser/stability/selector.py
cp zerotoken/wait_strategy.py zerotoken/browser/stability/wait.py
cp zerotoken/recovery.py zerotoken/browser/stability/recovery.py
cp zerotoken/adaptive.py zerotoken/browser/stability/adaptive.py
```

Update relative imports in each copied file (e.g. `from .selector import ...` -> adjust paths). The stability modules' internal APIs stay the same; only import paths change.

- [ ] **Step 2: Write failing tests for StabilityMiddleware and ActionPipeline**

```python
# tests/unit/test_browser/test_stability_middleware.py
"""StabilityMiddleware 单元测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_locate_direct_success():
    """选择器直接命中时返回 element + candidates"""
    from zerotoken.browser.stability.middleware import StabilityMiddleware
    mock_page = AsyncMock()
    mock_element = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(return_value=mock_element)
    mw = StabilityMiddleware(selector_gen=None, adaptive_storage=None)
    element, candidates = await mw.locate(mock_page, "#btn", auto_save=False, adaptive=False, identifier=None)
    assert element == mock_element


@pytest.mark.asyncio
async def test_locate_failure_no_adaptive():
    """选择器失败且 adaptive=False 时抛异常"""
    from zerotoken.browser.stability.middleware import StabilityMiddleware
    mock_page = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=Exception("not found"))
    mw = StabilityMiddleware(selector_gen=None, adaptive_storage=None)
    with pytest.raises(Exception, match="not found"):
        await mw.locate(mock_page, "#btn", auto_save=False, adaptive=False, identifier=None)
```

```python
# tests/unit/test_browser/test_pipeline.py
"""ActionPipeline 单元测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_pipeline_execute_success():
    """成功执行动作返回 OperationRecord"""
    from zerotoken.browser.pipeline import ActionPipeline
    from zerotoken.models.operation import ActionType

    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_page.page = AsyncMock()
    mock_page.page.url = "https://example.com"
    mock_page.page.title = AsyncMock(return_value="Example")
    mock_page.active_frame = mock_page.page
    mock_page.tab_id = 0
    mock_context.active_page = mock_page
    mock_context._pages = {0: mock_page}

    mock_stability = AsyncMock()

    pipeline = ActionPipeline(context=mock_context, stability=mock_stability)

    async def mock_action(frame, element, params):
        return {"navigated": False}

    record = await pipeline.execute(
        action=ActionType.CLICK,
        params={"selector": "#btn"},
        action_fn=mock_action,
        needs_selector=False,
        take_screenshot=False,
    )

    assert record.step == 1
    assert record.action == ActionType.CLICK
    assert record.result.success is True
    assert record.result.data["navigated"] is False


@pytest.mark.asyncio
async def test_pipeline_step_counter_increments():
    """步骤计数器递增"""
    from zerotoken.browser.pipeline import ActionPipeline
    from zerotoken.models.operation import ActionType

    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_page.page = AsyncMock()
    mock_page.page.url = "https://x.com"
    mock_page.page.title = AsyncMock(return_value="X")
    mock_page.active_frame = mock_page.page
    mock_page.tab_id = 0
    mock_context.active_page = mock_page
    mock_context._pages = {0: mock_page}

    pipeline = ActionPipeline(context=mock_context, stability=AsyncMock())

    async def noop(frame, element, params):
        return {}

    r1 = await pipeline.execute(ActionType.OPEN, {}, action_fn=noop, needs_selector=False, take_screenshot=False)
    r2 = await pipeline.execute(ActionType.CLICK, {}, action_fn=noop, needs_selector=False, take_screenshot=False)
    assert r1.step == 1
    assert r2.step == 2
```

- [ ] **Step 3: Implement StabilityMiddleware and ActionPipeline**

```python
# zerotoken/browser/stability/middleware.py
"""统一稳定性中间件：智能选择器 + 自适应定位 + 错误恢复"""
from __future__ import annotations

from typing import Any, Optional


class StabilityMiddleware:
    """统一封装定位流程"""

    def __init__(
        self,
        selector_gen: Any = None,
        adaptive_storage: Any = None,
        timeout: int = 30000,
    ):
        self.selector_gen = selector_gen
        self.adaptive_storage = adaptive_storage
        self.timeout = timeout

    async def locate(
        self,
        page: Any,
        selector: str,
        *,
        auto_save: bool = False,
        adaptive: bool = False,
        identifier: str | None = None,
    ) -> tuple[Any, list[dict[str, Any]]]:
        """
        统一定位流程:
        1. 直接用 selector 定位
        2. 失败 + adaptive=True 时用指纹重定位
        3. 成功时生成 selector_candidates
        4. auto_save=True 时保存指纹
        返回 (element, selector_candidates)
        """
        ident = identifier or selector
        candidates: list[dict[str, Any]] = []

        try:
            element = await page.wait_for_selector(selector, timeout=self.timeout)
            if element and self.selector_gen:
                try:
                    smart = await self.selector_gen.generate(element)
                    candidates = [
                        {"type": c.type.value, "value": c.value, "stability_score": c.stability_score}
                        for c in smart.all_selectors()
                    ]
                except Exception:
                    pass
            if element and auto_save and self.adaptive_storage:
                try:
                    from .adaptive import extract_fingerprint, _domain_from_url
                    fp = await extract_fingerprint(element, page)
                    if fp:
                        domain = _domain_from_url(page.url)
                        self.adaptive_storage.fingerprint_save(domain, ident, fp)
                except Exception:
                    pass
            return element, candidates
        except Exception as e:
            if adaptive and self.adaptive_storage:
                try:
                    from .adaptive import relocate, _domain_from_url
                    domain = _domain_from_url(page.url)
                    handle = await relocate(page, domain, ident, self.adaptive_storage)
                    if handle:
                        return handle, candidates
                except Exception:
                    pass
            raise
```

```python
# zerotoken/browser/pipeline.py
"""统一执行管道：所有浏览器操作经过同一流程"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from zerotoken.models.operation import (
    ActionType, OperationRecord, OperationResult,
    PageState, SelectorCandidate,
)
from .context import BrowserContextManager, ManagedPage
from .stability.middleware import StabilityMiddleware

ActionFn = Callable[[Any, Any, dict[str, Any]], Awaitable[dict[str, Any]]]


class ActionPipeline:
    """统一执行管道"""

    def __init__(
        self,
        context: BrowserContextManager,
        stability: StabilityMiddleware,
    ):
        self.context = context
        self.stability = stability
        self._step_counter = 0

    def _next_step(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def reset_counter(self) -> None:
        self._step_counter = 0

    async def execute(
        self,
        action: ActionType,
        params: dict[str, Any],
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
        mp = self.context.active_page
        frame = mp.active_frame

        element = None
        candidates: list[SelectorCandidate] = []
        if needs_selector and params.get("selector"):
            raw_element, raw_candidates = await self.stability.locate(
                frame, params["selector"],
                auto_save=auto_save, adaptive=adaptive, identifier=identifier,
            )
            element = raw_element
            candidates = [SelectorCandidate(**c) for c in raw_candidates]

        result_data = await action_fn(frame, element, params)

        page_state = await self._capture_state(mp)
        screenshot = None
        if take_screenshot:
            screenshot = await self._take_screenshot_safe(mp.page)

        return OperationRecord(
            step=step,
            action=action,
            params=params,
            result=OperationResult(success=True, data=result_data),
            page_state=page_state,
            screenshot=screenshot,
            selector_candidates=candidates,
        )

    async def _capture_state(self, mp: ManagedPage) -> PageState:
        try:
            title = await mp.page.title()
        except Exception:
            title = ""
        return PageState(
            url=mp.page.url,
            title=title,
            tab_id=mp.tab_id,
            tab_count=len(self.context._pages),
        )

    async def _take_screenshot_safe(self, page: Any) -> str | None:
        try:
            import base64
            data = await page.screenshot()
            return base64.b64encode(data).decode("utf-8")
        except Exception:
            return None

    async def capture_state_safe(self) -> PageState | None:
        try:
            return await self._capture_state(self.context.active_page)
        except Exception:
            return None

    async def take_screenshot_safe(self) -> str | None:
        try:
            return await self._take_screenshot_safe(self.context.active_page.page)
        except Exception:
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_browser/ -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zerotoken/browser/
git add tests/unit/test_browser/
git commit -m "feat(browser): ActionPipeline and StabilityMiddleware"
```

---

## Task 8: Browser Actions (navigate + interact + extract)

**Files:**
- Create: `zerotoken/browser/actions/navigate.py`
- Create: `zerotoken/browser/actions/interact.py`
- Create: `zerotoken/browser/actions/extract.py`
- Test: `tests/unit/test_browser/test_actions_navigate.py`
- Test: `tests/unit/test_browser/test_actions_interact.py`
- Test: `tests/unit/test_browser/test_actions_extract.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_browser/test_actions_navigate.py
"""Navigate actions 单元测试"""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_open_action():
    from zerotoken.browser.actions.navigate import open_action
    mock_frame = AsyncMock()
    result = await open_action(mock_frame, None, {"url": "https://example.com", "wait_until": "networkidle"})
    mock_frame.goto.assert_called_once_with("https://example.com", wait_until="networkidle", timeout=30000)
    assert result["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_wait_for_action_selector():
    from zerotoken.browser.actions.navigate import wait_for_action
    mock_frame = AsyncMock()
    result = await wait_for_action(mock_frame, None, {"condition": "selector", "value": "#btn", "timeout": 5000})
    mock_frame.wait_for_selector.assert_called_once_with("#btn", timeout=5000)
    assert result["condition"] == "selector"
```

```python
# tests/unit/test_browser/test_actions_interact.py
"""Interact actions 单元测试"""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_click_action():
    from zerotoken.browser.actions.interact import click_action
    mock_frame = AsyncMock()
    mock_frame.url = "https://example.com"
    mock_element = AsyncMock()
    result = await click_action(mock_frame, mock_element, {"scroll_into_view": True, "wait_after": 0})
    mock_element.scroll_into_view_if_needed.assert_called_once()
    mock_element.click.assert_called_once()
    assert "navigated" in result


@pytest.mark.asyncio
async def test_input_action():
    from zerotoken.browser.actions.interact import input_action
    mock_frame = AsyncMock()
    mock_element = AsyncMock()
    mock_element.evaluate = AsyncMock(return_value="hello")
    result = await input_action(mock_frame, mock_element, {"text": "hello", "delay": 50, "clear_first": True})
    mock_element.fill.assert_called_once_with("")
    mock_element.type.assert_called_once_with("hello", delay=50)
    assert result["text"] == "hello"
    assert result["actual_value"] == "hello"
```

```python
# tests/unit/test_browser/test_actions_extract.py
"""Extract actions 单元测试"""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_get_text_action():
    from zerotoken.browser.actions.extract import get_text_action
    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value="  Hello World  ")
    result = await get_text_action(AsyncMock(), mock_element, {"attribute": "text"})
    assert result["value"] == "Hello World"


@pytest.mark.asyncio
async def test_get_html_action_with_selector():
    from zerotoken.browser.actions.extract import get_html_action
    mock_element = AsyncMock()
    mock_element.inner_html = AsyncMock(return_value="<span>hi</span>")
    result = await get_html_action(AsyncMock(), mock_element, {"selector": "#box"})
    assert result["html"] == "<span>hi</span>"


@pytest.mark.asyncio
async def test_get_html_action_full_page():
    from zerotoken.browser.actions.extract import get_html_action
    mock_frame = AsyncMock()
    mock_frame.content = AsyncMock(return_value="<html>full</html>")
    result = await get_html_action(mock_frame, None, {})
    assert result["html"] == "<html>full</html>"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_browser/test_actions_navigate.py tests/unit/test_browser/test_actions_interact.py tests/unit/test_browser/test_actions_extract.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement action functions**

```python
# zerotoken/browser/actions/navigate.py
"""导航类动作：open, wait_for"""
from __future__ import annotations
from typing import Any
import json


async def open_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """打开 URL"""
    url = params.get("url", "")
    wait_until = params.get("wait_until", "networkidle")
    timeout = params.get("timeout", 30000)
    await frame.goto(url, wait_until=wait_until, timeout=timeout)
    return {"url": url}


async def wait_for_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """等待条件"""
    condition = params.get("condition", "")
    value = params.get("value")
    timeout = params.get("timeout", 30000)

    if condition == "selector":
        await frame.wait_for_selector(value, timeout=timeout)
    elif condition == "url":
        await frame.wait_for_url(value, timeout=timeout)
    elif condition == "text":
        safe_value = json.dumps(value)
        await frame.wait_for_function(
            f"document.body.innerText.includes({safe_value})", timeout=timeout
        )
    elif condition == "navigation":
        await frame.wait_for_load_state("networkidle", timeout=timeout)
    else:
        raise ValueError(f"Unknown wait condition: {condition}")

    return {"condition": condition, "value": value}
```

```python
# zerotoken/browser/actions/interact.py
"""交互类动作：click, input"""
from __future__ import annotations

import asyncio
from typing import Any


async def click_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """点击元素"""
    if params.get("scroll_into_view", True) and element:
        await element.scroll_into_view_if_needed()
    await element.click()
    wait_after = params.get("wait_after", 0.5)
    if wait_after > 0:
        await asyncio.sleep(wait_after)
    old_url = params.get("_old_url", frame.url if hasattr(frame, "url") else "")
    current_url = frame.url if hasattr(frame, "url") else ""
    navigated = current_url != old_url
    return {"navigated": navigated, "new_url": current_url if navigated else None}


async def input_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """输入文本"""
    text = params.get("text", "")
    delay = params.get("delay", 50)
    clear_first = params.get("clear_first", True)
    if clear_first:
        await element.fill("")
    await element.type(text, delay=delay)
    actual_value = await element.evaluate("el => el.value")
    return {
        "text": text,
        "actual_value": actual_value,
        "match": actual_value == text,
    }
```

```python
# zerotoken/browser/actions/extract.py
"""提取类动作：get_text, get_html, screenshot, extract_data"""
from __future__ import annotations

import base64
from typing import Any


async def get_text_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """提取文本或属性"""
    attr = params.get("attribute", params.get("attr", "text"))
    if attr == "text":
        value = await element.text_content()
    elif attr == "html":
        value = await element.inner_html()
    elif attr == "value":
        value = await element.get_attribute("value")
    elif attr == "innerText":
        value = await element.evaluate("el => el.innerText")
    else:
        value = await element.get_attribute(attr)
    return {"attribute": attr, "value": value.strip() if value else value}


async def get_html_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """获取 HTML 内容"""
    if element:
        html = await element.inner_html()
    else:
        html = await frame.content()
    return {"html": html}


async def screenshot_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """截图"""
    full_page = params.get("full_page", False)
    path = params.get("path")
    if element:
        data = await element.screenshot()
    else:
        data = await frame.screenshot(full_page=full_page)
    b64 = base64.b64encode(data).decode("utf-8")
    if path:
        with open(path, "wb") as f:
            f.write(data)
    return {"screenshot": b64, "path": path, "full_page": full_page}


async def extract_data_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """按 schema 提取结构化数据"""
    schema = params.get("schema", {})
    extracted: dict[str, Any] = {}
    for field in schema.get("fields", []):
        name = field["name"]
        selector = field["selector"]
        field_type = field.get("type", "text")
        try:
            el = await frame.wait_for_selector(selector, timeout=5000)
            if field_type == "text":
                extracted[name] = (await el.text_content() or "").strip()
            elif field_type == "html":
                extracted[name] = await el.inner_html()
            elif field_type == "value":
                extracted[name] = await el.get_attribute("value")
            elif field_type == "float":
                text = await el.text_content() or ""
                extracted[name] = float(text.replace("$", "").replace(",", "").strip())
            elif field_type == "int":
                text = await el.text_content() or ""
                extracted[name] = int("".join(filter(str.isdigit, text)))
            else:
                extracted[name] = await el.text_content()
        except Exception as e:
            extracted[name] = None
            extracted[f"{name}_error"] = str(e)
    return {"data": extracted, "schema": schema}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_browser/ -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zerotoken/browser/actions/ tests/unit/test_browser/
git commit -m "feat(browser): navigate, interact, extract action functions"
```

---

## Task 9: Services (BrowserService + TrajectoryService + ScriptService)

**Files:**
- Create: `zerotoken/services/__init__.py`
- Create: `zerotoken/services/browser_service.py`
- Create: `zerotoken/services/trajectory_service.py`
- Create: `zerotoken/services/script_service.py`
- Test: `tests/unit/test_services/__init__.py`
- Test: `tests/unit/test_services/test_browser_service.py`
- Test: `tests/unit/test_services/test_trajectory_service.py`
- Test: `tests/unit/test_services/test_script_service.py`

- [ ] **Step 1: Write failing tests**

```bash
mkdir -p tests/unit/test_services
touch tests/unit/test_services/__init__.py
```

```python
# tests/unit/test_services/test_trajectory_service.py
"""TrajectoryService 单元测试（含探索模式）"""
import pytest
from unittest.mock import MagicMock
from zerotoken.models.operation import (
    OperationRecord, ActionType, PageState, OperationResult
)


def _make_record(step=1, success=True):
    return OperationRecord(
        step=step, action=ActionType.CLICK,
        params={"selector": "#btn"},
        result=OperationResult(success=success),
        page_state=PageState(url="https://x.com"),
    )


def test_recording_mode_records():
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    svc.start_trajectory("t1", "test goal")
    record = _make_record()
    svc.record_operation(record)
    traj = svc.get_current_trajectory()
    assert traj is not None
    assert len(traj.operations) == 1


def test_explore_mode_skips_recording():
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    svc.start_trajectory("t1", "test goal")
    svc.start_explore(reason="looking around")
    assert svc.should_record() is False
    svc.record_operation(_make_record(step=1))
    svc.record_operation(_make_record(step=2))
    result = svc.stop_explore()
    assert result["skipped_steps"] == 2
    assert svc.should_record() is True
    traj = svc.get_current_trajectory()
    assert len(traj.operations) == 0


def test_explore_mode_without_trajectory_raises():
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    with pytest.raises(ValueError, match="No active trajectory"):
        svc.start_explore()


def test_complete_trajectory():
    from zerotoken.services.trajectory_service import TrajectoryService
    mock_repo = MagicMock()
    mock_repo.trajectory_save = MagicMock(return_value=42)
    svc = TrajectoryService(trajectory_repo=mock_repo)
    svc.start_trajectory("t1", "goal")
    svc.record_operation(_make_record())
    traj = svc.complete_trajectory()
    assert traj is not None
    assert traj.end_time is not None
    mock_repo.trajectory_save.assert_called_once()


def test_status():
    from zerotoken.services.trajectory_service import TrajectoryService, RecordingMode
    mock_repo = MagicMock()
    svc = TrajectoryService(trajectory_repo=mock_repo)
    status = svc.get_status()
    assert status["mode"] == RecordingMode.RECORDING.value
    assert status["has_trajectory"] is False
    svc.start_trajectory("t1", "g")
    status = svc.get_status()
    assert status["has_trajectory"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_services/test_trajectory_service.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement services**

```bash
mkdir -p zerotoken/services
touch zerotoken/services/__init__.py
```

```python
# zerotoken/services/trajectory_service.py
"""轨迹服务：录制/导出/管理 + 探索模式"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from zerotoken.models.operation import OperationRecord
from zerotoken.models.trajectory import Trajectory


class RecordingMode(str, Enum):
    RECORDING = "recording"
    EXPLORING = "exploring"


class TrajectoryService:
    """轨迹录制与管理"""

    def __init__(self, trajectory_repo: Any):
        self._repo = trajectory_repo
        self._current: Optional[Trajectory] = None
        self._mode = RecordingMode.RECORDING
        self._explore_depth = 0

    def start_trajectory(self, task_id: str, goal: str) -> Trajectory:
        self._current = Trajectory(task_id=task_id, goal=goal)
        self._mode = RecordingMode.RECORDING
        self._explore_depth = 0
        return self._current

    def get_current_trajectory(self) -> Optional[Trajectory]:
        return self._current

    def should_record(self) -> bool:
        return self._mode == RecordingMode.RECORDING

    def record_operation(self, record: OperationRecord) -> None:
        if self._mode == RecordingMode.EXPLORING:
            self._explore_depth += 1
            return
        if self._current:
            self._current.add_operation(record)

    def start_explore(self, reason: str = "") -> dict[str, Any]:
        if self._current is None:
            raise ValueError("No active trajectory")
        self._mode = RecordingMode.EXPLORING
        self._explore_depth = 0
        return {"mode": "exploring", "reason": reason}

    def stop_explore(self, keep_last: bool = False) -> dict[str, Any]:
        skipped = self._explore_depth
        self._mode = RecordingMode.RECORDING
        self._explore_depth = 0
        return {"mode": "recording", "skipped_steps": skipped}

    def complete_trajectory(self) -> Optional[Trajectory]:
        if self._current is None:
            return None
        self._current.complete()
        traj = self._current
        self._repo.trajectory_save(
            task_id=traj.task_id,
            goal=traj.goal,
            operations=[op.model_dump() for op in traj.operations],
            metadata=traj.metadata.model_dump(),
        )
        self._current = None
        self._mode = RecordingMode.RECORDING
        return traj

    def get_status(self) -> dict[str, Any]:
        return {
            "mode": self._mode.value,
            "has_trajectory": self._current is not None,
            "task_id": self._current.task_id if self._current else None,
            "operations_count": len(self._current.operations) if self._current else 0,
            "explore_depth": self._explore_depth,
        }
```

```python
# zerotoken/services/browser_service.py
"""浏览器服务：封装 ActionPipeline + BrowserContextManager"""
from __future__ import annotations

from typing import Any, Optional

from zerotoken.models.operation import ActionType, OperationRecord
from zerotoken.browser.context import BrowserContextManager
from zerotoken.browser.pipeline import ActionPipeline
from zerotoken.browser.stability.middleware import StabilityMiddleware
from zerotoken.browser.actions.navigate import open_action, wait_for_action
from zerotoken.browser.actions.interact import click_action, input_action
from zerotoken.browser.actions.extract import (
    get_text_action, get_html_action, screenshot_action, extract_data_action,
)


class BrowserService:
    """浏览器操作编排"""

    def __init__(self, fingerprint_repo: Any = None):
        self._context = BrowserContextManager()
        self._stability = StabilityMiddleware(adaptive_storage=fingerprint_repo)
        self._pipeline: Optional[ActionPipeline] = None

    async def init(self, *, headless: bool = True,
                   viewport: dict[str, int] | None = None,
                   stealth: bool = False) -> dict[str, Any]:
        await self._context.start(headless=headless, viewport=viewport, stealth=stealth)
        self._pipeline = ActionPipeline(self._context, self._stability)
        return {"success": True, "message": "Browser initialized"}

    async def close(self) -> dict[str, Any]:
        await self._context.stop()
        self._pipeline = None
        return {"success": True, "message": "Browser closed"}

    def _ensure_pipeline(self) -> ActionPipeline:
        if self._pipeline is None:
            raise RuntimeError("Browser not initialized. Call init() first.")
        return self._pipeline

    async def open(self, url: str, wait_until: str = "networkidle", **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.OPEN, {"url": url, "wait_until": wait_until},
            action_fn=open_action, needs_selector=False,
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def click(self, selector: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {"selector": selector, "scroll_into_view": kw.get("scroll_into_view", True),
                  "wait_after": kw.get("wait_after", 0.5),
                  "_old_url": self._context.active_page.page.url}
        return await pipeline.execute(
            ActionType.CLICK, params, action_fn=click_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def input(self, selector: str, text: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {"selector": selector, "text": text,
                  "delay": kw.get("delay", 50), "clear_first": kw.get("clear_first", True)}
        return await pipeline.execute(
            ActionType.INPUT, params, action_fn=input_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def get_text(self, selector: str, attr: str = "text", **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.GET_TEXT, {"selector": selector, "attribute": attr},
            action_fn=get_text_action,
            take_screenshot=kw.get("take_screenshot", False),
        )

    async def get_html(self, selector: str | None = None, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.GET_HTML, {"selector": selector} if selector else {},
            action_fn=get_html_action,
            needs_selector=selector is not None,
            take_screenshot=kw.get("take_screenshot", False),
        )

    async def screenshot(self, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {"full_page": kw.get("full_page", False), "path": kw.get("path"),
                  "selector": kw.get("selector")}
        return await pipeline.execute(
            ActionType.SCREENSHOT, params, action_fn=screenshot_action,
            needs_selector=False, take_screenshot=False,
        )

    async def wait_for(self, condition: str, value: str | None = None, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {"condition": condition, "value": value, "timeout": kw.get("timeout", 30000)}
        return await pipeline.execute(
            ActionType.WAIT_FOR, params, action_fn=wait_for_action,
            needs_selector=False, take_screenshot=kw.get("take_screenshot", True),
        )

    async def extract_data(self, schema: dict[str, Any], **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.EXTRACT_DATA, {"schema": schema},
            action_fn=extract_data_action, needs_selector=False,
            take_screenshot=kw.get("take_screenshot", True),
        )

    @property
    def context(self) -> BrowserContextManager:
        return self._context
```

```python
# zerotoken/services/script_service.py
"""脚本服务：脚本管理/执行/绑定（基础版，无 v2 引擎）"""
from __future__ import annotations

from typing import Any, Optional


class ScriptService:
    """脚本管理服务"""

    def __init__(self, script_repo: Any, trajectory_repo: Any,
                 session_repo: Any, runtime_repo: Any, binding_repo: Any):
        self._scripts = script_repo
        self._trajectories = trajectory_repo
        self._sessions = session_repo
        self._runtime = runtime_repo
        self._bindings = binding_repo

    def script_save(self, task_id: str, goal: str, steps: list[dict[str, Any]], **kw: Any) -> None:
        self._scripts.script_save(task_id, goal=goal, steps=steps, **kw)

    def script_load(self, task_id: str) -> dict[str, Any] | None:
        return self._scripts.script_load(task_id)

    def script_list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._scripts.script_list(limit=limit)

    def script_delete(self, task_id: str) -> bool:
        return self._scripts.script_delete(task_id)

    def trajectory_to_script(self, task_id: str, **kw: Any) -> str:
        """从轨迹生成脚本（复用现有 generator 逻辑）"""
        from zerotoken.engine.script_generator import save_script_from_trajectory
        traj_data = self._trajectories.trajectory_load_by_task_id(task_id)
        if traj_data is None:
            raise ValueError(f"No trajectory for task_id: {task_id}")
        return save_script_from_trajectory(
            traj_data, self._scripts,
            task_id=kw.get("script_task_id", task_id),
            prepend_init=kw.get("prepend_init", True),
            stealth=kw.get("stealth", False),
        )

    def binding_set(self, binding_key: str, script_task_id: str, **kw: Any) -> None:
        self._bindings.binding_set(binding_key, script_task_id=script_task_id, **kw)

    def binding_get(self, binding_key: str) -> dict[str, Any] | None:
        return self._bindings.binding_get(binding_key)

    def binding_list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._bindings.binding_list(limit=limit)

    def binding_delete(self, binding_key: str) -> bool:
        return self._bindings.binding_delete(binding_key)

    def session_list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._sessions.session_list(limit=limit)

    def session_get(self, session_id: str) -> list[dict[str, Any]]:
        return self._sessions.session_get(session_id)
```

```python
# zerotoken/services/__init__.py
"""ZeroToken Service Layer"""
from .browser_service import BrowserService
from .trajectory_service import TrajectoryService, RecordingMode
from .script_service import ScriptService

__all__ = ["BrowserService", "TrajectoryService", "RecordingMode", "ScriptService"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_services/ -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zerotoken/services/ tests/unit/test_services/
git commit -m "feat(services): BrowserService, TrajectoryService with explore mode, ScriptService"
```

---

## Task 10: Handlers + MCP Server Entry Point

**Files:**
- Create: `handlers/__init__.py`
- Create: `handlers/browser_handlers.py`
- Create: `handlers/trajectory_handlers.py`
- Create: `handlers/script_handlers.py`
- Rewrite: `mcp_server.py`
- Test: `tests/unit/test_handlers/__init__.py`
- Test: `tests/unit/test_handlers/test_browser_handlers.py`

- [ ] **Step 1: Write failing tests for browser handlers**

```bash
mkdir -p tests/unit/test_handlers
touch tests/unit/test_handlers/__init__.py
```

```python
# tests/unit/test_handlers/test_browser_handlers.py
"""Browser handler 单元测试"""
import pytest


def test_browser_tools_returns_list():
    """browser_tools() 返回 Tool 列表"""
    from handlers.browser_handlers import browser_tools
    tools = browser_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0
    names = {t.name for t in tools}
    assert "browser_init" in names
    assert "browser_close" in names
    assert "browser_open" in names
    assert "browser_click" in names
    assert "browser_input" in names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_handlers/test_browser_handlers.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement handlers and rewrite mcp_server.py**

创建 handlers 包并实现各 handler 模块。每个 handler 模块包含：
1. `*_tools()` 函数 -- 返回 MCP Tool 定义列表
2. `handle_*_tool()` 函数 -- 分发到具体处理函数

由于 handler 代码主要是工具定义 (inputSchema JSON) 和参数解析 + 调用 service，属于胶水代码。实现参照现有 `mcp_server.py` 的 Tool 定义，但拆分到各自模块。

重写 `mcp_server.py`：

```python
# mcp_server.py
"""ZeroToken MCP Server - 入口点"""
import asyncio
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from zerotoken.repository.sqlite import (
    new_connection, SQLiteScriptRepo, SQLiteTrajectoryRepo,
    SQLiteSessionRepo, SQLiteRuntimeRepo, SQLiteFingerprintRepo, SQLiteBindingRepo,
)
from zerotoken.services import BrowserService, TrajectoryService, ScriptService
from handlers.browser_handlers import browser_tools, handle_browser_tool
from handlers.trajectory_handlers import trajectory_tools, handle_trajectory_tool
from handlers.script_handlers import script_tools, handle_script_tool

server = Server("zerotoken")

_db_conn = None
_browser_svc = None
_trajectory_svc = None
_script_svc = None


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


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    _init_services()
    if name.startswith("browser_"):
        return await handle_browser_tool(name, arguments, _browser_svc, _trajectory_svc)
    elif name.startswith("trajectory_"):
        return await handle_trajectory_tool(name, arguments, _trajectory_svc)
    else:
        return await handle_script_tool(name, arguments, _script_svc)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run(transport: str = "stdio"):
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

- [ ] **Step 4: Run all tests**

```bash
pytest tests/unit/ -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add handlers/ mcp_server.py tests/unit/test_handlers/
git commit -m "feat: modular handlers and rewritten MCP server entry point"
```

---

## Task 11: Version Unification + pyproject.toml + CI

**Files:**
- Modify: `zerotoken/__init__.py`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: `server.json`

- [ ] **Step 1: Unify version**

```python
# zerotoken/__init__.py
"""ZeroToken - AI Agent browser automation MCP engine"""
try:
    from importlib.metadata import version
    __version__ = version("zerotoken")
except Exception:
    __version__ = "2.0.0-dev"
```

Update `pyproject.toml` version to `2.0.0`. Update `server.json` version to match.

- [ ] **Step 2: Update CI**

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install uv && uv sync --all-groups
      - run: uv run pytest tests/unit/ -v --tb=short
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install uv && uv sync --all-groups
      - run: uv run playwright install chromium --with-deps
      - run: uv run pytest tests/integration/ -v --tb=short || true
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/unit/ -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add zerotoken/__init__.py pyproject.toml server.json .github/workflows/ci.yml
git commit -m "chore: unify version to 2.0.0, update CI with lint + split test jobs"
```

---

## Task 12: Cleanup - Remove Old Modules

**Files:**
- Remove old top-level modules that have been migrated to new locations
- Keep old files temporarily with deprecation imports pointing to new locations (optional)

- [ ] **Step 1: Verify new architecture tests pass**

```bash
pytest tests/unit/ -v
```

- [ ] **Step 2: Update `zerotoken/__init__.py` to export from new locations**

Update `__init__.py` to re-export key symbols from new `models/`, `services/`, `browser/` modules for any code that might import from the package root.

- [ ] **Step 3: Run full tests including any remaining old tests that still pass**

```bash
pytest tests/ -v --ignore=tests/unit
```

Identify which old tests can be migrated or removed.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: wire up new architecture exports, prepare for old module removal"
```

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Domain Models - Operation | `models/operation.py` |
| 2 | Domain Models - Trajectory, Script, Session | `models/trajectory.py`, `models/script.py`, `models/session.py` |
| 3 | Repository Protocols + Migrations | `repository/protocols.py`, `repository/migrations.py` |
| 4 | SQLite Script + Trajectory Repos | `repository/sqlite.py` |
| 5 | SQLite Session/Runtime/Fingerprint/Binding Tests | test files |
| 6 | BrowserContextManager | `browser/context.py` |
| 7 | StabilityMiddleware + ActionPipeline | `browser/stability/middleware.py`, `browser/pipeline.py` |
| 8 | Browser Actions (navigate/interact/extract) | `browser/actions/*.py` |
| 9 | Services (Browser/Trajectory/Script) | `services/*.py` |
| 10 | Handlers + MCP Server Rewrite | `handlers/*.py`, `mcp_server.py` |
| 11 | Version + CI | `pyproject.toml`, CI config |
| 12 | Cleanup old modules | migration |

**After Plan 1 is complete:** The system is architecturally equivalent to the current one, running on the new layered architecture. Next steps are Plan 2 (capability expansion) and Plan 3 (ScriptEngine v2).
