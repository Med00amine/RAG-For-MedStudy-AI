# RAG Service

![CI](https://github.com/Med00amine/Rag-project/actions/workflows/ci.yml/badge.svg)

A Retrieval-Augmented Generation API: upload documents, then ask questions that
are answered from their content, with cited sources.

**Stack:** FastAPI · Sentence Transformers · ChromaDB · Claude · Docker · Nginx · GitHub Actions

## How it works

```
Upload ─► load (PDF/TXT/MD) ─► clean ─► chunk ─► embed ─► ChromaDB
Query  ─► embed question ─► top-k cosine search ─► score threshold ─► prompt + context ─► Claude ─► answer + sources
```

- **Chunking**: recursive splitting (paragraphs → lines → sentences → words) with overlap
- **Embeddings**: `all-MiniLM-L6-v2` (384-dim, normalized), loaded once per process
- **Retrieval**: top-k cosine similarity with a minimum score, optional filter by document
- **Generation**: numbered context blocks and inline citations. If nothing relevant is
  retrieved, the service answers "I don't know" without calling the LLM
- **LLM**: free, local open-source models through [Ollama](https://ollama.com) by default
  (`llama3.2`). Behind an `LLM` protocol, so you can switch to Claude with
  `LLM_PROVIDER=claude`. The tests use a fake

## Quick start

Everything runs locally and for free, with no API keys.

With Docker (starts the API and Ollama):

```bash
make docker-up
make pull-model               # one-time download of llama3.2 (~2 GB)
```

Without Docker: [install Ollama](https://ollama.com/download), then

```bash
ollama pull llama3.2
cp .env.example .env
make install
make run                      # http://localhost:8000/docs
```

```bash
curl -F "file=@paper.pdf" localhost:8000/documents
curl -X POST localhost:8000/query -H "Content-Type: application/json" \
     -d '{"question": "What is the main contribution?"}'
```

## API

| Method | Path            | Description                                    |
|--------|-----------------|------------------------------------------------|
| POST   | `/documents`    | Upload and ingest a PDF, TXT or MD file        |
| POST   | `/query`        | Ask a question (optional `source` filter)      |
| GET    | `/health`       | Liveness                                       |
| GET    | `/health/ready` | Readiness (checks the vector store)            |

## Project layout

```
app/
  api/           routes, dependencies, error handlers, middleware
  core/          settings, logging
  ingestion/     loader, cleaner, chunker
  embeddings/    sentence-transformers wrapper
  repositories/  ChromaDB vector store
  retrieval/     retriever
  generation/    prompts, LLM client
  services/      ingestion and RAG orchestration
tests/           unit, integration, API and retrieval-evaluation tests
deploy/          Nginx config
```

## Testing

```bash
make test                     # everything
pytest -m "not slow"          # skip tests that load the real embedding model
```

The retrieval evaluation (`tests/test_retrieval_eval.py`) checks hit rate@1 on a
labeled question set in `data/evaluation/`.

## Deployment

`docker-compose.prod.yml` runs the API, Ollama and Nginx (reverse proxy with rate limiting)
with persistent volumes for the vector store and models:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec ollama ollama pull llama3.2
```
