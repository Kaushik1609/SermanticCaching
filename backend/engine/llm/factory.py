"""LLM Provider Factory."""

from backend.app import config
from backend.engine.llm.base import BaseLLM
from backend.engine.llm.mock_llm import MockLLM
from backend.engine.llm.gemini import GeminiLLM


def get_llm(provider: str = config.LLM_PROVIDER) -> BaseLLM:
    """Instantiate the configured LLM provider."""
    provider = (provider or "mock").lower()
    if provider == "gemini":
        return GeminiLLM()
    # Default to MockLLM for determinism & tests
    return MockLLM()

