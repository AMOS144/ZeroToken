# Browser Resilience 设计 -- 操作降级与容错

## 背景

集成测试（benchmark session `20260415_225543_7951ab`，24 次调用）暴露 3 类高频失败：

| 问题 | 根因 | 失败次数 |
|------|------|---------|
| `wait_for_selector` 元素在 DOM 但不可见 | 懒加载页面，元素 `offsetHeight=0` | 1/3 |
| `click`/`input` 元素被遮罩隐藏 | 百度首页弹窗/简洁模式覆盖搜索框 | 2/2 |
| `screenshot` 字体加载超时 30s | Playwright 等待远端 webfont | 2/4 |

共同特征：都不是"元素不存在"，而是**元素可达但操作受阻**。当前引擎对这类场景直接抛 TimeoutError，打断整个操作链。

## 目标

在不改变现有 API 语义的前提下，让引擎对"元素可达但操作受阻"的场景自动降级，而非直接失败。降级行为对调用方透明（通过返回值标记），不掩盖问题。

### 不做

- 不做针对特定网站的适配（如百度弹窗检测）
- 不改变成功路径的行为
- 不引入新的 MCP 工具

---

## 修复 1: `wait_for_action` 智能降级

### 改动文件

- `zerotoken/browser/actions/navigate.py` -- `wait_for_action`
- `handlers/browser_handlers.py` -- `browser_wait_for` schema
- `zerotoken/services/browser_service.py` -- `wait_for` 透传 `state`

### 详细设计

**MCP Schema 变更**: `browser_wait_for` 新增可选参数 `state`（枚举: `visible`/`attached`/`hidden`/`detached`，默认 `visible`）。

**`wait_for_action` 逻辑**:

```
if condition == "selector":
    try:
        await frame.wait_for_selector(value, state=state, timeout=timeout)
        return {condition, value, state}
    except TimeoutError:
        if state == "visible":
            fallback_timeout = max(timeout // 2, 2000)
            await frame.wait_for_selector(
                value, state="attached", timeout=fallback_timeout
            )
            return {condition, value, state: "attached", degraded: true}
        raise
```

当 `state=visible` 超时时：
1. 用 `state=attached` 重试（timeout 取原始的一半，最少 2s）
2. 成功则返回 `degraded: true`，告知调用方元素存在但不可见
3. 如果 `attached` 也失败，抛原始异常

**`browser_service.py`**: `wait_for` 方法从 `kw` 中取 `state` 透传给 `params`。

**`browser_handlers.py`**: schema 新增 `state` 字段；dispatch 时 `args.get("state", "visible")` 传给 service。

---

## 修复 2: Pipeline 层 JS Fallback

### 改动文件

- `zerotoken/browser/pipeline.py` -- `execute` 方法

### 详细设计

当 `needs_selector=True` 且 `StabilityMiddleware.locate` 超时时，不立即抛异常，进入 JS fallback：

```
try:
    element, candidates = await self.stability.locate(...)
except TimeoutError:
    js_element = await frame.query_selector(params["selector"])
    if js_element is not None:
        element = js_element
        js_fallback_used = True
    else:
        raise  # 元素确实不存在
```

**作用范围**: 所有经过 `pipeline.execute(needs_selector=True)` 的操作自动获得此能力。包括 `click`、`input`、`get_text`、`get_html`、`hover`、`right_click`、`double_click` 等。

**标记**: 当 `js_fallback_used=True` 时，在 `OperationRecord.result.data` 中注入 `js_fallback: true`。

**注意**: JS fallback 只解决"定位"问题（元素在 DOM 但不可见）。后续操作（如 `element.click()`）可能仍因不可见而失败，此时由 Playwright 正常报错。但对于 `get_text`、`get_html` 等纯读取操作，JS fallback 足以成功。

---

## 修复 3: Screenshot 超时降级

### 改动文件

- `zerotoken/browser/actions/extract.py` -- `screenshot_action`
- `handlers/browser_handlers.py` -- `browser_screenshot` schema

### 详细设计

**MCP Schema 变更**: `browser_screenshot` 新增可选参数 `timeout`（毫秒，默认 10000）。

**三级降级策略**:

```
1. 正常截图:
   asyncio.wait_for(target.screenshot(full_page=...), timeout=T/1000)

2. 降级截图（正常超时后）:
   asyncio.wait_for(
       target.screenshot(full_page=..., animations="disabled"),
       timeout=5
   )

3. 放弃截图（降级也超时）:
   return {screenshot: None, error: "...", degraded: true}
```

**关键**: 第 3 级不抛异常。截图失败不应阻断操作链。调用方通过 `screenshot=None` 和 `degraded=true` 判断截图状态。

**默认 timeout 从 30s 降到 10s**: 当前 Playwright 默认 30s 太长，绝大多数页面 10s 内可完成截图。字体加载慢的页面走降级路径（`animations="disabled"` 跳过字体等待）。

---

## 对现有行为的影响

| 场景 | 改前 | 改后 |
|------|------|------|
| `wait_for` 元素可见 | 正常返回 | 不变 |
| `wait_for` 元素在 DOM 但不可见 | 超时失败 | 降级成功 + `degraded: true` |
| `wait_for` 元素不存在 | 超时失败 | 不变 |
| `click`/`input` 元素被遮罩 | 超时失败 | JS 定位成功，操作可能成功 |
| `click`/`input` 元素不存在 | 超时失败 | 不变 |
| `screenshot` 正常页面 | 正常返回 | 不变（timeout 从 30s 降到 10s） |
| `screenshot` 字体慢 | 30s 后失败 | 10s 后降级截图，再 5s 后放弃 |

所有降级行为通过 `degraded: true` 或 `js_fallback: true` 标记，对 AI Agent 透明。
