"""浏览器上下文管理：多标签页 + iframe 栈"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .stealth import STEALTH_LAUNCH_ARGS, STEALTH_INIT_SCRIPT, DEFAULT_STEALTH_USER_AGENT


@dataclass
class ManagedPage:
    """一个受管理的标签页，维护自身的 iframe 导航栈"""
    page: Page
    tab_id: int
    iframe_stack: list[Any] = field(default_factory=list)

    @property
    def active_frame(self) -> Any:
        """当前活动帧：iframe 内返回最内层 frame，否则返回 page"""
        return self.iframe_stack[-1] if self.iframe_stack else self.page


class BrowserContextManager:
    """管理浏览器生命周期 + 多标签页 + iframe 栈"""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pages: dict[int, ManagedPage] = {}
        self._active_tab_id: int = 0
        self._next_tab_id: int = 0

    # ---- 生命周期 ----

    async def start(
        self, *, headless: bool = True,
        viewport: dict[str, int] | None = None,
        stealth: bool = False,
    ) -> None:
        """启动浏览器，创建第一个标签页"""
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        launch_args = (
            STEALTH_LAUNCH_ARGS if stealth
            else ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        self._browser = await self._playwright.chromium.launch(
            headless=headless, args=launch_args,
        )
        vp = viewport or {"width": 1920, "height": 1080}
        if stealth:
            self._context = await self._browser.new_context(
                viewport=vp, user_agent=DEFAULT_STEALTH_USER_AGENT,
                locale="en-US", timezone_id="America/New_York",
            )
            await self._context.add_init_script(STEALTH_INIT_SCRIPT)
        else:
            self._context = await self._browser.new_context(
                viewport=vp,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
        page = await self._context.new_page()
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        self._pages[tab_id] = ManagedPage(page=page, tab_id=tab_id)
        self._active_tab_id = tab_id

    async def stop(self) -> None:
        """关闭所有标签页和浏览器"""
        for mp in self._pages.values():
            try:
                await mp.page.close()
            except Exception:
                pass
        self._pages.clear()
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
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    # ---- 标签页管理 ----

    @property
    def active_page(self) -> ManagedPage:
        """当前激活的标签页"""
        if self._active_tab_id not in self._pages:
            raise RuntimeError("No active page. Call start() first.")
        return self._pages[self._active_tab_id]

    async def new_tab(self, url: str | None = None) -> ManagedPage:
        """新建标签页，可选直接导航到 url"""
        if self._context is None:
            raise RuntimeError("Browser not started")
        page = await self._context.new_page()
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        mp = ManagedPage(page=page, tab_id=tab_id)
        self._pages[tab_id] = mp
        if url:
            await page.goto(url)
        return mp

    async def switch_tab(self, tab_id: int) -> ManagedPage:
        """切换到指定标签页"""
        if tab_id not in self._pages:
            raise ValueError(f"Tab {tab_id} not found")
        self._active_tab_id = tab_id
        await self._pages[tab_id].page.bring_to_front()
        return self._pages[tab_id]

    async def close_tab(self, tab_id: int | None = None) -> None:
        """关闭标签页，自动切到其他存活标签页"""
        tid = tab_id if tab_id is not None else self._active_tab_id
        if tid not in self._pages:
            raise ValueError(f"Tab {tid} not found")
        await self._pages[tid].page.close()
        del self._pages[tid]
        if self._pages and tid == self._active_tab_id:
            self._active_tab_id = next(iter(self._pages))

    def list_tabs_sync(self) -> list[dict[str, Any]]:
        """列出所有标签页（同步方法，不依赖 await）"""
        return [
            {"tab_id": mp.tab_id, "url": mp.page.url, "active": mp.tab_id == self._active_tab_id}
            for mp in self._pages.values()
        ]

    # ---- iframe 管理 ----

    def enter_iframe(self, selector: str) -> None:
        """进入 iframe（支持嵌套调用）"""
        mp = self.active_page
        parent = mp.active_frame
        frame = parent.frame_locator(selector)
        mp.iframe_stack.append(frame)

    def exit_iframe(self, exit_all: bool = False) -> None:
        """退出 iframe；exit_all=True 时退出所有层级"""
        mp = self.active_page
        if exit_all:
            mp.iframe_stack.clear()
        elif mp.iframe_stack:
            mp.iframe_stack.pop()
