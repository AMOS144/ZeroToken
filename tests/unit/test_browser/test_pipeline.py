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

    r1 = await pipeline.execute(
        ActionType.OPEN, {}, action_fn=noop,
        needs_selector=False, take_screenshot=False,
    )
    r2 = await pipeline.execute(
        ActionType.CLICK, {}, action_fn=noop,
        needs_selector=False, take_screenshot=False,
    )
    assert r1.step == 1
    assert r2.step == 2


@pytest.mark.asyncio
async def test_pipeline_reset_counter():
    """reset_counter() 重置步骤计数"""
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

    r1 = await pipeline.execute(
        ActionType.OPEN, {}, action_fn=noop,
        needs_selector=False, take_screenshot=False,
    )
    assert r1.step == 1

    pipeline.reset_counter()

    r2 = await pipeline.execute(
        ActionType.CLICK, {}, action_fn=noop,
        needs_selector=False, take_screenshot=False,
    )
    assert r2.step == 1


@pytest.mark.asyncio
async def test_pipeline_with_selector():
    """needs_selector=True 时通过 stability.locate 定位元素"""
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
    mock_stability.locate = AsyncMock(
        return_value=(mock_element, [{"type": "id", "value": "#btn", "stability_score": 0.9}]),
    )

    pipeline = ActionPipeline(context=mock_context, stability=mock_stability)

    received_elements = []

    async def capture_action(frame, element, params):
        received_elements.append(element)
        return {"clicked": True}

    record = await pipeline.execute(
        action=ActionType.CLICK,
        params={"selector": "#btn"},
        action_fn=capture_action,
        needs_selector=True,
        take_screenshot=False,
    )

    # action_fn 应收到 locate 返回的 element
    assert received_elements[0] == mock_element
    assert record.result.success is True
    assert len(record.selector_candidates) == 1
    assert record.selector_candidates[0].type == "id"


@pytest.mark.asyncio
async def test_pipeline_captures_page_state():
    """执行后应捕获 PageState"""
    from zerotoken.browser.pipeline import ActionPipeline
    from zerotoken.models.operation import ActionType

    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_page.page = AsyncMock()
    mock_page.page.url = "https://example.com/path"
    mock_page.page.title = AsyncMock(return_value="My Page")
    mock_page.active_frame = mock_page.page
    mock_page.tab_id = 2
    mock_context.active_page = mock_page
    mock_context._pages = {0: MagicMock(), 1: MagicMock(), 2: mock_page}

    pipeline = ActionPipeline(context=mock_context, stability=AsyncMock())

    async def noop(frame, element, params):
        return {}

    record = await pipeline.execute(
        ActionType.OPEN, {"url": "https://example.com/path"},
        action_fn=noop, needs_selector=False, take_screenshot=False,
    )

    assert record.page_state.url == "https://example.com/path"
    assert record.page_state.title == "My Page"
    assert record.page_state.tab_id == 2
    assert record.page_state.tab_count == 3


@pytest.mark.asyncio
async def test_pipeline_action_error_propagates():
    """action_fn 抛异常时应向上传播"""
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

    async def bad_action(frame, element, params):
        raise RuntimeError("action failed")

    with pytest.raises(RuntimeError, match="action failed"):
        await pipeline.execute(
            ActionType.CLICK, {},
            action_fn=bad_action, needs_selector=False, take_screenshot=False,
        )


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
