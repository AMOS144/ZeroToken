# Browser Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 high-frequency browser operation failures by adding smart degradation to wait_for, JS fallback to pipeline element location, and timeout-based screenshot degradation.

**Architecture:** Three independent fixes, each touching 2-3 files. Fix 1 modifies `wait_for_action` to degrade from `visible` to `attached`. Fix 2 modifies `ActionPipeline.execute` to fall back to `query_selector` when `locate` times out. Fix 3 wraps `screenshot_action` with `asyncio.wait_for` and a three-level degradation strategy.

**Tech Stack:** Python 3.11+, Playwright, asyncio

---

## File Structure

| File | Responsibility |
|------|----------------|
| `zerotoken/browser/actions/navigate.py` | [Modify] `wait_for_action`: add `state` param + degradation |
| `zerotoken/services/browser_service.py` | [Modify] `wait_for`: pass `state` through |
| `handlers/browser_handlers.py` | [Modify] `browser_wait_for` schema + `browser_screenshot` schema |
| `zerotoken/browser/pipeline.py` | [Modify] `execute`: JS fallback on locate timeout |
| `zerotoken/browser/actions/extract.py` | [Modify] `screenshot_action`: timeout + degradation |
| `tests/unit/test_browser/test_actions_navigate.py` | [Modify] Add wait_for degradation tests |
| `tests/unit/test_browser/test_pipeline.py` | [Modify] Add JS fallback tests |
| `tests/unit/test_browser/test_actions_extract.py` | [Modify] Add screenshot degradation tests |

---

### Task 1: `wait_for_action` 智能降级

**Files:**
- Modify: `zerotoken/browser/actions/navigate.py:17-38`
- Modify: `handlers/browser_handlers.py:198-207` (schema)
- Modify: `handlers/browser_handlers.py:399-405` (dispatch)
- Modify: `zerotoken/services/browser_service.py:66-77`
- Test: `tests/unit/test_browser/test_actions_navigate.py`

- [ ] **Step 1: Write failing tests for wait_for degradation**

Append to `tests/unit/test_browser/test_actions_navigate.py`:

```python
@pytest.mark.asyncio
async def test_wait_for_action_passes_state():
    """state 参数应透传给 wait_for_selector"""
    from zerotoken.browser.actions.navigate import wait_for_action

    mock_frame = AsyncMock()
    result = await wait_for_action(mock_frame, None, {
        "condition": "selector", "value": "#box",
        "timeout": 5000, "state": "attached",
    })
    mock_frame.wait_for_selector.assert_called_once_with(
        "#box", state="attached", timeout=5000,
    )
    assert result["state"] == "attached"


@pytest.mark.asyncio
async def test_wait_for_action_degrades_visible_to_attached():
    """visible 超时但 attached 成功时应降级并标记 degraded"""
    from playwright.async_api import TimeoutError as PwTimeout
    from zerotoken.browser.actions.navigate import wait_for_action

    mock_frame = AsyncMock()
    call_count = 0

    async def side_effect(selector, state="visible", timeout=30000):
        nonlocal call_count
        call_count += 1
        if state == "visible":
            raise PwTimeout("timeout")

    mock_frame.wait_for_selector = AsyncMock(side_effect=side_effect)
    result = await wait_for_action(mock_frame, None, {
        "condition": "selector", "value": ".card", "timeout": 10000,
    })
    assert result["degraded"] is True
    assert result["state"] == "attached"
    assert call_count == 2


@pytest.mark.asyncio
async def test_wait_for_action_no_degrade_if_attached_also_fails():
    """visible 和 attached 都超时时应抛原始异常"""
    from playwright.async_api import TimeoutError as PwTimeout
    from zerotoken.browser.actions.navigate import wait_for_action

    mock_frame = AsyncMock()
    mock_frame.wait_for_selector = AsyncMock(side_effect=PwTimeout("timeout"))

    with pytest.raises(PwTimeout):
        await wait_for_action(mock_frame, None, {
            "condition": "selector", "value": ".gone", "timeout": 4000,
        })


@pytest.mark.asyncio
async def test_wait_for_action_no_degrade_when_state_explicit():
    """显式传 state=attached 超时时不做二次降级"""
    from playwright.async_api import TimeoutError as PwTimeout
    from zerotoken.browser.actions.navigate import wait_for_action

    mock_frame = AsyncMock()
    mock_frame.wait_for_selector = AsyncMock(side_effect=PwTimeout("timeout"))

    with pytest.raises(PwTimeout):
        await wait_for_action(mock_frame, None, {
            "condition": "selector", "value": ".x",
            "timeout": 4000, "state": "attached",
        })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_browser/test_actions_navigate.py -v`
