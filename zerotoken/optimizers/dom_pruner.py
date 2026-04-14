"""DOM 剪枝：将 HTML 压缩为便于 AI 阅读的语义骨架"""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

# 整段移除的标签（含子树）
_STRIP_TAGS = frozenset({"script", "style", "svg", "noscript", "link", "meta"})

# 仅忽略开始标签、无子树解析负担的 void（link/meta 在 strip 中单独处理）
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

_LIST_CONTAINERS = frozenset({"ul", "ol", "tbody", "select", "datalist"})
_ITEM_TAG = {"ul": "li", "ol": "li", "tbody": "tr", "select": "option", "datalist": "option"}

# 不稳定 class 前缀（与 CLAUDE.md 中 SmartSelector 描述一致）
_UNSTABLE_CLASS_PREFIXES = ("css-", "sc-", "el-", "ant-", "Mui-")


def _clean_class_value(value: str) -> str | None:
    """移除 CSS Module / 组件库等不稳定 class token，返回剩余或 None。"""
    parts = []
    for tok in value.split():
        t = tok.strip()
        if not t:
            continue
        if any(t.startswith(p) for p in _UNSTABLE_CLASS_PREFIXES):
            continue
        parts.append(t)
    return " ".join(parts) if parts else None


def _keep_attr(name: str) -> bool:
    n = name.lower()
    if n in ("style",):
        return False
    if n.startswith("data-v-"):
        return False
    if n.startswith("aria-") or n.startswith("data-testid") or n in ("data-test", "data-cy"):
        return True
    if n.startswith("data-") and n not in ("data-testid", "data-test", "data-cy"):
        return False
    return n in {
        "id",
        "name",
        "class",
        "role",
        "href",
        "src",
        "alt",
        "title",
        "type",
        "placeholder",
        "value",
        "action",
        "method",
        "for",
    }


def _format_attrs(attrs: list[tuple[str, str | None]]) -> str:
    """将过滤后的属性序列化为 HTML 属性串。"""
    parts: list[str] = []
    for name, val in attrs:
        n = name.lower()
        if not _keep_attr(n):
            continue
        if n == "class":
            cleaned = _clean_class_value(val or "")
            if not cleaned:
                continue
            parts.append(f'class="{escape(cleaned, quote=True)}"')
            continue
        if val is None:
            parts.append(n)
        else:
            parts.append(f'{n}="{escape(val, quote=True)}"')
    return (" " + " ".join(parts)) if parts else ""


class _DomPruner(HTMLParser):
    """单次扫描的 DOM 剪枝解析器。"""

    def __init__(self, *, max_list_items: int, max_depth: int) -> None:
        super().__init__(convert_charrefs=True)
        self._max_list_items = max_list_items
        self._max_depth = max_depth
        self._out: list[str] = []
        # 需整段跳过的标签栈（script/style/svg/noscript 等）
        self._strip_stack: list[str] = []
        # 超深折叠：跳过子树
        self._overflow_skip = 0
        # 列表项过多：跳过多余 li/tr/option 子树
        self._list_item_skip = 0
        # 文档结构栈（小写标签名）
        self._stack: list[str] = []
        # 列表容器状态栈
        self._list_stack: list[dict] = []

    def _in_skip_region(self) -> bool:
        return bool(self._strip_stack) or self._overflow_skip > 0 or self._list_item_skip > 0

    def _emit_ellipsis(self) -> None:
        self._out.append("[...]")

    def _fold_ws(self, data: str) -> str:
        """折叠空白为单个空格并去两端。"""
        s = re.sub(r"\s+", " ", data)
        return s.strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        # link/meta：不进入文档栈，整段忽略
        if t in ("link", "meta"):
            return

        if self._strip_stack:
            self._strip_stack.append(t)
            return

        if self._overflow_skip > 0:
            self._overflow_skip += 1
            return

        if self._list_item_skip > 0:
            self._list_item_skip += 1
            return

        if t in _STRIP_TAGS:
            self._strip_stack.append(t)
            return

        # 超深：当前栈深度即已打开祖先数；再嵌套则折叠
        if len(self._stack) >= self._max_depth:
            self._emit_ellipsis()
            self._overflow_skip = 1
            return

        # 列表项计数与截断
        if self._list_stack:
            ctx = self._list_stack[-1]
            container = ctx["tag"]
            item_tag = ctx["item_tag"]
            if t == item_tag and (len(self._stack) == 0 or self._stack[-1] == container):
                ctx["total"] = ctx.get("total", 0) + 1
                if ctx["total"] > self._max_list_items:
                    self._list_item_skip = 1
                    return

        if t in _LIST_CONTAINERS:
            self._list_stack.append(
                {
                    "tag": t,
                    "item_tag": _ITEM_TAG[t],
                    "total": 0,
                }
            )

        if t in _VOID_TAGS:
            attr_str = _format_attrs(attrs)
            self._out.append(f"<{t}{attr_str}>")
            return

        attr_str = _format_attrs(attrs)
        self._out.append(f"<{t}{attr_str}>")
        self._stack.append(t)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # 与 handle_starttag 对齐；void 已在 handle_starttag 处理
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._strip_stack:
            if self._strip_stack and self._strip_stack[-1] == t:
                self._strip_stack.pop()
            else:
                # 畸形 HTML：尽量弹栈
                while self._strip_stack and self._strip_stack[-1] != t:
                    self._strip_stack.pop()
                if self._strip_stack and self._strip_stack[-1] == t:
                    self._strip_stack.pop()
            return

        if self._overflow_skip > 0:
            self._overflow_skip -= 1
            return

        if self._list_item_skip > 0:
            self._list_item_skip -= 1
            return

        if t in _VOID_TAGS:
            return

        # 列表容器收尾：在闭合标签前写入「共 M 项」注释
        if self._list_stack and self._list_stack[-1]["tag"] == t:
            ctx = self._list_stack[-1]
            total = ctx.get("total", 0)
            if total > self._max_list_items:
                self._out.append(f"<!-- 共 {total} 项 -->")
            self._list_stack.pop()

        if self._stack and self._stack[-1] == t:
            self._stack.pop()
        elif t in self._stack:
            while self._stack and self._stack[-1] != t:
                self._stack.pop()
            if self._stack and self._stack[-1] == t:
                self._stack.pop()

        self._out.append(f"</{t}>")

    def handle_data(self, data: str) -> None:
        if self._in_skip_region():
            return
        folded = self._fold_ws(data)
        if not folded:
            return
        self._out.append(escape(folded))

    def handle_comment(self, data: str) -> None:
        if self._in_skip_region():
            return
        # 剪枝目标为骨架，丢弃注释以省 token（列表「共 M 项」在 handle_endtag 单独写入）


def prune_dom(html: str, *, max_list_items: int = 10, max_depth: int = 10) -> str:
    """将 HTML 剪枝为语义骨架字符串。"""
    parser = _DomPruner(max_list_items=max_list_items, max_depth=max_depth)
    parser.feed(html)
    parser.close()
    return "".join(parser._out)


__all__ = ["prune_dom"]
