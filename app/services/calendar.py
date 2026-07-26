from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CalendarEvent, ConversationMemory, Task


def sync_task_calendar(db: Session, task: Task) -> None:
    event = db.scalar(
        select(CalendarEvent).where(
            CalendarEvent.source_type == "task",
            CalendarEvent.source_id == task.id,
        )
    )
    if task.due_at is None or task.status == "completed":
        if event:
            db.delete(event)
        return
    if event is None:
        event = CalendarEvent(source_type="task", source_id=task.id)
        db.add(event)
    event.conversation_id = task.conversation_id
    event.customer_id = task.customer_id
    event.title = task.calendar_title or f"任务截止：{task.title}"
    event.description = task.customer_intent
    event.starts_at = task.due_at
    event.status = "scheduled"
    event.time_basis = task.calendar_time_basis
    event.time_reason = task.calendar_reason


def sync_memory_calendar(db: Session, memory: ConversationMemory) -> None:
    event = db.scalar(
        select(CalendarEvent).where(
            CalendarEvent.source_type == "memory",
            CalendarEvent.source_id == memory.id,
        )
    )
    if (
        memory.resume_at is None
        or memory.status != "deferred"
    ):
        if event:
            db.delete(event)
        return
    if event is None:
        event = CalendarEvent(source_type="memory", source_id=memory.id)
        db.add(event)
    event.conversation_id = memory.conversation_id
    event.title = (
        memory.calendar_title or f"恢复延期事项：{memory.summary}"
    )
    event.description = memory.details
    event.starts_at = memory.resume_at
    event.status = "scheduled"
    event.time_basis = memory.calendar_time_basis
    event.time_reason = memory.calendar_reason


def delete_source_calendar(
    db: Session, source_type: str, source_id
) -> None:
    db.execute(
        delete(CalendarEvent).where(
            CalendarEvent.source_type == source_type,
            CalendarEvent.source_id == source_id,
        )
    )


def reconcile_calendar(db: Session) -> None:
    for task in db.scalars(select(Task)):
        sync_task_calendar(db, task)
    for memory in db.scalars(select(ConversationMemory)):
        sync_memory_calendar(db, memory)
    db.commit()
