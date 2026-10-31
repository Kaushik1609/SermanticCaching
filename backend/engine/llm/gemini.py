"""Google Gemini LLM Integration via google-genai SDK."""

import os
from backend.app import config
from backend.engine.llm.base import BaseLLM, LLMResult


class GeminiLLM(BaseLLM):
    """Real Gemini LLM client with 20s timeout."""

    def __init__(self, api_key: str = config.GEMINI_API_KEY, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name
        self._client = None

        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                self._client = None

    def generate(self, prompt: str) -> LLMResult:
        if not self._client:
            raise RuntimeError("Gemini API key is not configured or google-genai client failed to initialize.")

        try:
            # Call Gemini with 20 second timeout
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )

            text = response.text or ""
            # Extract usage metadata if available
            prompt_tokens = 0
            completion_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                completion_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            if prompt_tokens == 0:
                prompt_tokens = len(prompt.split()) + 5
            if completion_tokens == 0:
                completion_tokens = len(text.split())

            return LLMResult(
                text=text,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                provider="gemini",
            )
        except Exception as e:
            raise RuntimeError(f"Gemini API call failed: {str(e)}") from e

