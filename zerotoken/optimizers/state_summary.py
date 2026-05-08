"""页面状态摘要：将页面精简为结构化摘要供 AI 推理"""

from __future__ import annotations

from typing import Any

_JS_FORMS = """() => {
    return Array.from(document.querySelectorAll('form')).slice(0, 10).map(f => ({
        tag: 'form',
        id: f.id || null,
        action: f.action || null,
        method: f.method || 'get',
        fields: Array.from(f.querySelectorAll('input,select,textarea')).slice(0, 20).map(
            el => el.name || el.id || el.type || el.tagName.toLowerCase()
        )
    }))
}"""

_JS_LINKS = """() => {
    return Array.from(document.querySelectorAll('a[href]')).slice(0, 20).map(a => ({
        text: (a.textContent || '').trim().slice(0, 60),
        href: a.getAttribute('href')
    }))
}"""

_JS_BUTTONS = """() => {
    const btns = document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]');
    return Array.from(btns).slice(0, 20).map(b => ({
        text: (b.textContent || b.value || '').trim().slice(0, 60),
        tag: b.tagName.toLowerCase(),
        id: b.id || null,
        type: b.type || null
    }))
}"""

_JS_TEXT = """() => {
    const el = document.querySelector('main') || document.querySelector('article') || document.body;
    return (el.innerText || '').slice(0, 500)
}"""

_JS_INTERACTIVE_COUNT = """() => {
    return document.querySelectorAll(
        'a, button, input, select, textarea, [role="button"], [onclick], [tabindex]'
    ).length
}"""


async def summarize_page(page: Any, *, max_text_length: int = 500) -> dict[str, Any]:
    """生成页面状态摘要"""
    url = page.url if hasattr(page, "url") else ""

    title = ""
    try:
        title = await page.title()
    except Exception:
        pass

    forms: list[Any] = []
    links: list[Any] = []
    buttons: list[Any] = []
    text_summary = ""
    interactive_count = 0

    try:
        forms = await page.evaluate(_JS_FORMS)
    except Exception:
        pass

    try:
        links = await page.evaluate(_JS_LINKS)
    except Exception:
        pass

    try:
        buttons = await page.evaluate(_JS_BUTTONS)
    except Exception:
        pass

    try:
        text_summary = await page.evaluate(_JS_TEXT)
        if text_summary:
            text_summary = text_summary[:max_text_length]
    except Exception:
        pass

    try:
        interactive_count = await page.evaluate(_JS_INTERACTIVE_COUNT)
    except Exception:
        pass

    return {
        "url": url,
        "title": title,
        "forms": forms or [],
        "links": links or [],
        "buttons": buttons or [],
        "text_summary": text_summary or "",
        "interactive_elements": interactive_count,
    }
