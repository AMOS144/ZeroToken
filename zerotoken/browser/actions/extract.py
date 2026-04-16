"""提取类动作：get_text, get_html, screenshot, extract_data"""
from __future__ import annotations

import base64
from typing import Any


async def get_text_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """提取文本或属性（text / html / value / innerText / 自定义 attr）"""
    attr = params.get("attribute", params.get("attr", "text"))
    if attr == "text":
        value = await element.text_content()
    elif attr == "html":
        value = await element.inner_html()
    elif attr == "value":
        value = await element.get_attribute("value")
    elif attr == "innerText":
        value = await element.evaluate("el => el.innerText")
    else:
        value = await element.get_attribute(attr)
    return {"attribute": attr, "value": value.strip() if value else value}


async def get_html_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """获取 HTML：有 element 取元素 inner_html，否则取整页 content"""
    if element:
        html = await element.inner_html()
    else:
        html = await frame.content()
    return {"html": html}


async def screenshot_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """截图：三级降级策略（Playwright 正常 -> CDP 快速截图 -> 放弃）"""
    import asyncio

    full_page = params.get("full_page", False)
    path = params.get("path")
    timeout_ms = params.get("timeout", 10000)
    timeout_s = timeout_ms / 1000

    target = element if element else frame

    # 第一级：Playwright 正常截图
    try:
        kw: dict[str, Any] = {}
        if not element:
            kw["full_page"] = full_page
        data = await asyncio.wait_for(target.screenshot(**kw), timeout=timeout_s)
        b64 = base64.b64encode(data).decode("utf-8")
        if path:
            with open(path, "wb") as f:
                f.write(data)
        return {"screenshot": b64, "path": path, "full_page": full_page}
    except (asyncio.TimeoutError, Exception):
        pass

    # 第二级：CDP 直接截图（绕过 Playwright 的字体/网络等待）
    try:
        page = frame if hasattr(frame, "context") else frame.page
        cdp = await page.context.new_cdp_session(page)
        try:
            result = await asyncio.wait_for(
                cdp.send("Page.captureScreenshot", {"format": "png"}),
                timeout=5,
            )
            import base64 as b64mod
            data = b64mod.b64decode(result["data"])
            b64_str = result["data"]
            if path:
                with open(path, "wb") as f:
                    f.write(data)
            return {"screenshot": b64_str, "path": path, "full_page": full_page, "degraded": True}
        finally:
            await cdp.detach()
    except Exception:
        pass

    # 第三级：放弃截图
    return {
        "screenshot": None,
        "path": path,
        "full_page": full_page,
        "degraded": True,
        "error": "screenshot timeout",
    }


async def extract_data_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """按 schema 从页面提取结构化字段"""
    schema = params.get("schema", {})
    extracted: dict[str, Any] = {}
    for field in schema.get("fields", []):
        name = field["name"]
        selector = field["selector"]
        field_type = field.get("type", "text")
        try:
            el = await frame.wait_for_selector(selector, timeout=5000)
            if field_type == "text":
                extracted[name] = (await el.text_content() or "").strip()
            elif field_type == "html":
                extracted[name] = await el.inner_html()
            elif field_type == "value":
                extracted[name] = await el.get_attribute("value")
            elif field_type == "float":
                text = await el.text_content() or ""
                extracted[name] = float(text.replace("$", "").replace(",", "").strip())
            elif field_type == "int":
                text = await el.text_content() or ""
                extracted[name] = int("".join(filter(str.isdigit, text)))
            else:
                extracted[name] = await el.text_content()
        except Exception as e:
            extracted[name] = None
            extracted[f"{name}_error"] = str(e)
    return {"data": extracted, "schema": schema}


async def evaluate_action(frame: Any, element: Any, params: dict[str, Any]) -> dict[str, Any]:
    """在页面上下文执行 JavaScript 表达式（params 可含 return_value，当前与 Playwright evaluate 行为一致）"""
    expression = params.get("expression", "")
    value = await frame.evaluate(expression)
    return {"value": value}
