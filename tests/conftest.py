import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.dependencies import get_llm_service
from app.main import app
from app.schemas import AnalysisResult


class FakeLLMService:
    def __init__(self, result: AnalysisResult) -> None:
        self.result = result
        self.last_memory_context: str | None = None

    async def analyze(
        self, transcript: str, memory_context: str | None = None
    ) -> AnalysisResult:
        self.last_memory_context = memory_context
        return self.result


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
