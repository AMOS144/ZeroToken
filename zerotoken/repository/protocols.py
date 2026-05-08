"""存储层协议定义（Protocol，非 ABC）"""

from __future__ import annotations

from typing import Any, Protocol


class ScriptRepo(Protocol):
    def script_save(
        self,
        task_id: str,
        *,
        goal: str,
        steps: list[dict[str, Any]],
        params_schema: dict[str, Any] | None = None,
        source_trajectory_id: int | None = None,
    ) -> None: ...

    def script_load(self, task_id: str) -> dict[str, Any] | None: ...

    def script_list(
        self,
        limit: int = 100,
        status: str = "active",
    ) -> list[dict[str, Any]]: ...

    def script_delete(self, task_id: str) -> dict[str, Any]: ...

    def health(self, task_id: str) -> dict[str, Any] | None: ...

    def record_run_result(
        self,
        task_id: str,
        terminal_status: str,
        session_id: str,
    ) -> dict[str, Any]: ...

    def deprecate(self, task_id: str, *, reason: str = "") -> dict[str, Any]: ...

    def restore(self, task_id: str) -> dict[str, Any]: ...


class TrajectoryRepo(Protocol):
    def trajectory_save(
        self,
        *,
        task_id: str,
        goal: str,
        operations: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> int: ...

    def trajectory_load(self, trajectory_id: int) -> dict[str, Any] | None: ...

    def trajectory_load_by_task_id(self, task_id: str) -> dict[str, Any] | None: ...

    def trajectory_list(
        self, limit: int = 100, since: float | None = None
    ) -> list[dict[str, Any]]: ...

    def trajectory_delete_by_task_id(self, task_id: str) -> int: ...


class SessionRepo(Protocol):
    def session_start(
        self,
        session_id: str,
        *,
        task_id: str | None = None,
        session_type: str = "replay",
    ) -> None: ...

    def session_append(
        self,
        session_id: str,
        *,
        step_index: int,
        action: str,
        selector: str | None = None,
        url: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None: ...

    def session_get(self, session_id: str) -> list[dict[str, Any]]: ...

    def session_list(self, limit: int = 100) -> list[dict[str, Any]]: ...


class RuntimeRepo(Protocol):
    def runtime_init(
        self,
        session_id: str,
        *,
        task_id: str | None,
        cursor_step_index: int,
        status: str,
        pause_event: dict[str, Any] | None = None,
        vars: dict[str, Any] | None = None,
    ) -> None: ...

    def runtime_get(self, session_id: str) -> dict[str, Any] | None: ...

    def runtime_update(self, session_id: str, **fields: Any) -> None: ...

    def find_paused_before(self, task_id: str, cutoff_iso: str) -> list[dict[str, Any]]: ...


class FingerprintRepo(Protocol):
    def fingerprint_save(
        self, domain: str, identifier: str, fingerprint_dict: dict[str, Any]
    ) -> None: ...

    def fingerprint_load(self, domain: str, identifier: str) -> dict[str, Any] | None: ...

    def fingerprint_delete(self, domain: str, identifier: str) -> bool: ...


class BindingRepo(Protocol):
    def binding_set(
        self,
        binding_key: str,
        *,
        script_task_id: str,
        description: str = "",
        default_vars: dict[str, Any] | None = None,
    ) -> None: ...

    def binding_get(self, binding_key: str) -> dict[str, Any] | None: ...

    def binding_list(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def binding_delete(self, binding_key: str) -> bool: ...
