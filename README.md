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
- **LLM abstraction**: `LLM` protocol, so the provider can be swapped; the tests use a fake

## Quick start

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY
make install
make run                      # http://localhost:8000/docs
```

Or with Docker: `make docker-up`

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
docs/            deployment guide
```

## Testing

```bash
make test                     # everything
pytest -m "not slow"          # skip tests that load the real embedding model
```

The retrieval evaluation (`tests/test_retrieval_eval.py`) checks hit rate@1 on a
labeled question set in `data/evaluation/`.

## Deployment

See [docs/deployment.md](docs/deployment.md) for running on AWS EC2 behind Nginx.
