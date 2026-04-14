"""浏览器 MCP 工具定义 & 分发"""
from __future__ import annotations

import json
from typing import Any

from mcp.types import Tool, TextContent


# --------------- 工具 Schema 定义 ---------------

# 自适应定位公共属性（selector 类操作共用）
_ADAPTIVE_PROPS: dict[str, Any] = {
    "auto_save": {
        "type": "boolean",
        "description": "Save element fingerprint for adaptive relocation when selector works",
        "default": False,
    },
    "adaptive": {
        "type": "boolean",
        "description": "If selector fails, relocate element by stored fingerprint",
        "default": False,
    },
    "identifier": {
        "type": "string",
        "description": "Optional key for stored fingerprint (default: selector)",
    },
}

# include_screenshot 公共属性
_SCREENSHOT_PROP: dict[str, Any] = {
    "include_screenshot": {
        "type": "boolean",
        "description": "Include screenshot in response (set false to reduce token)",
        "default": True,
    },
}


def _obj_schema(
    props: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    """构建 JSON Schema object"""
    s: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        s["required"] = required
    return s


# ------------ 工具列表 ---------------

def browser_tools() -> list[Tool]:
    """返回所有浏览器相关 MCP 工具定义"""
    return [
        # -- 生命周期 --
        Tool(
            name="browser_init",
            description="Initialize the browser (call once before other browser tools). stealth=true enables anti-detection.",
            inputSchema=_obj_schema({
                "headless": {"type": "boolean", "description": "Run in headless mode", "default": True},
                "viewport_width": {"type": "integer", "description": "Viewport width", "default": 1920},
                "viewport_height": {"type": "integer", "description": "Viewport height", "default": 1080},
                "stealth": {"type": "boolean", "description": "Enable stealth mode", "default": False},
            }),
        ),
        Tool(
            name="browser_close",
            description="Close the browser and cleanup resources",
            inputSchema=_obj_schema({}),
        ),
        # -- 导航 --
        Tool(
            name="browser_open",
            description="Open a URL in the browser and return operation record",
            inputSchema=_obj_schema({
                "url": {"type": "string", "description": "The URL to open"},
                "wait_until": {"type": "string", "description": "Wait condition", "default": "networkidle"},
                **_SCREENSHOT_PROP,
            }, required=["url"]),
        ),
        # -- 鼠标交互 --
        Tool(
            name="browser_click",
            description="Click an element and return operation record with page state",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector of the element"},
                "timeout": {"type": "integer", "description": "Timeout in ms", "default": 30000},
                "wait_after": {"type": "number", "description": "Seconds to wait after click", "default": 0.5},
                **_ADAPTIVE_PROPS,
                **_SCREENSHOT_PROP,
            }, required=["selector"]),
        ),
        Tool(
            name="browser_hover",
            description="Hover over an element",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector"},
                **_ADAPTIVE_PROPS,
                **_SCREENSHOT_PROP,
            }, required=["selector"]),
        ),
        Tool(
            name="browser_right_click",
            description="Right-click an element to open context menu",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector"},
                **_ADAPTIVE_PROPS,
                **_SCREENSHOT_PROP,
            }, required=["selector"]),
        ),
        Tool(
            name="browser_double_click",
            description="Double-click an element",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector"},
                **_ADAPTIVE_PROPS,
                **_SCREENSHOT_PROP,
            }, required=["selector"]),
        ),
        Tool(
            name="browser_drag_drop",
            description="Drag an element to a target position",
            inputSchema=_obj_schema({
                "source": {"type": "string", "description": "CSS selector of source element"},
                "target": {"type": "string", "description": "CSS selector of target element"},
                **_SCREENSHOT_PROP,
            }, required=["source", "target"]),
        ),
        # -- 键盘 & 输入 --
        Tool(
            name="browser_input",
            description="Type text into an input field (clear + type)",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector of the input field"},
                "text": {"type": "string", "description": "Text to type"},
                "delay": {"type": "integer", "description": "Delay between keystrokes (ms)", "default": 50},
                "clear_first": {"type": "boolean", "description": "Clear existing value before typing", "default": True},
                **_ADAPTIVE_PROPS,
                **_SCREENSHOT_PROP,
            }, required=["selector", "text"]),
        ),
        Tool(
            name="browser_keyboard",
            description="Press a keyboard key (Enter, Escape, Tab, etc.)",
            inputSchema=_obj_schema({
                "key": {"type": "string", "description": "Key name (Enter, Escape, Tab, ArrowDown, ...)"},
                **_SCREENSHOT_PROP,
            }, required=["key"]),
        ),
        Tool(
            name="browser_type_text",
            description="Type text at current focus without clearing (raw keystrokes)",
            inputSchema=_obj_schema({
                "text": {"type": "string", "description": "Text to type"},
                "delay": {"type": "integer", "description": "Delay between keystrokes (ms)", "default": 50},
                **_SCREENSHOT_PROP,
            }, required=["text"]),
        ),
        # -- 提取 --
        Tool(
            name="browser_get_text",
            description="Extract text or attribute from an element",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector"},
                "attr": {"type": "string", "description": "Attribute to extract (text, html, value, innerText)", "default": "text"},
                **_ADAPTIVE_PROPS,
                **_SCREENSHOT_PROP,
            }, required=["selector"]),
        ),
        Tool(
            name="browser_get_html",
            description="Get HTML content of page or element",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector (omit for full page)"},
                **_ADAPTIVE_PROPS,
                **_SCREENSHOT_PROP,
            }),
        ),
        Tool(
            name="browser_screenshot",
            description="Take a screenshot and return image data",
            inputSchema=_obj_schema({
                "path": {"type": "string", "description": "File path to save screenshot (optional)"},
                "full_page": {"type": "boolean", "description": "Capture full page", "default": False},
                "selector": {"type": "string", "description": "CSS selector to capture specific element"},
            }),
        ),
        Tool(
            name="browser_extract_data",
            description="Extract structured data based on schema (AI-node capable)",
            inputSchema=_obj_schema({
                "schema": {"type": "object", "description": "Data extraction schema"},
                **_SCREENSHOT_PROP,
            }, required=["schema"]),
        ),
        # -- 等待 --
        Tool(
            name="browser_wait_for",
            description="Wait for a condition (selector, url, text, navigation)",
            inputSchema=_obj_schema({
                "condition": {"type": "string", "description": "Type of condition"},
                "value": {"type": "string", "description": "Condition value"},
                "timeout": {"type": "integer", "description": "Timeout in ms", "default": 30000},
                **_SCREENSHOT_PROP,
            }, required=["condition"]),
        ),
        # -- 滚动 --
        Tool(
            name="browser_scroll",
            description="Scroll page or element",
            inputSchema=_obj_schema({
                "direction": {"type": "string", "description": "up / down / left / right", "default": "down"},
                "amount": {"type": "integer", "description": "Pixels to scroll", "default": 300},
                "selector": {"type": "string", "description": "CSS selector of scrollable element (omit for page)"},
                **_SCREENSHOT_PROP,
            }),
        ),
        # -- Tab 管理 --
        Tool(
            name="browser_new_tab",
            description="Open a new tab with optional URL",
            inputSchema=_obj_schema({
                "url": {"type": "string", "description": "URL to open in new tab (blank if omitted)"},
            }),
        ),
        Tool(
            name="browser_switch_tab",
            description="Switch to a tab by index",
            inputSchema=_obj_schema({
                "index": {"type": "integer", "description": "Tab index (0-based)"},
            }, required=["index"]),
        ),
        Tool(
            name="browser_close_tab",
            description="Close a tab by index (defaults to current)",
            inputSchema=_obj_schema({
                "index": {"type": "integer", "description": "Tab index to close"},
            }),
        ),
        Tool(
            name="browser_list_tabs",
            description="List all open tabs with url and title",
            inputSchema=_obj_schema({}),
        ),
        # -- iframe --
        Tool(
            name="browser_enter_iframe",
            description="Enter an iframe context by selector",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector of the iframe"},
            }, required=["selector"]),
        ),
        Tool(
            name="browser_exit_iframe",
            description="Exit current iframe back to main frame",
            inputSchema=_obj_schema({}),
        ),
        # -- 文件 --
        Tool(
            name="browser_upload",
            description="Upload a file via file input element",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector of file input"},
                "path": {"type": "string", "description": "Local file path to upload"},
            }, required=["selector", "path"]),
        ),
        Tool(
            name="browser_download",
            description="Trigger download and return file path",
            inputSchema=_obj_schema({
                "selector": {"type": "string", "description": "CSS selector that triggers download"},
                "save_dir": {"type": "string", "description": "Directory to save file (default: tmp)"},
            }, required=["selector"]),
        ),
        # -- JS 执行 --
        Tool(
            name="browser_evaluate",
            description="Evaluate JavaScript expression in page context",
            inputSchema=_obj_schema({
                "expression": {"type": "string", "description": "JavaScript expression to evaluate"},
            }, required=["expression"]),
        ),
    ]


