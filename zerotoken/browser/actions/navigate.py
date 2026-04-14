"""导航类动作：open, wait_for"""
from __future__ import annotations

import json
from typing import Any


async def open_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """打开 URL"""
    url = params.get("url", "")
    wait_until = params.get("wait_until", "networkidle")
    timeout = params.get("timeout", 30000)
    await frame.goto(url, wait_until=wait_until, timeout=timeout)
    return {"url": url}


async def wait_for_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """等待条件（selector / url / text / navigation）"""
    condition = params.get("condition", "")
    value = params.get("value")
    timeout = params.get("timeout", 30000)

    if condition == "selector":
        await frame.wait_for_selector(value, timeout=timeout)
    elif condition == "url":
        await frame.wait_for_url(value, timeout=timeout)
    elif condition == "text":
        safe_value = json.dumps(value)
        await frame.wait_for_function(
            f"document.body.innerText.includes({safe_value})",
            timeout=timeout,
        )
    elif condition == "navigation":
        await frame.wait_for_load_state("networkidle", timeout=timeout)
    else:
        raise ValueError(f"Unknown wait condition: {condition}")

    return {"condition": condition, "value": value}
