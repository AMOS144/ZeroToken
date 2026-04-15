"""变量环境：参数解析 + 安全表达式求值

VarsEnvironment 负责：
1. 变量存取 (get/set)
2. {{varname}} 占位符替换 (resolve_params)
3. 条件表达式安全求值 (eval_condition)
4. 赋值表达式安全求值 (eval_expr)
5. 快照 / 恢复 (snapshot)
"""
from __future__ import annotations

import ast
import copy
import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")

# 表达式中禁止出现的标识符（避免 open/__import__ 等绕过白名单）
_BLOCKED_IDENTIFIERS = frozenset(
    {
        "open",
        "eval",
        "exec",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
        "input",
        "breakpoint",
    }
)


class VarsEnvironment:
    """脚本执行中的变量环境"""

    def __init__(self, initial: dict[str, Any] | None = None):
        self._vars: dict[str, Any] = dict(initial) if initial else {}

    def get(self, name: str) -> Any:
        return self._vars.get(name)

    def set(self, name: str, value: Any) -> None:
        self._vars[name] = value

    def resolve_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """替换 dict 中所有字符串值里的 {{varname}}，缺失变量保留原文"""
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str):
                resolved[k] = self._resolve_string(v)
            else:
                resolved[k] = v
        return resolved

    def snapshot(self) -> dict[str, Any]:
        """深拷贝当前变量（用于持久化 / pause-resume）"""
        return copy.deepcopy(self._vars)

    def eval_condition(self, expr: str) -> bool:
        """安全求值条件表达式，返回 bool"""
        result = self._safe_eval(expr)
        return bool(result)

    def eval_expr(self, expr: str) -> Any:
        """安全求值赋值表达式，返回计算结果"""
        return self._safe_eval(expr)

    # ---- 内部方法 ----

    def _resolve_string(self, text: str) -> str:
        def _replacer(m: re.Match) -> str:
            name = m.group(1)
            val = self._vars.get(name)
            if val is None:
                return m.group(0)
            return str(val)

        return _PLACEHOLDER_RE.sub(_replacer, text)

    # 允许的内建函数白名单
    _SAFE_BUILTINS = {
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "len": len,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "sorted": sorted,
        "list": list,
        "True": True,
        "False": False,
        "None": None,
    }

    # 允许的 AST 节点类型白名单
    _ALLOWED_NODES = (
        ast.Expression,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.Call,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.Subscript,
        ast.Index,
        ast.Slice,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.Is,
        ast.IsNot,
        ast.USub,
        ast.UAdd,
        ast.Attribute,
        ast.IfExp,
    )

    def _safe_eval(self, expr: str) -> Any:
        """白名单 AST 解析 + 求值"""
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Expression syntax error: {e}") from e

        for node in ast.walk(tree):
            if not isinstance(node, self._ALLOWED_NODES):
                raise ValueError(
                    f"Expression node type {type(node).__name__} not allowed in: {expr}"
                )

        # 禁止双下划线名与危险内建名，避免仅靠运行期 NameError 掩盖风险
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if node.id.startswith("__"):
                    raise ValueError(
                        f"Expression name {node.id!r} not allowed in: {expr}"
                    )
                if node.id in _BLOCKED_IDENTIFIERS:
                    raise ValueError(
                        f"Expression name {node.id!r} not allowed in: {expr}"
                    )

        namespace = {**self._SAFE_BUILTINS, **self._vars}
        code = compile(tree, "<expr>", "eval")
        try:
            return eval(code, {"__builtins__": {}}, namespace)
        except Exception as e:
            raise ValueError(f"Expression eval error: {e}") from e
