"""VarsEnvironment 测试：变量存取、参数解析、快照、表达式求值"""

import pytest


def test_get_set():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment()
    env.set("x", 42)
    assert env.get("x") == 42


def test_get_missing_returns_none():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment()
    assert env.get("missing") is None


def test_init_with_vars():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"a": 1, "b": "hello"})
    assert env.get("a") == 1
    assert env.get("b") == "hello"


def test_resolve_params_replaces_placeholders():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"url": "https://example.com", "user": "admin"})
    params = {"target": "{{url}}", "name": "{{user}}", "static": "unchanged"}
    resolved = env.resolve_params(params)
    assert resolved["target"] == "https://example.com"
    assert resolved["name"] == "admin"
    assert resolved["static"] == "unchanged"


def test_resolve_params_partial_replace():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"host": "example.com"})
    params = {"url": "https://{{host}}/login"}
    resolved = env.resolve_params(params)
    assert resolved["url"] == "https://example.com/login"


def test_resolve_params_missing_var_kept():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment()
    params = {"url": "{{missing}}"}
    resolved = env.resolve_params(params)
    assert resolved["url"] == "{{missing}}"


def test_resolve_params_non_string_untouched():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"x": 10})
    params = {"count": 5, "flag": True, "items": [1, 2]}
    resolved = env.resolve_params(params)
    assert resolved == {"count": 5, "flag": True, "items": [1, 2]}


def test_snapshot_and_restore():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"a": 1, "b": [1, 2]})
    snap = env.snapshot()
    assert snap == {"a": 1, "b": [1, 2]}
    env2 = VarsEnvironment(snap)
    assert env2.get("a") == 1
    assert env2.get("b") == [1, 2]


def test_eval_condition_comparison():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"x": 10, "threshold": 5})
    assert env.eval_condition("x > threshold") is True
    assert env.eval_condition("x < threshold") is False
    assert env.eval_condition("x == 10") is True


def test_eval_condition_arithmetic():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"page_num": 3, "max_pages": 5})
    assert env.eval_condition("page_num <= max_pages") is True
    assert env.eval_condition("page_num + 1 <= max_pages") is True
    assert env.eval_condition("page_num > max_pages") is False


def test_eval_condition_string_ops():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"status": "ok"})
    assert env.eval_condition("status == 'ok'") is True
    assert env.eval_condition("status != 'fail'") is True


def test_eval_condition_float_cast():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"price": "9.99", "budget": "20.00"})
    assert env.eval_condition("float(price) < float(budget)") is True


def test_eval_condition_bool_ops():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"a": True, "b": False})
    assert env.eval_condition("a and not b") is True
    assert env.eval_condition("a or b") is True


def test_eval_expr_arithmetic():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"page_num": 3})
    assert env.eval_expr("page_num + 1") == 4
    assert env.eval_expr("page_num * 2") == 6


def test_eval_expr_string_concat():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"base": "hello"})
    assert env.eval_expr("base + ' world'") == "hello world"


def test_eval_expr_float_int_cast():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"x": "42"})
    assert env.eval_expr("int(x)") == 42
    assert env.eval_expr("float(x)") == 42.0


def test_eval_expr_len_str():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"items": [1, 2, 3]})
    assert env.eval_expr("len(items)") == 3
    assert env.eval_expr("str(42)") == "42"


def test_eval_blocks_dangerous():
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment()
    with pytest.raises(ValueError, match="not allowed"):
        env.eval_expr("__import__('os').system('ls')")
    with pytest.raises(ValueError, match="not allowed"):
        env.eval_expr("open('/etc/passwd')")


def test_resolve_params_dotted_path():
    """{{var.key}} 应正确解析 dict 内的字段"""
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"tab": {"tab_id": 3, "url": "https://example.com"}})
    params = {"tab_id": "{{tab.tab_id}}", "label": "info: {{tab.url}}"}
    resolved = env.resolve_params(params)
    assert resolved["tab_id"] == 3
    assert resolved["label"] == "info: https://example.com"


def test_resolve_params_dotted_path_nested():
    """多层嵌套的 dot 路径应能正常解析"""
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"a": {"b": {"c": 42}}})
    resolved = env.resolve_params({"val": "{{a.b.c}}"})
    assert resolved["val"] == 42


def test_resolve_params_dotted_path_missing():
    """dot 路径找不到时保留原始占位符"""
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"tab": {"tab_id": 3}})
    resolved = env.resolve_params({"x": "{{tab.nonexist}}"})
    assert resolved["x"] == "{{tab.nonexist}}"


def test_resolve_params_preserves_native_type_for_single_placeholder():
    """当整个值为单个 {{var}} 时，返回原始类型而非字符串"""
    from zerotoken.engine.data_flow import VarsEnvironment

    env = VarsEnvironment({"count": 42, "flag": True, "data": {"k": "v"}})
    resolved = env.resolve_params(
        {
            "a": "{{count}}",
            "b": "{{flag}}",
            "c": "{{data}}",
        }
    )
    assert resolved["a"] == 42
    assert isinstance(resolved["a"], int)
    assert resolved["b"] is True
    assert resolved["c"] == {"k": "v"}
