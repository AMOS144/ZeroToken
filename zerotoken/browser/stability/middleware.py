"""统一稳定性中间件：智能选择器 + 自适应定位 + 错误恢复"""

from __future__ import annotations

from typing import Any

from .adaptive import extract_fingerprint, relocate, _domain_from_url


class StabilityMiddleware:
    """统一封装定位流程：直接定位 -> 自适应重定位 -> 指纹保存"""

    def __init__(
        self,
        selector_gen: Any = None,
        adaptive_storage: Any = None,
        timeout: int = 30000,
    ):
        self.selector_gen = selector_gen
        self.adaptive_storage = adaptive_storage
        self.timeout = timeout

    async def locate(
        self,
        page: Any,
        selector: str,
        *,
        auto_save: bool = False,
        adaptive: bool = False,
        identifier: str | None = None,
    ) -> tuple[Any, list[dict[str, Any]]]:
        """
        统一定位流程:
        1. 直接用 selector 定位
        2. 失败 + adaptive=True 时用指纹重定位
        3. 成功时生成 selector_candidates
        4. auto_save=True 时保存指纹
        返回 (element, selector_candidates)
        """
        ident = identifier or selector
        candidates: list[dict[str, Any]] = []

        try:
            element = await page.wait_for_selector(selector, timeout=self.timeout)

            # 成功定位后，用 selector_gen 生成备选选择器
            if element and self.selector_gen:
                try:
                    smart = await self.selector_gen.generate(element)
                    candidates = [
                        {
                            "type": c.type.value,
                            "value": c.value,
                            "stability_score": c.stability_score,
                        }
                        for c in smart.all_selectors()
                    ]
                except Exception:
                    pass

            # auto_save 时保存元素指纹到存储
            if element and auto_save and self.adaptive_storage:
                try:
                    fp = await extract_fingerprint(element, page)
                    if fp:
                        domain = _domain_from_url(page.url)
                        self.adaptive_storage.fingerprint_save(domain, ident, fp)
                except Exception:
                    pass

            return element, candidates

        except Exception:
            # 选择器失败时，若启用 adaptive 则尝试指纹重定位
            if adaptive and self.adaptive_storage:
                try:
                    domain = _domain_from_url(page.url)
                    handle = await relocate(page, domain, ident, self.adaptive_storage)
                    if handle:
                        return handle, candidates
                except Exception:
                    pass
            raise