Expected: New tests FAIL (no `state` param, no degradation)

- [ ] **Step 3: Implement wait_for_action degradation**

Replace `wait_for_action` in `zerotoken/browser/actions/navigate.py`:

```python
async def wait_for_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """等待条件（selector / url / text / navigation）
    selector 模式支持 state 参数和 visible -> attached 自动降级。
    """
    condition = params.get("condition", "")
    value = params.get("value")
    timeout = params.get("timeout", 30000)
    state = params.get("state", "visible")

    if condition == "selector":
        try:
            await frame.wait_for_selector(value, state=state, timeout=timeout)
            return {"condition": condition, "value": value, "state": state}
        except Exception as exc:
            if state == "visible" and "timeout" in str(exc).lower():
                fallback_timeout = max(timeout // 2, 2000)
                try:
                    await frame.wait_for_selector(
                        value, state="attached", timeout=fallback_timeout,
                    )
                    return {
                        "condition": condition, "value": value,
                        "state": "attached", "degraded": True,
                    }
                except Exception:
                    pass
            raise
    elif condition == "url":
        await frame.wait_for_url(value, timeout=timeout)
    elif condition == "text":
        safe_value = json.dumps(value)
        await frame.wait_for_function(
            f"document.body.innerText.includes({safe_value})",
            timeout=timeout,
        )
    elif condition == "navigation":
        await frame.wait_for_load_state("networkidle", timeout=timeout)
    else:
        raise ValueError(f"Unknown wait condition: {condition}")

    return {"condition": condition, "value": value}
```

- [ ] **Step 4: Update browser_wait_for schema and handler**

In `handlers/browser_handlers.py`, update the `browser_wait_for` Tool schema (around line 198-207):

Add `"state"` to the schema properties:

```python
        Tool(
            name="browser_wait_for",
            description="Wait for a condition (selector, url, text, navigation)",
            inputSchema=_obj_schema({
                "condition": {"type": "string", "description": "Type of condition"},
                "value": {"type": "string", "description": "Condition value"},
                "timeout": {"type": "integer", "description": "Timeout in ms", "default": 30000},
                "state": {"type": "string", "description": "Wait state: visible / attached / hidden / detached (default: visible)"},
                **_SCREENSHOT_PROP,
            }, required=["condition"]),
        ),
```

Update the dispatch section (around line 399-405):

```python
    if name == "browser_wait_for":
        return await svc.wait_for(
            args["condition"],
            args.get("value"),
            timeout=args.get("timeout", 30000),
            state=args.get("state", "visible"),
            **take_ss,
        )
```

- [ ] **Step 5: Update browser_service.py wait_for to pass state**

In `zerotoken/services/browser_service.py`, update `wait_for` (line 66-77):

```python
    async def wait_for(self, condition: str, value: str | None = None,
                       **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {
            "condition": condition,
            "value": value,
            "timeout": kw.get("timeout", 30000),
            "state": kw.get("state", "visible"),
        }
        return await pipeline.execute(
            ActionType.WAIT_FOR, params, action_fn=wait_for_action,
            needs_selector=False, take_screenshot=kw.get("take_screenshot", True),
        )
```

