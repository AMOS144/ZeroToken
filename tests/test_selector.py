"""
SmartSelector 测试

按照 TDD 流程，先编写测试，再实现功能。
"""

import pytest
from unittest.mock import AsyncMock

from zerotoken.selector import (
    SelectorType,
    SelectorCandidate,
    SmartSelector,
    SmartSelectorGenerator,
)


class TestSelectorCandidate:
    """测试 SelectorCandidate 类"""

    def test_create_candidate(self):
        """测试创建候选选择器"""
        candidate = SelectorCandidate(
            type=SelectorType.ID, value="#my-id", stability_score=0.9, description="id='my-id'"
        )

        assert candidate.type == SelectorType.ID
        assert candidate.value == "#my-id"
        assert candidate.stability_score == 0.9
        assert candidate.description == "id='my-id'"

    def test_candidate_to_dict(self):
        """测试转换为字典"""
        candidate = SelectorCandidate(
            type=SelectorType.CSS, value=".btn-primary", stability_score=0.7
        )

        result = candidate.to_dict()

        assert result == {
            "type": "css",
            "value": ".btn-primary",
            "stability_score": 0.7,
            "description": "",
        }


class TestSmartSelector:
    """测试 SmartSelector 类"""

    def test_create_smart_selector(self):
        """测试创建智能选择器"""
        primary = SelectorCandidate(
            type=SelectorType.TEST_ID, value="[data-testid='submit-btn']", stability_score=0.95
        )
        alternatives = [
            SelectorCandidate(type=SelectorType.CSS, value="button.submit", stability_score=0.7)
        ]

        smart_selector = SmartSelector(
            primary=primary,
            alternatives=alternatives,
            element_info={"tag": "button", "text": "Submit"},
        )

        assert smart_selector.primary == primary
        assert len(smart_selector.alternatives) == 1

    def test_best_selector(self):
        """测试获取最佳选择器"""
        primary = SelectorCandidate(type=SelectorType.ID, value="#submit", stability_score=0.9)
        smart_selector = SmartSelector(primary=primary, alternatives=[], element_info={})

        best = smart_selector.best_selector()

        assert best == primary
        assert best.stability_score == 0.9

    def test_all_selectors_sorted(self):
        """测试获取所有选择器（按稳定性排序）"""
        primary = SelectorCandidate(type=SelectorType.ID, value="#submit", stability_score=0.9)
        alternatives = [
            SelectorCandidate(type=SelectorType.CSS, value="button.submit", stability_score=0.7),
            SelectorCandidate(type=SelectorType.XPATH, value="//button", stability_score=0.5),
        ]

        smart_selector = SmartSelector(primary=primary, alternatives=alternatives, element_info={})

        all_selectors = smart_selector.all_selectors()

        # 应该按稳定性降序排列
        assert len(all_selectors) == 3
        assert all_selectors[0].stability_score == 0.9
        assert all_selectors[1].stability_score == 0.7
        assert all_selectors[2].stability_score == 0.5

    def test_smart_selector_to_dict(self):
        """测试转换为字典"""
        primary = SelectorCandidate(type=SelectorType.ID, value="#submit", stability_score=0.9)
        smart_selector = SmartSelector(
            primary=primary, alternatives=[], element_info={"tag": "button"}
        )

        result = smart_selector.to_dict()

        assert "primary" in result
        assert "alternatives" in result
        assert "element_info" in result
        assert result["element_info"]["tag"] == "button"


