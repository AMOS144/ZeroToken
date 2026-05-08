"""
ErrorRecovery 测试

按照 TDD 流程，先编写测试，再实现功能。
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from zerotoken.recovery import ErrorType, ErrorContext, RecoveryResult, ErrorRecovery, RetryWrapper


class TestErrorType:
    """测试 ErrorType 枚举"""

    def test_error_type_values(self):
        """测试错误类型值"""
        assert ErrorType.SELECTOR_NOT_FOUND.value == "selector_not_found"
        assert ErrorType.ELEMENT_NOT_VISIBLE.value == "element_not_visible"
        assert ErrorType.ELEMENT_NOT_INTERCEPTABLE.value == "element_not_interceptable"
        assert ErrorType.NAVIGATION_TIMEOUT.value == "navigation_timeout"
        assert ErrorType.NETWORK_ERROR.value == "network_error"
        assert ErrorType.JS_ERROR.value == "js_error"
        assert ErrorType.POPUP_BLOCKED.value == "popup_blocked"
        assert ErrorType.UNKNOWN.value == "unknown"


class TestErrorContext:
    """测试 ErrorContext 类"""

    def test_create_error_context(self):
        """测试创建错误上下文"""
        context = ErrorContext(
            error_type=ErrorType.SELECTOR_NOT_FOUND,
            original_error="Element not found",
            selector="#my-element",
            action="click",
        )

        assert context.error_type == ErrorType.SELECTOR_NOT_FOUND
        assert context.original_error == "Element not found"
        assert context.selector == "#my-element"
        assert context.action == "click"

    def test_error_context_to_dict(self):
        """测试转换为字典"""
        context = ErrorContext(
            error_type=ErrorType.ELEMENT_NOT_VISIBLE,
            original_error="Element is hidden",
            selector="#hidden",
        )

        result = context.to_dict()

        assert result["error_type"] == "element_not_visible"
        assert result["original_error"] == "Element is hidden"
        assert result["selector"] == "#hidden"


class TestRecoveryResult:
    """测试 RecoveryResult 类"""

    def test_create_success_result(self):
        """测试创建成功结果"""
        result = RecoveryResult(
            success=True, recovered=True, action_taken="Used alternative selector"
        )

        assert result.success is True
        assert result.recovered is True
        assert result.action_taken == "Used alternative selector"

    def test_create_failure_result(self):
        """测试创建失败结果"""
        result = RecoveryResult(
            success=False, recovered=False, action_taken="No recovery strategy available"
        )

        assert result.success is False
        assert result.recovered is False

    def test_result_with_new_selector(self):
        """测试带新选择器的结果"""
        result = RecoveryResult(
            success=True,
            recovered=True,
            action_taken="Found alternative selector",
            new_selector="#alternative-btn",
        )

        assert result.new_selector == "#alternative-btn"

    def test_result_to_dict(self):
        """测试转换为字典"""
        result = RecoveryResult(
            success=True,
            recovered=True,
            action_taken="Retried with success",
            new_selector="#new-selector",
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["recovered"] is True
        assert result_dict["action_taken"] == "Retried with success"
        assert result_dict["new_selector"] == "#new-selector"


class TestErrorRecovery:
    """测试 ErrorRecovery 类"""

    @pytest.fixture
    def mock_page(self):
        """创建模拟 page 对象"""
        page = AsyncMock()
        page.url = "https://example.com"
        page.frames = []
        page.main_frame = MagicMock()
        page.wait_for_selector = AsyncMock()
        page.locator = MagicMock()
        page.evaluate = AsyncMock()
        page.title = AsyncMock(return_value="Example")
        return page

    @pytest.fixture
    def mock_controller(self):
        """创建模拟 controller 对象"""
        return AsyncMock()

    def test_create_error_recovery(self, mock_page, mock_controller):
        """测试创建 ErrorRecovery"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        assert recovery.page == mock_page
        assert recovery.controller == mock_controller
        assert len(recovery._custom_handlers) == 0

    def test_detect_selector_not_found_error(self, mock_page, mock_controller):
        """测试检测选择器未找到错误"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        error = Exception("Element #my-element not found")
        error_type = recovery.detect_error_type(error)

        assert error_type == ErrorType.SELECTOR_NOT_FOUND

    def test_detect_element_not_visible_error(self, mock_page, mock_controller):
        """测试检测元素不可见错误"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        error = Exception("Element is not visible")
        error_type = recovery.detect_error_type(error)

        assert error_type == ErrorType.ELEMENT_NOT_VISIBLE

    def test_detect_navigation_timeout_error(self, mock_page, mock_controller):
        """测试检测导航超时错误"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        error = Exception("Navigation timeout exceeded")
        error_type = recovery.detect_error_type(error)

        assert error_type == ErrorType.NAVIGATION_TIMEOUT

    def test_detect_unknown_error(self, mock_page, mock_controller):
        """测试检测未知错误"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        error = Exception("Some unknown error occurred")
        error_type = recovery.detect_error_type(error)

        assert error_type == ErrorType.UNKNOWN

    def test_register_custom_handler(self, mock_page, mock_controller):
        """测试注册自定义处理器"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        async def custom_handler(ctx):
            return RecoveryResult(success=True, recovered=True, action_taken="Custom")

        recovery.register_handler(ErrorType.SELECTOR_NOT_FOUND, custom_handler)

        assert ErrorType.SELECTOR_NOT_FOUND in recovery._custom_handlers

    @pytest.mark.asyncio
    async def test_handle_selector_not_found(self, mock_page, mock_controller):
        """测试处理选择器未找到错误"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        error = Exception("Element #nonexistent not found")
        result = await recovery.handle_error(error, selector="#nonexistent", action="click")

        # 应该尝试恢复策略
        assert result.success is False or result.recovered is True

    @pytest.mark.asyncio
    async def test_handle_element_not_visible(self, mock_page, mock_controller):
        """测试处理元素不可见错误"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        # 模拟元素存在但不可见
        mock_element = AsyncMock()
        mock_element.bounding_box = AsyncMock(
            return_value={"x": 100, "y": 100, "width": 50, "height": 30}
        )
        mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

        error = Exception("Element is not visible")
        result = await recovery.handle_error(error, selector="#hidden-element", action="click")

        # 应该尝试滚动或点击位置
        assert result is not None

    def test_get_page_state(self, mock_page, mock_controller):
        """测试获取页面状态"""
        recovery = ErrorRecovery(mock_page, mock_controller)
        mock_page.evaluate = AsyncMock(return_value="complete")

        # 同步方法测试
        state = recovery._get_page_state()

        # _get_page_state 是异步的，需要 await
        # 这里测试返回的是 coroutine
        assert asyncio.iscoroutine(state)

    def test_generate_selector_variants(self, mock_page, mock_controller):
        """测试生成选择器变体"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        variants = recovery._generate_selector_variants("#button_123")

        # 应该生成多个变体
        assert len(variants) > 0
        assert "#button_123" in variants

    def test_generate_selector_variants_for_id(self, mock_page, mock_controller):
        """测试为 ID 生成变体"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        variants = recovery._generate_selector_variants("#submit_btn")

        # 应该包含部分匹配变体
        assert any("[id^='submit']" in v for v in variants)

    def test_record_recovery(self, mock_page, mock_controller):
        """测试记录恢复尝试"""
        recovery = ErrorRecovery(mock_page, mock_controller)

        context = ErrorContext(
            error_type=ErrorType.SELECTOR_NOT_FOUND, original_error="Element not found"
        )
        result = RecoveryResult(success=False, recovered=False, action_taken="Failed")

        recovery._record_recovery(context, result)

        history = recovery.get_recovery_history()
        assert len(history) == 1


class TestRetryWrapper:
    """测试 RetryWrapper 类"""

    def test_create_retry_wrapper(self):
        """测试创建 RetryWrapper"""
        wrapper = RetryWrapper()

        assert wrapper.max_retries == 3
        assert wrapper.base_delay == 1.0
        assert wrapper.max_delay == 10.0
        assert wrapper.exponential is True

    def test_create_with_custom_params(self):
        """测试使用自定义参数创建"""
        wrapper = RetryWrapper(max_retries=5, base_delay=0.5, max_delay=5.0, exponential=False)

        assert wrapper.max_retries == 5
        assert wrapper.base_delay == 0.5
        assert wrapper.max_delay == 5.0
        assert wrapper.exponential is False

    @pytest.mark.asyncio
    async def test_execute_success_first_try(self):
        """测试第一次执行成功"""
        wrapper = RetryWrapper(max_retries=3)

        async def success_func():
            return "success"

        result = await wrapper.execute(success_func, description="test")

        assert result == "success"

    @pytest.mark.asyncio
    async def test_execute_success_after_retries(self):
        """测试重试后成功"""
        wrapper = RetryWrapper(max_retries=3, base_delay=0.01)

        attempt_count = 0

        async def flaky_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Temporary error")
            return "finally success"

        result = await wrapper.execute(flaky_func, description="flaky test")

        assert result == "finally success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_execute_all_retries_fail(self):
        """测试所有重试都失败"""
        wrapper = RetryWrapper(max_retries=2, base_delay=0.01)

        async def always_fail():
            raise Exception("Always fails")

        with pytest.raises(Exception) as exc_info:
            await wrapper.execute(always_fail, description="failing test")

        assert str(exc_info.value) == "Always fails"

    @pytest.mark.asyncio
    async def test_retry_history(self):
        """测试重试历史"""
        wrapper = RetryWrapper(max_retries=1, base_delay=0.01)

        async def fail_func():
            raise Exception("Failed")

        try:
            await wrapper.execute(fail_func, description="history test")
        except:
            pass

        history = wrapper.get_retry_history()

        assert len(history) == 1
        assert history[0]["description"] == "history test"
        assert history[0]["attempts"] == 2  # 初始 + 1 次重试

    def test_calculate_delay_linear(self):
        """测试线性延迟计算"""
        wrapper = RetryWrapper(base_delay=1.0, exponential=False)

        assert wrapper._calculate_delay(0) == 1.0
        assert wrapper._calculate_delay(1) == 1.0
        assert wrapper._calculate_delay(2) == 1.0

    def test_calculate_delay_exponential(self):
        """测试指数延迟计算"""
        wrapper = RetryWrapper(base_delay=1.0, exponential=True)

        assert wrapper._calculate_delay(0) == 1.0  # 1 * 2^0
        assert wrapper._calculate_delay(1) == 2.0  # 1 * 2^1
        assert wrapper._calculate_delay(2) == 4.0  # 1 * 2^2

    def test_calculate_delay_with_max_limit(self):
        """测试最大延迟限制"""
        wrapper = RetryWrapper(base_delay=1.0, max_delay=5.0, exponential=True)

        # 2^3 = 8, 但应该被限制在 5.0
        delay = wrapper._calculate_delay(3)
        assert delay == 5.0


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
