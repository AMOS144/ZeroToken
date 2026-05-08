"""统一执行管道：所有浏览器操作经过同一流程"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from zerotoken.models.operation import (
    ActionType,
    OperationRecord,
    OperationResult,
    PageState,
    SelectorCandidate,
)
from .context import BrowserContextManager, ManagedPage
from .stability.middleware import StabilityMiddleware

# action_fn 签名：(frame, element, params) -> dict
ActionFn = Callable[[Any, Any, dict[str, Any]], Awaitable[dict[str, Any]]]


class ActionPipeline:
    """
    统一执行管道。

    所有浏览器动作都经过：定位 -> 执行 -> 捕获状态 -> 返回 OperationRecord。
    """

    def __init__(
        self,
        context: BrowserContextManager,
        stability: StabilityMiddleware,
    ):
        self.context = context
        self.stability = stability
        self._step_counter = 0

    def _next_step(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def reset_counter(self) -> None:
        """重置步骤计数器（新轨迹时使用）"""
        self._step_counter = 0

    async def execute(
        self,
        action: ActionType,
        params: dict[str, Any],
        *,
        action_fn: ActionFn,
        needs_selector: bool = True,
        take_screenshot: bool = True,
        auto_save: bool = False,
        adaptive: bool = False,
        identifier: str | None = None,
        screenshot_strategy: str = "compressed",
    ) -> OperationRecord:
        """
        执行一个浏览器动作，返回完整的 OperationRecord。

        流程: 获取 frame -> 定位元素(可选) -> 调用 action_fn -> 捕获状态 -> 截图(可选)
        """
        step = self._next_step()
        mp = self.context.active_page
        frame = mp.active_frame

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

        # 捕获页面状态
        page_state = await self._capture_state(mp)

        # 按需截图
        screenshot = None
        if take_screenshot:
            screenshot = await self._take_screenshot_safe(mp.page)

        return OperationRecord(
            step=step,
            action=action,
            params=params,
            result=OperationResult(success=True, data=result_data),
            page_state=page_state,
            screenshot=screenshot,
            selector_candidates=candidates,
        )

    # ---- 辅助方法 ----

    async def _capture_state(self, mp: ManagedPage) -> PageState:
        """安全地捕获当前页面状态"""
        try:
            title = await mp.page.title()
        except Exception:
            title = ""
        return PageState(
            url=mp.page.url,
            title=title,
            tab_id=mp.tab_id,
            tab_count=len(self.context._pages),
        )

    async def _take_screenshot_safe(self, page: Any, timeout: float = 5) -> str | None:
        """CDP 快速截图，不等待字体/网络。失败返回 None。"""
        try:
            cdp = await page.context.new_cdp_session(page)
            try:
                result = await asyncio.wait_for(
                    cdp.send("Page.captureScreenshot", {"format": "png"}),
                    timeout=timeout,
                )
                return result["data"]
            finally:
                await cdp.detach()
        except Exception:
            return None

    async def capture_state_safe(self) -> PageState | None:
        """公开的安全捕获状态方法（供外部使用）"""
        try:
            return await self._capture_state(self.context.active_page)
        except Exception:
            return None

    async def take_screenshot_safe(self) -> str | None:
        """公开的安全截图方法（供外部使用）"""
        try:
            return await self._take_screenshot_safe(self.context.active_page.page)
        except Exception:
            return None
