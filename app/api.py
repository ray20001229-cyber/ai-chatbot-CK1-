import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_llm_service
from app.models import ConversationMemory, Task
from app.schemas import (
    AnalysisResult,
    AnalyzeRequest,
    MemoryRead,
    MemoryStatus,
    MemoryUpdate,
    TaskConfirmRequest,
    TaskRead,
)
from app.services.llm import LLMService

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

    task = Task(
        conversation_id=payload.conversation_id,
        source_transcript=payload.transcript,
        customer_intent=analysis.customer_intent,
        title=analysis.task_title,
        status=analysis.task_status.value,
        priority=analysis.priority.value,
        due_at=analysis.due_at,
        customer_sentiment=analysis.customer_sentiment.value,
        risk_level=analysis.risk_level.value,
        suggested_reply=analysis.suggested_reply,
    )
    db.add(task)
    db.flush()
    if analysis.should_remember:
        db.add(
            ConversationMemory(
                conversation_id=payload.conversation_id,
                task_id=task.id,
                summary=analysis.memory_summary,
                details=payload.transcript,
                status=analysis.memory_status.value,
                resume_at=analysis.resume_at,
            )
        )
    db.commit()
    db.refresh(task)
    return task


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)) -> list[Task]:
    return list(db.scalars(select(Task).order_by(Task.created_at.desc())))


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
    db.commit()
    db.refresh(memory)
    return memory
    MemoryRead,
    MemoryStatus,
    MemoryUpdate,
