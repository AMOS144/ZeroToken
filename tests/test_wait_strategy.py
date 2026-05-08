"""
SmartWait 测试

按照 TDD 流程，先编写测试，再实现功能。
"""

import pytest
from unittest.mock import AsyncMock

from zerotoken.wait_strategy import WaitCondition, WaitConfig, WaitForResult, SmartWait, WaitChain


class TestWaitCondition:
    """测试 WaitCondition 枚举"""

    def test_wait_condition_values(self):
        """测试等待条件值"""
        assert WaitCondition.SELECTOR.value == "selector"
        assert WaitCondition.VISIBLE.value == "visible"
        assert WaitCondition.HIDDEN.value == "hidden"
        assert WaitCondition.NAVIGATION.value == "navigation"
        assert WaitCondition.NETWORK_IDLE.value == "network_idle"
        assert WaitCondition.LOAD_STATE.value == "load_state"
        assert WaitCondition.TEXT.value == "text"
        assert WaitCondition.FUNCTION.value == "function"


class TestWaitConfig:
    """测试 WaitConfig 类"""

    def test_default_config(self):
        """测试默认配置"""
        config = WaitConfig()

        assert config.timeout == 30000
        assert config.retry_interval == 100
        assert config.poll_interval == 50
        assert config.max_retries == 3
        assert config.wait_network_idle is True

    def test_custom_config(self):
        """测试自定义配置"""
        config = WaitConfig(timeout=10000, retry_interval=200, max_retries=5)

        assert config.timeout == 10000
        assert config.retry_interval == 200
        assert config.max_retries == 5


class TestWaitForResult:
    """测试 WaitForResult 类"""

    def test_create_result(self):
        """测试创建等待结果"""
        result = WaitForResult(success=True, condition=WaitCondition.SELECTOR, elapsed_ms=150.5)

        assert result.success is True
        assert result.condition == WaitCondition.SELECTOR
        assert result.elapsed_ms == 150.5
        assert result.error is None
        assert result.retries == 0

    def test_result_with_error(self):
        """测试带错误的结果"""
        result = WaitForResult(
            success=False,
            condition=WaitCondition.VISIBLE,
            elapsed_ms=5000,
            error="Timeout waiting for element",
            retries=3,
        )

        assert result.success is False
        assert result.error == "Timeout waiting for element"
        assert result.retries == 3

    def test_result_to_dict(self):
        """测试转换为字典"""
        result = WaitForResult(success=True, condition=WaitCondition.NETWORK_IDLE, elapsed_ms=200)

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["condition"] == "network_idle"
        assert result_dict["elapsed_ms"] == 200


