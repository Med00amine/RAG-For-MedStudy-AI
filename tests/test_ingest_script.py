from scripts.ingest import unique_files


def test_duplicate_lectures_are_indexed_once(tmp_path):
    shared = tmp_path / "C2 chir"
    nested = tmp_path / "DCEM2" / "S1" / "C2 chir"
    for folder in (shared, nested):
        folder.mkdir(parents=True)
        (folder / "hydatidose.txt").write_text("Kyste hydatique du foie", encoding="utf-8")
    (shared / "other.txt").write_text("Diverticulite", encoding="utf-8")
    (shared / "video.mp4").write_bytes(b"not a document")

    files = unique_files(tmp_path)

    assert [f.relative_to(tmp_path).as_posix() for f in files] == [
        "C2 chir/other.txt",
        "DCEM2/S1/C2 chir/hydatidose.txt",  # the copy with more folder context wins
    ]
