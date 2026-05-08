"""
Test fuzzy_point - OperationRecord and trajectory fuzzy point support.
"""

from zerotoken.controller import OperationRecord, PageState


class TestOperationRecordFuzzyPoint:
    """Test OperationRecord fuzzy_point field."""

    def test_operation_record_with_fuzzy_point(self):
        """Test creating OperationRecord with fuzzy_point."""
        ps = PageState("https://a.com", "Title")
        record = OperationRecord(
            step=1,
            action="extract_data",
            params={},
            result={"success": True},
            page_state=ps,
            fuzzy_point={"requires_judgment": True, "reason": "验证码需识别"},
        )
        d = record.to_dict()
        assert d["fuzzy_point"]["requires_judgment"] is True
        assert d["fuzzy_point"]["reason"] == "验证码需识别"

    def test_operation_record_with_fuzzy_point_and_hint(self):
        """Test fuzzy_point with hint field."""
        ps = PageState("https://a.com", "Title")
        record = OperationRecord(
            step=1,
            action="extract_data",
            params={},
            result={},
            page_state=ps,
            fuzzy_point={
                "requires_judgment": True,
                "reason": "列表项需选择",
                "hint": "根据用户意图选择第一项",
            },
        )
        d = record.to_dict()
        assert d["fuzzy_point"]["hint"] == "根据用户意图选择第一项"

    def test_operation_record_without_fuzzy_point(self):
        """Test OperationRecord without fuzzy_point omits it from dict."""
        ps = PageState("https://a.com", "Title")
        record = OperationRecord(
            step=1,
            action="click",
            params={"selector": "#btn"},
            result={"success": True},
            page_state=ps,
        )
        d = record.to_dict()
        assert "fuzzy_point" not in d

    def test_extract_data_fuzzy_reason_override(self):
        """Test extract_data with fuzzy_reason override (via controller)."""
        from unittest.mock import AsyncMock, MagicMock
        from zerotoken.controller import BrowserController

        BrowserController._instance = None
        controller = MagicMock(spec=BrowserController)
        controller._step_counter = 0
        controller._operation_history = []
        controller._config = {}
        controller._page = AsyncMock()
        controller._page.url = "https://example.com"
        controller._page.title = AsyncMock(return_value="Example")
        controller._page.screenshot = AsyncMock(return_value=b"x")
        mock_el = AsyncMock()
        mock_el.text_content = AsyncMock(return_value="test")
        controller._page.wait_for_selector = AsyncMock(return_value=mock_el)
        controller._get_page_state = AsyncMock(return_value=PageState("https://a.com", "Title"))
        controller._take_screenshot = AsyncMock(return_value=None)
        controller._next_step = lambda: 1

        import asyncio
        from zerotoken.controller import BrowserController as BC

        real_extract = BC.extract_data.__get__(controller, BC)
        record = asyncio.run(
            real_extract(
                controller,
                {"fields": [{"name": "t", "selector": "h1", "type": "text"}]},
                fuzzy_reason="验证码需识别",
            )
        )
        assert record.fuzzy_point["reason"] == "验证码需识别"
