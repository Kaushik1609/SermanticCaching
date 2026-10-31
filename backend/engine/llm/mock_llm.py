"""Mock LLM implementation for deterministic, reproducible testing and demo."""

import time
from backend.app import config
from backend.engine.llm.base import BaseLLM, LLMResult


class MockLLM(BaseLLM):
    """Deterministic LLM that simulates realistic latency and token consumption."""

    def __init__(self, latency_ms: int = config.MOCK_LLM_LATENCY_MS, simulated_latency_ms: int = None):
        self.latency_ms = simulated_latency_ms if simulated_latency_ms is not None else latency_ms

    def generate(self, prompt: str) -> LLMResult:
        # Simulate network & generation latency
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

        # Deterministic mock response
        text = f"[mock answer] {prompt.strip()}"

        # Standard simulated token counts
        prompt_tokens = max(5, len(prompt.split()) + 8)
        completion_tokens = 34

        return LLMResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider="mock",
        )

