from app.ingestion.chunker import Chunk


def test_add_and_search(store):
    chunks = [
        Chunk("about cats", {"source": "a.txt"}),
        Chunk("about cars", {"source": "b.txt"}),
    ]
    store.add(chunks, [[1.0, 0.0], [0.0, 1.0]])

    results = store.search([0.9, 0.1], top_k=1)

    assert store.count() == 2
    assert results[0].text == "about cats"
    assert results[0].score > 0.9


def test_metadata_filter(store):
    store.add(
        [Chunk("x", {"source": "a.txt"}), Chunk("y", {"source": "b.txt"})],
        [[1.0, 0.0], [0.9, 0.1]],
    )

    results = store.search([1.0, 0.0], top_k=2, where={"source": "b.txt"})

    assert [r.text for r in results] == ["y"]


def test_has_and_delete_source(store):
    store.add([Chunk("about cats", {"source": "a.txt"})], [[1.0, 0.0]], ids=["a.txt#0"])

    assert store.has_source("a.txt")
    assert not store.has_source("b.txt")

    store.delete_source("a.txt")
    assert store.count() == 0
