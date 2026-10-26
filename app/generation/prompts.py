from app.repositories.vector_store import SearchResult

SYSTEM_PROMPT = """You answer questions using only the provided context.
If the context does not contain the answer, say you don't know.
Cite sources inline like [1], [2] matching the numbered context blocks."""


def build_prompt(question: str, results: list[SearchResult]) -> str:
    context = "\n\n".join(
        f"[{i}] (source: {r.metadata.get('source', 'unknown')})\n{r.text}"
        for i, r in enumerate(results, start=1)
    )
    return f"<context>\n{context}\n</context>\n\nQuestion: {question}"
