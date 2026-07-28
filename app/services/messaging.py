import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message


def get_or_create_conversation(
    db: Session,
    *,
    channel: str,
    external_id: str,
    subject: str | None = None,
    automation_enabled: bool = False,
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.channel == channel,
            Conversation.external_id == external_id,
        )
    )
    if conversation is None:
        conversation = Conversation(
            channel=channel,
            external_id=external_id,
            subject=subject,
            status="open",
            automation_enabled=automation_enabled,
        )
        db.add(conversation)
        db.flush()
    elif subject and not conversation.subject:
        conversation.subject = subject
    return conversation


def create_message(
    db: Session,
    *,
    conversation: Conversation,
    sender_type: str,
    content: str,
    sender_id: str | None = None,
    sender_name: str | None = None,
    external_message_id: str | None = None,
    received_at: datetime | None = None,
    reply_to_message_id: uuid.UUID | None = None,
    processing_status: str = "received",
) -> tuple[Message, bool]:
    if external_message_id:
        existing = db.scalar(
            select(Message).where(
                Message.channel == conversation.channel,
                Message.external_message_id == external_message_id,
            )
        )
        if existing:
            return existing, False
    message = Message(
        conversation_id=conversation.id,
        channel=conversation.channel,
        external_message_id=external_message_id,
        reply_to_message_id=reply_to_message_id,
        sender_type=sender_type,
        sender_id=sender_id,
        sender_name=sender_name,
        content=content,
        processing_status=processing_status,
        received_at=received_at or datetime.now(timezone.utc),
    )
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message, True


def serialize_message(message: Message) -> dict:
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "channel": message.channel,
        "external_message_id": message.external_message_id,
        "reply_to_message_id": (
            str(message.reply_to_message_id)
            if message.reply_to_message_id
            else None
        ),
        "sender_type": message.sender_type,
        "sender_id": message.sender_id,
        "sender_name": message.sender_name,
        "content": message.content,
        "processing_status": message.processing_status,
        "received_at": message.received_at.isoformat(),
        "created_at": message.created_at.isoformat(),
    }
