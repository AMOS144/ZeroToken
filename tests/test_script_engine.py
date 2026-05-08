"""Tests for ScriptEngine param substitution and step resolution."""

from zerotoken.engine import resolve_params


def test_resolve_params_replaces_placeholders():
    """Given steps with {{a}} and vars {a: 'x'}, resolved params contain 'x'."""
    steps = [
        {"action": "browser_input", "params": {"selector": "#from", "text": "{{from_city}}"}},
        {"action": "browser_input", "params": {"selector": "#to", "text": "{{to_city}}"}},
    ]
    vars_map = {"from_city": "shanghai", "to_city": "beijing"}
    resolved = resolve_params(steps, vars_map)
    assert len(resolved) == 2
    assert resolved[0]["params"]["text"] == "shanghai"
    assert resolved[0]["params"]["selector"] == "#from"
    assert resolved[1]["params"]["text"] == "beijing"
    assert resolved[1]["params"]["selector"] == "#to"


def test_resolve_params_keeps_unmatched_placeholder():
    """Placeholder with no var stays as {{name}}."""
    steps = [{"action": "browser_input", "params": {"selector": "#x", "text": "{{unknown}}"}}]
    resolved = resolve_params(steps, {})
    assert resolved[0]["params"]["text"] == "{{unknown}}"


def test_resolve_params_empty_vars():
    """Empty vars leaves placeholders unchanged."""
    steps = [{"action": "browser_click", "params": {"selector": "{{btn}}"}}]
    resolved = resolve_params(steps, {})
    assert resolved[0]["params"]["selector"] == "{{btn}}"
