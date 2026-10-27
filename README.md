# MedStudy AI — assistant de révision médicale

![CI](https://github.com/Med00amine/Rag-project/actions/workflows/ci.yml/badge.svg)

A volunteer project: a study chatbot for medical students that answers from **their own
course material** (lecture slides, polycopiés, internship handouts, textbooks), explains
with a clinical example and a memory tip, and tells them **exactly which lecture and slide
to revise**. Everything runs locally with free, open models.

> *Pose une question sur tes cours : la réponse cite le cours et la diapo à revoir.*
> Outil de révision — ne remplace pas un avis médical.

**Stack:** FastAPI · Sentence Transformers · ChromaDB · EasyOCR · Ollama (Qwen2.5 7B) ·
Docker · Nginx · GitHub Actions

## What a student gets

Ask *« Quelle est la classification de Gharbi du kyste hydatique ? »* and the answer comes
back streamed, in three sections:

1. **Réponse** – the essentials, key criteria and numbers in bold, each fact cited `[n]`
2. **Exemple clinique** – a short realistic case
3. **Astuce** – a mnemonic or a classic exam trap

Under it, **Où réviser** lists the lectures behind the answer with the exact slide or page
(*Hydatidose hépatique · diapo 19*), grouped by lecture, built from the retrieval metadata
rather than written by the model, so a page number can never be invented. Clicking a
citation opens the passage in a side panel, with a button that opens the PDF at that page.

Follow-up questions (*« et le traitement ? »*) keep the context, and questions the courses
don't cover get an honest *« je n'ai rien trouvé dans les cours »* instead of a made-up answer.

The web app (dark or light theme, desktop to phone) also has:

- **Conversations and saved answers**, searchable, kept in the student's browser
- **A library** of every indexed document, filtered by course, with *ask this document only*
  and *open the original*; maintainers add or remove documents there with the admin token
- **Courses in the sidebar**, derived from the drive folders (*C1 · Gynéco obstét*, *Stage*…)

## How it works

```
Google Drive ─► sync ─► load (PDF · PPTX · legacy PPT · DOCX · images)
                           │  scanned pages, image-only slides ─► OCR (EasyOCR, GPU, cached)
                           ▼
                 chunk per page/slide ─► multilingual embeddings ─► ChromaDB
                                                                      │
question (+ previous one) ─► embed ─► top-k cosine ─► score threshold ┘
        ─► prompt with numbered excerpts ─► Qwen2.5 7B (Ollama) ─► streamed answer + citations
```

## Engineering notes

- **Every format in the drives.** Legacy binary `.ppt` files are parsed straight from the
  PowerPoint record stream (`olefile`), using the persist directory to recover slide order;
  no LibreOffice needed.
- **OCR where text is missing.** About one file in five was a scan or a deck of slide
  screenshots with no extractable text. Pages and slides with little text get their
  pictures OCR'd (French), results cached by image hash so re-indexing is cheap.
- **Citations students can use.** Chunks keep their page or slide number and the lecture
  title; the source card shows the module path (*C2 chir générale › Chir*).
- **Clean index.** Identical lectures shared in several folders are indexed once; closing
  and outline slides (*Merci pour votre attention*) are dropped; view-only Drive files are
  respected, not scraped.
- **Model chosen by evaluation.** A French question set mapped to the lectures that answer
  them compares embedding models (below) and calibrates the "not in the course" threshold.
- **Safe to share.** Adding or removing documents requires an admin token; the UI escapes
  all model and course text (its Markdown renderer is unit-tested against injection); only
  indexed course files inside the library folders can be opened, and textbooks are quoted,
  never handed out whole.
- **No frontend build.** The UI is plain ES modules served by FastAPI, with inline Lucide
  icons and no runtime dependency.

## Retrieval evaluation

26 student-style questions (`data/evaluation/medical_retrieval_eval.json`), ~10,500 chunks:

| Embedding model                         | hit@1 | hit@5 | MRR  |
|-----------------------------------------|-------|-------|------|
| all-MiniLM-L6-v2 (English baseline)     | 0.65  | 0.81  | 0.73 |
| paraphrase-multilingual-MiniLM-L12-v2   | 0.50  | 0.81  | 0.60 |
| multilingual-e5-small                   | 0.85  | 0.96  | 0.90 |
| **multilingual-e5-base** (used)         | **0.88** | **1.00** | **0.91** |

e5-base finds the right lecture in the top 5 for every question, and is the only model
whose weakest course question still scores above every off-topic question, which is what
lets `MIN_SCORE` answer *"not in the course"* reliably.

Reproduce with `python -m scripts.evaluate_retrieval <model> [<model> ...]`.

## Run it

Requirements: Python 3.11+, [Ollama](https://ollama.com/download), and ideally an NVIDIA GPU
for OCR (indexing) and the LLM.

```bash
ollama pull qwen2.5:7b
pip install -e ".[dev,sync,ocr]"
cp .env.example .env

python -m scripts.sync_drive <drive-folder-url> [...] --exclude .mp4   # download the courses
python -m scripts.ingest data/raw/drive                                 # index (OCR included)
make run                                                                # http://localhost:8000
```

Sharing the chatbot with other students? Index only the course material:
`python -m scripts.ingest data/raw/drive --exclude Books`. Course files stay on your
machine (`data/` is git-ignored) and belong to their authors.

## API

| Method | Path              | Description                                              |
|--------|-------------------|----------------------------------------------------------|
| GET    | `/`               | Web app                                                  |
| POST   | `/chat`           | Streamed answer (NDJSON: `sources`, `token`…, `done`)    |
| POST   | `/query`          | Same answer as one JSON response                         |
| GET    | `/documents`      | Indexed documents, with passage counts                   |
| GET    | `/documents/file` | Original course file (PDFs open inline, at `#page=N`)    |
| POST   | `/documents`      | Add a document (requires `X-Admin-Token`)                |
| DELETE | `/documents`      | Remove a document from the index (requires the token)    |
| GET    | `/health/ready`   | Readiness, with the number of indexed chunks             |

## Project layout

```
app/
  api/           routes, dependencies, error handlers, middleware
  ingestion/     loaders (PDF, PPTX, PPT, DOCX, images), OCR, cleaning, chunking
  embeddings/    sentence-transformers wrapper (query/passage prefixes)
  repositories/  ChromaDB vector store
  retrieval/     retriever
  generation/    prompt, LLM clients (Ollama, Claude)
  services/      ingestion and RAG orchestration
  static/        web app: ES modules (chat, library, Markdown renderer), CSS, no build step
scripts/         sync_drive, ingest, evaluate_retrieval
tests/           unit, API and retrieval tests (fake embedder and LLM, no downloads)
  js/            frontend unit tests (node --test)
deploy/          Nginx config
```

## Testing

```bash
make test                     # everything
pytest -m "not slow"          # skip tests that load the real embedding model
make test-ui                  # frontend unit tests (Node 22, no dependencies)
```
