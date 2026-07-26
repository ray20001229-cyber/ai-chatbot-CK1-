import uuid
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_llm_service
from app.models import CalendarEvent, ConversationMemory, Customer, Reminder, Task
from app.schemas import (
    AnalysisResult,
    AnalyzeRequest,
    CalendarEventCreate,
    CalendarEventRead,
    CalendarEventUpdate,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    DashboardRead,
    MemoryRead,
    MemoryStatus,
    MemoryUpdate,
    ReminderRead,
    TaskConfirmRequest,
    TaskRead,
    TaskUpdate,
)
from app.services.llm import LLMService
from app.services.calendar import (
    delete_source_calendar,
    sync_memory_calendar,
    sync_task_calendar,
)
from app.services.redis_store import cache_delete, cache_get, cache_set
from app.services.reminders import scan_due_items

router = APIRouter(prefix="/api")


@router.post("/analyze", response_model=AnalysisResult)
async def analyze(
    payload: AnalyzeRequest,
    llm: LLMService = Depends(get_llm_service),
    db: Session = Depends(get_db),
) -> AnalysisResult:
    memories = list(
        db.scalars(
            select(ConversationMemory)
            .where(
                ConversationMemory.conversation_id == payload.conversation_id,
                ConversationMemory.status.in_(
                    [MemoryStatus.PENDING.value, MemoryStatus.DEFERRED.value]
                ),
            )
            .order_by(ConversationMemory.created_at.asc())
        )
    )
    memory_context = "\n".join(
        f"- [{memory.status}] {memory.summary}"
        + (
            f"；恢复时间：{memory.resume_at.isoformat()}"
            if memory.resume_at
            else ""
        )
        for memory in memories
    )
    try:
        return await llm.analyze(payload.transcript, memory_context or None)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"大模型分析失败：{exc}") from exc


@router.post(
    "/tasks/confirm", response_model=TaskRead, status_code=status.HTTP_201_CREATED
)
def confirm_task(
    payload: TaskConfirmRequest, db: Session = Depends(get_db)
) -> Task:
    analysis = payload.analysis
    if not analysis.has_task:
        raise HTTPException(status_code=400, detail="分析结果不包含可确认的任务")
    if payload.customer_id and db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail="客户不存在")

    is_deferred = (
        analysis.should_remember
        and analysis.memory_status == MemoryStatus.DEFERRED
    )
    task_due_at = analysis.due_at
    if analysis.should_schedule and not is_deferred and task_due_at is None:
        task_due_at = analysis.calendar_starts_at

    task = Task(
        conversation_id=payload.conversation_id,
        customer_id=payload.customer_id,
        source_transcript=payload.transcript,
        customer_intent=analysis.customer_intent,
        title=analysis.task_title,
        status=analysis.task_status.value,
        priority=analysis.priority.value,
        due_at=task_due_at,
        calendar_title=analysis.calendar_event_title,
        calendar_time_basis=(
            analysis.calendar_time_basis.value
            if analysis.calendar_time_basis
            else None
        ),
        calendar_reason=analysis.calendar_reason,
        customer_sentiment=analysis.customer_sentiment.value,
        risk_level=analysis.risk_level.value,
        suggested_reply=analysis.suggested_reply,
    )
    db.add(task)
    db.flush()
    sync_task_calendar(db, task)
    if analysis.should_remember:
        memory_resume_at = analysis.resume_at
        if (
            analysis.should_schedule
            and analysis.memory_status == MemoryStatus.DEFERRED
            and memory_resume_at is None
        ):
            memory_resume_at = analysis.calendar_starts_at
        memory = ConversationMemory(
            conversation_id=payload.conversation_id,
            task_id=task.id,
            summary=analysis.memory_summary,
            details=payload.transcript,
            status=analysis.memory_status.value,
            resume_at=memory_resume_at,
            calendar_title=analysis.calendar_event_title,
            calendar_time_basis=(
                analysis.calendar_time_basis.value
                if analysis.calendar_time_basis
                else None
            ),
            calendar_reason=analysis.calendar_reason,
        )
        db.add(memory)
        db.flush()
        sync_memory_calendar(db, memory)
    db.commit()
    _invalidate_dashboard()
    db.refresh(task)
    return task


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    task_status: str | None = None,
    customer_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
) -> list[Task]:
    query = select(Task)
    if task_status:
        query = query.where(Task.status == task_status)
    if customer_id:
        query = query.where(Task.customer_id == customer_id)
    return list(db.scalars(query.order_by(Task.created_at.desc())))


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
) -> Task:
    task = _get_task(db, task_id)
    changes = payload.model_dump(exclude_unset=True)
    if "customer_id" in changes and changes["customer_id"]:
        if db.get(Customer, changes["customer_id"]) is None:
            raise HTTPException(status_code=404, detail="客户不存在")
    for field, value in changes.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(task, field, value)
    if task.status == "completed":
        _dismiss_source_reminders(db, "task", task.id)
    sync_task_calendar(db, task)
    db.commit()
    _invalidate_dashboard()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    task = _get_task(db, task_id)
    db.execute(
        delete(Reminder).where(
            Reminder.source_type == "task", Reminder.source_id == task.id
        )
    )
    delete_source_calendar(db, "task", task.id)
    db.delete(task)
    db.commit()
    _invalidate_dashboard()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/memories", response_model=list[MemoryRead])
