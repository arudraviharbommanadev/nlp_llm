import os
import re
from collections import Counter
from typing import Any


DEFAULT_CODE_MODEL = os.getenv("OLLAMA_CODE_MODEL", "qwen2.5-coder")
DEFAULT_EXPLAIN_MODEL = os.getenv("OLLAMA_EXPLAIN_MODEL", "mistral")
DEFAULT_REASONING_MODEL = os.getenv("OLLAMA_REASONING_MODEL", "mistral")
DEFAULT_MATH_MODEL = os.getenv("OLLAMA_MATH_MODEL", "llama3")
DEFAULT_LIGHT_MODEL = os.getenv("OLLAMA_LIGHT_MODEL", "phi3")


class StudyOrchestrator:
    def __init__(self) -> None:
        self.intent_keywords = {
            "coding": {
                "code",
                "debug",
                "bug",
                "python",
                "java",
                "javascript",
                "sql",
                "api",
                "function",
                "class",
                "implement",
                "fix",
                "compile",
            },
            "explain": {
                "explain",
                "why",
                "how",
                "concept",
                "theory",
                "understand",
                "meaning",
                "teach",
            },
            "quiz": {
                "quiz",
                "mcq",
                "question",
                "test",
                "practice",
                "structured",
            },
            "summarize": {
                "summary",
                "summarize",
                "notes",
                "shorten",
                "brief",
            },
            "math": {
                "solve",
                "equation",
                "math",
                "integral",
                "derivative",
                "matrix",
                "proof",
                "calculate",
            },
            "translate": {
                "translate",
                "translation",
                "convert",
            },
            "compare": {
                "compare",
                "difference",
                "versus",
                "vs",
            },
            "rewrite": {
                "rewrite",
                "rephrase",
                "improve",
                "polish",
            },
            "flashcards": {
                "flashcard",
                "flashcards",
            },
            "planning": {
                "plan",
                "roadmap",
                "steps",
                "workflow",
                "design",
                "architecture",
            },
        }
        self.model_map = {
            "coding": DEFAULT_CODE_MODEL,
            "explain": DEFAULT_EXPLAIN_MODEL,
            "deep_reasoning": DEFAULT_REASONING_MODEL,
            "quiz": DEFAULT_LIGHT_MODEL,
            "summarize": DEFAULT_LIGHT_MODEL,
            "math": DEFAULT_MATH_MODEL,
            "translate": DEFAULT_LIGHT_MODEL,
            "compare": DEFAULT_REASONING_MODEL,
            "rewrite": DEFAULT_LIGHT_MODEL,
            "flashcards": DEFAULT_LIGHT_MODEL,
            "planning": DEFAULT_REASONING_MODEL,
            "rag_search": DEFAULT_REASONING_MODEL,
        }

    def analyze(self, message: str) -> dict[str, Any]:
        normalized = re.sub(r"\s+", " ", message).strip()
        lower_message = normalized.lower()
        tokens = re.findall(r"[a-zA-Z0-9_+#.\-]{2,}", lower_message)

        scores = self._score_intents(lower_message, tokens)
        ranked_intents = [intent for intent, score in scores.most_common() if score > 0]

        if not ranked_intents:
            ranked_intents = ["explain"]

        primary_intent = ranked_intents[0]
        secondary_intents = ranked_intents[1:3]
        needs_rag = self._needs_rag(lower_message)
        rag_mode = self._rag_mode(lower_message, needs_rag)
        query_type = self._query_type(normalized, ranked_intents)
        response_strategy = self._response_strategy(query_type, needs_rag)
        tasks = self._build_tasks(
            normalized,
            primary_intent,
            secondary_intents,
            needs_rag,
            rag_mode,
            query_type,
        )
        final_aggregation_model = self._choose_aggregation_model(
            primary_intent,
            secondary_intents,
            query_type,
            needs_rag,
        )

        return {
            "query_type": query_type,
            "primary_intent": primary_intent,
            "secondary_intents": secondary_intents,
            "needs_rag": needs_rag,
            "rag_mode": rag_mode,
            "response_strategy": response_strategy,
            "tasks": tasks,
            "final_aggregation_model": final_aggregation_model,
        }

    def _score_intents(self, message: str, tokens: list[str]) -> Counter[str]:
        scores: Counter[str] = Counter()
        for intent, keywords in self.intent_keywords.items():
            scores[intent] = sum(1 for token in tokens if token in keywords)

        if any(marker in message for marker in ("```", "def ", "class ", "{", "};", "traceback")):
            scores["coding"] += 3
        if any(word in message for word in ("explain", "teach me", "simple terms")):
            scores["explain"] += 2
        if any(word in message for word in ("mcq", "quiz", "multiple choice")):
            scores["quiz"] += 3
        if any(word in message for word in ("summary", "summarize", "notes")):
            scores["summarize"] += 2
        if any(word in message for word in ("equation", "solve", "calculate")):
            scores["math"] += 2
        if any(word in message for word in ("compare", "difference between", "vs")):
            scores["compare"] += 2
        if any(word in message for word in ("rewrite", "improve", "refine")):
            scores["rewrite"] += 2
        if any(word in message for word in ("flashcard", "flashcards")):
            scores["flashcards"] += 2
        if any(word in message for word in ("workflow", "architecture", "design", "roadmap")):
            scores["planning"] += 2

        return scores

    def _needs_rag(self, message: str) -> bool:
        rag_markers = (
            "from my notes",
            "from the notes",
            "based on the document",
            "based on the pdf",
            "from the chapter",
            "cite",
            "sources",
            "reference",
            "latest",
            "current",
            "recent",
        )
        return any(marker in message for marker in rag_markers)

    def _rag_mode(self, message: str, needs_rag: bool) -> str:
        if not needs_rag:
            return "none"
        if any(marker in message for marker in ("notes", "chapter", "document", "pdf", "slides")):
            return "local_notes"
        if any(marker in message for marker in ("latest", "current", "recent", "today")):
            return "web"
        return "hybrid"

    def _query_type(self, message: str, intents: list[str]) -> str:
        separators = sum(message.count(token) for token in (" and ", " then ", ",", ";"))
        if len(intents) > 1:
            return "multi_intent"
        if len(message) > 180 or separators >= 2:
            return "complex"
        return "simple"

    def _response_strategy(self, query_type: str, needs_rag: bool) -> str:
        if needs_rag:
            return "retrieve_then_answer"
        if query_type == "simple":
            return "direct"
        return "decompose"

    def _build_tasks(
        self,
        message: str,
        primary_intent: str,
        secondary_intents: list[str],
        needs_rag: bool,
        rag_mode: str,
        query_type: str,
    ) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        task_index = 1

        if needs_rag:
            tasks.append(
                {
                    "task_id": f"task_{task_index}",
                    "task_type": "rag_search",
                    "model": self.model_map["rag_search"],
                    "query": f"Retrieve supporting material for: {message}",
                    "priority": task_index,
                    "depends_on": [],
                    "rag_mode": rag_mode,
                }
            )
            task_index += 1

        if self._needs_deep_reasoning_task(primary_intent, secondary_intents, query_type, needs_rag):
            tasks.append(
                {
                    "task_id": f"task_{task_index}",
                    "task_type": "deep_reasoning",
                    "model": self.model_map["deep_reasoning"],
                    "query": f"Reason through the full request carefully before answering: {message}",
                    "priority": task_index,
                    "depends_on": [task["task_id"] for task in tasks],
                }
            )
            task_index += 1

        all_intents = [primary_intent, *secondary_intents]
        dependency_ids = [task["task_id"] for task in tasks]

        for intent in all_intents:
            tasks.append(
                {
                    "task_id": f"task_{task_index}",
                    "task_type": intent,
                    "model": self.model_map.get(intent, DEFAULT_EXPLAIN_MODEL),
                    "query": self._task_query(intent, message),
                    "priority": task_index,
                    "depends_on": dependency_ids.copy(),
                }
            )
            task_index += 1
            if not dependency_ids:
                dependency_ids = [tasks[-1]["task_id"]]

        return tasks

    def _needs_deep_reasoning_task(
        self,
        primary_intent: str,
        secondary_intents: list[str],
        query_type: str,
        needs_rag: bool,
    ) -> bool:
        if primary_intent in {"coding", "math", "quiz", "summarize"}:
            return False
        if primary_intent in {"planning", "compare"}:
            return True
        if needs_rag:
            return True
        return query_type in {"complex", "multi_intent"} or len(secondary_intents) > 0

    def _task_query(self, intent: str, message: str) -> str:
        prompts = {
            "coding": f"Solve the coding request carefully: {message}",
            "explain": f"Explain clearly for a student: {message}",
            "deep_reasoning": f"Work through the request with deep reasoning: {message}",
            "quiz": f"Generate a structured quiz for: {message}",
            "summarize": f"Summarize the following clearly: {message}",
            "math": f"Solve the math problem step by step: {message}",
            "translate": f"Translate accurately: {message}",
            "compare": f"Compare the relevant concepts in: {message}",
            "rewrite": f"Rewrite and improve the following: {message}",
            "flashcards": f"Create structured flashcards from: {message}",
            "planning": f"Create a practical plan for: {message}",
        }
        return prompts.get(intent, message)

    def _choose_aggregation_model(
        self,
        primary_intent: str,
        secondary_intents: list[str],
        query_type: str,
        needs_rag: bool,
    ) -> str:
        if primary_intent == "coding":
            return self.model_map["coding"]
        if primary_intent == "math":
            return self.model_map["math"]
        if primary_intent == "quiz":
            return self.model_map["quiz"]
        if primary_intent == "summarize":
            return self.model_map["summarize"]
        if needs_rag or primary_intent in {"planning", "compare"}:
            return self.model_map["deep_reasoning"]
        if query_type in {"complex", "multi_intent"} or secondary_intents:
            return self.model_map["deep_reasoning"]
        return self.model_map.get(primary_intent, DEFAULT_EXPLAIN_MODEL)
