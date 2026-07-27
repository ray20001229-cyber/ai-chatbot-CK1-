from pathlib import Path

from app.config import Settings
from app.schemas import AnalysisResult
from app.services.email_receiver import poll_email_once
from tests.test_api import CASES


def test_conversation_messages_and_websocket(client_factory):
    client = client_factory(AnalysisResult.model_validate(CASES[0]["analysis"]))
    created = client.post(
        "/api/conversations",
        json={
            "channel": "web",
            "external_id": "web-customer-001",
            "subject": "Realtime support",
        },
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    with client.websocket_connect(
        f"/api/ws/conversations/{conversation_id}"
    ) as websocket:
        websocket.send_json(
            {
                "sender_type": "customer",
                "sender_name": "Customer",
                "content": "Hello, I need help.",
            }
        )
        received = websocket.receive_json()
        assert received["content"] == "Hello, I need help."
        assert received["sender_type"] == "customer"

    posted = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={
            "sender_type": "agent",
            "sender_name": "Agent",
            "content": "How can I help?",
        },
    )
    assert posted.status_code == 201
    history = client.get(
        f"/api/conversations/{conversation_id}/messages"
    ).json()
    assert [row["sender_type"] for row in history] == ["customer", "agent"]


def test_inbound_webhooks_are_idempotent(client_factory):
    client = client_factory(AnalysisResult.model_validate(CASES[0]["analysis"]))
    payload = {
        "external_conversation_id": "wx-openid-001",
        "external_message_id": "wx-message-001",
        "sender_id": "openid-001",
        "sender_name": "Wechat Customer",
        "content": "Where is my order?",
    }
    first = client.post("/api/inbound/wechat", json=payload)
    second = client.post("/api/inbound/wechat", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    conversations = client.get(
        "/api/conversations", params={"channel": "wechat"}
    ).json()
    assert len(conversations) == 1
    history = client.get(
        f"/api/conversations/{conversations[0]['id']}/messages"
    ).json()
    assert len(history) == 1

    support = client.post(
        "/api/inbound/support",
        json={**payload, "external_message_id": "support-message-001"},
    )
    assert support.status_code == 200
    assert support.json()["channel"] == "support"


def test_attachment_upload_download_and_type_validation(client_factory):
    client = client_factory(AnalysisResult.model_validate(CASES[0]["analysis"]))
    conversation = client.post(
        "/api/conversations",
        json={"channel": "web", "external_id": "attachment-case"},
    ).json()
    conversation_id = conversation["id"]

    uploaded = client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"upload": ("notes.txt", b"safe attachment", "text/plain")},
    )
    assert uploaded.status_code == 201
    attachment_id = uploaded.json()["id"]
    downloaded = client.get(f"/api/attachments/{attachment_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"safe attachment"

    rejected = client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={
            "upload": (
                "malware.exe",
                b"not executable",
                "application/octet-stream",
            )
        },
    )
    assert rejected.status_code == 415

    listed = client.get(
        f"/api/conversations/{conversation_id}/attachments"
    ).json()
    assert len(listed) == 1
    stored_files = list(Path(".test_uploads").glob("*"))
    for stored_file in stored_files:
        stored_file.unlink()


def test_email_poller_is_disabled_without_credentials():
    settings = Settings(email_imap_enabled=False)
    assert poll_email_once(settings) == 0
