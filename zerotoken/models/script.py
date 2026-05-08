"""脚本数据模型（支持嵌套流程控制）"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .operation import SelectorCandidate


class ScriptStep(BaseModel):
    """脚本步骤（可嵌套：if/loop 的 body 也是 ScriptStep 列表）"""

    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    selector_candidates: list[SelectorCandidate] = Field(default_factory=list)
    condition: Optional[str] = None
    body: list[ScriptStep] = Field(default_factory=list)
    else_body: list[ScriptStep] = Field(default_factory=list)
    assign_to: Optional[str] = None
    hint: Optional[str] = None


class Script(BaseModel):
    """完整脚本"""

    task_id: str
    goal: str
    steps: list[ScriptStep]
    params_schema: dict[str, Any] = Field(default_factory=dict)
    source_trajectory_id: Optional[int] = None


class StepHint(BaseModel):
    """步骤提示模板（可选，替代原 DFU）"""

    hint_id: str
    match_rules: list[dict[str, Any]]
    hint_text: str
