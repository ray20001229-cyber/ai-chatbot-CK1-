import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Conversation, ConversationMemory, Customer, Message, Task


def build_context(
    db: Session,
    *,
    conversation: Conversation,
    customer_message: Message,
    settings: Settings,
) -> str:
    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.id != customer_message.id,
            )
            .order_by(Message.received_at.desc())
            .limit(100)
        )
    )
    recent = messages[: settings.auto_reply_recent_messages]
    recent_ids = {message.id for message in recent}
    terms = _terms(customer_message.content)
    relevant = sorted(
        (
            (len(terms & _terms(message.content)), message)
            for message in messages
            if message.id not in recent_ids
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    selected = recent + [
        message
        for score, message in relevant[
            : settings.auto_reply_relevant_messages
        ]
        if score > 0
    ]
    selected.sort(key=lambda message: message.received_at)

    sections: list[str] = []
    if conversation.memory_summary:
        sections.append("历史摘要：\n" + conversation.memory_summary)
    if conversation.customer_id:
        customer = db.get(Customer, conversation.customer_id)
        if customer:
            sections.append(
                "客户资料：\n"
                f"姓名：{customer.name}\n"
                f"外部编号：{customer.external_id}\n"
                f"备注：{customer.notes or '无'}"
            )

    legacy_id = conversation.external_id
    tasks = list(
        db.scalars(
            select(Task)
            .where(
                Task.conversation_id == legacy_id,
                Task.status != "completed",
            )
            .order_by(Task.updated_at.desc())
            .limit(10)
        )
    )
    memories = list(
        db.scalars(
            select(ConversationMemory)
            .where(
                ConversationMemory.conversation_id == legacy_id,
                ConversationMemory.status != "completed",
            )
            .order_by(ConversationMemory.updated_at.desc())
            .limit(10)
        )
    )
    if tasks:
        sections.append(
            "未完成任务：\n"
            + "\n".join(
                f"- {task.title}；状态={task.status}；截止={task.due_at or '未指定'}"
                for task in tasks
            )
        )
    if memories:
        sections.append(
            "待处理记忆：\n"
            + "\n".join(
                f"- {memory.summary}；状态={memory.status}；恢复时间={memory.resume_at or '未指定'}"
                for memory in memories
            )
        )
    if selected:
        sections.append(
            "筛选后的历史消息：\n"
            + "\n".join(
                f"[{message.sender_type}] {message.content}"
                for message in selected
            )
        )
    context = "\n\n".join(sections) or "没有可用的历史上下文。"
    return context[-settings.auto_reply_max_context_chars :]


def _terms(text: str) -> set[str]:
    chunks = set(re.findall(r"[a-zA-Z0-9]{2,}", text.lower()))
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        chunks.add(phrase)
        chunks.update(
            phrase[index : index + 2]
            for index in range(max(0, len(phrase) - 1))
        )
    return chunks
