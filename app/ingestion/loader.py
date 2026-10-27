import io
import re
import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import docx
import olefile
from PIL import Image
from pptx import Presentation
from pptx.shapes.picture import Picture
from pypdf import PdfReader

Ocr = Callable[[Image.Image], str]
MIN_TEXT_CHARS = 20  # a page or slide with less text than this is probably an image
MIN_OCR_PIXELS = 300 * 300  # smaller pictures are logos and icons, not worth reading


@dataclass
class Page:
    text: str
    number: int | None = None  # page or slide number, when the format has one


@dataclass
class Document:
    pages: list[Page]
    metadata: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)


def _load_text(path: Path, ocr: Ocr | None = None) -> list[Page]:
    return [Page(path.read_text(encoding="utf-8"))]


def _load_pdf(path: Path, ocr: Ocr | None = None) -> list[Page]:
    reader = PdfReader(path)
    pages = [Page(page.extract_text() or "", i) for i, page in enumerate(reader.pages, start=1)]
    scanned = [p for p in pages if len(p.text.strip()) < MIN_TEXT_CHARS]
    if ocr and scanned:
        import pypdfium2  # renders pages to images, only needed for OCR

        pdf = pypdfium2.PdfDocument(path)
        for page in scanned:
            page.text = ocr(pdf[page.number - 1].render(scale=2).to_pil())
    return pages


def _shape_texts(shape) -> list[str]:
    if hasattr(shape, "shapes"):  # group shape
        return [t for s in shape.shapes for t in _shape_texts(s)]
    if shape.has_text_frame:
        return [shape.text_frame.text]
    if shape.has_table:
        return [" | ".join(cell.text for cell in row.cells) for row in shape.table.rows]
    return []


def _pictures(shapes) -> Iterator[Image.Image]:
    for shape in shapes:
        if hasattr(shape, "shapes"):  # group shape
            yield from _pictures(shape.shapes)
        elif isinstance(shape, Picture):
            try:
                image = Image.open(io.BytesIO(shape.image.blob))
                image.load()
            except Exception:  # linked or vector (EMF/WMF) pictures can't be read
                continue
            if image.width * image.height >= MIN_OCR_PIXELS:
                yield image


def _load_pptx(path: Path, ocr: Ocr | None = None) -> list[Page]:
    pages = []
    for number, slide in enumerate(Presentation(path).slides, start=1):
        parts = [t for shape in slide.shapes for t in _shape_texts(shape)]
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            parts.append(slide.notes_slide.notes_text_frame.text)
        text = "\n".join(parts)
        if ocr and len(text.strip()) < MIN_TEXT_CHARS:  # slide is a screenshot or a scan
            text = "\n".join([text, *map(ocr, _pictures(slide.shapes))])
        pages.append(Page(text, number))
    return pages


def _load_image(path: Path, ocr: Ocr | None = None) -> list[Page]:
    return [Page(ocr(Image.open(path)))] if ocr else []


def _load_docx(path: Path, ocr: Ocr | None = None) -> list[Page]:
    document = docx.Document(path)
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        parts += [" | ".join(cell.text for cell in row.cells) for row in table.rows]
    return [Page("\n".join(parts))]


# Legacy binary PowerPoint (MS-PPT) record types.
SLIDE, NOTES, MAIN_MASTER = 0x03EE, 0x03F0, 0x03F8
SLIDE_LIST, SLIDE_PERSIST, PERSIST_DIRECTORY = 0x0FF0, 0x03F3, 0x1772
TEXT_CHARS, TEXT_BYTES = 0x0FA0, 0x0FA8
SKIPPED_CONTAINERS = {NOTES, MAIN_MASTER}  # only template text like "Cliquez pour modifier"


def _records(data: bytes, start: int, end: int):
    """Yield (offset, ver_inst, rec_type, body_start, body_end) for each record in a range."""
    pos = start
    while pos + 8 <= end:
        ver_inst, rec_type, length = struct.unpack_from("<HHI", data, pos)
        yield pos, ver_inst, rec_type, pos + 8, min(pos + 8 + length, end)
        pos += 8 + length


