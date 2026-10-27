from collections.abc import Iterator
from dataclasses import dataclass

from app.generation.llm import LLM, Message
from app.generation.prompts import SYSTEM_PROMPT, build_prompt
from app.repositories.vector_store import SearchResult
from app.retrieval.retriever import Retriever

NO_CONTEXT_ANSWER = (
    "Je n'ai rien trouvé dans les cours qui réponde à cette question. "
    "Essaie de la reformuler ou de préciser le module (néphro, gynéco, chirurgie...)."
)
HISTORY_TURNS = 6  # recent messages sent to the model so follow-up questions make sense


@dataclass
class RagAnswer:
    answer: str
    sources: list[SearchResult]


class RagService:
    def __init__(self, retriever: Retriever, llm: LLM):
        self.retriever = retriever
        self.llm = llm

    def retrieve(
        self, question: str, history: list[Message] | None = None, source: str | None = None
    ) -> list[SearchResult]:
        # A follow-up like "et le traitement ?" is only searchable with the previous question.
        previous = [m["content"] for m in history or [] if m["role"] == "user"][-1:]
        return self.retriever.retrieve(" ".join([*previous, question]), source=source)

    def stream_answer(
        self, question: str, results: list[SearchResult], history: list[Message] | None = None
    ) -> Iterator[str]:
        if not results:
            # Skip the LLM entirely: without course material any answer would be a guess.
            yield NO_CONTEXT_ANSWER
            return
        prompt = {"role": "user", "content": build_prompt(question, results)}
        yield from self.llm.stream(SYSTEM_PROMPT, [*(history or [])[-HISTORY_TURNS:], prompt])

    def ask(
        self, question: str, history: list[Message] | None = None, source: str | None = None
    ) -> RagAnswer:
        results = self.retrieve(question, history, source)
        return RagAnswer("".join(self.stream_answer(question, results, history)), results)
