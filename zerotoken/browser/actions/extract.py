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
    """截图：元素或整页，可选 full_page、落盘 path"""
    full_page = params.get("full_page", False)
    path = params.get("path")
    if element:
        data = await element.screenshot()
    else:
        data = await frame.screenshot(full_page=full_page)
    b64 = base64.b64encode(data).decode("utf-8")
    if path:
        with open(path, "wb") as f:
            f.write(data)
    return {"screenshot": b64, "path": path, "full_page": full_page}


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