# --------------- 公共辅助 ---------------

def _error_resp(
    error: str,
    code: str | None = None,
    retryable: bool | None = None,
) -> list[TextContent]:
    out: dict[str, Any] = {"success": False, "error": error}
    if code is not None:
        out["code"] = code
    if retryable is not None:
        out["retryable"] = retryable
    return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False, default=str))]


def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, default=str))]


def _format_record(record: Any, include_screenshot: bool = True) -> dict[str, Any]:
    """将 OperationRecord 转为 dict，可选去掉截图"""
    d = record.model_dump()
    if not include_screenshot:
        d.pop("screenshot", None)
    return d


# --------------- 分发入口 ---------------

# 返回 OperationRecord 的操作（需同步录入轨迹）
_RECORD_ACTIONS = {
    "browser_open", "browser_click", "browser_input",
    "browser_get_text", "browser_get_html", "browser_screenshot",
    "browser_wait_for", "browser_extract_data",
    "browser_hover", "browser_right_click", "browser_double_click",
    "browser_keyboard", "browser_type_text", "browser_drag_drop",
    "browser_scroll", "browser_new_tab", "browser_switch_tab",
    "browser_close_tab", "browser_list_tabs",
    "browser_enter_iframe", "browser_exit_iframe",
    "browser_upload", "browser_download", "browser_evaluate",
}


