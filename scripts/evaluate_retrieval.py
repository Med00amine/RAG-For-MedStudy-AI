"""Compare embedding models on the French medical retrieval eval set.

    python -m scripts.evaluate_retrieval intfloat/multilingual-e5-small BAAI/bge-m3
    python -m scripts.evaluate_retrieval intfloat/multilingual-e5-base --penalties 0 0.02

Re-embeds the chunks already in the vector store with each model (no re-ingestion,
no OCR) and reports hit@1, hit@5 and MRR for data/evaluation/medical_retrieval_eval.json,
for each textbook ranking penalty, using the same Retriever as the app.
"""

import argparse
import json
import time
from pathlib import Path

import chromadb

from app.core.config import get_settings
from app.embeddings.embedder import Embedder
from app.repositories.vector_store import VectorStore, get_vector_store
from app.retrieval.retriever import Retriever

EVAL_FILE = Path("data/evaluation/medical_retrieval_eval.json")
BATCH = 5000  # stay under Chroma's max batch size


def all_chunks(store: VectorStore) -> dict[str, list]:
    """Every stored chunk, read in pages: one big get() exceeds SQLite's variable limit."""
    chunks: dict[str, list] = {"ids": [], "documents": [], "metadatas": []}
    for offset in range(0, store.count(), BATCH):
        page = store.collection.get(include=["documents", "metadatas"], limit=BATCH, offset=offset)
        for key, values in chunks.items():
            values += page[key]
    return chunks


def build_store(embedder: Embedder, chunks: dict, name: str) -> VectorStore:
    store = VectorStore(chromadb.EphemeralClient(), name)
    pairs = zip(chunks["documents"], chunks["metadatas"], strict=True)
    vectors = embedder.embed_documents([f"{meta['title']}\n{doc}" for doc, meta in pairs])
    for i in range(0, len(vectors), BATCH):
        store.collection.add(
            ids=chunks["ids"][i : i + BATCH],
            documents=chunks["documents"][i : i + BATCH],
            metadatas=chunks["metadatas"][i : i + BATCH],
            embeddings=vectors[i : i + BATCH],
        )
    return store


def score(retriever: Retriever, questions: list[dict], k: int) -> dict[str, float]:
    first_hits = []  # rank of the first chunk from an expected lecture, or None
    for q in questions:
        results = retriever.retrieve(q["question"])
        ranks = [
            rank
            for rank, r in enumerate(results, start=1)
            if any(e in r.metadata["source"].lower() for e in q["expected"])
        ]
        first_hits.append(ranks[0] if ranks else None)
    n = len(questions)
    return {
        "hit@1": sum(r == 1 for r in first_hits) / n,
        f"hit@{k}": sum(r is not None for r in first_hits) / n,
        "mrr": sum(1 / r for r in first_hits if r) / n,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("models", nargs="+")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--penalties", type=float, nargs="+", default=[0.0])
    args = parser.parse_args()

    settings = get_settings()
    eval_set = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    questions, off_topic = eval_set["questions"], eval_set["off_topic"]
    chunks = all_chunks(get_vector_store())
    print(f"{len(chunks['ids'])} chunks, {len(questions)} questions, {len(off_topic)} off-topic\n")
    print(
        f"{'model':42} {'penalty':>7} {'hit@1':>6} {'hit@' + str(args.k):>6} {'MRR':>6}"
        f" {'course min':>11} {'off-topic max':>14}"
    )
    for model in args.models:
        start = time.perf_counter()
        embedder = Embedder(model)
        store = build_store(embedder, chunks, f"eval-{abs(hash(model))}")
        # Raw similarity of the best match shows where MIN_SCORE must sit.
        best = [store.search(embedder.embed_query(q["question"]), 1)[0].score for q in questions]
        off = [store.search(embedder.embed_query(q), 1)[0].score for q in off_topic]
        for penalty in args.penalties:
            retriever = Retriever(
                embedder, store, args.k, 0.0, settings.textbook_paths, textbook_penalty=penalty
            )
            m = score(retriever, questions, args.k)
            print(
                f"{model:42} {penalty:7.3f} {m['hit@1']:6.2f} {m[f'hit@{args.k}']:6.2f}"
                f" {m['mrr']:6.2f} {min(best):11.3f} {max(off):14.3f}"
            )
        print(f"  (indexed and scored in {time.perf_counter() - start:.0f}s)")


if __name__ == "__main__":
    main()
