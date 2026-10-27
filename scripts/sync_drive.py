"""Download course material from public Google Drive folders.

    python -m scripts.sync_drive <folder_url> [<folder_url> ...] --exclude Books --exclude .mp4

Walks each folder recursively, downloads regular files, exports Google Slides/Docs to
PPTX/DOCX, and fixes missing file extensions by sniffing the content. Files that are
already on disk are skipped, so the script can be re-run to pick up new material.
"""

import argparse
import html
import re
import sys
import time
import zipfile
from pathlib import Path

import olefile
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ENTRY = re.compile(
    r'<div class="flip-entry" id="entry-([\w-]+)".*?href="([^"]+)"'
    r'.*?<div class="flip-entry-title">([^<]*)</div>',
    re.S,
)
TITLE = re.compile(r"<title>([^<]*)</title>")
TARGET_ID = re.compile(r"/(?:folders|d)/([\w-]+)")
DOWNLOAD_URL = "https://drive.usercontent.google.com/download?id={id}&export=download&confirm=t"
KNOWN_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".mp4"}
EXPORTS = {
    "/presentation/": ("https://docs.google.com/presentation/d/{id}/export/pptx", ".pptx"),
    "/document/": ("https://docs.google.com/document/d/{id}/export?format=docx", ".docx"),
}


def safe(name: str) -> str:
    """Make a Drive name usable as a Windows/Linux path component."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip().rstrip(".") or "_"


def list_folder(
    session: requests.Session, folder_id: str
) -> tuple[str, list[tuple[str, str, str]]]:
    resp = session.get(f"https://drive.google.com/embeddedfolderview?id={folder_id}", timeout=30)
    resp.raise_for_status()
    title = TITLE.search(resp.text)
    entries = [(i, html.unescape(h), html.unescape(t)) for i, h, t in ENTRY.findall(resp.text)]
    return html.unescape(title.group(1)) if title else folder_id, entries


def walk(session, folder_id: str, path: Path, seen: set[str] | None = None):
    """Yield (file_id, href, relative_path) for every file below a folder."""
    seen = set() if seen is None else seen
    if folder_id in seen:  # shortcuts can point back up the tree
        return
    seen.add(folder_id)
    try:
        _, entries = list_folder(session, folder_id)
    except requests.RequestException as exc:  # a private or flaky subfolder: skip it
        print(f"SKIP folder {path}: {exc}", flush=True)
        return
    for entry_id, href, title in entries:
        # A shortcut has its own entry id; its link points at the real file or folder.
        target = TARGET_ID.search(href)
        item_id = target.group(1) if target else entry_id
        if "/drive/folders/" in href:
            time.sleep(0.3)  # be gentle with Drive
            yield from walk(session, item_id, path / safe(title), seen)
        else:
            yield item_id, href, path / safe(title)


def sniff_extension(path: Path) -> str:
    head = path.read_bytes()[:8]
    if head.startswith(b"%PDF"):
        return ".pdf"
    if head.startswith(b"PK"):
        names = zipfile.ZipFile(path).namelist()
        for folder, ext in (("ppt/", ".pptx"), ("word/", ".docx")):
            if any(n.startswith(folder) for n in names):
                return ext
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return ".ppt" if olefile.OleFileIO(path).exists("PowerPoint Document") else ".doc"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG"):
        return ".png"
    return ""


def already_downloaded(dest: Path) -> bool:
    """True if the file exists, possibly under a name with an extension we added."""
    if dest.exists():
        return True
    return dest.parent.is_dir() and any(
        p.name.startswith(dest.name + ".") for p in dest.parent.iterdir()
    )


def fetch(session, url: str, dest: Path, retries: int = 3) -> None:
    """Stream a URL to disk, backing off when Drive rate-limits or returns an HTML error page."""
    tmp = dest.with_name(f".{dest.name}.part")  # never leave a truncated file under the real name
    for attempt in range(retries + 1):
        with session.get(url, stream=True, timeout=120) as resp:
            is_html = "text/html" in resp.headers.get("Content-Type", "")
            if resp.ok and not is_html:
                with tmp.open("wb") as f:
                    for block in resp.iter_content(1 << 20):
                        f.write(block)
                tmp.replace(dest)
                return
            if is_html and "permission to download" in resp.text:
                # The owner made the file view-only: retrying won't help, and we respect it.
                raise PermissionError("the owner has disabled downloads for this file")
        if attempt < retries:
            time.sleep(15 * 2**attempt)
    raise RuntimeError(f"Drive refused the download (HTTP {resp.status_code})")


def download(session, file_id: str, href: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = DOWNLOAD_URL
    for marker, (export_url, ext) in EXPORTS.items():
        if marker in href:
            url, dest = export_url, dest.with_name(dest.name + ext)
    fetch(session, url.format(id=file_id), dest)
    if dest.suffix.lower() not in KNOWN_EXTENSIONS and (ext := sniff_extension(dest)):
        dest = dest.rename(dest.with_name(dest.name + ext))
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("folders", nargs="+", help="public Google Drive folder URLs")
    parser.add_argument("--out", default="data/raw/drive", type=Path)
    parser.add_argument("--exclude", action="append", default=[], help="skip paths containing this")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")  # Windows consoles can't print every accent

    session = requests.Session()
    # Drive drops connections now and then during long syncs: retry them with backoff.
    retry = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    downloaded, skipped, failed = 0, 0, []
    for url in args.folders:
        folder_id = url.rstrip("/").split("/")[-1].split("?")[0]
        title, _ = list_folder(session, folder_id)
        for file_id, href, rel in walk(session, folder_id, Path(safe(title))):
            if any(p.lower() in str(rel).lower() for p in args.exclude):
                continue
            dest = args.out / rel
            if already_downloaded(dest):
                skipped += 1
                continue
            try:
                saved = download(session, file_id, href, dest)
                downloaded += 1
                print(f"ok   {saved.relative_to(args.out)}", flush=True)
                time.sleep(1)  # stay under Drive's anonymous download rate limit
            except Exception as exc:  # keep going: one bad file shouldn't stop the sync
                failed.append(str(rel))
                print(f"FAIL {rel}: {exc}", flush=True)

    print(f"\n{downloaded} downloaded, {skipped} already present, {len(failed)} failed")


if __name__ == "__main__":
    main()
