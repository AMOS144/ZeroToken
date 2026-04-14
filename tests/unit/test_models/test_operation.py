"""OperationRecord 及相关模型的单元测试"""
from datetime import datetime


def test_action_type_values():
    """ActionType 枚举包含所有预期动作"""
    from zerotoken.models.operation import ActionType
    expected = {
        "open", "click", "input", "get_text", "get_html", "screenshot",
        "wait_for", "extract_data", "hover", "keyboard", "right_click",
        "double_click", "drag_drop", "scroll", "new_tab", "switch_tab",
        "close_tab", "list_tabs", "enter_iframe", "exit_iframe",
        "file_upload", "file_download", "evaluate", "type_text",
    }
    actual = {e.value for e in ActionType}
    assert actual == expected


def test_page_state_defaults():
    """PageState 有合理默认值"""
    from zerotoken.models.operation import PageState
    ps = PageState()
    assert ps.url == ""
    assert ps.title == ""
    assert ps.tab_id == 0
    assert ps.tab_count == 1
    assert isinstance(ps.timestamp, datetime)


def test_page_state_with_values():
    """PageState 可以指定值"""
    from zerotoken.models.operation import PageState
    ps = PageState(url="https://example.com", title="Example", tab_id=2, tab_count=3)
    assert ps.url == "https://example.com"
    assert ps.tab_id == 2


def test_selector_candidate():
    """SelectorCandidate 序列化/反序列化"""
    from zerotoken.models.operation import SelectorCandidate
    sc = SelectorCandidate(type="css", value="#btn", stability_score=0.9)
    d = sc.model_dump()
    assert d == {"type": "css", "value": "#btn", "stability_score": 0.9}
    sc2 = SelectorCandidate.model_validate(d)
    assert sc2.value == "#btn"


def test_operation_result_success():
    """OperationResult 成功场景"""
    from zerotoken.models.operation import OperationResult
    r = OperationResult(success=True, data={"navigated": True})
    assert r.success is True
    assert r.data["navigated"] is True
    assert r.error is None


def test_operation_result_failure():
    """OperationResult 失败场景"""
    from zerotoken.models.operation import OperationResult
    r = OperationResult(success=False, error="element not found")
    assert r.success is False
    assert r.error == "element not found"


def test_operation_record_full():
    """OperationRecord 完整构建和序列化"""
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult, SelectorCandidate
    )
    record = OperationRecord(
        step=1,
        action=ActionType.CLICK,
        params={"selector": "#btn"},
        result=OperationResult(success=True, data={"navigated": False}),
        page_state=PageState(url="https://example.com", title="Test"),
        screenshot="base64data",
        selector_candidates=[
            SelectorCandidate(type="css", value="#btn", stability_score=0.9)
        ],
    )
    d = record.model_dump()
    assert d["step"] == 1
    assert d["action"] == "click"
    assert d["result"]["success"] is True
    assert d["page_state"]["url"] == "https://example.com"
    assert d["screenshot"] == "base64data"
    assert len(d["selector_candidates"]) == 1


def test_operation_record_minimal():
    """OperationRecord 最小构建（无可选字段）"""
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult
    )
    record = OperationRecord(
        step=1,
        action=ActionType.OPEN,
        params={"url": "https://example.com"},
        result=OperationResult(success=True),
        page_state=PageState(),
    )
    d = record.model_dump()
    assert d["screenshot"] is None
    assert d["selector_candidates"] == []


def test_operation_record_json_roundtrip():
    """OperationRecord JSON 序列化 <-> 反序列化"""
    from zerotoken.models.operation import (
        OperationRecord, ActionType, PageState, OperationResult
    )
    record = OperationRecord(
        step=5,
        action=ActionType.INPUT,
        params={"selector": "#name", "text": "hello"},
        result=OperationResult(success=True, data={"actual_value": "hello"}),
        page_state=PageState(url="https://x.com", title="Form"),
    )
    json_str = record.model_dump_json()
    record2 = OperationRecord.model_validate_json(json_str)
    assert record2.step == 5
    assert record2.action == ActionType.INPUT
    assert record2.result.data["actual_value"] == "hello"
