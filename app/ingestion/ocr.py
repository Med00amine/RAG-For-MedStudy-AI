"""OCR for scanned pages, image-only slides and photos.

Optional: install with `pip install -e ".[ocr]"`. Uses the GPU when PyTorch can see one.
"""

import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from app.core.config import get_settings


@lru_cache
def _reader():
    import easyocr  # heavy import, only paid when a document actually needs OCR

    return easyocr.Reader(["fr", "en"], verbose=False)


def ocr_image(image: Image.Image) -> str:
    """Read the text in an image. Results are cached on disk, so re-indexing is cheap."""
    image = image.convert("RGB")
    digest = hashlib.sha1(image.tobytes()).hexdigest()
    cached = Path(get_settings().ocr_cache_dir) / f"{digest}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8")

    text = "\n".join(_reader().readtext(np.array(image), detail=0, paragraph=True))
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text
