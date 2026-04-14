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
        """初始化浏览器实例"""
        await self._context.start(headless=headless, viewport=viewport, stealth=stealth)
        self._pipeline = ActionPipeline(self._context, self._stability)
        return {"success": True, "message": "Browser initialized"}

    async def close(self) -> dict[str, Any]:
        """关闭浏览器"""
        await self._context.stop()
        self._pipeline = None
        return {"success": True, "message": "Browser closed"}

    def _ensure_pipeline(self) -> ActionPipeline:
        if self._pipeline is None:
            raise RuntimeError("Browser not initialized. Call init() first.")
        return self._pipeline

    async def open(self, url: str, wait_until: str = "networkidle",
                   **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.OPEN, {"url": url, "wait_until": wait_until},
            action_fn=open_action, needs_selector=False,
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def click(self, selector: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {
            "selector": selector,
            "scroll_into_view": kw.get("scroll_into_view", True),
            "wait_after": kw.get("wait_after", 0.5),
            "_old_url": self._context.active_page.page.url,
        }
        return await pipeline.execute(
            ActionType.CLICK, params, action_fn=click_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def input(self, selector: str, text: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {
            "selector": selector,
            "text": text,
            "delay": kw.get("delay", 50),
            "clear_first": kw.get("clear_first", True),
        }
        return await pipeline.execute(
            ActionType.INPUT, params, action_fn=input_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def get_text(self, selector: str, attr: str = "text",
                       **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.GET_TEXT, {"selector": selector, "attribute": attr},
            action_fn=get_text_action,
            take_screenshot=kw.get("take_screenshot", False),
        )

    async def get_html(self, selector: str | None = None,
                       **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.GET_HTML, {"selector": selector} if selector else {},
            action_fn=get_html_action,
            needs_selector=selector is not None,
            take_screenshot=kw.get("take_screenshot", False),
        )

    async def screenshot(self, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {
            "full_page": kw.get("full_page", False),
            "path": kw.get("path"),
            "selector": kw.get("selector"),
        }
        return await pipeline.execute(
            ActionType.SCREENSHOT, params, action_fn=screenshot_action,
            needs_selector=False, take_screenshot=False,
        )

    async def wait_for(self, condition: str, value: str | None = None,
                       **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params = {
            "condition": condition,
            "value": value,
            "timeout": kw.get("timeout", 30000),
        }
        return await pipeline.execute(
            ActionType.WAIT_FOR, params, action_fn=wait_for_action,
            needs_selector=False, take_screenshot=kw.get("take_screenshot", True),
        )

    async def extract_data(self, schema: dict[str, Any],
                           **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.EXTRACT_DATA, {"schema": schema},
            action_fn=extract_data_action, needs_selector=False,
            take_screenshot=kw.get("take_screenshot", True),
        )

    @property
    def context(self) -> BrowserContextManager:
        return self._context
