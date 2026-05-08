"""
Storage interfaces for ZeroToken: scripts, trajectories, sessions.
MCP and Engine depend on these abstractions; implementation is SQLite by default.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

_RUNTIME_UNSET = object()


class ScriptStore(ABC):
    """Abstract script storage."""

    @abstractmethod
    def script_save(
        self,
        task_id: str,
        *,
        goal: str,
        steps: List[Dict[str, Any]],
        params_schema: Optional[Dict[str, Any]] = None,
        source_trajectory_id: Optional[int] = None,
    ) -> None:
        """Save or overwrite script by task_id."""
        ...

    @abstractmethod
    def script_load(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load script by task_id. Returns None if not found."""
        ...

    @abstractmethod
    def script_list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List scripts (task_id, goal, created_at)."""
        ...

    @abstractmethod
    def script_delete(self, task_id: str) -> bool:
        """Delete script. Returns True if deleted."""
        ...


class TrajectoryStore(ABC):
    """Abstract trajectory storage."""

    @abstractmethod
    def trajectory_save(
        self,
        *,
        task_id: str,
        goal: str,
        operations: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Save trajectory. Returns id."""
        ...

    @abstractmethod
    def trajectory_load(self, trajectory_id: int) -> Optional[Dict[str, Any]]:
        """Load trajectory by id. Returns None if not found."""
        ...

    @abstractmethod
    def trajectory_list(
        self, limit: int = 100, since: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """List trajectories (id, task_id, goal, created_at). since: Unix timestamp, only return created_at >= since."""
        ...

    @abstractmethod
    def trajectory_delete(self, trajectory_id: int) -> bool:
        """Delete trajectory. Returns True if deleted."""
        ...

    @abstractmethod
    def trajectory_load_by_task_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load latest trajectory with given task_id. Returns None if not found."""
        ...

    @abstractmethod
    def trajectory_delete_by_task_id(self, task_id: str) -> int:
        """Delete all trajectories with given task_id. Returns number deleted."""
        ...


class SessionStore(ABC):
    """Abstract session/trace storage."""

    @abstractmethod
    def session_start(
        self,
        session_id: str,
        *,
        task_id: Optional[str] = None,
        session_type: str = "replay",
    ) -> None:
        """Start a new session (create placeholder or first row)."""
        ...

    @abstractmethod
    def session_append(
        self,
        session_id: str,
        *,
        step_index: int,
        action: str,
        selector: Optional[str] = None,
        url: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append a step to the session."""
        ...

    @abstractmethod
    def session_get(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all steps for session_id, ordered by step_index."""
        ...

    @abstractmethod
    def session_list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List sessions (session_id, task_id, type, created_at)."""
        ...


class DFUStore(ABC):
    """Abstract DFU (Dynamic Fuzzy Unit) storage."""

    @abstractmethod
    def dfu_save(
        self,
        dfu_id: str,
        *,
        name: str,
        description: str = "",
        triggers: List[Dict[str, Any]],
        prompt: str = "",
        allowed_resolutions: Optional[List[str]] = None,
    ) -> None:
        """Save or overwrite a DFU by dfu_id."""
        ...

    @abstractmethod
    def dfu_load(self, dfu_id: str) -> Optional[Dict[str, Any]]:
        """Load DFU by dfu_id. Returns None if not found."""
        ...

    @abstractmethod
    def dfu_list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List DFUs (dfu_id, name, updated_at)."""
        ...

    @abstractmethod
    def dfu_delete(self, dfu_id: str) -> bool:
        """Delete DFU. Returns True if deleted."""
        ...


class SessionRuntimeStore(ABC):
    """Abstract runtime state store for pause/resume."""

    @abstractmethod
    def runtime_init(
        self,
        session_id: str,
        *,
        task_id: Optional[str],
        cursor_step_index: int,
        status: str,
        pause_event: Optional[Dict[str, Any]] = None,
        vars: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize runtime state for a session."""
        ...

    @abstractmethod
    def runtime_get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get runtime state for a session. Returns None if missing."""
        ...

    @abstractmethod
    def runtime_update(
        self,
        session_id: str,
        *,
        cursor_step_index: Optional[int] = None,
        status: Optional[str] = None,
        pause_event: Any = _RUNTIME_UNSET,
        vars: Any = _RUNTIME_UNSET,
    ) -> None:
        """Update runtime state fields for a session."""
        ...


class AdaptiveStore(ABC):
    """Abstract store for element fingerprints (domain, identifier) for adaptive relocation."""

    @abstractmethod
    def fingerprint_save(
        self, domain: str, identifier: str, fingerprint_dict: Dict[str, Any]
    ) -> None:
        """Save or overwrite fingerprint for (domain, identifier)."""
        ...

    @abstractmethod
    def fingerprint_load(self, domain: str, identifier: str) -> Optional[Dict[str, Any]]:
        """Load fingerprint for (domain, identifier). Returns None if not found."""
        ...

    @abstractmethod
    def fingerprint_delete(self, domain: str, identifier: str) -> bool:
        """Remove fingerprint. Returns True if a row was deleted."""
        ...


class ScriptBindingStore(ABC):
    """Abstract store for binding external job_ids to script task_ids."""

    @abstractmethod
    def script_binding_set(
        self,
        binding_key: str,
        *,
        script_task_id: str,
        description: str = "",
        default_vars: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create or update a binding from binding_key (e.g. OpenClaw job_id) to script_task_id."""
        ...

    @abstractmethod
    def script_binding_get(self, binding_key: str) -> Optional[Dict[str, Any]]:
        """Get binding by binding_key. Returns None if not found."""
        ...

    @abstractmethod
    def script_binding_list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List bindings (binding_key, script_task_id, description)."""
        ...

    @abstractmethod
    def script_binding_delete(self, binding_key: str) -> bool:
        """Delete binding. Returns True if deleted."""
        ...
