"""
Wait Strategy - 智能等待策略
解决时序问题，提高自动化稳定性
"""

import asyncio
import json
from typing import Optional, Dict, Any, List, Callable, Awaitable
from enum import Enum
from dataclasses import dataclass
import time


class WaitCondition(Enum):
    """等待条件类型"""
    SELECTOR = "selector"           # 等待元素出现
    VISIBLE = "visible"             # 等待元素可见
    HIDDEN = "hidden"               # 等待元素隐藏
    NAVIGATION = "navigation"       # 等待导航完成
    NETWORK_IDLE = "network_idle"   # 等待网络空闲
    LOAD_STATE = "load_state"       # 等待加载状态
    TEXT = "text"                   # 等待文本出现
    FUNCTION = "function"           # 等待函数返回 true


@dataclass
class WaitConfig:
    """等待配置"""
    timeout: float = 30000          # 默认超时 (ms)
    retry_interval: float = 100     # 重试间隔 (ms)
    poll_interval: float = 50       # 轮询间隔 (ms)
    max_retries: int = 3            # 最大重试次数
    wait_network_idle: bool = True  # 是否等待网络空闲


class WaitForResult:
    """等待结果"""

    def __init__(
        self,
        success: bool,
        condition: WaitCondition,
        elapsed_ms: float,
        error: Optional[str] = None,
        retries: int = 0
    ):
        self.success = success
        self.condition = condition
        self.elapsed_ms = elapsed_ms
        self.error = error
        self.retries = retries

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "condition": self.condition.value,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "retries": self.retries
        }


class SmartWait:
    """
    智能等待策略

    提供多种等待条件，自动检测页面稳定状态。
    支持级联等待（如：等待元素 + 等待网络空闲）。
    """

    def __init__(self, page, config: Optional[WaitConfig] = None):
        self.page = page
        self.config = config or WaitConfig()
        self._wait_history: List[WaitForResult] = []

    async def wait_for(
        self,
        condition: WaitCondition,
        value: Optional[str] = None,
        timeout: Optional[float] = None,
        description: str = ""
    ) -> WaitForResult:
        """
        智能等待

        Args:
            condition: 等待条件
            value: 条件值（如选择器、文本等）
            timeout: 覆盖默认超时 (ms)
            description: 等待描述（用于日志）

        Returns:
            WaitForResult
        """
        timeout = timeout or self.config.timeout
        start_time = time.time()
        retries = 0
        error = None

        try:
            if condition == WaitCondition.SELECTOR:
                await self._wait_selector(value, timeout)
            elif condition == WaitCondition.VISIBLE:
                await self._wait_visible(value, timeout)
            elif condition == WaitCondition.HIDDEN:
                await self._wait_hidden(value, timeout)
            elif condition == WaitCondition.NAVIGATION:
                await self._wait_navigation(timeout)
            elif condition == WaitCondition.NETWORK_IDLE:
                await self._wait_network_idle(timeout)
            elif condition == WaitCondition.LOAD_STATE:
                await self._wait_load_state(value, timeout)
            elif condition == WaitCondition.TEXT:
                await self._wait_text(value, timeout)
            elif condition == WaitCondition.FUNCTION:
                await self._wait_function(value, timeout)
            else:
                raise ValueError(f"Unknown wait condition: {condition}")

        except Exception as e:
            error = str(e)

        elapsed_ms = (time.time() - start_time) * 1000

        result = WaitForResult(
            success=error is None,
            condition=condition,
            elapsed_ms=elapsed_ms,
            error=error,
            retries=retries
        )

        self._wait_history.append(result)
        return result

    async def _wait_selector(self, selector: str, timeout: float) -> None:
        """等待元素出现"""
        await self.page.wait_for_selector(selector, timeout=timeout)

    async def _wait_visible(self, selector: str, timeout: float) -> None:
        """等待元素可见"""
        await self.page.wait_for_selector(selector, timeout=timeout, state="visible")

    async def _wait_hidden(self, selector: str, timeout: float) -> None:
        """等待元素隐藏"""
        await self.page.wait_for_selector(selector, timeout=timeout, state="hidden")

    async def _wait_navigation(self, timeout: float) -> None:
        """等待导航完成"""
        await self.page.wait_for_load_state("networkidle", timeout=timeout)

    async def _wait_network_idle(self, timeout: float) -> None:
        """等待网络空闲"""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
        except asyncio.TimeoutError:
            # 网络空闲超时是可接受的，继续执行
            pass

    async def _wait_load_state(self, state: str = "networkidle", timeout: float = None) -> None:
        """等待加载状态"""
        await self.page.wait_for_load_state(state, timeout=timeout)

    async def _wait_text(self, text: str, timeout: float) -> None:
        """等待文本出现。使用 json.dumps 安全转义，防止 JS 注入。"""
        safe_text = json.dumps(text)
        await self.page.wait_for_function(
            f"document.body.innerText.includes({safe_text})",
            timeout=timeout
        )

    async def _wait_function(self, function: str, timeout: float) -> None:
        """等待函数返回 true"""
        await self.page.wait_for_function(function, timeout=timeout)

    async def wait_for_operation(
        self,
        selector: str,
        before_action: Optional[Callable] = None,
        after_action: Optional[Callable] = None
    ) -> Dict[str, WaitForResult]:
        """
        操作前后的智能等待

        流程：
        1. 等待元素可操作
        2. 执行 before_action（可选）
        3. 执行操作
        4. 执行 after_action（可选）
        5. 等待页面稳定

        Args:
            selector: 目标元素选择器
            before_action: 操作前等待/检查
            after_action: 操作后等待/检查

        Returns:
            包含各阶段等待结果
        """
        results = {}

        # 阶段 1: 等待元素可操作
        results["before"] = await self.wait_for(
            WaitCondition.VISIBLE,
            selector,
            description="等待元素可见"
        )

        if not results["before"].success:
            return results

        # 阶段 2: 执行操作前检查
        if before_action:
            await before_action()

        # 阶段 3: 执行操作（由调用者执行）

        # 阶段 4: 等待页面稳定
        results["after"] = await self.wait_for(
            WaitCondition.NETWORK_IDLE,
            description="等待网络空闲"
        )

        # 阶段 5: 执行操作后检查
        if after_action:
            await after_action()

        return results

    async def wait_stable(
        self,
        timeout: float = 5000,
        stable_window: float = 500
    ) -> bool:
        """
        等待页面稳定

        通过检测 DOM 变化判断页面是否稳定。
        如果在 stable_window 时间内 DOM 没有变化，认为页面稳定。

        Args:
            timeout: 最大等待时间 (ms)
            stable_window: 稳定观察窗口 (ms)

        Returns:
            是否成功等待稳定
        """
        start_time = time.time()

        # 获取初始 DOM 状态
        async def get_dom_hash() -> str:
            return await self.page.evaluate("""() => {
                const dom = document.documentElement;
                return dom.innerHTML.length.toString() + '-' + dom.children.length.toString();
            }""")

        last_hash = await get_dom_hash()
        stable_start = None

        while (time.time() - start_time) * 1000 < timeout:
            await asyncio.sleep(self.config.poll_interval / 1000)

            current_hash = await get_dom_hash()

            if current_hash == last_hash:
                if stable_start is None:
                    stable_start = time.time()
                elif (time.time() - stable_start) * 1000 >= stable_window:
                    return True  # 页面稳定
            else:
                stable_start = None
                last_hash = current_hash

        return timeout >= 10000  # 超时较长时返回成功

    async def wait_with_retry(
        self,
        condition: WaitCondition,
        value: Optional[str] = None,
        max_retries: Optional[int] = None
    ) -> WaitForResult:
        """
        带重试的等待

        Args:
            condition: 等待条件
            value: 条件值
            max_retries: 最大重试次数

        Returns:
            WaitForResult
        """
        max_retries = max_retries or self.config.max_retries
        retries = 0
        last_error = None

        while retries <= max_retries:
            start_time = time.time()

            try:
                result = await self.wait_for(condition, value)
                if result.success:
                    result.retries = retries
                    return result
                last_error = result.error
            except Exception as e:
                last_error = str(e)

            retries += 1

            if retries <= max_retries:
                # 指数退避等待
                wait_time = self.config.retry_interval * (2 ** (retries - 1))
                await asyncio.sleep(wait_time / 1000)

        elapsed_ms = (time.time() - start_time) * 1000

        return WaitForResult(
            success=False,
            condition=condition,
            elapsed_ms=elapsed_ms,
            error=last_error,
            retries=retries
        )

    def get_wait_history(self) -> List[Dict[str, Any]]:
        """获取等待历史"""
        return [r.to_dict() for r in self._wait_history]

    def clear_history(self) -> None:
        """清除等待历史"""
        self._wait_history = []


