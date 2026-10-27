import json

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_ingestion_service, get_rag_service
from app.core.config import get_settings
from app.main import app
from app.repositories.vector_store import get_vector_store
from app.retrieval.retriever import Retriever
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RagService
from tests.test_rag_service import FakeLLM


@pytest.fixture
def client(fake_embedder, store, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "admin_token", "s3cret")
    retriever = Retriever(fake_embedder, store, top_k=3, min_score=0.5)
    app.dependency_overrides[get_ingestion_service] = lambda: IngestionService(fake_embedder, store)
    app.dependency_overrides[get_rag_service] = lambda: RagService(retriever, FakeLLM())
    app.dependency_overrides[get_vector_store] = lambda: store
    yield TestClient(app, headers={"X-Admin-Token": "s3cret"})
    app.dependency_overrides.clear()


@pytest.mark.parametrize("token", ["", "wrong"])
def test_upload_requires_admin_token(client, token):
    response = client.post(
        "/documents",
        files={"file": ("fake.txt", b"Fake course content")},
        headers={"X-Admin-Token": token},
    )
    assert response.status_code == 403


def test_upload_disabled_without_configured_token(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_token", "")
    response = client.post("/documents", files={"file": ("fake.txt", b"Fake course content")})
    assert response.status_code == 403


def test_upload_then_query(client):
    upload = client.post("/documents", files={"file": ("pets.txt", b"My cat sleeps all day.")})
    assert upload.status_code == 201
    assert upload.json() == {"filename": "pets.txt", "chunks": 1}

    response = client.post("/query", json={"question": "What does the cat do?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Cats sleep a lot [1]."
    assert body["sources"][0]["source"] == "pets.txt"


def test_upload_rejects_unsupported_type(client):
    response = client.post("/documents", files={"file": ("lecture.mp4", b"...")})
    assert response.status_code == 415


def test_query_validation(client):
    assert client.post("/query", json={"question": ""}).status_code == 422


class BrokenLLM:
    def stream(self, system, messages):
        request = httpx2.Request("POST", "https://api.anthropic.com")
        raise anthropic.APIConnectionError(request=request)
        yield  # makes this a generator, like a real streaming client


def use_broken_llm(client, fake_embedder, store):
    retriever = Retriever(fake_embedder, store, top_k=3, min_score=0.5)
    app.dependency_overrides[get_rag_service] = lambda: RagService(retriever, BrokenLLM())
    client.post("/documents", files={"file": ("pets.txt", b"My cat sleeps all day.")})


def test_llm_failure_returns_502(client, fake_embedder, store):
    use_broken_llm(client, fake_embedder, store)

    response = client.post("/query", json={"question": "What does the cat do?"})

    assert response.status_code == 502


def test_chat_streams_sources_then_tokens(client):
    client.post("/documents", files={"file": ("pets.txt", b"My cat sleeps all day.")})

    response = client.post(
        "/chat",
        json={
            "question": "What does the cat do?",
            "history": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
            ],
        },
    )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.headers["content-type"] == "application/x-ndjson"
    assert events[0]["type"] == "sources"
    assert events[0]["sources"][0]["title"] == "pets"
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Cats sleep a lot [1]."
    assert events[-1] == {"type": "done"}


def test_chat_reports_llm_failure_in_stream(client, fake_embedder, store):
    use_broken_llm(client, fake_embedder, store)

    response = client.post("/chat", json={"question": "What does the cat do?"})

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [e["type"] for e in events] == ["sources", "error", "done"]


def test_documents_lists_the_library(client):
    client.post("/documents", files={"file": ("pets.txt", b"My cat sleeps all day.")})

    body = client.get("/documents").json()

    assert body["uploads_enabled"] is True
    assert ".pdf" in body["upload_types"]
    assert body["documents"] == [
        {
            "source": "pets.txt",
            "title": "pets",
            "type": "txt",
            "chunks": 1,
            "textbook": False,
            "openable": True,
        }
    ]


def test_original_file_is_served(client):
    client.post("/documents", files={"file": ("pets.txt", b"My cat sleeps all day.")})

    response = client.get("/documents/file", params={"source": "pets.txt"})

    assert response.status_code == 200
    assert response.text == "My cat sleeps all day."
    assert response.headers["content-disposition"].startswith("inline")


def test_textbooks_and_files_outside_the_library_are_not_served(
    client, fake_embedder, store, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "source_dirs", [str(tmp_path / "drive")])
    service = IngestionService(fake_embedder, store)
    for name, source in [
        ("drive/DCEM2/Books/cardio.txt", "DCEM2/Books/cardio.txt"),
        ("private/secret.txt", "../private/secret.txt"),
    ]:
        path = tmp_path / name
        path.parent.mkdir(parents=True)
        path.write_text("My cat sleeps all day long.")
        service.ingest(path, source=source)

    listing = {d["source"]: d for d in client.get("/documents").json()["documents"]}

    assert listing["DCEM2/Books/cardio.txt"]["textbook"] is True
    for source in ["DCEM2/Books/cardio.txt", "../private/secret.txt", "missing.txt"]:
        assert client.get("/documents/file", params={"source": source}).status_code == 404
        assert not listing.get(source, {}).get("openable")


def test_delete_document(client):
    client.post("/documents", files={"file": ("pets.txt", b"My cat sleeps all day.")})
    params = {"source": "pets.txt"}

    forbidden = client.delete("/documents", params=params, headers={"X-Admin-Token": ""})

    assert forbidden.status_code == 403
    assert client.delete("/documents", params=params).status_code == 204
    assert client.get("/documents").json()["documents"] == []
    assert client.delete("/documents", params=params).status_code == 404
