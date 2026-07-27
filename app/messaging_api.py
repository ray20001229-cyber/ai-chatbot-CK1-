import hmac
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse
from fastapi import Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Attachment, Conversation, Customer, Message
from app.schemas import (
    AttachmentRead,
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    InboundMessage,
    MessageCreate,
    MessageRead,
)
from app.services.attachments import save_upload
from app.services.messaging import (
    create_message,
    get_or_create_conversation,
    serialize_message,
)
from app.services.realtime import manager

router = APIRouter(prefix="/api")


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreate, db: Session = Depends(get_db)
) -> Conversation:
    if payload.customer_id and db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    conversation = Conversation(
        channel=payload.channel.value,
        external_id=payload.external_id,
        customer_id=payload.customer_id,
        subject=payload.subject,
        status="open",
    )
    db.add(conversation)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该渠道会话已经存在") from exc
    db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    channel: str | None = None,
    conversation_status: str | None = None,
    db: Session = Depends(get_db),
) -> list[Conversation]:
    query = select(Conversation)
    if channel:
        query = query.where(Conversation.channel == channel)
    if conversation_status:
        query = query.where(Conversation.status == conversation_status)
    return list(db.scalars(query.order_by(Conversation.updated_at.desc())))


@router.patch(
    "/conversations/{conversation_id}", response_model=ConversationRead
)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
) -> Conversation:
    conversation = _get_conversation(db, conversation_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("customer_id") and db.get(
        Customer, changes["customer_id"]
    ) is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    for field, value in changes.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(conversation, field, value)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Response:
    conversation = _get_conversation(db, conversation_id)
    attachments = list(
        db.scalars(
            select(Attachment).where(
                Attachment.conversation_id == conversation_id
            )
        )
    )
    for attachment in attachments:
        Path(attachment.storage_path).unlink(missing_ok=True)
    db.delete(conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
)
def list_messages(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[Message]:
    _get_conversation(db, conversation_id)
    return list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.received_at.asc())
        )
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    db: Session = Depends(get_db),
) -> Message:
    conversation = _get_conversation(db, conversation_id)
    message, _ = create_message(
        db,
        conversation=conversation,
        sender_type=payload.sender_type.value,
        sender_id=payload.sender_id,
        sender_name=payload.sender_name,
        content=payload.content,
    )
    await manager.broadcast(conversation_id, serialize_message(message))
    return message


@router.post("/inbound/wechat", response_model=MessageRead)
async def inbound_wechat(
    payload: InboundMessage,
    x_webhook_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Message:
    _verify_webhook(x_webhook_token)
    return await _receive_inbound("wechat", payload, db)


@router.post("/inbound/support", response_model=MessageRead)
async def inbound_support(
    payload: InboundMessage,
    x_webhook_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Message:
    _verify_webhook(x_webhook_token)
    return await _receive_inbound("support", payload, db)


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID | None = None,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Attachment:
    conversation = _get_conversation(db, conversation_id)
    message = None
    if message_id:
        message = db.get(Message, message_id)
        if message is None or message.conversation_id != conversation.id:
            raise HTTPException(status_code=404, detail="消息不存在")
    return await save_upload(
        db, conversation=conversation, message=message, upload=upload
    )


@router.get(
    "/conversations/{conversation_id}/attachments",
    response_model=list[AttachmentRead],
)
def list_attachments(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[Attachment]:
    _get_conversation(db, conversation_id)
    return list(
        db.scalars(
            select(Attachment)
            .where(Attachment.conversation_id == conversation_id)
            .order_by(Attachment.created_at.desc())
        )
    )


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = Path(attachment.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="附件文件已丢失")
    return FileResponse(
        path,
        media_type=attachment.content_type,
        filename=attachment.original_name,
    )


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_websocket(
    websocket: WebSocket,
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        await websocket.close(code=4404)
        return
    await manager.connect(conversation_id, websocket)
    try:
        while True:
            raw = await websocket.receive_json()
            try:
                payload = MessageCreate.model_validate(raw)
            except ValidationError as exc:
                await websocket.send_json(
                    {"type": "error", "detail": str(exc)}
                )
                continue
            conversation = db.get(Conversation, conversation_id)
            if conversation is None:
                await websocket.close(code=4404)
                return
            message, _ = create_message(
                db,
                conversation=conversation,
                sender_type=payload.sender_type.value,
                sender_id=payload.sender_id,
                sender_name=payload.sender_name,
                content=payload.content,
            )
            serialized = serialize_message(message)
            await manager.broadcast(conversation_id, serialized)
    except WebSocketDisconnect:
        manager.disconnect(conversation_id, websocket)


async def _receive_inbound(
    channel: str, payload: InboundMessage, db: Session
) -> Message:
    conversation = get_or_create_conversation(
        db,
        channel=channel,
        external_id=payload.external_conversation_id,
        subject=payload.subject,
    )
    message, created = create_message(
        db,
        conversation=conversation,
        sender_type="customer",
        sender_id=payload.sender_id,
        sender_name=payload.sender_name,
        content=payload.content,
        external_message_id=payload.external_message_id,
        received_at=payload.received_at,
    )
    if created:
        await manager.broadcast(conversation.id, serialize_message(message))
    return message


def _verify_webhook(provided: str | None) -> None:
    settings = get_settings()
    expected = settings.webhook_shared_secret
    if not expected:
        if settings.app_env == "development":
            return
        raise HTTPException(status_code=503, detail="Webhook 尚未配置")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Webhook 认证失败")


def _get_conversation(
    db: Session, conversation_id: uuid.UUID
) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation
