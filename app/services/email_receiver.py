import asyncio
import email
import imaplib
import logging
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from app.config import Settings
from app.database import SessionLocal
from app.services.messaging import create_message, get_or_create_conversation

logger = logging.getLogger(__name__)


async def email_poll_loop(settings: Settings) -> None:
    while True:
        try:
            await asyncio.to_thread(poll_email_once, settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Email polling failed")
        await asyncio.sleep(settings.email_poll_interval_seconds)


def poll_email_once(settings: Settings) -> int:
    if not _configured(settings):
        return 0
    count = 0
    with imaplib.IMAP4_SSL(
        settings.email_imap_host, settings.email_imap_port
    ) as mailbox:
        mailbox.login(settings.email_imap_username, settings.email_imap_password)
        mailbox.select(settings.email_imap_folder)
        status, data = mailbox.search(None, "UNSEEN")
        if status != "OK":
            return 0
        for message_number in data[0].split():
            status, raw_parts = mailbox.fetch(message_number, "(RFC822)")
            if status != "OK":
                continue
            raw = next(
                part[1] for part in raw_parts if isinstance(part, tuple)
            )
            parsed = email.message_from_bytes(raw)
            sender_name, sender_address = parseaddr(parsed.get("From", ""))
            subject = str(make_header(decode_header(parsed.get("Subject", ""))))
            message_id = parsed.get("Message-ID") or (
                f"{sender_address}:{message_number.decode()}"
            )
            body = _plain_text(parsed)
            date_header = parsed.get("Date")
            received_at = (
                parsedate_to_datetime(date_header) if date_header else None
            )
            with SessionLocal() as db:
                conversation = get_or_create_conversation(
                    db,
                    channel="email",
                    external_id=sender_address or message_id,
                    subject=subject,
                )
                _, created = create_message(
                    db,
                    conversation=conversation,
                    sender_type="customer",
                    sender_id=sender_address,
                    sender_name=sender_name or sender_address,
                    content=body or "(无文本内容)",
                    external_message_id=message_id,
                    received_at=received_at,
                )
                count += int(created)
    return count


def _plain_text(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if (
                part.get_content_type() == "text/plain"
                and part.get_content_disposition() != "attachment"
            ):
                return _decode_part(part)
        return ""
    return _decode_part(message)


def _decode_part(part) -> str:
    payload = part.get_payload(decode=True) or b""
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def _configured(settings: Settings) -> bool:
    return bool(
        settings.email_imap_enabled
        and settings.email_imap_host
        and settings.email_imap_username
        and settings.email_imap_password
    )
