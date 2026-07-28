import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["UPLOAD_DIR"] = ".test_uploads"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.dependencies import get_llm_service
from app.main import app
from app.schemas import AnalysisResult, AutoReplyDecision


class FakeLLMService:
    def __init__(self, result: AnalysisResult) -> None:
        self.result = result
        self.last_memory_context: str | None = None
        self.auto_reply_result = AutoReplyDecision(
            should_reply=True,
            handoff_required=False,
            risk_level="low",
            reply="您好，已收到您的问题。",
            updated_summary="客户正在咨询问题，等待进一步处理。",
        )
        self.auto_reply_calls = 0
        self.last_auto_reply_context: str | None = None

    async def analyze(
        self, transcript: str, memory_context: str | None = None
    ) -> AnalysisResult:
        self.last_memory_context = memory_context
        return self.result

    async def decide_auto_reply(
        self, *, customer_message: str, context: str
    ) -> AutoReplyDecision:
        self.auto_reply_calls += 1
        self.last_auto_reply_context = context
        return self.auto_reply_result


@pytest.fixture
def client_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def make_client(result: AnalysisResult) -> TestClient:
        fake_llm = FakeLLMService(result)

        def override_db():
            with TestingSession() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_llm_service] = lambda: fake_llm
        client = TestClient(app)
        client.fake_llm = fake_llm
        return client

    yield make_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
