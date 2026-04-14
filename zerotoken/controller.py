"""
Browser Controller - Enhanced for AI Agent automation.
Provides detailed state tracking, screenshots, and structured operation records.
Integrated with stability modules: SmartSelector, SmartWait, ErrorRecovery.
"""

import asyncio
import base64
import json
from datetime import datetime
from typing import Optional, Any, Dict, List, Literal, Callable
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .selector import SmartSelectorGenerator, SmartSelector
from .wait_strategy import SmartWait, WaitConfig
from .recovery import ErrorRecovery, RetryWrapper
from .adaptive import extract_fingerprint, relocate, _domain_from_url
from .storage import AdaptiveStore
from .stealth import (
    STEALTH_LAUNCH_ARGS,
    STEALTH_INIT_SCRIPT,
    DEFAULT_STEALTH_USER_AGENT,
)


class PageState:
    """Represents the current state of the page."""

    def __init__(self, url: str, title: str, html: Optional[str] = None):
        self.url = url
        self.title = title
        self.html = html
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "timestamp": self.timestamp
        }


class OperationRecord:
    """Represents a single operation record."""

    def __init__(
        self,
        step: int,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        page_state: PageState,
        screenshot: Optional[str] = None,
        error: Optional[str] = None,
        fuzzy_point: Optional[Dict[str, Any]] = None,
        selector_candidates: Optional[List[Dict[str, Any]]] = None,
    ):
        self.step = step
        self.action = action
        self.params = params
        self.result = result
        self.page_state = page_state
        self.screenshot = screenshot
        self.error = error
        self.fuzzy_point = fuzzy_point
        self.selector_candidates = selector_candidates
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        record = {
            "step": self.step,
            "action": self.action,
            "params": self.params,
            "result": self.result,
            "page_state": self.page_state.to_dict(),
            "timestamp": self.timestamp
        }
        if self.screenshot:
            record["screenshot"] = self.screenshot
        if self.error:
            record["error"] = self.error
        if self.fuzzy_point is not None:
            record["fuzzy_point"] = self.fuzzy_point
        if self.selector_candidates is not None:
            record["selector_candidates"] = self.selector_candidates
        return record


