"""StabilityMiddleware 单元测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_locate_direct_success():
    """选择器直接命中时返回 element + candidates"""
    from zerotoken.browser.stability.middleware import StabilityMiddleware

    mock_page = AsyncMock()
    mock_element = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

    mw = StabilityMiddleware(selector_gen=None, adaptive_storage=None)
    element, candidates = await mw.locate(
        mock_page, "#btn",
        auto_save=False, adaptive=False, identifier=None,
    )
    assert element == mock_element


@pytest.mark.asyncio
async def test_locate_failure_no_adaptive():
    """选择器失败且 adaptive=False 时抛异常"""
    from zerotoken.browser.stability.middleware import StabilityMiddleware

    mock_page = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=Exception("not found"))

    mw = StabilityMiddleware(selector_gen=None, adaptive_storage=None)
    with pytest.raises(Exception, match="not found"):
        await mw.locate(
            mock_page, "#btn",
            auto_save=False, adaptive=False, identifier=None,
        )


@pytest.mark.asyncio
async def test_locate_with_selector_gen():
    """有 selector_gen 时应返回 candidates 列表"""
    from zerotoken.browser.stability.middleware import StabilityMiddleware

    mock_page = AsyncMock()
    mock_element = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

    # 构造 mock selector_gen
    mock_candidate = MagicMock()
    mock_candidate.type = MagicMock()
    mock_candidate.type.value = "id"
    mock_candidate.value = "#btn"
    mock_candidate.stability_score = 0.9

    mock_smart = MagicMock()
    mock_smart.all_selectors.return_value = [mock_candidate]

    mock_gen = AsyncMock()
    mock_gen.generate = AsyncMock(return_value=mock_smart)

    mw = StabilityMiddleware(selector_gen=mock_gen, adaptive_storage=None)
    element, candidates = await mw.locate(
        mock_page, "#btn",
        auto_save=False, adaptive=False, identifier=None,
    )
    assert element == mock_element
    assert len(candidates) == 1
    assert candidates[0]["type"] == "id"
    assert candidates[0]["stability_score"] == 0.9


@pytest.mark.asyncio
async def test_locate_adaptive_fallback():
    """选择器失败 + adaptive=True 时用指纹重定位"""
    from zerotoken.browser.stability.middleware import StabilityMiddleware

    mock_page = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=Exception("not found"))
    mock_page.url = "https://example.com/page"

    mock_relocated = AsyncMock()

    mock_storage = MagicMock()

    # 需要 mock adaptive 模块的 relocate 函数
    import unittest.mock as um
    with um.patch(
        "zerotoken.browser.stability.middleware.relocate",
        new_callable=AsyncMock,
        return_value=mock_relocated,
    ), um.patch(
        "zerotoken.browser.stability.middleware._domain_from_url",
        return_value="example.com",
    ):
        mw = StabilityMiddleware(selector_gen=None, adaptive_storage=mock_storage)
        element, candidates = await mw.locate(
            mock_page, "#btn",
            auto_save=False, adaptive=True, identifier="my_btn",
        )
        assert element == mock_relocated


@pytest.mark.asyncio
async def test_locate_auto_save():
    """auto_save=True 时应保存指纹"""
    from zerotoken.browser.stability.middleware import StabilityMiddleware

    mock_page = AsyncMock()
    mock_page.url = "https://example.com/page"
    mock_element = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

    mock_storage = MagicMock()
    mock_storage.fingerprint_save = MagicMock()

    mock_fp = {"self": {"tag": "button"}, "parent": {"tag": "div"}}

    import unittest.mock as um
    with um.patch(
        "zerotoken.browser.stability.middleware.extract_fingerprint",
        new_callable=AsyncMock,
        return_value=mock_fp,
    ), um.patch(
        "zerotoken.browser.stability.middleware._domain_from_url",
        return_value="example.com",
    ):
        mw = StabilityMiddleware(selector_gen=None, adaptive_storage=mock_storage)
        element, _ = await mw.locate(
            mock_page, "#btn",
            auto_save=True, adaptive=False, identifier="my_btn",
        )
        assert element == mock_element
        mock_storage.fingerprint_save.assert_called_once_with(
            "example.com", "my_btn", mock_fp,
        )
