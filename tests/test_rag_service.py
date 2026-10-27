from app.ingestion.chunker import Chunk
from app.retrieval.retriever import Retriever
from app.services.rag_service import NO_CONTEXT_ANSWER, RagService


class FakeLLM:
    def __init__(self):
        self.calls: list[list[dict]] = []

    def stream(self, system: str, messages: list[dict]):
        self.calls.append(messages)
        yield from ["Cats sleep ", "a lot [1]."]


def make_service(fake_embedder, store, llm, min_score=0.5):
    return RagService(Retriever(fake_embedder, store, top_k=3, min_score=min_score), llm)


def add(store, fake_embedder, text: str, source: str, **meta):
    store.add([Chunk(text, {"source": source, **meta})], fake_embedder.embed_documents([text]))


def test_answer_uses_retrieved_context(fake_embedder, store):
    add(store, fake_embedder, "My cat sleeps all day.", "pets.txt", title="Pets", page=3)
    llm = FakeLLM()

    result = make_service(fake_embedder, store, llm).ask("What does the cat do?")

    assert result.answer == "Cats sleep a lot [1]."
    prompt = llm.calls[0][-1]["content"]
    assert "[1] Pets — page 3\nMy cat sleeps all day." in prompt
    assert result.sources[0].metadata["source"] == "pets.txt"


def test_no_relevant_context_skips_llm(fake_embedder, store):
    add(store, fake_embedder, "Python tips and tricks", "code.txt")
    llm = FakeLLM()

    result = make_service(fake_embedder, store, llm).ask("Tell me about cars")

    assert result.answer == NO_CONTEXT_ANSWER
    assert llm.calls == []


def test_follow_up_question_uses_history(fake_embedder, store):
    add(store, fake_embedder, "My cat sleeps all day.", "pets.txt")
    llm = FakeLLM()
    history = [
        {"role": "user", "content": "Tell me about my cat"},
        {"role": "assistant", "content": "Your cat sleeps a lot."},
    ]

    service = make_service(fake_embedder, store, llm, min_score=0.6)

    # "and then?" alone matches nothing; with the previous question it finds the cat.
    assert service.retrieve("and then?") == []
    result = service.ask("and then?", history)

    assert result.sources[0].metadata["source"] == "pets.txt"
    assert llm.calls[0][:2] == history