class BrowserController:
    """
    Enhanced browser controller for AI Agent automation.
    Provides detailed operation records and page state tracking.
    """

    _instance: Optional["BrowserController"] = None
    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _page: Optional[Page] = None

    def __new__(cls) -> "BrowserController":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._step_counter = 0
            self._operation_history: List[OperationRecord] = []
            self._config = {
                "auto_screenshot": True,
                "track_state": True,
                "timeout": 30000,
                "wait_network_idle": True,
                "enable_stability": True,  # 启用稳定性增强
                "max_retries": 3,
                "retry_delay": 1.0,
                "enable_adaptive": True,
            }
            # 稳定性模块（延迟初始化）
            self._selector_generator: Optional[SmartSelectorGenerator] = None
            self._adaptive_storage: Optional[AdaptiveStore] = None
            self._smart_wait: Optional[SmartWait] = None
            self._error_recovery: Optional[ErrorRecovery] = None
            self._retry_wrapper: Optional[RetryWrapper] = None
            # 选择器缓存
            self._selector_cache: Dict[str, SmartSelector] = {}

    async def start(
        self,
        headless: bool = True,
        viewport: Dict[str, int] = None,
        stealth: bool = False,
    ) -> None:
        """Initialize browser with enhanced configuration.
        When stealth=True, use launch args and init script to reduce automation detection.
        """
        if self._browser is not None and not self._browser.is_connected():
            self._page = None
            self._context = None
            self._browser = None
        if self._browser is None:
            playwright = await async_playwright().start()
            launch_args = (
                STEALTH_LAUNCH_ARGS
                if stealth
                else ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
            )
            self._browser = await playwright.chromium.launch(
                headless=headless,
                args=launch_args,
            )
            vp = viewport or {"width": 1920, "height": 1080}
            if stealth:
                self._context = await self._browser.new_context(
                    viewport=vp,
                    user_agent=DEFAULT_STEALTH_USER_AGENT,
                    locale="en-US",
                    timezone_id="America/New_York",
                    extra_http_headers={
                        "Sec-CH-UA": '"Chromium";v="120", "Google Chrome";v="120", "Not_A Brand";v="24"',
                        "Sec-CH-UA-Mobile": "?0",
                        "Sec-CH-UA-Platform": '"Windows"',
                    },
                )
                await self._context.add_init_script(STEALTH_INIT_SCRIPT)
            else:
                self._context = await self._browser.new_context(
                    viewport=vp,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
            self._page = await self._context.new_page()
            self._step_counter = 0
            self._operation_history = []

    async def stop(self) -> None:
        """Close browser and cleanup."""
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None
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

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    def _next_step(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def set_adaptive_store(self, store: Optional[AdaptiveStore]) -> None:
        """Inject adaptive store (e.g. main SQLiteStorage). Used when unified DB."""
        self._adaptive_storage = store

    def _get_adaptive_storage(self) -> Optional[AdaptiveStore]:
        """Get adaptive storage: uses injected store (main DB) only. Call set_adaptive_store() to inject."""
        if not self._config.get("enable_adaptive"):
            return None
        return self._adaptive_storage

    async def _get_page_state(self, include_html: bool = False) -> PageState:
        """Get current page state."""
        url = self._page.url
        title = await self._page.title()
        html = await self._page.content() if include_html else None
        return PageState(url=url, title=title, html=html)

    async def _take_screenshot(self, full_page: bool = False) -> str:
        """Take screenshot and return base64 encoded string."""
        screenshot = await self._page.screenshot(full_page=full_page)
        return base64.b64encode(screenshot).decode('utf-8')

    async def _wait_for_stable_state(self) -> None:
        """Wait for page to reach stable state."""
        if self._config["wait_network_idle"]:
            try:
                await self._page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass  # Timeout is acceptable

    def _init_stability_modules(self) -> None:
        """初始化稳定性模块"""
        if not self._selector_generator:
            self._selector_generator = SmartSelectorGenerator()
        if not self._smart_wait:
            wait_config = WaitConfig(timeout=self._config["timeout"])
            self._smart_wait = SmartWait(self._page, wait_config)
        if not self._error_recovery:
            self._error_recovery = ErrorRecovery(self._page, self)
        if not self._retry_wrapper:
            self._retry_wrapper = RetryWrapper(
                max_retries=self._config["max_retries"],
                base_delay=self._config["retry_delay"]
            )

    async def _get_smart_selector(self, selector: str) -> Optional[SmartSelector]:
        """
        获取智能选择器（带缓存）

        如果选择器已经在缓存中，返回缓存的智能选择器。
        否则尝试为当前元素生成智能选择器。
        """
        # 检查缓存
        if selector in self._selector_cache:
            return self._selector_cache[selector]

        # 尝试查找元素并生成智能选择器
        try:
            element = await self._page.wait_for_selector(selector, timeout=5000)
            smart_selector = await self._selector_generator.generate(element)
            self._selector_cache[selector] = smart_selector
            return smart_selector
        except:
            return None

    async def _execute_with_stability(
        self,
        action: str,
        selector: Optional[str],
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        使用稳定性增强执行操作

        流程：
        1. 初始化稳定性模块
        2. 使用智能选择器（如果有）
        3. 执行操作带重试
        4. 错误恢复
        """
        self._init_stability_modules()

        # 如果有选择器，尝试使用智能选择器
        if selector and self._config.get("enable_stability"):
            smart_selector = await self._get_smart_selector(selector)
            if smart_selector:
                # 使用最佳选择器
                selector = smart_selector.best_selector().value

        # 执行带重试
        async def execute():
            return await func(*args, **kwargs)

        try:
            if self._config.get("enable_stability"):
                return await self._retry_wrapper.execute(
                    execute,
                    description=f"{action}: {selector}"
                )
            else:
                return await execute()
        except Exception as e:
            # 尝试错误恢复
            if self._config.get("enable_stability") and self._error_recovery:
                recovery = await self._error_recovery.handle_error(e, selector, action)
                if recovery.recovered and recovery.new_selector:
                    # 使用新选择器重试
                    kwargs['selector'] = recovery.new_selector
                    return await func(*args, **kwargs)
            raise

    def _make_fuzzy_point(
        self,
        fuzzy_reason: Optional[str] = None,
        fuzzy_hint: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Build fuzzy_point dict when caller provides override."""
        if fuzzy_reason is None and fuzzy_hint is None:
            return None
        return {
            "requires_judgment": True,
            "reason": fuzzy_reason or "",
            "hint": fuzzy_hint
        }

    async def open(
        self,
        url: str,
        wait_until: str = "networkidle",
        take_screenshot: bool = None,
        fuzzy_reason: Optional[str] = None,
        fuzzy_hint: Optional[str] = None
    ) -> OperationRecord:
        """
        Open a URL and capture complete state.

        Args:
            url: Target URL
            wait_until: Wait condition (load, domcontentloaded, networkidle, commit)
            take_screenshot: Override auto_screenshot config

        Returns:
            OperationRecord with full context
        """
        step = self._next_step()
        take_screenshot = take_screenshot if take_screenshot is not None else self._config["auto_screenshot"]

        screenshot = None
        error = None

        try:
            await self._page.goto(url, wait_until=wait_until, timeout=self._config["timeout"])
            await self._wait_for_stable_state()

            page_state = await self._get_page_state()

            if take_screenshot:
                screenshot = await self._take_screenshot()

            result = {"success": True, "url": url, "title": page_state.title}

        except Exception as e:
            page_state = await self._get_page_state()
            result = {"success": False, "error": str(e)}
            error = str(e)

        record = OperationRecord(
            step=step,
            action="open",
            params={"url": url, "wait_until": wait_until},
            result=result,
            page_state=page_state,
            screenshot=screenshot,
            error=error,
            fuzzy_point=self._make_fuzzy_point(fuzzy_reason, fuzzy_hint)
        )
        self._operation_history.append(record)
        return record

    async def click(
        self,
        selector: str,
        timeout: int = None,
        wait_after: float = 0.5,
        take_screenshot: bool = None,
        scroll_into_view: bool = True,
        fuzzy_reason: Optional[str] = None,
        fuzzy_hint: Optional[str] = None,
        auto_save: bool = False,
        adaptive: bool = False,
        identifier: Optional[str] = None,
    ) -> OperationRecord:
        """
        Click an element with enhanced error handling and state capture.

        Args:
            selector: CSS selector of element to click
            timeout: Override default timeout
            wait_after: Seconds to wait after click
            take_screenshot: Override auto_screenshot config
            scroll_into_view: Whether to scroll element into view first
            auto_save: If True, save element fingerprint for adaptive relocation
            adaptive: If True and selector fails, try to relocate by stored fingerprint
            identifier: Optional key for stored fingerprint (default: selector)

        Returns:
            OperationRecord with click result and new page state
        """
        step = self._next_step()
        timeout = timeout or self._config["timeout"]
        take_screenshot = take_screenshot if take_screenshot is not None else self._config["auto_screenshot"]
        ident = identifier or selector
        storage = self._get_adaptive_storage()

        screenshot_before = None
        screenshot_after = None
        error = None
        old_url = self._page.url
        page_state = None
        selector_candidates = None

        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            el = await self._page.query_selector(selector)
            if el:
                self._init_stability_modules()
                if self._selector_generator:
                    try:
                        smart = await self._selector_generator.generate(el)
                        selector_candidates = [{"type": c.type.value, "value": c.value} for c in smart.all_selectors()]
                    except Exception:
                        pass
            if el and auto_save and storage:
                fp = await extract_fingerprint(el, self._page)
                if fp:
                    storage.fingerprint_save(_domain_from_url(self._page.url), ident, fp)
            if take_screenshot:
                screenshot_before = await self._take_screenshot()
            if scroll_into_view:
                await self._page.locator(selector).scroll_into_view_if_needed()
            await self._page.click(selector, timeout=timeout)
            await asyncio.sleep(wait_after)
            await self._wait_for_stable_state()
            page_state = await self._get_page_state()
            if take_screenshot:
                screenshot_after = await self._take_screenshot()
            navigated = page_state.url != old_url
            result = {
                "success": True,
                "selector": selector,
                "navigated": navigated,
                "new_url": page_state.url if navigated else None
            }
        except Exception as e:
            if adaptive and storage:
                handle = await relocate(self._page, _domain_from_url(self._page.url), ident, storage)
                if handle:
                    try:
                        await handle.scroll_into_view_if_needed()
                        await handle.click()
                        await asyncio.sleep(wait_after)
                        await self._wait_for_stable_state()
                        page_state = await self._get_page_state()
                        if take_screenshot:
                            screenshot_after = await self._take_screenshot()
                        navigated = page_state.url != old_url
                        result = {
                            "success": True,
                            "selector": selector,
                            "navigated": navigated,
                            "new_url": page_state.url if navigated else None,
                            "adaptive_used": True
                        }
                    except Exception as e2:
                        page_state = await self._get_page_state()
                        result = {"success": False, "error": str(e2), "selector": selector, "adaptive_used": True}
                        error = str(e2)
                else:
                    page_state = await self._get_page_state()
                    result = {"success": False, "error": str(e), "selector": selector}
                    error = str(e)
            else:
                page_state = await self._get_page_state()
                result = {"success": False, "error": str(e), "selector": selector}
                error = str(e)

        if page_state is None:
            page_state = await self._get_page_state()
        record = OperationRecord(
            step=step,
            action="click",
            params={"selector": selector, "timeout": timeout},
            result=result,
            page_state=page_state,
            screenshot=screenshot_after,
            error=error,
            fuzzy_point=self._make_fuzzy_point(fuzzy_reason, fuzzy_hint),
            selector_candidates=selector_candidates,
        )
        self._operation_history.append(record)
        return record

    async def input(
        self,
        selector: str,
        text: str,
        delay: int = 50,
        clear_first: bool = True,
        take_screenshot: bool = None,
        fuzzy_reason: Optional[str] = None,
        fuzzy_hint: Optional[str] = None,
        auto_save: bool = False,
        adaptive: bool = False,
        identifier: Optional[str] = None,
    ) -> OperationRecord:
        """
        Type text into an input field.

        Args:
            selector: CSS selector of input field
            text: Text to type
            delay: Delay between keystrokes (ms)
            clear_first: Clear existing value before typing
            take_screenshot: Override auto_screenshot config
            auto_save: Save element fingerprint for adaptive relocation
            adaptive: On selector failure, try relocate by stored fingerprint
            identifier: Optional key for stored fingerprint (default: selector)

        Returns:
            OperationRecord with input result
        """
        step = self._next_step()
        take_screenshot = take_screenshot if take_screenshot is not None else self._config["auto_screenshot"]
        ident = identifier or selector
        storage = self._get_adaptive_storage()

        screenshot = None
        error = None
        page_state = None
        selector_candidates = None

        try:
            await self._page.wait_for_selector(selector, timeout=self._config["timeout"])
            el = await self._page.query_selector(selector)
            if el:
                self._init_stability_modules()
                if self._selector_generator:
                    try:
                        smart = await self._selector_generator.generate(el)
                        selector_candidates = [{"type": c.type.value, "value": c.value} for c in smart.all_selectors()]
                    except Exception:
                        pass
            if el and auto_save and storage:
                fp = await extract_fingerprint(el, self._page)
                if fp:
                    storage.fingerprint_save(_domain_from_url(self._page.url), ident, fp)
            if clear_first:
                await self._page.locator(selector).clear()
            await self._page.type(selector, text, delay=delay)
            actual_value = await self._page.input_value(selector)
            if take_screenshot:
                screenshot = await self._take_screenshot()
            page_state = await self._get_page_state()
            result = {
                "success": True,
                "selector": selector,
                "text": text,
                "actual_value": actual_value,
                "match": actual_value == text
            }
        except Exception as e:
            if adaptive and storage:
                handle = await relocate(self._page, _domain_from_url(self._page.url), ident, storage)
                if handle:
                    try:
                        if clear_first:
                            await handle.fill("")
                        if delay > 0:
                            await handle.type(text, delay=delay)
                        else:
                            await handle.fill(text)
                        actual_value = await handle.evaluate("el => el.value")
                        if take_screenshot:
                            screenshot = await self._take_screenshot()
                        page_state = await self._get_page_state()
                        result = {"success": True, "selector": selector, "text": text, "actual_value": actual_value, "match": actual_value == text, "adaptive_used": True}
                    except Exception as e2:
                        page_state = await self._get_page_state()
                        result = {"success": False, "error": str(e2), "selector": selector, "adaptive_used": True}
                        error = str(e2)
                else:
                    page_state = await self._get_page_state()
                    result = {"success": False, "error": str(e), "selector": selector}
                    error = str(e)
            else:
                page_state = await self._get_page_state()
                result = {"success": False, "error": str(e), "selector": selector}
                error = str(e)

        if page_state is None:
            page_state = await self._get_page_state()
        record = OperationRecord(
            step=step,
            action="input",
            params={"selector": selector, "text": text, "delay": delay},
            result=result,
            page_state=page_state,
            screenshot=screenshot,
            error=error,
            fuzzy_point=self._make_fuzzy_point(fuzzy_reason, fuzzy_hint),
            selector_candidates=selector_candidates,
        )
        self._operation_history.append(record)
        return record

    async def get_text(
        self,
        selector: str,
        attr: Literal["text", "html", "value", "innerText"] = "text",
        take_screenshot: bool = False,
        fuzzy_reason: Optional[str] = None,
        fuzzy_hint: Optional[str] = None,
        auto_save: bool = False,
        adaptive: bool = False,
        identifier: Optional[str] = None,
    ) -> OperationRecord:
        """
        Extract text or attribute from an element.

        Args:
            selector: CSS selector of element
            attr: Attribute to extract (text, html, value, innerText)
            take_screenshot: Whether to take screenshot
            auto_save: Save element fingerprint for adaptive relocation
            adaptive: On selector failure, try relocate by stored fingerprint
            identifier: Optional key for stored fingerprint (default: selector)

        Returns:
            OperationRecord with extracted value
        """
        step = self._next_step()
        ident = identifier or selector
        storage = self._get_adaptive_storage()

        error = None
        page_state = None
        screenshot = None

        async def _get_value_from_el(el: Any) -> Optional[str]:
            if attr == "text":
                return await el.text_content()
            if attr == "html":
                return await el.inner_html()
            if attr == "value":
                return await el.get_attribute("value")
            if attr == "innerText":
                return await el.evaluate("el => el.innerText")
            return await el.get_attribute(attr)

        try:
            element = await self._page.wait_for_selector(selector, timeout=self._config["timeout"])
            if element and auto_save and storage:
                fp = await extract_fingerprint(element, self._page)
                if fp:
                    storage.fingerprint_save(_domain_from_url(self._page.url), ident, fp)
            value = await _get_value_from_el(element)
            screenshot = await self._take_screenshot() if take_screenshot else None
            page_state = await self._get_page_state()
            result = {"success": True, "selector": selector, "attribute": attr, "value": value.strip() if value else value}
        except Exception as e:
            if adaptive and storage:
                handle = await relocate(self._page, _domain_from_url(self._page.url), ident, storage)
                if handle:
                    try:
                        value = await _get_value_from_el(handle)
                        screenshot = await self._take_screenshot() if take_screenshot else None
                        page_state = await self._get_page_state()
                        result = {"success": True, "selector": selector, "attribute": attr, "value": value.strip() if value else value, "adaptive_used": True}
                    except Exception as e2:
                        page_state = await self._get_page_state()
                        screenshot = await self._take_screenshot() if take_screenshot else None
                        result = {"success": False, "error": str(e2), "selector": selector, "adaptive_used": True}
                        error = str(e2)
                else:
                    page_state = await self._get_page_state()
                    screenshot = await self._take_screenshot() if take_screenshot else None
                    result = {"success": False, "error": str(e), "selector": selector}
                    error = str(e)
            else:
                page_state = await self._get_page_state()
                screenshot = await self._take_screenshot() if take_screenshot else None
                result = {"success": False, "error": str(e), "selector": selector}
                error = str(e)

        if page_state is None:
            page_state = await self._get_page_state()
        record = OperationRecord(
            step=step,
            action="get_text",
            params={"selector": selector, "attribute": attr},
            result=result,
            page_state=page_state,
            screenshot=screenshot,
            error=error,
            fuzzy_point=self._make_fuzzy_point(fuzzy_reason, fuzzy_hint)
        )
        self._operation_history.append(record)
        return record

    async def get_html(
        self,
        selector: Optional[str] = None,
        take_screenshot: bool = False,
        fuzzy_reason: Optional[str] = None,
        fuzzy_hint: Optional[str] = None,
        auto_save: bool = False,
        adaptive: bool = False,
        identifier: Optional[str] = None,
    ) -> OperationRecord:
        """
        Get HTML content of page or element.

        Args:
            selector: Optional CSS selector (None for full page)
            take_screenshot: Whether to take screenshot
            auto_save: Save element fingerprint (only when selector is set)
            adaptive: On selector failure, try relocate (only when selector is set)
            identifier: Optional key for stored fingerprint (default: selector)

        Returns:
            OperationRecord with HTML content
        """
        step = self._next_step()
        error = None
        page_state = None
        screenshot = None
        ident = identifier or selector
        storage = self._get_adaptive_storage()

        try:
            if selector:
                element = await self._page.wait_for_selector(selector, timeout=self._config["timeout"])
                if element and auto_save and storage:
                    fp = await extract_fingerprint(element, self._page)
                    if fp:
                        storage.fingerprint_save(_domain_from_url(self._page.url), ident, fp)
                html = await element.inner_html()
            else:
                html = await self._page.content()

            screenshot = await self._take_screenshot() if take_screenshot else None
            page_state = await self._get_page_state()
            result = {"success": True, "selector": selector, "html": html}
        except Exception as e:
            if selector and adaptive and storage:
                handle = await relocate(self._page, _domain_from_url(self._page.url), ident, storage)
                if handle:
                    try:
                        html = await handle.inner_html()
                        screenshot = await self._take_screenshot() if take_screenshot else None
                        page_state = await self._get_page_state()
                        result = {"success": True, "selector": selector, "html": html, "adaptive_used": True}
                    except Exception as e2:
                        page_state = await self._get_page_state()
                        screenshot = await self._take_screenshot() if take_screenshot else None
                        result = {"success": False, "error": str(e2), "adaptive_used": True}
                        error = str(e2)
                else:
                    page_state = await self._get_page_state()
                    screenshot = await self._take_screenshot() if take_screenshot else None
                    result = {"success": False, "error": str(e)}
                    error = str(e)
            else:
                page_state = await self._get_page_state()
                screenshot = await self._take_screenshot() if take_screenshot else None
                result = {"success": False, "error": str(e)}
                error = str(e)

        if page_state is None:
            page_state = await self._get_page_state()
        record = OperationRecord(
            step=step,
            action="get_html",
            params={"selector": selector},
            result=result,
            page_state=page_state,
            screenshot=screenshot,
            error=error,
            fuzzy_point=self._make_fuzzy_point(fuzzy_reason, fuzzy_hint)
        )
        self._operation_history.append(record)
        return record

    async def screenshot(
        self,
        path: Optional[str] = None,
        full_page: bool = False,
        selector: Optional[str] = None,
        fuzzy_reason: Optional[str] = None,
        fuzzy_hint: Optional[str] = None
    ) -> OperationRecord:
        """
        Take a screenshot.

        Args:
            path: Optional file path to save
            full_page: Capture full page height
            selector: Optional selector to capture specific element

        Returns:
            OperationRecord with screenshot data
        """
        step = self._next_step()
        error = None

        try:
            page_state = await self._get_page_state()

            if selector:
                element = await self._page.wait_for_selector(selector, timeout=self._config["timeout"])
                screenshot_data = await element.screenshot()
            else:
                screenshot_data = await self._page.screenshot(full_page=full_page)

            screenshot_b64 = base64.b64encode(screenshot_data).decode('utf-8')

            if path:
                with open(path, 'wb') as f:
                    f.write(screenshot_data)

            result = {
                "success": True,
                "path": path,
                "full_page": full_page,
                "selector": selector,
                "screenshot": screenshot_b64
            }

        except Exception as e:
            page_state = await self._get_page_state()
            result = {"success": False, "error": str(e)}
            error = str(e)
            screenshot_b64 = None

        record = OperationRecord(
            step=step,
            action="screenshot",
            params={"path": path, "full_page": full_page, "selector": selector},
            result=result,
            page_state=page_state,
            screenshot=screenshot_b64,
            error=error,
            fuzzy_point=self._make_fuzzy_point(fuzzy_reason, fuzzy_hint)
        )
        self._operation_history.append(record)
        return record

    async def wait_for(
        self,
        condition: str,
        value: Optional[str] = None,
        timeout: int = None,
        fuzzy_reason: Optional[str] = None,
        fuzzy_hint: Optional[str] = None
    ) -> OperationRecord:
        """
        Wait for a condition to be true.

        Args:
            condition: Type of condition (selector, url, text, navigation)
            value: Condition value
            timeout: Override timeout

        Returns:
            OperationRecord with wait result
        """
        step = self._next_step()
        timeout = timeout or self._config["timeout"]
        error = None

        try:
            if condition in ("selector", "url", "text") and (value is None or value == ""):
                raise ValueError(f"value is required when condition is {condition}")

            if condition == "selector":
                await self._page.wait_for_selector(value, timeout=timeout)
            elif condition == "url":
                await self._page.wait_for_url(value, timeout=timeout)
            elif condition == "text":
                # Use json.dumps to safely escape value for JS (prevents injection)
                safe_value = json.dumps(value)
                await self._page.wait_for_function(
                    f"document.body.innerText.includes({safe_value})", timeout=timeout
                )
            elif condition == "navigation":
                await self._page.wait_for_load_state("networkidle", timeout=timeout)
            else:
                raise ValueError(f"Unknown condition: {condition}")

            page_state = await self._get_page_state()
            screenshot = await self._take_screenshot()

            result = {"success": True, "condition": condition, "value": value}

        except Exception as e:
            page_state = await self._get_page_state()
            screenshot = await self._take_screenshot()
            result = {"success": False, "error": str(e), "condition": condition}
            error = str(e)

        record = OperationRecord(
            step=step,
            action="wait_for",
            params={"condition": condition, "value": value},
            result=result,
            page_state=page_state,
            screenshot=screenshot,
            error=error,
            fuzzy_point=self._make_fuzzy_point(fuzzy_reason, fuzzy_hint)
        )
        self._operation_history.append(record)
        return record

    async def extract_data(
        self,
        schema: Dict[str, Any],
        take_screenshot: bool = True,
        fuzzy_reason: Optional[str] = None,
        fuzzy_hint: Optional[str] = None
    ) -> OperationRecord:
        """
        Extract structured data based on schema.
        This is an AI-node capable operation.

        Args:
            schema: Data extraction schema
                {
                    "fields": [
                        {"name": "price", "selector": ".price", "type": "float"},
                        {"name": "title", "selector": "h1", "type": "text"}
                    ]
                }
            take_screenshot: Whether to take screenshot

        Returns:
            OperationRecord with extracted data and AI node flag
        """
        step = self._next_step()
        error = None

        try:
            page_state = await self._get_page_state()
            screenshot = await self._take_screenshot() if take_screenshot else None

            extracted_data = {}

            for field in schema.get("fields", []):
                name = field["name"]
                selector = field["selector"]
                field_type = field.get("type", "text")

                try:
                    element = await self._page.wait_for_selector(selector, timeout=5000)

                    if field_type == "text":
                        value = (await element.text_content() or "").strip()
                    elif field_type == "html":
                        value = await element.inner_html()
                    elif field_type == "value":
                        value = await element.get_attribute("value")
                    elif field_type == "float":
                        text = await element.text_content() or ""
                        value = float(text.replace('$', '').replace(',', '').strip())
                    elif field_type == "int":
                        text = await element.text_content() or ""
                        value = int(''.join(filter(str.isdigit, text)))
                    else:
                        value = await element.text_content()

                    extracted_data[name] = value

                except Exception as field_error:
                    extracted_data[name] = None
                    extracted_data[f"{name}_error"] = str(field_error)

            result = {
                "success": True,
                "data": extracted_data,
                "schema": schema
            }

        except Exception as e:
            page_state = await self._get_page_state()
            screenshot = await self._take_screenshot() if take_screenshot else None
            result = {"success": False, "error": str(e)}
            error = str(e)

        fuzzy_point = {
            "requires_judgment": True,
            "reason": fuzzy_reason or "需根据 schema 提取可变内容",
            "hint": fuzzy_hint
        }
        record = OperationRecord(
            step=step,
            action="extract_data",
            params={"schema": schema},
            result=result,
            page_state=page_state,
            screenshot=screenshot,
            error=error,
            fuzzy_point=fuzzy_point
        )
        record.result["ai_node"] = True
        self._operation_history.append(record)
        return record

    def get_operation_history(self) -> List[Dict[str, Any]]:
        """Get all operation records."""
        return [record.to_dict() for record in self._operation_history]

    def get_last_operation(self) -> Optional[Dict[str, Any]]:
        """Get the last operation record."""
        if self._operation_history:
            return self._operation_history[-1].to_dict()
        return None

    def clear_history(self) -> None:
        """Clear operation history."""
        self._operation_history = []
        self._step_counter = 0

    def set_config(self, **kwargs) -> None:
        """Update controller configuration."""
        self._config.update(kwargs)

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self._config.copy()
