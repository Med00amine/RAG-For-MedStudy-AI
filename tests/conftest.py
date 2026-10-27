import chromadb
import pytest

from app.repositories.vector_store import VectorStore

VOCAB = ["cat", "car", "python", "rag"]


class FakeEmbedder:
    """Bag-of-words embedder over a tiny vocabulary — deterministic and model-free."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(w in t.lower()) + 1e-6 for w in VOCAB] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture
def store():
    client = chromadb.EphemeralClient()
    yield VectorStore(client, "test")
    client.delete_collection("test")
