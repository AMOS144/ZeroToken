"""ZeroToken - AI Agent browser automation MCP engine"""
try:
    from importlib.metadata import version

    __version__ = version("zerotoken")
except Exception:
    __version__ = "2.0.0-dev"

from zerotoken.models import (
    ActionType,
    PageState,
    SelectorCandidate,
    OperationResult,
    OperationRecord,
    Trajectory,
    TrajectoryMetadata,
    ScriptStep,
    Script,
    StepHint,
    PauseReason,
    PauseEvent,
    Resolution,
    RuntimeState,
)
from zerotoken.services import BrowserService, TrajectoryService, ScriptService

__all__ = [
    "__version__",
    "ActionType",
    "PageState",
    "SelectorCandidate",
    "OperationResult",
    "OperationRecord",
    "Trajectory",
    "TrajectoryMetadata",
    "ScriptStep",
    "Script",
    "StepHint",
    "PauseReason",
    "PauseEvent",
    "Resolution",
    "RuntimeState",
    "BrowserService",
    "TrajectoryService",
    "ScriptService",
]
