from app.retrieval.retriever import Retriever
from app.services.ingestion_service import IngestionService


def test_ingest_then_retrieve(tmp_path, fake_embedder, store):
    (tmp_path / "pets.txt").write_text("My cat sleeps all day.", encoding="utf-8")
    (tmp_path / "code.txt").write_text("Python makes rag pipelines easy.", encoding="utf-8")
    ingestion = IngestionService(fake_embedder, store)
    for f in tmp_path.iterdir():
        assert ingestion.ingest(f) == 1

    retriever = Retriever(fake_embedder, store, top_k=2, min_score=0.5)
    results = retriever.retrieve("tell me about the cat")

    assert [r.metadata["source"] for r in results] == ["pets.txt"]


def test_source_filter(tmp_path, fake_embedder, store):
    (tmp_path / "a.txt").write_text("The cat sleeps on the sofa.", encoding="utf-8")
    (tmp_path / "b.txt").write_text("The cat sits in the car all day.", encoding="utf-8")
    ingestion = IngestionService(fake_embedder, store)
    for f in tmp_path.iterdir():
        ingestion.ingest(f)

    results = Retriever(fake_embedder, store, top_k=5, min_score=0).retrieve("cat", source="b.txt")

    assert [r.metadata["source"] for r in results] == ["b.txt"]


def test_reingest_replaces_chunks(tmp_path, fake_embedder, store):
    file = tmp_path / "pets.txt"
    file.write_text("My cat sleeps all day long.", encoding="utf-8")
    ingestion = IngestionService(fake_embedder, store)

    ingestion.ingest(file)
    ingestion.ingest(file)

    assert store.count() == 1