def parse_ppt_stream(data: bytes) -> list[Page]:
    """Extract per-slide text from a 'PowerPoint Document' stream.

    SlideListWithText lists slides in presentation order (one SlidePersistAtom each) and,
    in older files, holds their text. Newer files keep text inside each Slide record,
    which the PersistDirectory maps back to its slide through the record's stream offset.
    """
    persist_ids: dict[int, int] = {}  # stream offset -> persist id
    for _, _, rec_type, body, end in _records(data, 0, len(data)):
        if rec_type == PERSIST_DIRECTORY:
            while body + 4 <= end:
                (header,) = struct.unpack_from("<I", data, body)
                first_id, count = header & 0xFFFFF, header >> 20
                offsets = struct.unpack_from(f"<{count}I", data, body + 4)
                persist_ids.update({off: first_id + i for i, off in enumerate(offsets)})
                body += 4 + 4 * count

    order: list[int] = []  # slide persist ids, in presentation order
    slides: dict[int, list[str]] = {}

    def walk(start: int, end: int, slide: int | None) -> None:
        for offset, ver_inst, rec_type, body, stop in _records(data, start, end):
            if ver_inst & 0xF == 0xF:  # container record
                if rec_type == SLIDE_LIST and ver_inst >> 4 == 0:  # instance 0 = slides
                    order.clear()
                    walk(body, stop, 0)
                elif rec_type == SLIDE:
                    if (persist_id := persist_ids.get(offset)) in order:  # else a title master
                        walk(body, stop, order.index(persist_id) + 1)
                elif rec_type not in SKIPPED_CONTAINERS:
                    walk(body, stop, slide)
            elif rec_type == SLIDE_PERSIST and slide is not None:
                order.append(struct.unpack_from("<I", data, body)[0])
                slide = len(order)
            elif rec_type in (TEXT_CHARS, TEXT_BYTES) and slide:
                encoding = "utf-16-le" if rec_type == TEXT_CHARS else "latin-1"
                text = data[body:stop].decode(encoding, errors="ignore")
                slides.setdefault(slide, []).append(re.sub(r"[\r\x0b]", "\n", text))

    walk(0, len(data), None)
    # Fast-saved files can hold several copies of the same text: keep the first one.
    return [Page("\n".join(dict.fromkeys(t)), number) for number, t in sorted(slides.items())]


def _load_ppt(path: Path, ocr: Ocr | None = None) -> list[Page]:
    with olefile.OleFileIO(path) as ole:
        return parse_ppt_stream(ole.openstream("PowerPoint Document").read())


LOADERS = {
    ".pdf": _load_pdf,
    ".pptx": _load_pptx,
    ".ppt": _load_ppt,
    ".docx": _load_docx,
    ".txt": _load_text,
    ".md": _load_text,
    ".jpg": _load_image,
    ".jpeg": _load_image,
    ".png": _load_image,
}
SUPPORTED_EXTENSIONS = set(LOADERS)


def clean_title(path: Path) -> str:
    """'1-[25-26]Physiologie du vieillissement .pdf' -> 'Physiologie du vieillissement'."""
    stem = re.sub(r"\.(pptx?|pdf|docx?)\b.*$", "", path.stem, flags=re.IGNORECASE)
    stem = re.sub(r"^\s*\d+\s*[-_.]?|\[\d+-\d+\]", "", stem)
    return re.sub(r"[_\s]+", " ", stem).strip(" -") or path.stem


def load_document(path: Path, ocr: Ocr | None = None) -> Document:
    """Load a file as pages; with `ocr`, scans, image-only slides and photos are read too."""
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    pages = [p for p in loader(path, ocr) if p.text.strip()]
    return Document(
        pages=pages,
        metadata={"source": path.name, "title": clean_title(path), "type": path.suffix[1:].lower()},
    )
