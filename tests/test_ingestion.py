import pytest

from app.ingestion.cleaner import clean_text
from app.ingestion.loader import load_document


def test_load_text_file(tmp_path):
    file = tmp_path / "notes.txt"
    file.write_text("hello world", encoding="utf-8")

    doc = load_document(file)

    assert doc.text == "hello world"
    assert doc.metadata["source"] == "notes.txt"


def test_unsupported_extension(tmp_path):
    file = tmp_path / "image.png"
    file.write_bytes(b"")
    with pytest.raises(ValueError):
        load_document(file)


def test_clean_text():
    raw = "Retrieval   aug-\nmented\n\n\n\ngeneration "
    assert clean_text(raw) == "Retrieval augmented\n\ngeneration"
