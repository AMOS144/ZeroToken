"""页面管理动作：new_tab, switch_tab, close_tab, list_tabs

注意：这些函数的第一个参数是 BrowserContextManager 而非 frame，
因为页面管理操作需要访问上下文级别的 API。
"""

from __future__ import annotations

from typing import Any


async def new_tab_action(context: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """新建标签页，可选打开 URL"""
    url = params.get("url")
    mp = await context.new_tab(url=url)
    return {"tab_id": mp.tab_id, "url": mp.page.url}


async def switch_tab_action(context: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """切换到指定标签页"""
    tab_id = params.get("tab_id", 0)
    mp = await context.switch_tab(tab_id)
    return {"tab_id": mp.tab_id, "url": mp.page.url}


async def close_tab_action(context: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """关闭指定标签页"""
    tab_id = params.get("tab_id")
    await context.close_tab(tab_id)
    return {"closed_tab_id": tab_id}


async def list_tabs_action(context: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """列出所有标签页"""
    return {"tabs": context.list_tabs_sync()}
