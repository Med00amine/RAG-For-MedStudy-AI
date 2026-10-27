import json
from pathlib import Path

import pytest

from app.embeddings.embedder import get_embedder
from app.ingestion.chunker import chunk_document
from app.retrieval.retriever import Retriever

EVAL_FILE = Path(__file__).parents[1] / "data" / "evaluation" / "retrieval_eval.json"


@pytest.mark.slow
def test_retrieval_hit_rate(store):
    data = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    embedder = get_embedder()
    for name, text in data["documents"].items():
        chunks = chunk_document(text, {"source": name})
        store.add(chunks, embedder.embed_documents([c.text for c in chunks]))

    retriever = Retriever(embedder, store, top_k=1, min_score=0.0)
    hits = sum(
        retriever.retrieve(q["question"])[0].metadata["source"] == q["expected_source"]
        for q in data["questions"]
    )

    assert hits / len(data["questions"]) >= 0.8
