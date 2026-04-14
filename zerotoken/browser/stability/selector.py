"""
Smart Selector - 智能选择器生成器
自动生成多个备选选择器，提高脚本稳定性
"""

import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class SelectorType(Enum):
    """选择器类型"""
    ID = "id"
    CSS = "css"
    XPATH = "xpath"
    TEST_ID = "test_id"
    ARIA = "aria"
    TEXT = "text"
    ROLE = "role"


@dataclass
class SelectorCandidate:
    """候选选择器"""
    type: SelectorType
    value: str
    stability_score: float  # 0-1，越高越稳定
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "value": self.value,
            "stability_score": self.stability_score,
            "description": self.description
        }


@dataclass
class SmartSelector:
    """智能选择器，包含多个候选"""
    primary: SelectorCandidate  # 首选选择器
    alternatives: List[SelectorCandidate]  # 备选选择器
    element_info: Dict[str, Any]  # 元素信息快照

    def best_selector(self) -> SelectorCandidate:
        """获取最佳选择器"""
        return self.primary

    def all_selectors(self) -> List[SelectorCandidate]:
        """获取所有选择器（按稳定性排序）"""
        all_selectors = [self.primary] + self.alternatives
        return sorted(all_selectors, key=lambda x: x.stability_score, reverse=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary": self.primary.to_dict(),
            "alternatives": [a.to_dict() for a in self.alternatives],
            "element_info": self.element_info
        }


