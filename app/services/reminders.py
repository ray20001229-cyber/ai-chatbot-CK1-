import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ConversationMemory, Reminder, Task

logger = logging.getLogger(__name__)


def scan_due_items(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    created = 0

    due_tasks = list(
        db.scalars(
            select(Task).where(
                Task.due_at.is_not(None),
                Task.due_at <= now,
                Task.status != "completed",
            )
        )
    )
    for task in due_tasks:
        created += _create_reminder(
            db,
            source_type="task",
            source_id=task.id,
            conversation_id=task.conversation_id,
            title=f"任务已到期：{task.title}",
            message=f"任务“{task.title}”已到期，请尽快处理。",
            remind_at=task.due_at,
        )

    due_memories = list(
        db.scalars(
            select(ConversationMemory).where(
                ConversationMemory.status == "deferred",
                ConversationMemory.resume_at.is_not(None),
                ConversationMemory.resume_at <= now,
            )
        )
    )
    for memory in due_memories:
        created += _create_reminder(
            db,
            source_type="memory",
            source_id=memory.id,
            conversation_id=memory.conversation_id,
            title=f"延期事项可恢复：{memory.summary}",
            message=f"延期事项“{memory.summary}”已到恢复处理时间。",
            remind_at=memory.resume_at,
        )

    db.commit()
    return created


def _create_reminder(
    db: Session,
    *,
    source_type: str,
    source_id,
    conversation_id: str,
    title: str,
    message: str,
    remind_at: datetime,
) -> int:
    exists = db.scalar(
        select(Reminder.id).where(
            Reminder.source_type == source_type,
            Reminder.source_id == source_id,
        )
    )
    if exists:
        return 0
    db.add(
        Reminder(
            source_type=source_type,
            source_id=source_id,
            conversation_id=conversation_id,
            title=title,
            message=message,
            remind_at=remind_at,
        )
    )
    try:
        db.flush()
        return 1
    except IntegrityError:
        db.rollback()
        return 0


async def reminder_scan_loop(interval_seconds: int) -> None:
    while True:
        try:
            await asyncio.to_thread(_scan_with_new_session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reminder scan failed")
        await asyncio.sleep(interval_seconds)


def _scan_with_new_session() -> None:
    with SessionLocal() as db:
        scan_due_items(db)