- [ ] **Step 6: Run all tests to verify**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_browser/test_actions_navigate.py tests/unit/test_browser/test_pipeline.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/browser/actions/navigate.py zerotoken/services/browser_service.py handlers/browser_handlers.py tests/unit/test_browser/test_actions_navigate.py
git commit -m "feat(browser): add state param and visible->attached degradation to wait_for"
```

---

### Task 2: Pipeline JS Fallback

**Files:**
- Modify: `zerotoken/browser/pipeline.py:45-100`
- Test: `tests/unit/test_browser/test_pipeline.py`

- [ ] **Step 1: Write failing tests for JS fallback**

Append to `tests/unit/test_browser/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_pipeline_js_fallback_on_locate_timeout():
    """locate 超时但 query_selector 找到元素时应使用 JS fallback"""
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

    mock_js_element = AsyncMock()
    mock_page.page.query_selector = AsyncMock(return_value=mock_js_element)

    mock_stability = AsyncMock()
    mock_stability.locate = AsyncMock(side_effect=Exception("Timeout 30000ms exceeded"))

    pipeline = ActionPipeline(context=mock_context, stability=mock_stability)

    received_elements = []

    async def capture_action(frame, element, params):
        received_elements.append(element)
        return {"text": "hello"}

    record = await pipeline.execute(
        action=ActionType.GET_TEXT,
        params={"selector": "#hidden-el"},
        action_fn=capture_action,
        needs_selector=True,
        take_screenshot=False,
    )

    assert received_elements[0] == mock_js_element
    assert record.result.success is True
    assert record.result.data.get("js_fallback") is True


@pytest.mark.asyncio
async def test_pipeline_js_fallback_element_not_in_dom():
    """locate 超时且 query_selector 也找不到时应抛原始异常"""
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

    mock_page.page.query_selector = AsyncMock(return_value=None)

    mock_stability = AsyncMock()
    mock_stability.locate = AsyncMock(side_effect=Exception("Timeout 30000ms exceeded"))

    pipeline = ActionPipeline(context=mock_context, stability=mock_stability)

    async def noop(frame, element, params):
        return {}

    with pytest.raises(Exception, match="Timeout"):
        await pipeline.execute(
            action=ActionType.CLICK,
            params={"selector": "#gone"},
            action_fn=noop,
            needs_selector=True,
            take_screenshot=False,
        )


@pytest.mark.asyncio
async def test_pipeline_no_fallback_when_locate_succeeds():
    """locate 成功时不应触发 JS fallback"""
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

    mock_element = AsyncMock()
    mock_stability = AsyncMock()
    mock_stability.locate = AsyncMock(return_value=(mock_element, []))

    pipeline = ActionPipeline(context=mock_context, stability=mock_stability)

    async def capture_action(frame, element, params):
        return {"clicked": True}

    record = await pipeline.execute(
        action=ActionType.CLICK,
        params={"selector": "#btn"},
        action_fn=capture_action,
        needs_selector=True,
        take_screenshot=False,
    )

    assert record.result.data.get("js_fallback") is None
    mock_page.page.query_selector.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_browser/test_pipeline.py::test_pipeline_js_fallback_on_locate_timeout tests/unit/test_browser/test_pipeline.py::test_pipeline_js_fallback_element_not_in_dom -v`
Expected: FAIL (no fallback logic)

- [ ] **Step 3: Implement JS fallback in pipeline.execute**

Replace the element location block in `zerotoken/browser/pipeline.py` (lines 67-79) with:

```python
        # 按需通过 StabilityMiddleware 定位元素
        element = None
        candidates: list[SelectorCandidate] = []
        js_fallback_used = False
        if needs_selector and params.get("selector"):
            try:
                raw_element, raw_candidates = await self.stability.locate(
                    frame,
                    params["selector"],
                    auto_save=auto_save,
                    adaptive=adaptive,
                    identifier=identifier,
                )
                element = raw_element
                candidates = [SelectorCandidate(**c) for c in raw_candidates]
            except Exception:
                # JS fallback: 元素可能在 DOM 中但不可见
                js_element = await frame.query_selector(params["selector"])
                if js_element is not None:
                    element = js_element
                    js_fallback_used = True
                else:
                    raise

        # 执行实际动作
        result_data = await action_fn(frame, element, params)

        # 标记 JS fallback
        if js_fallback_used:
            result_data["js_fallback"] = True
