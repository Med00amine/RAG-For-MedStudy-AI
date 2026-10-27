import json
from collections.abc import Iterator
from typing import Protocol

import anthropic
import httpx

Message = dict[str, str]  # {"role": "user" | "assistant", "content": "..."}


class LLM(Protocol):
    def stream(self, system: str, messages: list[Message]) -> Iterator[str]:
        """Yield the answer piece by piece as the model writes it."""
        ...


class ClaudeLLM:
    def __init__(self, model: str, max_tokens: int):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def stream(self, system: str, messages: list[Message]) -> Iterator[str]:
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            # Re-route to a fallback model if the request is declined by safety classifiers.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            yield from stream.text_stream
            if stream.get_final_message().stop_reason == "refusal":
                yield "\n\nThe model declined to answer this question."


class OllamaLLM:
    """Free, local open-source models (Qwen, Llama, Mistral...) served by Ollama."""

    def __init__(self, model: str, base_url: str, timeout: float = 300.0):
        self.client = httpx.Client(base_url=base_url, timeout=timeout)
        self.model = model

    def stream(self, system: str, messages: list[Message]) -> Iterator[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            # Ollama's default context window is too small for several course excerpts, and
            # a capped answer length keeps one runaway generation from blocking the queue.
            "options": {"num_ctx": 8192, "num_predict": 1024, "temperature": 0.3},
            "keep_alive": "30m",  # avoid a cold start between two student questions
        }
        with self.client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    yield json.loads(line).get("message", {}).get("content", "")
