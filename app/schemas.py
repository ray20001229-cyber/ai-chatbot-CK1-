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


class HandoffStatus(StrEnum):
    BOT = "bot"
    PENDING = "pending"
    HUMAN = "human"


class MemoryStatus(StrEnum):
    PENDING = "pending"
    DEFERRED = "deferred"
    COMPLETED = "completed"


class ReminderStatus(StrEnum):
    ACTIVE = "active"
    DISMISSED = "dismissed"


class CalendarTimeBasis(StrEnum):
    EXACT = "exact"
    INFERRED = "inferred"
    SUGGESTED = "suggested"


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
    should_schedule: bool = Field(
        default=False, description="是否需要把该事项自动加入日历"
    )
    calendar_event_title: str | None = Field(
        default=None, description="根据聊天上下文总结的日历事件标题"
    )
    calendar_starts_at: datetime | None = Field(
        default=None, description="日历开始时间，必须为带时区的 ISO 8601 时间"
    )
    calendar_time_basis: CalendarTimeBasis | None = Field(
        default=None,
        description="exact=明确提到，inferred=相对时间推导，suggested=合理建议",
    )
    calendar_reason: str | None = Field(
        default=None, description="选择该日历时间的简短理由"
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
        if self.should_schedule:
            required_calendar = (
                self.calendar_event_title,
                self.calendar_starts_at,
                self.calendar_time_basis,
                self.calendar_reason,
            )
            if not self.has_task:
                raise ValueError("只有任务事项才能自动加入日历")
            if any(value is None for value in required_calendar):
                raise ValueError("日历标题、时间、时间依据和理由不能为空")
            if self.calendar_starts_at.tzinfo is None:
                raise ValueError("日历时间必须包含时区")
        else:
            self.calendar_event_title = None
            self.calendar_starts_at = None
            self.calendar_time_basis = None
            self.calendar_reason = None
        return self


class TaskConfirmRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=50_000)
    conversation_id: str = Field(default="default", min_length=1, max_length=100)
    customer_id: uuid.UUID | None = None
    analysis: AnalysisResult


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: str
    customer_id: uuid.UUID | None
    source_transcript: str
    customer_intent: str
    title: str
    status: TaskStatus
    priority: Priority
    due_at: datetime | None
    calendar_title: str | None
    calendar_time_basis: CalendarTimeBasis | None
    calendar_reason: str | None
    customer_sentiment: Sentiment
    risk_level: RiskLevel
    suggested_reply: str
    created_at: datetime
    updated_at: datetime


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: TaskStatus | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    customer_id: uuid.UUID | None = None
    suggested_reply: str | None = None


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


class CustomerCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class CustomerUpdate(BaseModel):
    external_id: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class CustomerRead(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    conversation_id: str
    title: str
    message: str
    remind_at: datetime
    status: ReminderStatus
    triggered_at: datetime


class DashboardRead(BaseModel):
    total_tasks: int
    pending_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    overdue_tasks: int
    high_risk_tasks: int
    active_reminders: int
    deferred_memories: int
    customers: int
    tasks_by_priority: dict[str, int]
    tasks_by_status: dict[str, int]


class CalendarEventStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    all_day: bool = False
    conversation_id: str | None = Field(default=None, max_length=100)
    customer_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_times(self) -> "CalendarEventCreate":
        if self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("结束时间不能早于开始时间")
        return self


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool | None = None
    status: CalendarEventStatus | None = None
    conversation_id: str | None = Field(default=None, max_length=100)
    customer_id: uuid.UUID | None = None


class CalendarEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: str
    source_id: uuid.UUID | None
    conversation_id: str | None
    customer_id: uuid.UUID | None
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    status: CalendarEventStatus
    time_basis: CalendarTimeBasis | None
    time_reason: str | None
    created_at: datetime
    updated_at: datetime


class MessageChannel(StrEnum):
    WECHAT = "wechat"
    EMAIL = "email"
    SUPPORT = "support"
    WEB = "web"


class SenderType(StrEnum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"


class ConversationStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ConversationCreate(BaseModel):
    channel: MessageChannel = MessageChannel.WEB
    external_id: str = Field(min_length=1, max_length=200)
    subject: str | None = Field(default=None, max_length=300)
    customer_id: uuid.UUID | None = None


class ConversationUpdate(BaseModel):
    subject: str | None = Field(default=None, max_length=300)
    status: ConversationStatus | None = None
    customer_id: uuid.UUID | None = None
    automation_enabled: bool | None = None
    handoff_status: HandoffStatus | None = None
    handoff_reason: str | None = Field(default=None, max_length=1000)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: MessageChannel
    external_id: str
    customer_id: uuid.UUID | None
    subject: str | None
    status: ConversationStatus
    automation_enabled: bool
    handoff_status: HandoffStatus
    handoff_reason: str | None
    memory_summary: str | None
    summary_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    sender_type: SenderType
    sender_id: str | None = Field(default=None, max_length=200)
    sender_name: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1, max_length=50_000)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    channel: MessageChannel
    external_message_id: str | None
    reply_to_message_id: uuid.UUID | None
    sender_type: SenderType
    sender_id: str | None
    sender_name: str | None
    content: str
    processing_status: str
    received_at: datetime
    created_at: datetime


class InboundMessage(BaseModel):
    external_conversation_id: str = Field(min_length=1, max_length=200)
    external_message_id: str = Field(min_length=1, max_length=300)
    sender_id: str | None = Field(default=None, max_length=200)
    sender_name: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1, max_length=50_000)
    subject: str | None = Field(default=None, max_length=300)
    received_at: datetime | None = None


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class AutoReplyDecision(BaseModel):
    should_reply: bool = Field(
        description="是否允许机器人针对本次客户消息自动回复"
    )
    handoff_required: bool = Field(
        description="是否应停止自动回复并转交人工"
    )
    handoff_reason: str | None = Field(
        default=None, description="转人工的简短原因"
    )
    risk_level: RiskLevel
    reply: str | None = Field(
        default=None, description="可直接发送给客户的简洁回复"
    )
    updated_summary: str = Field(
        min_length=1,
        max_length=4000,
        description="包含客户诉求、已确认事实、承诺、待办和未解决问题的滚动摘要",
    )

    @model_validator(mode="after")
    def validate_reply_decision(self) -> "AutoReplyDecision":
        if self.handoff_required:
            self.should_reply = False
            self.reply = None
            if not self.handoff_reason:
                raise ValueError("转人工时必须说明原因")
        elif self.should_reply and not self.reply:
            raise ValueError("自动回复时回复内容不能为空")
        else:
            self.reply = None
        return self


class AutomationProcessRead(BaseModel):
    inbound_message_id: uuid.UUID
    duplicate: bool
    action: str
    reply_message: MessageRead | None = None
    handoff_status: HandoffStatus
    handoff_reason: str | None = None
    memory_summary: str | None = None
