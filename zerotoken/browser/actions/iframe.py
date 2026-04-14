"""iframe 动作：enter_iframe, exit_iframe

注意：这些函数的第一个参数是 BrowserContextManager 而非 frame。
"""
from __future__ import annotations

from typing import Any


async def enter_iframe_action(context: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """进入指定 iframe"""
    selector = params.get("selector", "")
    context.enter_iframe(selector)
    return {"selector": selector}


async def exit_iframe_action(context: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """退出 iframe；all=True 退出所有嵌套层"""
    exit_all = params.get("all", False)
    context.exit_iframe(exit_all=exit_all)
    return {"exit_all": exit_all}
