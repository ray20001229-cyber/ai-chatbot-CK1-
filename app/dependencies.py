from functools import lru_cache

from app.config import get_settings
from app.services.llm import LLMService


@lru_cache
def get_llm_service() -> LLMService:
    return LLMService(get_settings())

