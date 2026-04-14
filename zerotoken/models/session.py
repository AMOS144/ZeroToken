"""会话与运行时状态模型"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .operation import PageState, SelectorCandidate


class PauseReason(str, Enum):
    """暂停原因"""
    STEP_FAILED = "step_failed"
    PRE_STEP_HINT = "pre_step_hint"


def _default_allowed_resolutions() -> list[str]:
    """暂停后可用的默认仲裁动作（避免可变 list 默认参数）"""
    return ["retry", "patch_step", "skip", "abort"]


class PauseEvent(BaseModel):
    """暂停事件：包含 AI 仲裁所需的全部上下文"""
    reason: PauseReason
    session_id: str
    task_id: str
    step_index: int
    step_path: list[int | str] = Field(default_factory=list)
    action: str
    params: dict[str, Any]
    selector_candidates: list[SelectorCandidate] = Field(default_factory=list)
    error: Optional[str] = None
    page_state: Optional[PageState] = None
    screenshot: Optional[str] = None
    hint: Optional[str] = None
    allowed_resolutions: list[str] = Field(default_factory=_default_allowed_resolutions)


class Resolution(BaseModel):
    """AI 仲裁决议"""
    type: str
    patch: dict[str, Any] = Field(default_factory=dict)
    vars: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class RuntimeState(BaseModel):
    """脚本执行运行时状态（持久化到 DB，支持 pause/resume）"""
    session_id: str
    task_id: str
    cursor_step_index: int
    step_path: list[int | str] = Field(default_factory=list)
    status: str
    pause_event: Optional[PauseEvent] = None
    vars: dict[str, Any] = Field(default_factory=dict)