async def handle_browser_tool(
    name: str,
    args: dict[str, Any],
    browser_svc: Any,
    trajectory_svc: Any,
) -> list[TextContent]:
    """浏览器工具分发：调用 BrowserService，记录轨迹，返回 TextContent"""
    include_screenshot = args.pop("include_screenshot", True)

    try:
        if name == "browser_init":
            result = await browser_svc.init(
                headless=args.get("headless", True),
                viewport={
                    "width": args.get("viewport_width", 1920),
                    "height": args.get("viewport_height", 1080),
                },
                stealth=args.get("stealth", False),
            )
            return _ok(result)

        if name == "browser_close":
            result = await browser_svc.close()
            return _ok(result)

        # 统一分发 record 类操作
        record = await _dispatch_action(name, args, browser_svc)
        if record is not None:
            trajectory_svc.record_operation(record)
            return _ok(_format_record(record, include_screenshot))

        return _error_resp(f"Unknown browser tool: {name}", code="UNKNOWN_TOOL", retryable=False)

    except Exception as e:
        err = str(e)
        code = "INTERNAL_ERROR"
        retryable = False
        if "timeout" in err.lower():
            code, retryable = "TIMEOUT", True
        elif "not found" in err.lower() or "selector" in err.lower():
            retryable = True
        return _error_resp(err, code=code, retryable=retryable)


async def _dispatch_action(
    name: str, args: dict[str, Any], svc: Any,
) -> Any:
    """按工具名调用 BrowserService 对应方法，返回 OperationRecord 或 None"""
    # 提取自适应定位公共参数
    adaptive_kw = {
        "auto_save": args.pop("auto_save", False),
        "adaptive": args.pop("adaptive", False),
        "identifier": args.pop("identifier", None),
    }
    take_ss = {"take_screenshot": args.get("include_screenshot", True)}

    if name == "browser_open":
        return await svc.open(
            args["url"],
            wait_until=args.get("wait_until", "networkidle"),
            **take_ss,
        )
    if name == "browser_click":
        return await svc.click(
            args["selector"],
            timeout=args.get("timeout"),
            wait_after=args.get("wait_after", 0.5),
            **adaptive_kw, **take_ss,
        )
    if name == "browser_input":
        return await svc.input(
            args["selector"], args["text"],
            delay=args.get("delay", 50),
            clear_first=args.get("clear_first", True),
            **adaptive_kw, **take_ss,
        )
    if name == "browser_get_text":
        return await svc.get_text(
            args["selector"],
            attr=args.get("attr", "text"),
            **adaptive_kw, **take_ss,
        )
    if name == "browser_get_html":
        return await svc.get_html(
            selector=args.get("selector"),
            **adaptive_kw, **take_ss,
        )
    if name == "browser_screenshot":
        return await svc.screenshot(
            path=args.get("path"),
            full_page=args.get("full_page", False),
            selector=args.get("selector"),
        )
    if name == "browser_wait_for":
        return await svc.wait_for(
            args["condition"],
            args.get("value"),
            timeout=args.get("timeout", 30000),
            **take_ss,
        )
    if name == "browser_extract_data":
        return await svc.extract_data(args["schema"], **take_ss)

    # -- 扩展操作：尚未在 BrowserService 中实现的动作走通用 pipeline --
    # 当 BrowserService 增加对应方法后可逐步替换
    method = getattr(svc, name.removeprefix("browser_"), None)
    if method is not None:
        return await method(**args, **adaptive_kw)
    return None
