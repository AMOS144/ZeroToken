"""
Error Recovery - 错误恢复机制
自动检测和处理常见错误，提高自动化稳定性
"""

import asyncio
from typing import Optional, Dict, Any, List, Callable, Awaitable
from enum import Enum
from dataclasses import dataclass
import time


class ErrorType(Enum):
    """错误类型"""
    SELECTOR_NOT_FOUND = "selector_not_found"
    ELEMENT_NOT_VISIBLE = "element_not_visible"
    ELEMENT_NOT_INTERCEPTABLE = "element_not_interceptable"
    NAVIGATION_TIMEOUT = "navigation_timeout"
    NETWORK_ERROR = "network_error"
    JS_ERROR = "js_error"
    POPUP_BLOCKED = "popup_blocked"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """错误上下文"""
    error_type: ErrorType
    original_error: str
    selector: Optional[str] = None
    action: Optional[str] = None
    page_state: Optional[Dict[str, Any]] = None
    screenshot: Optional[str] = None
    timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type.value,
            "original_error": self.original_error,
            "selector": self.selector,
            "action": self.action,
            "page_state": self.page_state,
            "timestamp": self.timestamp
        }


@dataclass
class RecoveryResult:
    """恢复结果"""
    success: bool
    recovered: bool
    action_taken: str
    new_selector: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "recovered": self.recovered,
            "action_taken": self.action_taken,
            "new_selector": self.new_selector,
            "error": self.error
        }


