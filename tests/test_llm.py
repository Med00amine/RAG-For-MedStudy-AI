import json

import httpx
import pytest

from app.generation.llm import OllamaLLM


def make_llm(handler) -> OllamaLLM:
    llm = OllamaLLM(model="qwen2.5:7b", base_url="http://ollama")
    llm.client = httpx.Client(base_url="http://ollama", transport=httpx.MockTransport(handler))
    return llm


def test_ollama_streams_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        assert request.url.path == "/api/chat"
        assert body["model"] == "qwen2.5:7b"
        assert body["messages"][0] == {"role": "system", "content": "system"}
        assert body["options"]["num_ctx"] >= 8192
        lines = [
            {"message": {"role": "assistant", "content": "Classification "}, "done": False},
            {"message": {"role": "assistant", "content": "de Gharbi [1]"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True},
        ]
        return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines))

    tokens = make_llm(handler).stream("system", [{"role": "user", "content": "question"}])

    assert "".join(tokens) == "Classification de Gharbi [1]"


def test_ollama_error_raises():
    llm = make_llm(lambda request: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(httpx.HTTPStatusError):
        list(llm.stream("system", [{"role": "user", "content": "question"}]))
