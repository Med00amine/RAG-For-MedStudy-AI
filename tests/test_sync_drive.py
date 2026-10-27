from pathlib import Path

import pytest

pytest.importorskip("requests")
from scripts.sync_drive import walk  # noqa: E402


def entry(entry_id: str, href: str, title: str) -> str:
    return (
        f'<div class="flip-entry" id="entry-{entry_id}"><a href="{href}"></a>'
        f'<div class="flip-entry-title">{title}</div></div>'
    )


class FakeDrive:
    """Serves Drive's embedded folder view for a few hand-written folders."""

    folders = {
        "root": entry("f1", "https://drive.google.com/file/d/file1/view", "a.pdf")
        # a shortcut: its entry id differs from the folder it points to
        + entry("shortcut1", "https://drive.google.com/drive/folders/old", "Anciens drives"),
        "old": entry("f2", "https://drive.google.com/file/d/file2/view", "b.pdf")
        + entry("shortcut2", "https://drive.google.com/drive/folders/root", "Back to root"),
    }

    def get(self, url, timeout):
        folder_id = url.split("id=")[1]

        class Response:
            text = f"<title>{folder_id}</title>" + self.folders.get(folder_id, "")

            def raise_for_status(self):
                pass

        return Response()


def test_walk_follows_shortcuts_without_looping():
    files = [(file_id, rel.as_posix()) for file_id, _, rel in walk(FakeDrive(), "root", Path("R"))]

    assert files == [("file1", "R/a.pdf"), ("file2", "R/Anciens drives/b.pdf")]