class ErrorRecovery:
    """
    错误恢复机制

    自动检测错误类型，尝试恢复策略。
    支持自定义恢复处理器。
    """

    def __init__(self, page, browser_controller=None):
        self.page = page
        self.controller = browser_controller
        self._recovery_history: List[Dict[str, Any]] = []
        self._custom_handlers: Dict[ErrorType, Callable] = {}

    def register_handler(
        self,
        error_type: ErrorType,
        handler: Callable[[ErrorContext], Awaitable[RecoveryResult]]
    ) -> None:
        """注册自定义错误处理器"""
        self._custom_handlers[error_type] = handler

    def detect_error_type(self, error: Exception) -> ErrorType:
        """检测错误类型"""
        error_msg = str(error).lower()

        if "selector" in error_msg or "element" in error_msg:
            if "not found" in error_msg or "timeout" in error_msg:
                return ErrorType.SELECTOR_NOT_FOUND
            if "visible" in error_msg:
                return ErrorType.ELEMENT_NOT_VISIBLE
            if "interceptable" in error_msg:
                return ErrorType.ELEMENT_NOT_INTERCEPTABLE

        if "navigation" in error_msg or "timeout" in error_msg:
            return ErrorType.NAVIGATION_TIMEOUT

        if "network" in error_msg:
            return ErrorType.NETWORK_ERROR

        if "popup" in error_msg or "window.open" in error_msg:
            return ErrorType.POPUP_BLOCKED

        if "evaluation" in error_msg or "javascript" in error_msg:
            return ErrorType.JS_ERROR

        return ErrorType.UNKNOWN

    async def handle_error(
        self,
        error: Exception,
        selector: Optional[str] = None,
        action: Optional[str] = None
    ) -> RecoveryResult:
        """
        处理错误，尝试恢复

        Args:
            error: 原始异常
            selector: 相关选择器
            action: 相关操作

        Returns:
            RecoveryResult
        """
        error_type = self.detect_error_type(error)
        context = ErrorContext(
            error_type=error_type,
            original_error=str(error),
            selector=selector,
            action=action,
            page_state=await self._get_page_state(),
            timestamp=time.time()
        )

        # 尝试自定义处理器
        if error_type in self._custom_handlers:
            try:
                result = await self._custom_handlers[error_type](context)
                self._record_recovery(context, result)
                return result
            except Exception as e:
                return RecoveryResult(
                    success=False,
                    recovered=False,
                    action_taken=f"Custom handler failed: {str(e)}"
                )

        # 使用内置恢复策略
        result = await self._builtin_recovery(error_type, context)
        self._record_recovery(context, result)
        return result

    async def _builtin_recovery(
        self,
        error_type: ErrorType,
        context: ErrorContext
    ) -> RecoveryResult:
        """内置恢复策略"""

        if error_type == ErrorType.SELECTOR_NOT_FOUND:
            return await self._handle_selector_not_found(context)

        elif error_type == ErrorType.ELEMENT_NOT_VISIBLE:
            return await self._handle_element_not_visible(context)

        elif error_type == ErrorType.ELEMENT_NOT_INTERCEPTABLE:
            return await self._handle_element_not_interceptable(context)

        elif error_type == ErrorType.NAVIGATION_TIMEOUT:
            return await self._handle_navigation_timeout(context)

        elif error_type == ErrorType.NETWORK_ERROR:
            return await self._handle_network_error(context)

        elif error_type == ErrorType.POPUP_BLOCKED:
            return await self._handle_popup_blocked(context)

        else:
            return RecoveryResult(
                success=False,
                recovered=False,
                action_taken="No recovery strategy for this error type"
            )

    async def _handle_selector_not_found(self, context: ErrorContext) -> RecoveryResult:
        """处理选择器未找到错误"""
        selector = context.selector

        # 策略 1: 尝试常见变体
        variants = self._generate_selector_variants(selector)
        for variant in variants:
            try:
                await self.page.wait_for_selector(variant, timeout=2000)
                return RecoveryResult(
                    success=True,
                    recovered=True,
                    action_taken=f"Tried selector variants, found: {variant}",
                    new_selector=variant
                )
            except:
                continue

        # 策略 2: 在 iframe 中查找
        try:
            frames = self.page.frames
            for frame in frames:
                if frame != self.page.main_frame:
                    try:
                        await frame.wait_for_selector(selector, timeout=2000)
                        return RecoveryResult(
                            success=True,
                            recovered=True,
                            action_taken=f"Found element in iframe",
                            new_selector=selector
                        )
                    except:
                        continue
        except:
            pass

        # 策略 3: 检查页面是否已导航到其他位置
        current_url = self.page.url
        if context.page_state and context.page_state.get("url") != current_url:
            return RecoveryResult(
                success=False,
                recovered=False,
                action_taken=f"Page URL changed from {context.page_state.get('url')} to {current_url}"
            )

        return RecoveryResult(
            success=False,
            recovered=False,
            action_taken=f"Selector not found: {selector}. Tried {len(variants)} variants."
        )

    async def _handle_element_not_visible(self, context: ErrorContext) -> RecoveryResult:
        """处理元素不可见错误"""
        selector = context.selector

        # 策略 1: 滚动到元素
        try:
            await self.page.locator(selector).scroll_into_view_if_needed()
            await asyncio.sleep(0.3)
            return RecoveryResult(
                success=True,
                recovered=True,
                action_taken="Scrolled element into view"
            )
        except:
            pass

        # 策略 2: 尝试点击元素位置
        try:
            element = await self.page.wait_for_selector(selector, timeout=5000)
            box = await element.bounding_box()
            if box:
                # 点击元素中心
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                await self.page.mouse.click(x, y)
                return RecoveryResult(
                    success=True,
                    recovered=True,
                    action_taken=f"Clicked element at position ({x}, {y})"
                )
        except:
            pass

        # 策略 3: 检查是否有遮罩层
        try:
            overlay = await self.page.evaluate("""() => {
                const overlays = document.querySelectorAll('[style*="position: fixed"], [style*="position: absolute"]');
                for (const overlay of overlays) {
                    const rect = overlay.getBoundingClientRect();
                    if (rect.width > window.innerWidth * 0.5 && rect.height > window.innerHeight * 0.5) {
                        return overlay.tagName;
                    }
                }
                return null;
            }""")
            if overlay:
                return RecoveryResult(
                    success=False,
                    recovered=False,
                    action_taken=f"Element blocked by overlay: {overlay}"
                )
        except:
            pass

        return RecoveryResult(
            success=False,
            recovered=False,
            action_taken="Element not visible, could not recover"
        )

    async def _handle_element_not_interceptable(self, context: ErrorContext) -> RecoveryResult:
        """处理元素不可点击错误"""
        selector = context.selector

        # 策略 1: 等待元素可点击
        try:
            await self.page.wait_for_selector(selector, state="stable", timeout=5000)
            return RecoveryResult(
                success=True,
                recovered=True,
                action_taken="Waited for element to be stable"
            )
        except:
            pass

        # 策略 2: 使用 JavaScript 点击
        try:
            await self.page.evaluate(f"""() => {{
                const el = document.querySelector('{selector}');
                if (el) el.click();
            }}""")
            return RecoveryResult(
                success=True,
                recovered=True,
                action_taken="Used JavaScript click"
            )
        except:
            pass

        return RecoveryResult(
            success=False,
            recovered=False,
            action_taken="Could not make element interceptable"
        )

    async def _handle_navigation_timeout(self, context: ErrorContext) -> RecoveryResult:
        """处理导航超时错误"""
        # 检查当前页面是否已经到达目标
        try:
            # 等待网络空闲（可能已经加载完成）
            await asyncio.sleep(2)
            return RecoveryResult(
                success=True,
                recovered=True,
                action_taken="Navigation may have completed, waited for network idle"
            )
        except:
            pass

        return RecoveryResult(
            success=False,
            recovered=False,
            action_taken="Navigation timeout, page may be stuck"
        )

    async def _handle_network_error(self, context: ErrorContext) -> RecoveryResult:
        """处理网络错误"""
        # 策略 1: 等待后重试
        await asyncio.sleep(2)
        return RecoveryResult(
            success=True,
            recovered=True,
            action_taken="Waited 2 seconds after network error"
        )

    async def _handle_popup_blocked(self, context: ErrorContext) -> RecoveryResult:
        """处理弹窗被阻止"""
        # 尝试接受弹窗
        try:
            async with self.page.expect_popup(timeout=3000) as popup_info:
                popup = await popup_info.value
                return RecoveryResult(
                    success=True,
                    recovered=True,
                    action_taken=f"Popup opened: {popup.url}"
                )
        except:
            return RecoveryResult(
                success=False,
                recovered=False,
                action_taken="Could not handle popup"
            )

    def _generate_selector_variants(self, selector: str) -> List[str]:
        """生成选择器变体"""
        variants = []

        # 移除可能的动态部分
        variants.append(selector)

        # 尝试 ID 选择器
        if selector.startswith("#"):
            # 尝试部分匹配
            id_part = selector[1:].split("_")[0]
            variants.append(f"[id^='{id_part}']")
            variants.append(f"[id*='{id_part}']")

        # 尝试类选择器变体
        if selector.startswith("."):
            parts = selector.split(".")
            if len(parts) > 2:
                # 只保留第一个类
                variants.append(parts[0] + "." + parts[1])

        # 尝试属性选择器
        if "data-testid" in selector:
            # 尝试 name 属性
            variants.append(selector.replace("data-testid", "name"))
            variants.append(selector.replace("data-testid", "id"))

        # 尝试 XPath 变体
        variants.append(f"//{selector}")

        return variants

    async def _get_page_state(self) -> Dict[str, Any]:
        """获取页面状态"""
        try:
            return {
                "url": self.page.url,
                "title": await self.page.title(),
                "ready_state": await self.page.evaluate("document.readyState")
            }
        except:
            return {}

    def _record_recovery(self, context: ErrorContext, result: RecoveryResult) -> None:
        """记录恢复尝试"""
        self._recovery_history.append({
            "context": context.to_dict(),
            "result": result.to_dict()
        })

    def get_recovery_history(self) -> List[Dict[str, Any]]:
        """获取恢复历史"""
        return self._recovery_history


class RetryWrapper:
    """
    重试包装器

    为浏览器操作自动添加重试逻辑
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
        exponential: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential = exponential
        self._retry_history: List[Dict[str, Any]] = []

    async def execute(
        self,
        func: Callable,
        *args,
        description: str = "",
        **kwargs
    ) -> Any:
        """
        执行带重试的函数

        Args:
            func: 要执行的异步函数
            *args: 函数参数
            description: 操作描述
            **kwargs: 函数关键字参数

        Returns:
            函数执行结果
        """
        last_error = None
        retries = 0

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                retries = attempt + 1

                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    await asyncio.sleep(delay)

        # 所有重试失败
        self._retry_history.append({
            "description": description,
            "attempts": retries,
            "last_error": str(last_error)
        })
        raise last_error

    def _calculate_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        if self.exponential:
            delay = self.base_delay * (2 ** attempt)
        else:
            delay = self.base_delay

        return min(delay, self.max_delay)

    def get_retry_history(self) -> List[Dict[str, Any]]:
        """获取重试历史"""
        return self._retry_history
