"""script_generator 单元测试：tab_id 变量化、setup 步骤处理"""
import pytest

from zerotoken.engine.script_generator import trajectory_to_script, _build_tab_id_mapping


def _make_trajectory(operations, task_id="test", goal="test goal"):
    return {"task_id": task_id, "goal": goal, "operations": operations}


class TestBuildTabIdMapping:
    """_build_tab_id_mapping 应能从轨迹操作中提取 new_tab 的 tab_id 映射"""

    def test_no_new_tab(self):
        ops = [{"action": "click", "params": {"selector": "#btn"}}]
        assert _build_tab_id_mapping(ops) == {}

    def test_single_new_tab(self):
        ops = [
            {"action": "new_tab", "params": {}, "result": {"data": {"tab_id": 3, "url": "about:blank"}}},
        ]
        mapping = _build_tab_id_mapping(ops)
        assert mapping == {3: "_new_tab_0"}

    def test_multiple_new_tabs(self):
        ops = [
            {"action": "new_tab", "params": {}, "result": {"data": {"tab_id": 3}}},
            {"action": "new_tab", "params": {}, "result": {"data": {"tab_id": 4}}},
            {"action": "new_tab", "params": {}, "result": {"data": {"tab_id": 5}}},
        ]
        mapping = _build_tab_id_mapping(ops)
        assert mapping == {3: "_new_tab_0", 4: "_new_tab_1", 5: "_new_tab_2"}


class TestTrajectoryToScriptTabMapping:
    """trajectory_to_script 应自动变量化 tab_id"""

    def test_new_tab_gets_assign_to(self):
        ops = [
            {"action": "new_tab", "params": {"url": "https://b.com"},
             "result": {"data": {"tab_id": 3, "url": "https://b.com"}}},
        ]
        script = trajectory_to_script(_make_trajectory(ops), prepend_init=False)
        new_tab_step = script["steps"][0]
        assert new_tab_step["assign_to"] == "_new_tab_0"

    def test_close_tab_uses_variable_reference(self):
        ops = [
            {"action": "new_tab", "params": {"url": "https://a.com"},
             "result": {"data": {"tab_id": 3}}},
            {"action": "close_tab", "params": {"tab_id": 3}},
        ]
        script = trajectory_to_script(_make_trajectory(ops), prepend_init=False)
        close_step = script["steps"][1]
        assert close_step["params"]["tab_id"] == "{{_new_tab_0.tab_id}}"

    def test_switch_tab_uses_variable_reference(self):
        ops = [
            {"action": "new_tab", "params": {},
             "result": {"data": {"tab_id": 5}}},
            {"action": "switch_tab", "params": {"tab_id": 5}},
        ]
        script = trajectory_to_script(_make_trajectory(ops), prepend_init=False)
        switch_step = script["steps"][1]
        assert switch_step["params"]["tab_id"] == "{{_new_tab_0.tab_id}}"

    def test_close_tab_without_matching_new_tab_keeps_literal(self):
        """close_tab 引用了不是由 new_tab 创建的 tab_id（如初始 tab 0），保持原值"""
        ops = [
            {"action": "close_tab", "params": {"tab_id": 0}},
        ]
        script = trajectory_to_script(_make_trajectory(ops), prepend_init=False)
        assert script["steps"][0]["params"]["tab_id"] == 0

    def test_multi_tab_end_to_end(self):
        """完整的多标签页录制 -> 脚本生成场景"""
        ops = [
            {"action": "open", "params": {"url": "https://main.com"}},
            {"action": "new_tab", "params": {"url": "https://a.com"},
             "result": {"data": {"tab_id": 1}}},
            {"action": "new_tab", "params": {"url": "https://b.com"},
             "result": {"data": {"tab_id": 2}}},
            {"action": "new_tab", "params": {"url": "https://c.com"},
             "result": {"data": {"tab_id": 3}}},
            {"action": "close_tab", "params": {"tab_id": 3}},
            {"action": "close_tab", "params": {"tab_id": 2}},
            {"action": "close_tab", "params": {"tab_id": 1}},
        ]
        script = trajectory_to_script(_make_trajectory(ops), prepend_init=False)
        steps = script["steps"]

        assert steps[1]["assign_to"] == "_new_tab_0"
        assert steps[2]["assign_to"] == "_new_tab_1"
        assert steps[3]["assign_to"] == "_new_tab_2"

        assert steps[4]["params"]["tab_id"] == "{{_new_tab_2.tab_id}}"
        assert steps[5]["params"]["tab_id"] == "{{_new_tab_1.tab_id}}"
        assert steps[6]["params"]["tab_id"] == "{{_new_tab_0.tab_id}}"


class TestPrependInit:
    """prepend_init 选项生成 setup 步骤（引擎会自动跳过）"""

    def test_prepend_init_true(self):
        script = trajectory_to_script(_make_trajectory([]), prepend_init=True)
        assert script["steps"][0]["action"] == "browser_init"
        assert script["steps"][1]["action"] == "trajectory_start"

    def test_prepend_init_false(self):
        script = trajectory_to_script(_make_trajectory([]), prepend_init=False)
        assert len(script["steps"]) == 0

    def test_prepend_init_stealth(self):
        script = trajectory_to_script(_make_trajectory([]), prepend_init=True, stealth=True)
        assert script["steps"][0]["params"]["stealth"] is True
