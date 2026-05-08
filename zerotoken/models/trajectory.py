"""轨迹数据模型"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .operation import OperationRecord


class TrajectoryMetadata(BaseModel):
    """轨迹统计元数据"""

    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    duration_seconds: Optional[float] = None


class Trajectory(BaseModel):
    """完整的操作轨迹"""

    task_id: str
    goal: str
    operations: list[OperationRecord] = Field(default_factory=list)
    metadata: TrajectoryMetadata = Field(default_factory=TrajectoryMetadata)
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def add_operation(self, record: OperationRecord) -> None:
        """添加一条操作记录，自动更新统计"""
        self.operations.append(record)
        self.metadata.total_steps = len(self.operations)
        if record.result.success:
            self.metadata.successful_steps += 1
        else:
            self.metadata.failed_steps += 1

    def complete(self) -> None:
        """标记轨迹完成"""
        self.end_time = datetime.now()
        if self.start_time and self.end_time:
            self.metadata.duration_seconds = (self.end_time - self.start_time).total_seconds()

    def to_ai_prompt(self) -> str:
        """导出 AI 友好的文本格式"""
        lines = [f"Task Goal: {self.goal}", "", "Operation History:"]
        for op in self.operations:
            param_str = ", ".join(f"{k}={repr(v)}" for k, v in op.params.items())
            lines.append(f"[Step {op.step}] {op.action.value}({param_str})")
        return "\n".join(lines)
