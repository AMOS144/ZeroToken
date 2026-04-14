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


async def hover_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """悬停在元素上"""
    await element.hover()
    return {}


async def right_click_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """右键点击元素"""
    await element.click(button="right")
    return {}


async def double_click_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """双击元素"""
    await element.dblclick()
    return {}


async def drag_drop_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """拖拽：从 element 拖到 target 选择器指定的元素"""
    target_selector = params.get("target", "")
    target = await frame.wait_for_selector(target_selector, timeout=params.get("timeout", 10000))
    src_box = await element.bounding_box()
    dst_box = await target.bounding_box()
    await frame.mouse.move(src_box["x"] + src_box["width"] / 2, src_box["y"] + src_box["height"] / 2)
    await frame.mouse.down()
    await frame.mouse.move(dst_box["x"] + dst_box["width"] / 2, dst_box["y"] + dst_box["height"] / 2)
    await frame.mouse.up()
    return {"target": target_selector}


async def scroll_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """滚动页面或元素"""
    direction = params.get("direction", "down")
    amount = params.get("amount", 300)

    scroll_map = {
        "down": f"el => el.scrollBy(0, {amount})",
        "up": f"el => el.scrollBy(0, -{amount})",
        "right": f"el => el.scrollBy({amount}, 0)",
        "left": f"el => el.scrollBy(-{amount}, 0)",
    }
    js = scroll_map.get(direction, scroll_map["down"])

    if element:
        await element.evaluate(js)
    else:
        page_js = js.replace("el =>", "() =>").replace("el.", "window.")
        await frame.evaluate(page_js)
    return {"direction": direction, "amount": amount}


async def keyboard_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """按键/组合键（Enter, Escape, Control+A 等）"""
    key = params.get("key", "")
    await frame.keyboard.press(key)
    return {"key": key}


async def type_text_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """在当前聚焦元素上原始键入文本（不清空）"""
    text = params.get("text", "")
    delay = params.get("delay", 50)
    await frame.keyboard.type(text, delay=delay)
    return {"text": text}
