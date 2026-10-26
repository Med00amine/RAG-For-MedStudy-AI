from app.ingestion.chunker import chunk_document, chunk_text


def test_short_text_is_single_chunk():
    assert chunk_text("short text", chunk_size=100) == ["short text"]


def test_chunks_respect_size():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(20))
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_long_word_is_hard_split():
    chunks = chunk_text("a" * 1000, chunk_size=200, overlap=0)
    assert all(len(c) <= 200 for c in chunks)


def test_chunk_metadata():
    chunks = chunk_document("one. two. three.", {"source": "x.txt"}, chunk_size=6, overlap=0)
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert all(c.metadata["source"] == "x.txt" for c in chunks)


def test_overlap_does_not_exceed_chunk_size():
    chunks = chunk_text("a" * 1000, chunk_size=200, overlap=50)
    assert all(len(c) <= 200 for c in chunks)