class SmartSelectorGenerator:
    """
    智能选择器生成器

    为元素生成多个备选选择器，按稳定性排序。
    优先级：data-testid > id > aria > 稳定 CSS > XPath
    """

    # 稳定性评分权重
    STABILITY_WEIGHTS = {
        SelectorType.TEST_ID: 0.95,    # data-testid 最稳定
        SelectorType.ID: 0.90,         # id 次之
        SelectorType.ARIA: 0.85,       # ARIA 属性
        SelectorType.ROLE: 0.80,       # 角色选择器
        SelectorType.CSS: 0.70,        # CSS 选择器
        SelectorType.TEXT: 0.65,       # 文本选择器
        SelectorType.XPATH: 0.50,      # XPath 最不稳定
    }

    # 不稳定类名前缀（动态生成）
    UNSTABLE_PATTERNS = [
        r'^el-\d',              # Element UI
        r'^ant-.*-\d+$',        # Ant Design (e.g., ant-btn-primary-123)
        r'^Mui[A-Z]\w*(-\d+)?', # Material UI (e.g., MuiButton, MuiButton-123)
        r'^chakra-\w+(-\d+)?',  # Chakra UI
        r'^css-[a-z0-9]',       # CSS Modules
        r'^_[a-z0-9]{6}',       # 哈希类名
        r'^sc-\w+',             # Styled Components
        r'-\d{4,}$',            # 以大数字结尾的类名 (e.g., btn-1234)
    ]

    def __init__(self):
        self.unstable_regex = [re.compile(p) for p in self.UNSTABLE_PATTERNS]

    async def generate(self, element) -> SmartSelector:
        """
        为元素生成智能选择器

        Args:
            element: Playwright ElementHandle

        Returns:
            SmartSelector 包含多个候选选择器
        """
        candidates: List[SelectorCandidate] = []

        # 收集元素信息
        element_info = await self._collect_element_info(element)

        # 1. 尝试 data-testid
        test_id_selector = self._generate_test_id_selector(element_info)
        if test_id_selector:
            candidates.append(test_id_selector)

        # 2. 尝试 ID
        id_selector = self._generate_id_selector(element_info)
        if id_selector:
            candidates.append(id_selector)

        # 3. 尝试 ARIA 属性
        aria_selectors = self._generate_aria_selectors(element_info)
        candidates.extend(aria_selectors)

        # 4. 尝试 Role
        role_selector = self._generate_role_selector(element_info)
        if role_selector:
            candidates.append(role_selector)

        # 5. 生成 CSS 选择器
        css_selectors = await self._generate_css_selectors(element, element_info)
        candidates.extend(css_selectors)

        # 6. 生成文本选择器
        text_selector = self._generate_text_selector(element_info)
        if text_selector:
            candidates.append(text_selector)

        # 7. 生成 XPath 作为最后备选
        xpath_selector = await self._generate_xpath(element, element_info)
        if xpath_selector:
            candidates.append(xpath_selector)

        # 按稳定性排序
        candidates = sorted(candidates, key=lambda x: x.stability_score, reverse=True)

        if not candidates:
            raise ValueError("无法为元素生成任何选择器")

        return SmartSelector(
            primary=candidates[0],
            alternatives=candidates[1:],
            element_info=element_info
        )

    async def _collect_element_info(self, element) -> Dict[str, Any]:
        """收集元素信息用于生成选择器"""
        info = await element.evaluate("""el => {
            return {
                tag: el.tagName.toLowerCase(),
                id: el.id,
                className: el.className,
                text: el.textContent?.slice(0, 50)?.trim(),
                name: el.getAttribute('name'),
                placeholder: el.getAttribute('placeholder'),
                ariaLabel: el.getAttribute('aria-label'),
                ariaRole: el.getAttribute('role'),
                dataTestId: el.getAttribute('data-testid'),
                dataId: el.getAttribute('data-id'),
                type: el.getAttribute('type'),
                htmlFor: el.getAttribute('for'),
                parentClass: el.parentElement?.className,
                siblingText: Array.from(el.parentElement?.children || [])
                    .find(c => c !== el && c.textContent)?.textContent?.slice(0, 30)?.trim()
            };
        }""")
        return info

    def _generate_test_id_selector(self, info: Dict) -> Optional[SelectorCandidate]:
        """生成 data-testid 选择器"""
        test_id = info.get('dataTestId')
        if test_id:
            return SelectorCandidate(
                type=SelectorType.TEST_ID,
                value=f"[data-testid='{test_id}']",
                stability_score=self.STABILITY_WEIGHTS[SelectorType.TEST_ID],
                description=f"data-testid='{test_id}'"
            )

        data_id = info.get('dataId')
        if data_id:
            return SelectorCandidate(
                type=SelectorType.TEST_ID,
                value=f"[data-id='{data_id}']",
                stability_score=self.STABILITY_WEIGHTS[SelectorType.TEST_ID] - 0.05,
                description=f"data-id='{data_id}'"
            )

        return None

    def _generate_id_selector(self, info: Dict) -> Optional[SelectorCandidate]:
        """生成 ID 选择器"""
        element_id = info.get('id')
        if not element_id:
            return None

        # 检查 ID 是否稳定（不包含动态模式）
        if self._is_stable_identifier(element_id):
            return SelectorCandidate(
                type=SelectorType.ID,
                value=f"#{element_id}",
                stability_score=self.STABILITY_WEIGHTS[SelectorType.ID],
                description=f"id='{element_id}'"
            )

        return None

    def _generate_aria_selectors(self, info: Dict) -> List[SelectorCandidate]:
        """生成 ARIA 选择器"""
        selectors = []

        aria_label = info.get('ariaLabel')
        if aria_label:
            selectors.append(SelectorCandidate(
                type=SelectorType.ARIA,
                value=f"[aria-label='{aria_label}']",
                stability_score=self.STABILITY_WEIGHTS[SelectorType.ARIA],
                description=f"aria-label='{aria_label}'"
            ))

        return selectors

    def _generate_role_selector(self, info: Dict) -> Optional[SelectorCandidate]:
        """生成 Role 选择器"""
        role = info.get('ariaRole')
        if not role:
            return None

        # 常见角色映射
        role_map = {
            'button': 'button',
            'link': 'link',
            'checkbox': 'checkbox',
            'textbox': 'textbox',
            'combobox': 'combobox',
            'menu': 'menu',
            'menuitem': 'menuitem',
            'tab': 'tab',
            'dialog': 'dialog',
            'alert': 'alert',
        }

        role_name = role_map.get(role.lower())
        if role_name:
            return SelectorCandidate(
                type=SelectorType.ROLE,
                value=f"role={role_name}",
                stability_score=self.STABILITY_WEIGHTS[SelectorType.ROLE],
                description=f"role='{role}'"
            )

        return None

    async def _generate_css_selectors(self, element, info: Dict) -> List[SelectorCandidate]:
        """生成 CSS 选择器"""
        selectors = []
        tag = info.get('tag', '')

        # 1. tag + class
        class_name = info.get('className', '')
        if class_name:
            # 过滤不稳定类名
            stable_classes = self._filter_stable_classes(class_name)
            if stable_classes:
                selector = f"{tag}.{stable_classes[0]}"
                selectors.append(SelectorCandidate(
                    type=SelectorType.CSS,
                    value=selector,
                    stability_score=self.STABILITY_WEIGHTS[SelectorType.CSS] + 0.1,
                    description=f"CSS: {selector}"
                ))

        # 2. tag + attribute
        name_attr = info.get('name')
        if name_attr:
            selector = f"{tag}[name='{name_attr}']"
            selectors.append(SelectorCandidate(
                type=SelectorType.CSS,
                value=selector,
                stability_score=self.STABILITY_WEIGHTS[SelectorType.CSS] + 0.05,
                description=f"CSS: {selector}"
            ))

        # 3. tag + placeholder
        placeholder = info.get('placeholder')
        if placeholder:
            selector = f"{tag}[placeholder='{placeholder}']"
            selectors.append(SelectorCandidate(
                type=SelectorType.CSS,
                value=selector,
                stability_score=self.STABILITY_WEIGHTS[SelectorType.CSS],
                description=f"CSS: {selector}"
            ))

        # 4. 生成父级路径 CSS（更稳定）
        parent_css = await self._generate_parent_css(element, info)
        if parent_css:
            selectors.append(parent_css)

        return selectors

    def _generate_text_selector(self, info: Dict) -> Optional[SelectorCandidate]:
        """生成文本选择器"""
        text = info.get('text')
        if not text or len(text) < 3:
            return None

        # 使用完整文本或截断文本
        if len(text) > 30:
            text = text[:30]

        return SelectorCandidate(
            type=SelectorType.TEXT,
            value=text,
            stability_score=self.STABILITY_WEIGHTS[SelectorType.TEXT],
            description=f"text='{text}'"
        )

    async def _generate_xpath(self, element, info: Dict) -> Optional[SelectorCandidate]:
        """生成 XPath 选择器（最后备选）"""
        try:
            # 生成基于文本的 XPath
            text = info.get('text')
            tag = info.get('tag', '')

            if text:
                # 使用文本匹配
                selector = f"//{tag}[contains(normalize-space(), '{text[:20]}')]"
                return SelectorCandidate(
                    type=SelectorType.XPATH,
                    value=selector,
                    stability_score=self.STABILITY_WEIGHTS[SelectorType.XPATH] + 0.1,
                    description=f"XPath: {selector}"
                )

            # 生成绝对路径（最不稳定）
            selector = await element.evaluate("""el => {
                const parts = [];
                let current = el;
                while (current && current.nodeType === 1) {
                    let path = current.tagName.toLowerCase();
                    if (current.id) {
                        path = `${path}[@id='${current.id}']`;
                        parts.unshift(path);
                        break;
                    } else {
                        let sibling = current;
                        let nth = 1;
                        while (sibling.previousElementSibling) {
                            sibling = sibling.previousElementSibling;
                            if (sibling.tagName === current.tagName) nth++;
                        }
                        if (nth > 1) path += `[${nth}]`;
                    }
                    parts.unshift(path);
                    current = current.parentElement;
                }
                return '//' + parts.join('/');
            """)

            return SelectorCandidate(
                type=SelectorType.XPATH,
                value=selector,
                stability_score=self.STABILITY_WEIGHTS[SelectorType.XPATH],
                description=f"XPath: {selector}"
            )
        except:
            return None

    async def _generate_parent_css(self, element, info: Dict) -> Optional[SelectorCandidate]:
        """生成包含父级信息的 CSS 选择器"""
        try:
            parent_info = await element.evaluate("""el => {
                const parent = el.parentElement;
                if (!parent) return null;
                return {
                    tag: parent.tagName.toLowerCase(),
                    class: parent.className,
                    id: parent.id,
                    text: parent.textContent?.slice(0, 30)?.trim()
                };
            }""")

            if not parent_info:
                return None

            tag = info.get('tag', '')
            parent_tag = parent_info.get('tag', '')
            parent_text = parent_info.get('text', '')

            if parent_text:
                # 使用父级文本定位
                selector = f"{parent_tag}:has-text('{parent_text[:20]}') > {tag}"
                return SelectorCandidate(
                    type=SelectorType.CSS,
                    value=selector,
                    stability_score=self.STABILITY_WEIGHTS[SelectorType.CSS] + 0.15,
                    description=f"CSS (parent): {selector}"
                )

            return None
        except:
            return None

    def _is_stable_identifier(self, identifier: str) -> bool:
        """检查标识符是否稳定（非动态生成）"""
        if not identifier:
            return False

        # 检查是否匹配不稳定模式
        for pattern in self.unstable_regex:
            if pattern.match(identifier):
                return False

        return True

    def _filter_stable_classes(self, class_string: str) -> List[str]:
        """过滤出稳定的类名"""
        classes = class_string.split()
        stable = []

        for cls in classes:
            is_stable = True
            for pattern in self.unstable_regex:
                if pattern.match(cls):
                    is_stable = False
                    break
            if is_stable:
                stable.append(cls)

        return stable
