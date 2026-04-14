"""Script 模型单元测试"""
import pytest


def test_script_step_basic():
    from zerotoken.models.script import ScriptStep
    step = ScriptStep(action="browser_click", params={"selector": "#btn"})
    assert step.action == "browser_click"
    assert step.condition is None
    assert step.body == []
    assert step.assign_to is None
    assert step.hint is None


def test_script_step_with_flow_control():
    """ScriptStep 支持嵌套 body/else_body"""
    from zerotoken.models.script import ScriptStep
    step = ScriptStep(
        action="if",
        condition="price < 100",
        body=[
            ScriptStep(action="browser_click", params={"selector": "#buy"}),
        ],
        else_body=[
            ScriptStep(action="browser_screenshot", params={}),
        ],
    )
    assert len(step.body) == 1
    assert len(step.else_body) == 1
    assert step.body[0].action == "browser_click"


def test_script_step_with_assign():
    from zerotoken.models.script import ScriptStep
    step = ScriptStep(
        action="browser_get_text",
        params={"selector": ".price"},
        assign_to="current_price",
    )
    assert step.assign_to == "current_price"


def test_script_full():
    from zerotoken.models.script import Script, ScriptStep
    script = Script(
        task_id="demo",
        goal="demo goal",
        steps=[
            ScriptStep(action="browser_open", params={"url": "https://x.com"}),
            ScriptStep(action="browser_click", params={"selector": "#btn"}),
        ],
    )
    assert len(script.steps) == 2
    d = script.model_dump()
    assert d["task_id"] == "demo"
    assert len(d["steps"]) == 2


def test_script_json_roundtrip():
    from zerotoken.models.script import Script, ScriptStep
    script = Script(
        task_id="rt",
        goal="roundtrip",
        steps=[ScriptStep(action="browser_open", params={"url": "https://x.com"})],
    )
    json_str = script.model_dump_json()
    script2 = Script.model_validate_json(json_str)
    assert script2.task_id == "rt"
    assert script2.steps[0].action == "browser_open"


def test_step_hint():
    from zerotoken.models.script import StepHint
    h = StepHint(hint_id="h1", match_rules=[{"action_is": "browser_click"}], hint_text="may need captcha")
    assert h.hint_id == "h1"
