"""Compare embedding models on the French medical retrieval eval set.

    python -m scripts.evaluate_retrieval intfloat/multilingual-e5-small BAAI/bge-m3

Re-embeds the chunks already in the vector store with each model (no re-ingestion,
no OCR) and reports hit@1, hit@5 and MRR for data/evaluation/medical_retrieval_eval.json.
"""

import argparse
import json
import time
from pathlib import Path

import chromadb

from app.embeddings.embedder import Embedder
from app.repositories.vector_store import VectorStore, get_vector_store

EVAL_FILE = Path("data/evaluation/medical_retrieval_eval.json")
BATCH = 5000  # stay under Chroma's max batch size


def evaluate(model: str, chunks: dict, questions: list[dict], k: int) -> dict[str, float]:
    embedder = Embedder(model)
    store = VectorStore(chromadb.EphemeralClient(), f"eval-{abs(hash(model))}")
    start = time.perf_counter()
    pairs = zip(chunks["documents"], chunks["metadatas"], strict=True)
    texts = [f"{meta['title']}\n{doc}" for doc, meta in pairs]
    vectors = embedder.embed_documents(texts)
    for i in range(0, len(texts), BATCH):
        store.collection.add(
            ids=chunks["ids"][i : i + BATCH],
            documents=chunks["documents"][i : i + BATCH],
            metadatas=chunks["metadatas"][i : i + BATCH],
            embeddings=vectors[i : i + BATCH],
        )
    index_seconds = time.perf_counter() - start

    first_hits = []  # rank of the first relevant chunk, or None
    for q in questions:
        results = store.search(embedder.embed_query(q["question"]), top_k=k)
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
        "index_s": index_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("models", nargs="+")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    questions = json.loads(EVAL_FILE.read_text(encoding="utf-8"))["questions"]
    chunks = get_vector_store().collection.get(include=["documents", "metadatas"])
    print(f"{len(chunks['ids'])} chunks, {len(questions)} questions\n")
    print(f"{'model':48} {'hit@1':>6} {'hit@' + str(args.k):>6} {'MRR':>6} {'index':>8}")
    for model in args.models:
        m = evaluate(model, chunks, questions, args.k)
        print(
            f"{model:48} {m['hit@1']:6.2f} {m[f'hit@{args.k}']:6.2f} {m['mrr']:6.2f}"
            f" {m['index_s']:7.0f}s"
        )


if __name__ == "__main__":
    main()
