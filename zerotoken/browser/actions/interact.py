"""交互类动作：click, input"""
from __future__ import annotations

import asyncio
from typing import Any


async def click_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """点击元素，可选滚动入视、点击后等待，并判断是否发生导航"""
    if params.get("scroll_into_view", True) and element:
        await element.scroll_into_view_if_needed()
    await element.click()
    wait_after = params.get("wait_after", 0.5)
    if wait_after > 0:
        await asyncio.sleep(wait_after)
    old_url = params.get("_old_url", frame.url if hasattr(frame, "url") else "")
    current_url = frame.url if hasattr(frame, "url") else ""
    navigated = current_url != old_url
    return {"navigated": navigated, "new_url": current_url if navigated else None}


async def input_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """输入文本：可清空后 type，并读取实际 value 校验"""
    text = params.get("text", "")
    delay = params.get("delay", 50)
    clear_first = params.get("clear_first", True)
    if clear_first:
        await element.fill("")
    await element.type(text, delay=delay)
    actual_value = await element.evaluate("el => el.value")
    return {
        "text": text,
        "actual_value": actual_value,
        "match": actual_value == text,
    }
