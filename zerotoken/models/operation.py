"""浏览器操作的核心数据模型"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """所有支持的浏览器动作类型"""

    OPEN = "open"
    CLICK = "click"
    INPUT = "input"
    GET_TEXT = "get_text"
    GET_HTML = "get_html"
    SCREENSHOT = "screenshot"
    WAIT_FOR = "wait_for"
    EXTRACT_DATA = "extract_data"
    HOVER = "hover"
    KEYBOARD = "keyboard"
    RIGHT_CLICK = "right_click"
    DOUBLE_CLICK = "double_click"
    DRAG_DROP = "drag_drop"
    SCROLL = "scroll"
    NEW_TAB = "new_tab"
    SWITCH_TAB = "switch_tab"
    CLOSE_TAB = "close_tab"
    LIST_TABS = "list_tabs"
    ENTER_IFRAME = "enter_iframe"
    EXIT_IFRAME = "exit_iframe"
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    EVALUATE = "evaluate"
    TYPE_TEXT = "type_text"


class PageState(BaseModel):
    """页面状态快照"""

    url: str = ""
    title: str = ""
    tab_id: int = 0
    tab_count: int = 1
    timestamp: datetime = Field(default_factory=datetime.now)


class SelectorCandidate(BaseModel):
    """备选选择器（含稳定性评分）"""

    type: str
    value: str
    stability_score: float = 0.0


class OperationResult(BaseModel):
    """操作执行结果"""

    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class OperationRecord(BaseModel):
    """一次浏览器操作的完整记录"""

    step: int
    action: ActionType
    params: dict[str, Any] = Field(default_factory=dict)
    result: OperationResult
    page_state: PageState
    screenshot: Optional[str] = None
    selector_candidates: list[SelectorCandidate] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
