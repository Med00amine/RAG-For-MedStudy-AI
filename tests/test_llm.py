import httpx
import pytest

from app.generation.llm import OllamaLLM


def make_llm(handler) -> OllamaLLM:
    llm = OllamaLLM(model="llama3.2", base_url="http://ollama")
    llm.client = httpx.Client(base_url="http://ollama", transport=httpx.MockTransport(handler))
    return llm


def test_ollama_generate():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert request.url.path == "/api/chat"
        assert '"model":"llama3.2"' in body.replace(" ", "")
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Hi [1]"}})

    assert make_llm(handler).generate("system", "question") == "Hi [1]"


def test_ollama_error_raises():
    llm = make_llm(lambda request: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(httpx.HTTPStatusError):
        llm.generate("system", "question")
