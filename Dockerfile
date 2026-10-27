FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# CPU-only torch keeps the image ~2GB smaller than the default CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# Install dependencies before copying source so code changes don't bust the layer cache.
COPY pyproject.toml .
RUN mkdir app && touch app/__init__.py && pip install . && rm -rf app

COPY app ./app

# Bake the configured embedding model into the image so containers start without downloading it.
RUN python -c "from app.embeddings.embedder import get_embedder; get_embedder()"

RUN useradd --create-home appuser && mkdir -p data && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
