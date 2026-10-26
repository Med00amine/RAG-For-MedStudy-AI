"""Rough embedding throughput benchmark: python -m scripts.benchmark_embeddings"""

import time

from app.embeddings.embedder import get_embedder

texts = ["Retrieval-augmented generation grounds LLM answers in documents."] * 256

embedder = get_embedder()
embedder.embed(texts[:8])  # warm-up

for batch in (1, 32, 256):
    start = time.perf_counter()
    embedder.embed(texts[:batch])
    elapsed = time.perf_counter() - start
    print(f"batch={batch:>3}  {elapsed:.3f}s  {batch / elapsed:.0f} texts/s")
