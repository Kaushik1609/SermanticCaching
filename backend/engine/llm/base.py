"""CacheIQ Abstract LLM Layer."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResult:
    """Standardized response from any LLM provider."""
    text: str
    prompt_tokens: int
    completion_tokens: int
    provider: str


class BaseLLM(ABC):
    """Abstract interface for LLM backends."""

    @abstractmethod
    def generate(self, prompt: str) -> LLMResult:
        """Generate a response for a prompt.

        Returns (text, prompt_tokens, completion_tokens).
        """
        pass