```

The rest of the method (capture state, screenshot, return OperationRecord) stays unchanged.

- [ ] **Step 4: Run all pipeline tests**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_browser/test_pipeline.py -v`
Expected: All 9 tests PASS (6 existing + 3 new)

- [ ] **Step 5: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/browser/pipeline.py tests/unit/test_browser/test_pipeline.py
git commit -m "feat(browser): add JS fallback when element locate times out in pipeline"
```

---

### Task 3: Screenshot 超时降级

**Files:**
- Modify: `zerotoken/browser/actions/extract.py:33-45`
- Modify: `handlers/browser_handlers.py:181-188` (schema)
- Modify: `handlers/browser_handlers.py:460-465` (dispatch)
- Test: `tests/unit/test_browser/test_actions_extract.py`

- [ ] **Step 1: Write failing tests for screenshot degradation**

Append to `tests/unit/test_browser/test_actions_extract.py`:

```python
@pytest.mark.asyncio
async def test_screenshot_action_success():
    """正常截图应返回 base64 数据"""
    from zerotoken.browser.actions.extract import screenshot_action

    mock_frame = AsyncMock()
    mock_frame.screenshot = AsyncMock(return_value=b"fake-png-data")
    result = await screenshot_action(mock_frame, None, {})
    assert result["screenshot"] is not None
    assert result.get("degraded") is not True


@pytest.mark.asyncio
async def test_screenshot_action_timeout_degrades():
    """正常截图超时应降级为 animations=disabled"""
    import asyncio
    from zerotoken.browser.actions.extract import screenshot_action

    call_args = []

    async def slow_then_fast(**kwargs):
        call_args.append(kwargs)
        if "animations" not in kwargs:
            await asyncio.sleep(100)  # 模拟超时
        return b"degraded-png-data"

    mock_frame = AsyncMock()
    mock_frame.screenshot = slow_then_fast

    result = await screenshot_action(mock_frame, None, {"timeout": 100})
    assert result["degraded"] is True
    assert result["screenshot"] is not None


@pytest.mark.asyncio
async def test_screenshot_action_all_fail_returns_none():
    """正常和降级截图都失败时应返回 None 而不是抛异常"""
    import asyncio
    from zerotoken.browser.actions.extract import screenshot_action

    async def always_slow(**kwargs):
        await asyncio.sleep(100)
        return b"data"

    mock_frame = AsyncMock()
    mock_frame.screenshot = always_slow

    result = await screenshot_action(mock_frame, None, {"timeout": 50})
    assert result["screenshot"] is None
    assert result["degraded"] is True
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_browser/test_actions_extract.py::test_screenshot_action_timeout_degrades tests/unit/test_browser/test_actions_extract.py::test_screenshot_action_all_fail_returns_none -v`
Expected: FAIL (no timeout/degradation logic)

- [ ] **Step 3: Implement screenshot degradation**

Replace `screenshot_action` in `zerotoken/browser/actions/extract.py`:

```python
async def screenshot_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """截图：三级降级策略（正常 -> 跳过动画 -> 放弃）"""
    import asyncio

    full_page = params.get("full_page", False)
    path = params.get("path")
    timeout_ms = params.get("timeout", 10000)
    timeout_s = timeout_ms / 1000

    target = element if element else frame

    # 第一级：正常截图
    try:
        data = await asyncio.wait_for(
            target.screenshot(full_page=full_page),
            timeout=timeout_s,
        )
        b64 = base64.b64encode(data).decode("utf-8")
        if path:
            with open(path, "wb") as f:
                f.write(data)
        return {"screenshot": b64, "path": path, "full_page": full_page}
    except (asyncio.TimeoutError, Exception):
        pass

    # 第二级：禁用动画截图
    try:
        data = await asyncio.wait_for(
            target.screenshot(full_page=full_page, animations="disabled"),
            timeout=5,
        )
        b64 = base64.b64encode(data).decode("utf-8")
        if path:
            with open(path, "wb") as f:
                f.write(data)
        return {"screenshot": b64, "path": path, "full_page": full_page, "degraded": True}
    except (asyncio.TimeoutError, Exception) as e:
        pass

    # 第三级：放弃截图
    return {"screenshot": None, "path": path, "full_page": full_page, "degraded": True, "error": "screenshot timeout"}