class TestSmartSelectorGenerator:
    """测试 SmartSelectorGenerator 类"""

    def test_create_generator(self):
        """测试创建生成器"""
        generator = SmartSelectorGenerator()
        assert generator is not None

    def test_stability_weights(self):
        """测试稳定性权重"""
        generator = SmartSelectorGenerator()

        # TEST_ID 应该最高
        assert generator.STABILITY_WEIGHTS[SelectorType.TEST_ID] == 0.95
        # ID 次之
        assert generator.STABILITY_WEIGHTS[SelectorType.ID] == 0.90
        # XPATH 应该最低
        assert generator.STABILITY_WEIGHTS[SelectorType.XPATH] == 0.50

    def test_is_stable_identifier(self):
        """测试稳定标识符检测"""
        generator = SmartSelectorGenerator()

        # 稳定的 ID
        assert generator._is_stable_identifier("submit-btn") is True
        assert generator._is_stable_identifier("login-form") is True

        # 不稳定的 ID（动态生成）
        assert generator._is_stable_identifier("el-12345") is False
        assert generator._is_stable_identifier("ant-btn-primary-123") is False
        assert generator._is_stable_identifier("MuiButton-123") is False

    def test_filter_stable_classes(self):
        """测试过滤稳定类名"""
        generator = SmartSelectorGenerator()

        # 混合稳定和 unstable 类名
        classes = "btn btn-primary el-12345 custom-class MuiButton-abc"
        stable = generator._filter_stable_classes(classes)

        assert "btn" in stable
        assert "btn-primary" in stable
        assert "custom-class" in stable
        assert "el-12345" not in stable
        assert "MuiButton-abc" not in stable  # MuiButton 开头的会被过滤

    def test_generate_test_id_selector(self):
        """测试生成 data-testid 选择器"""
        generator = SmartSelectorGenerator()

        # 有 data-testid
        info = {"dataTestId": "submit-btn"}
        selector = generator._generate_test_id_selector(info)

        assert selector is not None
        assert selector.type == SelectorType.TEST_ID
        assert selector.value == "[data-testid='submit-btn']"
        assert selector.stability_score == 0.95

        # 没有 data-testid
        info = {}
        selector = generator._generate_test_id_selector(info)
        assert selector is None

    def test_generate_id_selector(self):
        """测试生成 ID 选择器"""
        generator = SmartSelectorGenerator()

        # 有稳定 ID
        info = {"id": "submit-btn"}
        selector = generator._generate_id_selector(info)

        assert selector is not None
        assert selector.type == SelectorType.ID
        assert selector.value == "#submit-btn"
        assert selector.stability_score == 0.90

        # 有不稳定 ID
        info = {"id": "el-12345"}
        selector = generator._generate_id_selector(info)
        assert selector is None

    def test_generate_aria_selectors(self):
        """测试生成 ARIA 选择器"""
        generator = SmartSelectorGenerator()

        info = {"ariaLabel": "Submit form"}
        selectors = generator._generate_aria_selectors(info)

        assert len(selectors) == 1
        assert selectors[0].type == SelectorType.ARIA
        assert "[aria-label='Submit form']" in selectors[0].value

    def test_generate_text_selector(self):
        """测试生成文本选择器"""
        generator = SmartSelectorGenerator()

        # 有足够的文本
        info = {"text": "Click me to submit the form"}
        selector = generator._generate_text_selector(info)

        assert selector is not None
        assert selector.type == SelectorType.TEXT
        assert len(selector.value) <= 30  # 应该被截断

        # 文本太短
        info = {"text": "Hi"}
        selector = generator._generate_text_selector(info)
        assert selector is None

    @pytest.mark.asyncio
    async def test_generate_css_selectors(self):
        """测试生成 CSS 选择器"""
        generator = SmartSelectorGenerator()

        # 模拟 element
        mock_element = AsyncMock()

        info = {
            "tag": "button",
            "className": "btn btn-primary el-123",
            "placeholder": "Enter name",
            "name": "username",
        }

        selectors = await generator._generate_css_selectors(mock_element, info)

        # 应该生成多个 CSS 选择器
        assert len(selectors) > 0

        # 检查选择器类型
        for selector in selectors:
            assert selector.type == SelectorType.CSS

    @pytest.mark.asyncio
    async def test_generate_xpath(self):
        """测试生成 XPath 选择器"""
        generator = SmartSelectorGenerator()

        mock_element = AsyncMock()
        info = {"tag": "button", "text": "Submit"}

        selector = await generator._generate_xpath(mock_element, info)

        assert selector is not None
        assert selector.type == SelectorType.XPATH

    @pytest.mark.asyncio
    async def test_generate_full_selector(self):
        """测试完整的选择器生成流程"""
        generator = SmartSelectorGenerator()

        # 模拟 element
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(
            return_value={
                "tag": "button",
                "id": "submit-btn",
                "className": "btn btn-primary",
                "text": "Submit",
                "dataTestId": None,
                "ariaLabel": None,
                "ariaRole": "button",
                "name": None,
                "placeholder": None,
            }
        )

        smart_selector = await generator.generate(mock_element)

        assert smart_selector is not None
        assert smart_selector.primary is not None
        assert smart_selector.primary.stability_score > 0.5


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
