"""浏览器服务：封装 ActionPipeline + BrowserContextManager"""
from __future__ import annotations

from typing import Any, Optional

from zerotoken.models.operation import ActionType, OperationRecord
from zerotoken.browser.context import BrowserContextManager
from zerotoken.browser.pipeline import ActionPipeline
from zerotoken.browser.stability.middleware import StabilityMiddleware
from zerotoken.browser.actions.navigate import open_action, wait_for_action
from zerotoken.browser.actions.interact import (
    click_action, input_action,
    hover_action, right_click_action, double_click_action,
    drag_drop_action, scroll_action,
    keyboard_action, type_text_action,
)
from zerotoken.browser.actions.extract import (
    get_text_action, get_html_action, screenshot_action,
    extract_data_action, evaluate_action,
)
from zerotoken.browser.actions.page_mgmt import (
    new_tab_action, switch_tab_action, close_tab_action, list_tabs_action,
)
from zerotoken.browser.actions.iframe import enter_iframe_action, exit_iframe_action
from zerotoken.browser.actions.file_ops import upload_action, download_action


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

    # ---- 导航 ----

    async def open(self, url: str, wait_until: str = "networkidle",
                   **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.OPEN, {"url": url, "wait_until": wait_until},
            action_fn=open_action, needs_selector=False,
            take_screenshot=kw.get("take_screenshot", True),
        )

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

    # ---- 鼠标交互 ----

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

    async def hover(self, selector: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.HOVER, {"selector": selector},
            action_fn=hover_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def right_click(self, selector: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.RIGHT_CLICK, {"selector": selector},
            action_fn=right_click_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def double_click(self, selector: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.DOUBLE_CLICK, {"selector": selector},
            action_fn=double_click_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def drag_drop(self, source: str, target: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.DRAG_DROP, {"selector": source, "target": target},
            action_fn=drag_drop_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def scroll(self, direction: str = "down", amount: int = 300,
                     selector: str | None = None, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        params: dict[str, Any] = {"direction": direction, "amount": amount}
        if selector:
            params["selector"] = selector
        return await pipeline.execute(
            ActionType.SCROLL, params, action_fn=scroll_action,
            needs_selector=selector is not None,
            take_screenshot=kw.get("take_screenshot", True),
        )

    # ---- 键盘输入 ----

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

    async def keyboard(self, key: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.KEYBOARD, {"key": key},
            action_fn=keyboard_action, needs_selector=False,
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def type_text(self, text: str, delay: int = 50, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.TYPE_TEXT, {"text": text, "delay": delay},
            action_fn=type_text_action, needs_selector=False,
            take_screenshot=kw.get("take_screenshot", True),
        )

    # ---- 数据提取 ----

    async def get_text(self, selector: str, attr: str = "text",
                       **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.GET_TEXT, {"selector": selector, "attribute": attr},
            action_fn=get_text_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", False),
        )

    async def get_html(self, selector: str | None = None,
                       **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.GET_HTML, {"selector": selector} if selector else {},
            action_fn=get_html_action,
            needs_selector=selector is not None,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
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

    async def extract_data(self, schema: dict[str, Any],
                           **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.EXTRACT_DATA, {"schema": schema},
            action_fn=extract_data_action, needs_selector=False,
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def evaluate(self, expression: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.EVALUATE, {"expression": expression},
            action_fn=evaluate_action, needs_selector=False,
            take_screenshot=kw.get("take_screenshot", False),
        )

    # ---- 页面管理（传入 context 而非 frame）----

    async def new_tab(self, url: str | None = None, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.NEW_TAB, {"url": url},
            action_fn=lambda _f, _e, p: new_tab_action(self._context, _e, p),
            needs_selector=False, take_screenshot=kw.get("take_screenshot", False),
        )

    async def switch_tab(self, tab_id: int, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.SWITCH_TAB, {"tab_id": tab_id},
            action_fn=lambda _f, _e, p: switch_tab_action(self._context, _e, p),
            needs_selector=False, take_screenshot=kw.get("take_screenshot", False),
        )

    async def close_tab(self, tab_id: int | None = None, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.CLOSE_TAB, {"tab_id": tab_id},
            action_fn=lambda _f, _e, p: close_tab_action(self._context, _e, p),
            needs_selector=False, take_screenshot=kw.get("take_screenshot", False),
        )

    async def list_tabs(self, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.LIST_TABS, {},
            action_fn=lambda _f, _e, p: list_tabs_action(self._context, _e, p),
            needs_selector=False, take_screenshot=kw.get("take_screenshot", False),
        )

    # ---- iframe 管理（传入 context 而非 frame）----

    async def enter_iframe(self, selector: str, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.ENTER_IFRAME, {"selector": selector},
            action_fn=lambda _f, _e, p: enter_iframe_action(self._context, _e, p),
            needs_selector=False, take_screenshot=kw.get("take_screenshot", True),
        )

    async def exit_iframe(self, exit_all: bool = False, **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.EXIT_IFRAME, {"all": exit_all},
            action_fn=lambda _f, _e, p: exit_iframe_action(self._context, _e, p),
            needs_selector=False, take_screenshot=kw.get("take_screenshot", True),
        )

    # ---- 文件操作 ----

    async def upload(self, selector: str, path: str | list[str],
                     **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.FILE_UPLOAD, {"selector": selector, "path": path},
            action_fn=upload_action,
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    async def download(self, selector: str, save_dir: str | None = None,
                       **kw: Any) -> OperationRecord:
        pipeline = self._ensure_pipeline()
        return await pipeline.execute(
            ActionType.FILE_DOWNLOAD,
            {"selector": selector, "save_dir": save_dir},
            action_fn=lambda _f, _e, p: download_action(
                self._context.active_page.page, _e, p
            ),
            auto_save=kw.get("auto_save", False),
            adaptive=kw.get("adaptive", False),
            identifier=kw.get("identifier"),
            take_screenshot=kw.get("take_screenshot", True),
        )

    @property
    def context(self) -> BrowserContextManager:
        return self._context