```

- [ ] **Step 4: Update browser_screenshot schema**

In `handlers/browser_handlers.py`, update the `browser_screenshot` Tool schema (around line 181-188):

```python
        Tool(
            name="browser_screenshot",
            description="Take a screenshot and return image data",
            inputSchema=_obj_schema({
                "path": {"type": "string", "description": "File path to save screenshot (optional)"},
                "full_page": {"type": "boolean", "description": "Capture full page", "default": False},
                "selector": {"type": "string", "description": "CSS selector to capture specific element"},
                "timeout": {"type": "integer", "description": "Screenshot timeout in ms (default 10000)", "default": 10000},
            }),
        ),
```

Update the dispatch section (around line 460-465):

```python
    if name == "browser_screenshot":
        return await svc.screenshot(
            path=args.get("path"),
            full_page=args.get("full_page", False),
            selector=args.get("selector"),
            timeout=args.get("timeout", 10000),
        )
```

- [ ] **Step 5: Update browser_service.py screenshot to pass timeout**

In `zerotoken/services/browser_service.py`, update `screenshot` method to pass timeout through params:

```python
    async def screenshot(self, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {
            "full_page": kw.get("full_page", False),
            "path": kw.get("path"),
            "selector": kw.get("selector"),
            "timeout": kw.get("timeout", 10000),
        }
        return await pipeline.execute(
            ActionType.SCREENSHOT, params, action_fn=screenshot_action,
            needs_selector=False, take_screenshot=False,
        )
```

- [ ] **Step 6: Run all tests**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/test_browser/test_actions_extract.py -v`
Expected: All 6 tests PASS (3 existing + 3 new)

- [ ] **Step 7: Run full unit test suite for regressions**

Run: `cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite && uv run python -m pytest tests/unit/ --tb=short -q`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
cd /Users/amos/project/ZeroToken/.worktrees/v2-rewrite
git add zerotoken/browser/actions/extract.py zerotoken/services/browser_service.py handlers/browser_handlers.py tests/unit/test_browser/test_actions_extract.py
git commit -m "feat(browser): add three-level screenshot degradation with timeout control"
```

---

## Self-Review

### Spec Coverage

| Spec Requirement | Task |
|---|---|
| wait_for state param + degradation | Task 1 |
| Pipeline JS fallback | Task 2 |
| Screenshot timeout degradation | Task 3 |
| Schema updates (wait_for + screenshot) | Task 1 + Task 3 |
| Service layer pass-through | Task 1 + Task 3 |

### Type/Name Consistency

- `wait_for_action(frame, element, params)` -- params includes `state`, `condition`, `value`, `timeout`
- `screenshot_action(frame, element, params)` -- params includes `timeout` (ms)
- `pipeline.execute` -- `js_fallback_used` bool, injected as `result_data["js_fallback"] = True`
- `degraded: True` -- used in both wait_for and screenshot results