def list_memories(
    conversation_id: str | None = None,
    include_completed: bool = False,
    db: Session = Depends(get_db),
) -> list[ConversationMemory]:
    query = select(ConversationMemory)
    if conversation_id:
        query = query.where(
            ConversationMemory.conversation_id == conversation_id
        )
    if not include_completed:
        query = query.where(
            ConversationMemory.status != MemoryStatus.COMPLETED.value
        )
    return list(db.scalars(query.order_by(ConversationMemory.created_at.desc())))


@router.patch("/memories/{memory_id}", response_model=MemoryRead)
def update_memory(
    memory_id: uuid.UUID,
    payload: MemoryUpdate,
    db: Session = Depends(get_db),
) -> ConversationMemory:
    memory = db.get(ConversationMemory, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    memory.status = payload.status.value
    memory.resume_at = payload.resume_at
    if memory.status == MemoryStatus.COMPLETED.value:
        _dismiss_source_reminders(db, "memory", memory.id)
    sync_memory_calendar(db, memory)
    db.commit()
    _invalidate_dashboard()
    db.refresh(memory)
    return memory


@router.post(
    "/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED
)
def create_customer(
    payload: CustomerCreate, db: Session = Depends(get_db)
) -> Customer:
    customer = Customer(**payload.model_dump())
    db.add(customer)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="客户编号已存在") from exc
    db.refresh(customer)
    _invalidate_dashboard()
    return customer


@router.get("/customers", response_model=list[CustomerRead])
def list_customers(db: Session = Depends(get_db)) -> list[Customer]:
    return list(db.scalars(select(Customer).order_by(Customer.created_at.desc())))


@router.patch("/customers/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
) -> Customer:
    customer = _get_customer(db, customer_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="客户编号已存在") from exc
    db.refresh(customer)
    _invalidate_dashboard()
    return customer


@router.delete(
    "/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_customer(
    customer_id: uuid.UUID, db: Session = Depends(get_db)
) -> Response:
    customer = _get_customer(db, customer_id)
    db.delete(customer)
    db.commit()
    _invalidate_dashboard()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reminders", response_model=list[ReminderRead])
def list_reminders(
    include_dismissed: bool = False,
    db: Session = Depends(get_db),
) -> list[Reminder]:
    query = select(Reminder)
    if not include_dismissed:
        query = query.where(Reminder.status == "active")
    return list(db.scalars(query.order_by(Reminder.remind_at.desc())))


@router.post("/reminders/scan")
def scan_reminders(db: Session = Depends(get_db)) -> dict[str, int]:
    return {"created": scan_due_items(db)}


