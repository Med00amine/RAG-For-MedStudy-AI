from typing import Protocol

import anthropic
import httpx


class LLM(Protocol):
    def generate(self, system: str, prompt: str) -> str: ...


class ClaudeLLM:
    def __init__(self, model: str, max_tokens: int):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def generate(self, system: str, prompt: str) -> str:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            # Re-route to a fallback model if the request is declined by safety classifiers.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            return "The model declined to answer this question."
        return "".join(b.text for b in response.content if b.type == "text")


class OllamaLLM:
    """Free, local open-source models (Llama, Mistral, Qwen...) served by Ollama."""

    def __init__(self, model: str, base_url: str, timeout: float = 120.0):
        self.client = httpx.Client(base_url=base_url, timeout=timeout)
        self.model = model

    def generate(self, system: str, prompt: str) -> str:
        response = self.client.post(
            "/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
