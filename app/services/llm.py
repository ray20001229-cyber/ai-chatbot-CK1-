import json
from datetime import datetime

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import Settings
from app.schemas import AnalysisResult


SYSTEM_PROMPT = """你是资深中文客服质检助手。分析用户提供的完整客服聊天记录。
只根据对话内容判断，不要虚构事实。任务状态规则：
- pending：已经形成需要处理的事项，但尚未开始；
- in_progress：客服明确表示正在办理、已提交处理中或等待外部结果；
- completed：对话明确表明事项已解决或完成。
投诉、退款争议、法律/监管威胁、舆情风险、强烈愤怒应提高风险等级。
没有可执行或需记录事项的普通咨询，has_task 必须为 false。
截止时间只有在对话明确给出或可从明确相对时间推导时填写，否则为 null。
建议回复应专业、简洁、同理且不作无依据承诺。
记忆规则：
- 对仍需处理的任务，should_remember=true，memory_status=pending；
- 对明确表示“稍后再做、延期、改天处理、到某时再继续”的任务，
  should_remember=true，memory_status=deferred，并尽量提取 resume_at；
- 已完成事项和无任务聊天不创建新记忆；
- 如果提供了历史未完成记忆，应结合当前对话判断本次意图和建议回复，
  但不要虚构记忆中没有的进展。
当前时间：{now}
"""


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.openai_api_key
        self.uses_compatible_api = bool(settings.openai_base_url)
        kwargs: dict[str, str] = {"api_key": self.api_key or "not-configured"}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self.client = AsyncOpenAI(**kwargs)
        self.model = settings.openai_model

    async def analyze(
        self, transcript: str, memory_context: str | None = None
    ) -> AnalysisResult:
        if not self.api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY")
        user_content = transcript
        if memory_context:
            user_content = (
                f"该会话的历史未完成记忆：\n{memory_context}\n\n"
                f"本次聊天记录：\n{transcript}"
            )
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    now=datetime.now().astimezone().isoformat()
                ),
            },
            {"role": "user", "content": user_content},
        ]

        if self.uses_compatible_api:
            return await self._analyze_with_compatible_api(messages)

        completion = await self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=AnalysisResult,
            temperature=0,
        )
        message = completion.choices[0].message
        if message.refusal:
            raise ValueError(f"模型拒绝分析：{message.refusal}")
        if message.parsed is None:
            raise ValueError("模型未返回有效的结构化结果")
        return message.parsed

    async def _analyze_with_compatible_api(
        self, messages: list[dict[str, str]]
    ) -> AnalysisResult:
        schema = json.dumps(
            AnalysisResult.model_json_schema(), ensure_ascii=False, separators=(",", ":")
        )
        messages[0]["content"] += (
            "\n必须只返回一个 JSON 对象，不要返回 Markdown、代码围栏或解释文字。"
            f"JSON 必须严格符合以下 Schema：{schema}"
        )
        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("模型未返回内容")
        cleaned = content.strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        try:
            return AnalysisResult.model_validate_json(cleaned)
        except ValidationError as exc:
            raise ValueError(f"模型返回内容未通过 Pydantic 校验：{exc}") from exc