class WaitChain:
    """
    级联等待构建器

    链式调用多个等待条件，例如：
    WaitChain(page)
        .wait_for_selector("#button")
        .wait_for_visible()
        .wait_for_network_idle()
    """

    def __init__(self, page):
        self.page = page
        self.smart_wait = SmartWait(page)
        self._conditions: List[Dict[str, Any]] = []
        self._results: List[WaitForResult] = []

    def wait_for_selector(self, selector: str, timeout: float = None) -> "WaitChain":
        """添加等待元素出现"""
        self._conditions.append({
            "condition": WaitCondition.SELECTOR,
            "value": selector,
            "timeout": timeout
        })
        return self

    def wait_for_visible(self, selector: str = None, timeout: float = None) -> "WaitChain":
        """添加等待元素可见"""
        self._conditions.append({
            "condition": WaitCondition.VISIBLE,
            "value": selector,
            "timeout": timeout
        })
        return self

    def wait_for_hidden(self, selector: str, timeout: float = None) -> "WaitChain":
        """添加等待元素隐藏"""
        self._conditions.append({
            "condition": WaitCondition.HIDDEN,
            "value": selector,
            "timeout": timeout
        })
        return self

    def wait_for_network_idle(self, timeout: float = None) -> "WaitChain":
        """添加等待网络空闲"""
        self._conditions.append({
            "condition": WaitCondition.NETWORK_IDLE,
            "value": None,
            "timeout": timeout
        })
        return self

    def wait_for_text(self, text: str, timeout: float = None) -> "WaitChain":
        """添加等待文本出现"""
        self._conditions.append({
            "condition": WaitCondition.TEXT,
            "value": text,
            "timeout": timeout
        })
        return self

    async def execute(self) -> Dict[str, Any]:
        """
        执行所有等待

        Returns:
            包含所有等待结果和总体成功状态
        """
        self._results = []
        all_success = True

        for condition in self._conditions:
            result = await self.smart_wait.wait_for(
                condition["condition"],
                condition.get("value"),
                condition.get("timeout")
            )
            self._results.append(result)

            if not result.success:
                all_success = False
                break  # 失败时停止后续等待

        return {
            "success": all_success,
            "results": [r.to_dict() for r in self._results],
            "total_elapsed_ms": sum(r.elapsed_ms for r in self._results)
        }
