from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Conversation, Message
from app.schemas import AutoReplyDecision
from app.services.conversation_memory import build_context
from app.services.llm import LLMService
from app.services.messaging import create_message


async def process_customer_message(
    db: Session,
    *,
    conversation: Conversation,
    inbound: Message,
    llm: LLMService,
    settings: Settings,
) -> tuple[str, Message | None, bool]:
    existing = db.scalar(
        select(Message).where(Message.reply_to_message_id == inbound.id)
    )
    if existing:
        return "replied", existing, True
    if inbound.processing_status in {"handoff", "ignored", "failed"}:
        return inbound.processing_status, None, True
    if inbound.sender_type != "customer":
        inbound.processing_status = "ignored"
        db.commit()
        return "ignored", None, False
    if not conversation.automation_enabled:
        inbound.processing_status = "ignored"
        db.commit()
        return "disabled", None, False
    if conversation.handoff_status != "bot":
        inbound.processing_status = "handoff"
        db.commit()
        return "handoff", None, False

    context = build_context(
        db,
        conversation=conversation,
        customer_message=inbound,
        settings=settings,
    )
    try:
        decision: AutoReplyDecision = await llm.decide_auto_reply(
            customer_message=inbound.content,
            context=context,
        )
    except Exception:
        inbound.processing_status = "failed"
        conversation.handoff_status = "pending"
        conversation.handoff_reason = "自动回复服务异常，需要人工处理"
        db.commit()
        return "failed", None, False

    conversation.memory_summary = decision.updated_summary
    conversation.summary_updated_at = datetime.now(timezone.utc)
    risk_handoff = {
        level.strip()
        for level in settings.auto_reply_risk_handoff_levels.split(",")
    }
    if decision.handoff_required or decision.risk_level.value in risk_handoff:
        conversation.handoff_status = "pending"
        conversation.handoff_reason = (
            decision.handoff_reason
            or f"{decision.risk_level.value} 风险消息需要人工处理"
        )
        inbound.processing_status = "handoff"
        db.commit()
        return "handoff", None, False
    if not decision.should_reply:
        inbound.processing_status = "ignored"
        db.commit()
        return "ignored", None, False

    try:
        reply, _ = create_message(
            db,
            conversation=conversation,
            sender_type="agent",
            sender_id="ai-assistant",
            sender_name="AI 客服",
            content=decision.reply or "",
            reply_to_message_id=inbound.id,
            processing_status="sent",
        )
        inbound.processing_status = "replied"
        db.commit()
        return "replied", reply, False
    except IntegrityError:
        db.rollback()
        reply = db.scalar(
            select(Message).where(Message.reply_to_message_id == inbound.id)
        )
        return "replied", reply, True