@router.patch("/reminders/{reminder_id}/dismiss", response_model=ReminderRead)
def dismiss_reminder(
    reminder_id: uuid.UUID, db: Session = Depends(get_db)
) -> Reminder:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="提醒不存在")
    reminder.status = "dismissed"
    db.commit()
    _invalidate_dashboard()
    db.refresh(reminder)
    return reminder


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(db: Session = Depends(get_db)) -> DashboardRead:
    cached = cache_get("dashboard:v1")
    if cached is not None:
        return DashboardRead.model_validate(cached)
    now = datetime.now(timezone.utc)
    tasks = list(db.scalars(select(Task)))
    memories = list(db.scalars(select(ConversationMemory)))
    task_statuses = Counter(task.status for task in tasks)
    priorities = Counter(task.priority for task in tasks)
    result = DashboardRead(
        total_tasks=len(tasks),
        pending_tasks=task_statuses["pending"],
        in_progress_tasks=task_statuses["in_progress"],
        completed_tasks=task_statuses["completed"],
        overdue_tasks=sum(
            1
            for task in tasks
            if task.due_at
            and _as_utc(task.due_at) <= now
            and task.status != "completed"
        ),
        high_risk_tasks=sum(
            1 for task in tasks if task.risk_level in {"high", "critical"}
        ),
        active_reminders=db.query(Reminder)
        .filter(Reminder.status == "active")
        .count(),
        deferred_memories=sum(
            1 for memory in memories if memory.status == "deferred"
        ),
        customers=db.query(Customer).count(),
        tasks_by_priority={
            key: priorities[key] for key in ("low", "medium", "high", "urgent")
        },
        tasks_by_status={
            key: task_statuses[key]
            for key in ("pending", "in_progress", "completed")
        },
    )
    cache_set("dashboard:v1", result.model_dump(mode="json"), ttl=30)
    return result


@router.post(
    "/calendar/events",
    response_model=CalendarEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_calendar_event(
    payload: CalendarEventCreate, db: Session = Depends(get_db)
) -> CalendarEvent:
    if payload.customer_id and db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    event = CalendarEvent(
        source_type="manual",
        source_id=None,
        status="scheduled",
        **payload.model_dump(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/calendar/events", response_model=list[CalendarEventRead])
def list_calendar_events(
    starts_from: datetime | None = None,
    starts_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> list[CalendarEvent]:
    query = select(CalendarEvent)
    if starts_from:
        query = query.where(CalendarEvent.starts_at >= starts_from)
    if starts_to:
        query = query.where(CalendarEvent.starts_at <= starts_to)
    return list(db.scalars(query.order_by(CalendarEvent.starts_at.asc())))


@router.patch(
    "/calendar/events/{event_id}", response_model=CalendarEventRead
)
def update_calendar_event(
    event_id: uuid.UUID,
    payload: CalendarEventUpdate,
    db: Session = Depends(get_db),
) -> CalendarEvent:
    event = _get_calendar_event(db, event_id)
    if event.source_type != "manual":
        raise HTTPException(
            status_code=409, detail="自动同步事件请通过对应任务或记忆修改"
        )
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("customer_id") and db.get(
        Customer, changes["customer_id"]
    ) is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    for field, value in changes.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(event, field, value)
    if event.ends_at and event.ends_at < event.starts_at:
        raise HTTPException(status_code=422, detail="结束时间不能早于开始时间")
    db.commit()
    db.refresh(event)
    return event


@router.delete(
    "/calendar/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_calendar_event(
    event_id: uuid.UUID, db: Session = Depends(get_db)
) -> Response:
    event = _get_calendar_event(db, event_id)
    if event.source_type != "manual":
        raise HTTPException(
            status_code=409, detail="自动同步事件请通过对应任务或记忆删除"
        )
    db.delete(event)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_task(db: Session, task_id: uuid.UUID) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


def _get_customer(db: Session, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    return customer


def _get_calendar_event(
    db: Session, event_id: uuid.UUID
) -> CalendarEvent:
    event = db.get(CalendarEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="日历事件不存在")
    return event


def _dismiss_source_reminders(
    db: Session, source_type: str, source_id: uuid.UUID
) -> None:
    reminders = list(
        db.scalars(
            select(Reminder).where(
                Reminder.source_type == source_type,
                Reminder.source_id == source_id,
                Reminder.status == "active",
            )
        )
    )
    for reminder in reminders:
        reminder.status = "dismissed"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _invalidate_dashboard() -> None:
    cache_delete("dashboard:v1")
