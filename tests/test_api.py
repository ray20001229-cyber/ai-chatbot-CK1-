import pytest

from app.schemas import AnalysisResult


CASES = [
    {
        "name": "待办",
        "transcript": "客户：请明天下午前给我补开发票。客服：好的，我来登记。",
        "analysis": {
            "customer_intent": "申请补开发票",
            "has_task": True,
            "task_title": "补开发票",
            "task_status": "pending",
            "priority": "medium",
            "due_at": "2026-07-25T17:00:00+08:00",
            "customer_sentiment": "neutral",
            "risk_level": "low",
            "suggested_reply": "已为您登记补开发票申请，我们会尽快处理。",
        },
    },
    {
        "name": "办理中",
        "transcript": "客服：退款申请已提交财务，正在处理中。客户：好的。",
        "analysis": {
            "customer_intent": "查询退款进度",
            "has_task": True,
            "task_title": "跟进退款进度",
            "task_status": "in_progress",
            "priority": "medium",
            "due_at": None,
            "customer_sentiment": "neutral",
            "risk_level": "low",
            "suggested_reply": "退款正在处理中，有进展我们会及时通知您。",
        },
    },
    {
        "name": "已完成",
        "transcript": "客服：地址已经修改成功。客户：看到了，谢谢。",
        "analysis": {
            "customer_intent": "修改收货地址",
            "has_task": True,
            "task_title": "修改收货地址",
            "task_status": "completed",
            "priority": "low",
            "due_at": None,
            "customer_sentiment": "positive",
            "risk_level": "low",
            "suggested_reply": "不客气，如有其他问题请随时联系我们。",
        },
    },
    {
        "name": "投诉风险",
        "transcript": "客户：扣款两次还不退款，我要去监管部门投诉并曝光！",
        "analysis": {
            "customer_intent": "投诉重复扣款并要求退款",
            "has_task": True,
            "task_title": "紧急核查重复扣款",
            "task_status": "pending",
            "priority": "urgent",
            "due_at": None,
            "customer_sentiment": "angry",
            "risk_level": "critical",
            "suggested_reply": "非常抱歉给您带来困扰，我们会立即核查扣款记录并尽快反馈。",
        },
    },
    {
        "name": "无任务聊天",
        "transcript": "客户：你们周末营业吗？客服：营业时间是每天9点到18点。",
        "analysis": {
            "customer_intent": "咨询营业时间",
            "has_task": False,
            "task_title": None,
            "task_status": None,
            "priority": None,
            "due_at": None,
            "customer_sentiment": "neutral",
            "risk_level": "low",
            "suggested_reply": "我们每天9点到18点营业，欢迎您前来。",
        },
    },
]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_analyze_five_customer_service_cases(client_factory, case):
    client = client_factory(AnalysisResult.model_validate(case["analysis"]))
    response = client.post("/api/analyze", json={"transcript": case["transcript"]})
    assert response.status_code == 200
    assert response.json()["has_task"] == case["analysis"]["has_task"]
    assert response.json()["task_status"] == case["analysis"]["task_status"]
    assert response.json()["risk_level"] == case["analysis"]["risk_level"]


def test_confirm_then_list_task(client_factory):
    case = CASES[0]
    client = client_factory(AnalysisResult.model_validate(case["analysis"]))
    payload = {"transcript": case["transcript"], "analysis": case["analysis"]}
    created = client.post("/api/tasks/confirm", json=payload)
    assert created.status_code == 201
    assert created.json()["title"] == "补开发票"

    listed = client.get("/api/tasks")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_cannot_confirm_no_task(client_factory):
    case = CASES[4]
    client = client_factory(AnalysisResult.model_validate(case["analysis"]))
    response = client.post(
        "/api/tasks/confirm",
        json={"transcript": case["transcript"], "analysis": case["analysis"]},
    )
    assert response.status_code == 400


def test_analyze_rejects_blank_transcript(client_factory):
    case = CASES[0]
    client = client_factory(AnalysisResult.model_validate(case["analysis"]))
    response = client.post("/api/analyze", json={"transcript": "   "})
    assert response.status_code == 422


def test_deferred_task_is_remembered_and_recalled(client_factory):
    analysis = AnalysisResult.model_validate(
        {
            "customer_intent": "延期办理发票",
            "has_task": True,
            "task_title": "下周补开发票",
            "task_status": "pending",
            "priority": "medium",
            "due_at": None,
            "customer_sentiment": "neutral",
            "risk_level": "low",
            "suggested_reply": "好的，我们将在约定时间继续办理。",
            "should_remember": True,
            "memory_summary": "下周一继续办理补开发票",
            "memory_status": "deferred",
            "resume_at": "2026-07-27T09:00:00+08:00",
        }
    )
    client = client_factory(analysis)
    transcript = "客户：发票先别开，下周一再处理。"
    confirmed = client.post(
        "/api/tasks/confirm",
        json={
            "conversation_id": "customer-001",
            "transcript": transcript,
            "analysis": analysis.model_dump(mode="json"),
        },
    )
    assert confirmed.status_code == 201

    memories = client.get(
        "/api/memories", params={"conversation_id": "customer-001"}
    )
    assert memories.status_code == 200
    assert memories.json()[0]["status"] == "deferred"
    assert memories.json()[0]["summary"] == "下周一继续办理补开发票"

    analyzed = client.post(
        "/api/analyze",
        json={
            "conversation_id": "customer-001",
            "transcript": "客户：上次说的事情现在怎么样了？",
        },
    )
    assert analyzed.status_code == 200
    assert "下周一继续办理补开发票" in client.fake_llm.last_memory_context

    other = client.post(
        "/api/analyze",
        json={
            "conversation_id": "customer-002",
            "transcript": "客户：上次说的事情现在怎么样了？",
        },
    )
    assert other.status_code == 200
    assert client.fake_llm.last_memory_context is None

    memory_id = memories.json()[0]["id"]
    completed = client.patch(
        f"/api/memories/{memory_id}", json={"status": "completed"}
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert client.get(
        "/api/memories", params={"conversation_id": "customer-001"}
    ).json() == []
