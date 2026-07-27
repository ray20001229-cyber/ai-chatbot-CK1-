import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Attachment, Conversation, Message

ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


async def save_upload(
    db: Session,
    *,
    conversation: Conversation,
    upload: UploadFile,
    message: Message | None = None,
) -> Attachment:
    settings = get_settings()
    content_type = upload.content_type or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="不支持该附件类型")

    safe_name = _safe_original_name(upload.filename or "attachment")
    suffix = Path(safe_name).suffix.lower()[:12]
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    root = Path(settings.upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / stored_name).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=400, detail="附件路径无效")

    size = 0
    try:
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="附件超过大小限制")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    attachment = Attachment(
        conversation_id=conversation.id,
        message_id=message.id if message else None,
        original_name=safe_name,
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=size,
        storage_path=str(target),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def _safe_original_name(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", name).strip()
    return (name or "attachment")[:255]
