"""Index every supported file under a folder into the vector store.

    python -m scripts.ingest data/raw/drive [--force] [--no-ocr]

Each file is stored under its path relative to the folder, which is what answers cite.
Identical copies are indexed once, and files already in the store are skipped, so an
interrupted run can simply be restarted.
"""

import argparse
import hashlib
import importlib.util
import sys
import time
from pathlib import Path

from app.core.logging import setup_logging
from app.embeddings.embedder import get_embedder
from app.ingestion.loader import SUPPORTED_EXTENSIONS
from app.repositories.vector_store import get_vector_store
from app.services.ingestion_service import IngestionService


def unique_files(folder: Path) -> list[Path]:
    """Each distinct file once: the same lecture is often shared in several Drive folders."""
    by_content: dict[str, Path] = {}
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        # Keep the copy with the most folder context: it makes clearer citations.
        if digest not in by_content or len(path.parts) > len(by_content[digest].parts):
            by_content[digest] = path
    return sorted(by_content.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--force", action="store_true", help="re-index files already stored")
    parser.add_argument("--no-ocr", action="store_true", help="skip scanned pages and images")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    setup_logging("WARNING")

    ocr = None
    if not args.no_ocr:
        if importlib.util.find_spec("easyocr"):
            from app.ingestion.ocr import ocr_image as ocr
        else:
            print('EasyOCR not installed (pip install -e ".[ocr]"): scanned pages are skipped')

    store = get_vector_store()
    service = IngestionService(get_embedder(), store, ocr=ocr)
    files = unique_files(args.folder)
    new_chunks, failed = 0, []
    for i, path in enumerate(files, start=1):
        source = path.relative_to(args.folder).as_posix()
        if not args.force and store.has_source(source):
            continue
        start = time.perf_counter()
        try:
            chunks = service.ingest(path, source=source)
        except Exception as exc:  # one corrupt file shouldn't stop the run
            failed.append(source)
            print(f"[{i}/{len(files)}] FAILED {source}: {exc}", flush=True)
            continue
        new_chunks += chunks
        elapsed = time.perf_counter() - start
        print(f"[{i}/{len(files)}] {chunks:5d} chunks {elapsed:6.1f}s  {source}", flush=True)

    print(f"\n{new_chunks} new chunks, {store.count()} in the store, {len(failed)} files failed")


if __name__ == "__main__":
    main()