class TestSmartWait:
    """测试 SmartWait 类"""

    @pytest.fixture
    def mock_page(self):
        """创建模拟 page 对象"""
        page = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.wait_for_function = AsyncMock()
        page.evaluate = AsyncMock()
        return page

    def test_create_smart_wait(self):
        """测试创建 SmartWait"""
        mock_page = AsyncMock()
        smart_wait = SmartWait(mock_page)

        assert smart_wait.page == mock_page
        assert smart_wait.config.timeout == 30000

    def test_create_with_custom_config(self):
        """测试使用自定义配置创建"""
        mock_page = AsyncMock()
        config = WaitConfig(timeout=5000)
        smart_wait = SmartWait(mock_page, config)

        assert smart_wait.config.timeout == 5000

    @pytest.mark.asyncio
    async def test_wait_for_selector(self, mock_page):
        """测试等待选择器"""
        smart_wait = SmartWait(mock_page)

        result = await smart_wait.wait_for(WaitCondition.SELECTOR, "#my-element")

        assert result.success is True
        assert result.condition == WaitCondition.SELECTOR
        mock_page.wait_for_selector.assert_called_once_with("#my-element", timeout=30000)

    @pytest.mark.asyncio
    async def test_wait_for_visible(self, mock_page):
        """测试等待元素可见"""
        smart_wait = SmartWait(mock_page)

        result = await smart_wait.wait_for(WaitCondition.VISIBLE, "#my-element")

        assert result.success is True
        mock_page.wait_for_selector.assert_called_once_with(
            "#my-element", timeout=30000, state="visible"
        )

    @pytest.mark.asyncio
    async def test_wait_for_hidden(self, mock_page):
        """测试等待元素隐藏"""
        smart_wait = SmartWait(mock_page)

        result = await smart_wait.wait_for(WaitCondition.HIDDEN, "#my-element")

        assert result.success is True
        mock_page.wait_for_selector.assert_called_once_with(
            "#my-element", timeout=30000, state="hidden"
        )

    @pytest.mark.asyncio
    async def test_wait_for_network_idle(self, mock_page):
        """测试等待网络空闲"""
        smart_wait = SmartWait(mock_page)

        result = await smart_wait.wait_for(WaitCondition.NETWORK_IDLE)

        # 网络空闲超时是可接受的，应该总是返回成功
        assert result.success is True

    @pytest.mark.asyncio
    async def test_wait_for_text(self, mock_page):
        """测试等待文本出现"""
        smart_wait = SmartWait(mock_page)
        mock_page.wait_for_function = AsyncMock()

        result = await smart_wait.wait_for(WaitCondition.TEXT, "Welcome")

        assert result.success is True
        mock_page.wait_for_function.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_function(self, mock_page):
        """测试等待函数返回 true"""
        smart_wait = SmartWait(mock_page)

        result = await smart_wait.wait_for(
            WaitCondition.FUNCTION, "() => document.readyState === 'complete'"
        )

        assert result.success is True
        mock_page.wait_for_function.assert_called_once_with(
            "() => document.readyState === 'complete'", timeout=30000
        )

    @pytest.mark.asyncio
    async def test_wait_with_custom_timeout(self, mock_page):
        """测试使用自定义超时"""
        smart_wait = SmartWait(mock_page)

        await smart_wait.wait_for(WaitCondition.SELECTOR, "#my-element", timeout=5000)

        mock_page.wait_for_selector.assert_called_once_with("#my-element", timeout=5000)

    @pytest.mark.asyncio
    async def test_wait_history(self, mock_page):
        """测试等待历史记录"""
        smart_wait = SmartWait(mock_page)

        await smart_wait.wait_for(WaitCondition.SELECTOR, "#elem1")
        await smart_wait.wait_for(WaitCondition.VISIBLE, "#elem2")

        history = smart_wait.get_wait_history()

        assert len(history) == 2
        assert history[0]["condition"] == "selector"
        assert history[1]["condition"] == "visible"

    def test_clear_history(self, mock_page):
        """测试清除历史"""
        smart_wait = SmartWait(mock_page)
        smart_wait._wait_history = [{"condition": "selector"}]

        smart_wait.clear_history()

        assert len(smart_wait._wait_history) == 0


class TestWaitChain:
    """测试 WaitChain 类"""

    @pytest.fixture
    def mock_page(self):
        """创建模拟 page 对象"""
        page = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        return page

    def test_create_wait_chain(self):
        """测试创建 WaitChain"""
        mock_page = AsyncMock()
        chain = WaitChain(mock_page)

        assert chain is not None
        assert len(chain._conditions) == 0

    def test_wait_for_selector_chain(self, mock_page):
        """测试链式等待选择器"""
        chain = WaitChain(mock_page)
        result = chain.wait_for_selector("#button")

        # 应该返回自身以支持链式调用
        assert result == chain
        assert len(chain._conditions) == 1
        assert chain._conditions[0]["condition"] == WaitCondition.SELECTOR
        assert chain._conditions[0]["value"] == "#button"

    def test_wait_for_visible_chain(self, mock_page):
        """测试链式等待可见"""
        chain = WaitChain(mock_page)
        result = chain.wait_for_visible("#button")

        assert result == chain
        assert chain._conditions[0]["condition"] == WaitCondition.VISIBLE

    def test_wait_for_network_idle_chain(self, mock_page):
        """测试链式等待网络空闲"""
        chain = WaitChain(mock_page)
        result = chain.wait_for_network_idle()

        assert result == chain
        assert chain._conditions[0]["condition"] == WaitCondition.NETWORK_IDLE

    def test_chained_calls(self, mock_page):
        """测试链式调用"""
        chain = (
            WaitChain(mock_page)
            .wait_for_selector("#button")
            .wait_for_visible()
            .wait_for_network_idle()
        )

        assert len(chain._conditions) == 3
        assert chain._conditions[0]["condition"] == WaitCondition.SELECTOR
        assert chain._conditions[1]["condition"] == WaitCondition.VISIBLE
        assert chain._conditions[2]["condition"] == WaitCondition.NETWORK_IDLE

    @pytest.mark.asyncio
    async def test_execute_chain(self, mock_page):
        """测试执行链"""
        chain = WaitChain(mock_page).wait_for_selector("#button").wait_for_network_idle()

        result = await chain.execute()

        assert result["success"] is True
        assert len(result["results"]) == 2
        assert "total_elapsed_ms" in result


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
