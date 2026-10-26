from dataclasses import dataclass

from app.generation.llm import LLM
from app.generation.prompts import SYSTEM_PROMPT, build_prompt
from app.repositories.vector_store import SearchResult
from app.retrieval.retriever import Retriever

NO_CONTEXT_ANSWER = "I couldn't find anything relevant in the knowledge base to answer that."


@dataclass
class RagAnswer:
    answer: str
    sources: list[SearchResult]


class RagService:
    def __init__(self, retriever: Retriever, llm: LLM):
        self.retriever = retriever
        self.llm = llm

    def ask(self, question: str, source: str | None = None) -> RagAnswer:
        results = self.retriever.retrieve(question, source=source)
        if not results:
            # Skip the LLM call entirely: no context means any answer would be a guess.
            return RagAnswer(answer=NO_CONTEXT_ANSWER, sources=[])
        answer = self.llm.generate(SYSTEM_PROMPT, build_prompt(question, results))
        return RagAnswer(answer=answer, sources=results)
