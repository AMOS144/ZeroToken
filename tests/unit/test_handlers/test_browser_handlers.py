"""Browser handler 单元测试"""
import pytest


def test_browser_tools_returns_list():
    """browser_tools() 返回 Tool 列表"""
    from handlers.browser_handlers import browser_tools
    tools = browser_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0
    names = {t.name for t in tools}
    assert "browser_init" in names
    assert "browser_close" in names
    assert "browser_open" in names
    assert "browser_click" in names
    assert "browser_input" in names


def test_browser_tools_contains_all_expected():
    """browser_tools() 包含所有预期的工具名"""
    from handlers.browser_handlers import browser_tools
    names = {t.name for t in browser_tools()}
    expected = {
        "browser_init", "browser_close", "browser_open", "browser_click",
        "browser_input", "browser_get_text", "browser_get_html",
        "browser_screenshot", "browser_wait_for", "browser_extract_data",
        "browser_hover", "browser_right_click", "browser_double_click",
        "browser_keyboard", "browser_type_text", "browser_drag_drop",
        "browser_scroll", "browser_new_tab", "browser_switch_tab",
        "browser_close_tab", "browser_list_tabs", "browser_enter_iframe",
        "browser_exit_iframe", "browser_upload", "browser_download",
        "browser_evaluate",
    }
    assert expected.issubset(names), f"Missing tools: {expected - names}"


def test_browser_tools_have_input_schema():
    """每个 Tool 都必须有 inputSchema"""
    from handlers.browser_handlers import browser_tools
    for tool in browser_tools():
        assert hasattr(tool, "inputSchema"), f"{tool.name} missing inputSchema"
        assert isinstance(tool.inputSchema, dict), f"{tool.name} inputSchema not dict"
        assert tool.inputSchema.get("type") == "object", f"{tool.name} schema type"


def test_handle_browser_tool_exists():
    """handle_browser_tool 函数存在"""
    from handlers.browser_handlers import handle_browser_tool
    import inspect
    assert inspect.iscoroutinefunction(handle_browser_tool)
