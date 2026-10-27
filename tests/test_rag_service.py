from app.ingestion.chunker import Chunk
from app.retrieval.retriever import Retriever
from app.services.rag_service import NO_CONTEXT_ANSWER, RagService


class FakeLLM:
    def __init__(self):
        self.prompts: list[str] = []

    def generate(self, system: str, prompt: str) -> str:
        self.prompts.append(prompt)
        return "Cats sleep a lot [1]."


def make_service(fake_embedder, store, llm):
    return RagService(Retriever(fake_embedder, store, top_k=3, min_score=0.5), llm)


def test_answer_uses_retrieved_context(fake_embedder, store):
    store.add(
        [Chunk("My cat sleeps all day.", {"source": "pets.txt"})],
        fake_embedder.embed_documents(["cat"]),
    )
    llm = FakeLLM()

    result = make_service(fake_embedder, store, llm).ask("What does the cat do?")

    assert result.answer == "Cats sleep a lot [1]."
    assert "My cat sleeps all day." in llm.prompts[0]
    assert result.sources[0].metadata["source"] == "pets.txt"


def test_no_relevant_context_skips_llm(fake_embedder, store):
    store.add(
        [Chunk("Python tips", {"source": "code.txt"})], fake_embedder.embed_documents(["python"])
    )
    llm = FakeLLM()

    result = make_service(fake_embedder, store, llm).ask("Tell me about cars")

    assert result.answer == NO_CONTEXT_ANSWER
    assert llm.prompts == []
