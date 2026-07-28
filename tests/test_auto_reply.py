from app.schemas import AnalysisResult, AutoReplyDecision
from tests.test_api import CASES


def _client(client_factory):
    return client_factory(
        AnalysisResult.model_validate(CASES[0]["analysis"])
    )


def _create_enabled_conversation(client, external_id="auto-customer"):
    conversation = client.post(
        "/api/conversations",
        json={
            "channel": "wechat",
            "external_id": external_id,
            "subject": "自动回复测试",
        },
    ).json()
    updated = client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"automation_enabled": True},
    )
    assert updated.status_code == 200
    return updated.json()


def test_auto_reply_uses_context_summary_and_is_idempotent(client_factory):
    client = _client(client_factory)
    conversation = _create_enabled_conversation(client)
    client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={
            "sender_type": "agent",
            "sender_name": "客服",
            "content": "订单 A100 已登记查询。",
        },
    )
    payload = {
        "external_conversation_id": conversation["external_id"],
        "external_message_id": "wx-auto-001",
        "sender_id": "openid-auto",
        "content": "请问订单 A100 查到哪里了？",
    }
    first = client.post("/api/inbound/wechat", json=payload)
    second = client.post("/api/inbound/wechat", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert client.fake_llm.auto_reply_calls == 1
    assert "订单 A100 已登记查询" in client.fake_llm.last_auto_reply_context

    history = client.get(
        f"/api/conversations/{conversation['id']}/messages"
    ).json()
    assert len(history) == 3
    replies = [
        message for message in history if message["sender_id"] == "ai-assistant"
    ]
    assert len(replies) == 1
    assert replies[0]["reply_to_message_id"] == first.json()["id"]

    refreshed = next(
        row
        for row in client.get("/api/conversations").json()
        if row["id"] == conversation["id"]
    )
    assert refreshed["memory_summary"] == "客户正在咨询问题，等待进一步处理。"


def test_high_risk_message_hands_off_and_locks_auto_reply(client_factory):
    client = _client(client_factory)
    conversation = _create_enabled_conversation(client, "risk-customer")
    client.fake_llm.auto_reply_result = AutoReplyDecision(
        should_reply=False,
        handoff_required=True,
        handoff_reason="客户投诉并要求人工处理",
        risk_level="high",
        updated_summary="客户投诉，要求人工处理，当前尚未解决。",
    )
    first = client.post(
        "/api/inbound/wechat",
        json={
            "external_conversation_id": conversation["external_id"],
            "external_message_id": "wx-risk-001",
            "content": "我要投诉，马上转人工。",
        },
    )
    assert first.status_code == 200

    state = next(
        row
        for row in client.get("/api/conversations").json()
        if row["id"] == conversation["id"]
    )
    assert state["handoff_status"] == "pending"
    assert state["handoff_reason"] == "客户投诉并要求人工处理"

    second = client.post(
        "/api/inbound/wechat",
        json={
            "external_conversation_id": conversation["external_id"],
            "external_message_id": "wx-risk-002",
            "content": "有人吗？",
        },
    )
    assert second.status_code == 200
    assert client.fake_llm.auto_reply_calls == 1
    history = client.get(
        f"/api/conversations/{conversation['id']}/messages"
    ).json()
    assert all(message["sender_id"] != "ai-assistant" for message in history)


def test_manual_process_endpoint_does_not_duplicate_reply(client_factory):
    client = _client(client_factory)
    conversation = _create_enabled_conversation(client, "manual-process")
    inbound = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={
            "sender_type": "customer",
            "content": "请介绍一下服务时间。",
        },
    ).json()
    first = client.post(
        f"/api/conversations/{conversation['id']}/messages/"
        f"{inbound['id']}/process"
    )
    second = client.post(
        f"/api/conversations/{conversation['id']}/messages/"
        f"{inbound['id']}/process"
    )
    assert first.status_code == 200
    assert first.json()["action"] == "replied"
    assert second.json()["duplicate"] is True
    assert first.json()["reply_message"]["id"] == second.json()["reply_message"]["id"]
    assert client.fake_llm.auto_reply_calls == 1
