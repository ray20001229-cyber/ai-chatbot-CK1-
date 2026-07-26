import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    ANGRY = "angry"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MemoryStatus(StrEnum):
    PENDING = "pending"
    DEFERRED = "deferred"
    COMPLETED = "completed"


class AnalyzeRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=50_000)
    conversation_id: str = Field(default="default", min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_blank_transcript(self) -> "AnalyzeRequest":
        if not self.transcript.strip():
            raise ValueError("聊天记录不能为空")
        return self


class AnalysisResult(BaseModel):
    customer_intent: str = Field(description="客户的核心意图")
    has_task: bool = Field(description="是否存在需要跟进或记录的任务")
    task_title: str | None = Field(
        default=None, description="简短明确的任务标题；无任务时为 null"
    )
    task_status: TaskStatus | None = Field(
        default=None, description="任务状态；无任务时为 null"
    )
    priority: Priority | None = Field(
        default=None, description="任务优先级；无任务时为 null"
    )
    due_at: datetime | None = Field(
        default=None, description="ISO 8601 截止时间；未提及时为 null"
    )
    customer_sentiment: Sentiment
    risk_level: RiskLevel
    suggested_reply: str = Field(description="可直接参考的客服回复")
    should_remember: bool = Field(
        default=False, description="是否应把未完成或延期事项保存为会话记忆"
    )
    memory_summary: str | None = Field(
        default=None, description="供之后召回的简短事项摘要"
    )
    memory_status: MemoryStatus | None = Field(
        default=None, description="待处理或已延期；不保存记忆时为 null"
    )
    resume_at: datetime | None = Field(
        default=None, description="延期事项恢复处理时间；未明确时为 null"
    )

    @model_validator(mode="after")
    def validate_task_fields(self) -> "AnalysisResult":
        required = (self.task_title, self.task_status, self.priority)
        if self.has_task and any(value is None for value in required):
            raise ValueError("存在任务时，标题、状态和优先级不能为空")
        if not self.has_task:
            self.task_title = None
            self.task_status = None
            self.priority = None
            self.due_at = None
        if self.should_remember:
            if not self.has_task:
                raise ValueError("只有任务事项才能保存为记忆")
            if not self.memory_summary or self.memory_status is None:
                raise ValueError("保存记忆时，摘要和记忆状态不能为空")
            if self.memory_status == MemoryStatus.COMPLETED:
                raise ValueError("新记忆不能直接标记为已完成")
        else:
            self.memory_summary = None
            self.memory_status = None
            self.resume_at = None
        return self


class TaskConfirmRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=50_000)
    conversation_id: str = Field(default="default", min_length=1, max_length=100)
    analysis: AnalysisResult


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: str
    source_transcript: str
    customer_intent: str
    title: str
    status: TaskStatus
    priority: Priority
    due_at: datetime | None
    customer_sentiment: Sentiment
    risk_level: RiskLevel
    suggested_reply: str
    created_at: datetime


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: str
    task_id: uuid.UUID | None
    summary: str
    details: str
    status: MemoryStatus
    resume_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MemoryUpdate(BaseModel):
    status: MemoryStatus
    resume_at: datetime | None = None
