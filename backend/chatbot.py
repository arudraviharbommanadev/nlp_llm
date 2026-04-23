import os
import re
import subprocess
from collections import Counter
from typing import Any

from backend.orchestrator import StudyOrchestrator

try:
    import ollama
except ImportError:  # pragma: no cover
    ollama = None


DEFAULT_FALLBACK_MODEL = os.getenv("OLLAMA_MODEL", "phi3")
DEFAULT_TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "mistral")
DEFAULT_CODE_MODEL = os.getenv("OLLAMA_CODE_MODEL", "qwen2.5-coder")


class OllamaChatbot:
    def __init__(
        self,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
        text_model: str = DEFAULT_TEXT_MODEL,
        code_model: str = DEFAULT_CODE_MODEL,
    ) -> None:
        self.fallback_model = fallback_model
        self.text_model = text_model
        self.code_model = code_model
        self.orchestrator = StudyOrchestrator()
        self.code_keywords = {
            "algorithm",
            "api",
            "bug",
            "class",
            "code",
            "compile",
            "debug",
            "error",
            "exception",
            "fastapi",
            "function",
            "javascript",
            "json",
            "python",
            "refactor",
            "regex",
            "script",
            "sql",
            "stack",
            "terminal",
            "test",
            "traceback",
            "typescript",
        }
        self.subjective_keywords = {
            "analysis",
            "compare",
            "describe",
            "essay",
            "explain",
            "meaning",
            "opinion",
            "story",
            "subjective",
            "summary",
            "thoughts",
            "why",
        }

    def generate_response(self, message: str) -> str:
        return self.process_message(message)["response"]

    def process_message(self, message: str) -> dict[str, Any]:
        cleaned_message = self._clean_message(message)
        preprocessing = self._preprocess(cleaned_message)
        orchestration = self.orchestrator.analyze(cleaned_message)
        intent_summary = self._analyze_intent(
            cleaned_message,
            preprocessing["tokens"],
            orchestration["primary_intent"],
        )
        selected_model = self._select_model(orchestration["final_aggregation_model"])
        knowledge_context = self._build_knowledge_context(
            cleaned_message,
            preprocessing["keywords"],
            orchestration,
        )
        semantic_profile = self._build_semantic_profile(preprocessing["keywords"])
        response = self._generate_model_response(
            cleaned_message,
            selected_model,
            orchestration,
            knowledge_context,
            semantic_profile,
        )

        stages = [
            self._build_stage(
                "intake",
                "Query intake",
                "Accepted the user query and opened the NLP pipeline.",
            ),
            self._build_stage(
                "preprocess",
                "Text preprocessing",
                f"Normalized {preprocessing['token_count']} tokens and extracted focus terms.",
                {"keywords": preprocessing["keywords"]},
            ),
            self._build_stage(
                "orchestration",
                "Orchestration",
                self._orchestration_detail(orchestration),
                {
                    "intent": orchestration["primary_intent"],
                    "query_type": orchestration["query_type"],
                    "needs_rag": orchestration["needs_rag"],
                    "rag_mode": orchestration["rag_mode"],
                },
            ),
            self._build_stage(
                "routing",
                "Task routing",
                self._routing_detail(orchestration, selected_model),
                {
                    "model": selected_model,
                    "tasks": orchestration["tasks"],
                },
            ),
            self._build_stage(
                "retrieval",
                "Retrieval planning",
                self._retrieval_detail(orchestration),
                {"needs_rag": orchestration["needs_rag"], "rag_mode": orchestration["rag_mode"]},
            ),
            self._build_stage(
                "task_execution",
                "Task execution",
                self._task_execution_detail(orchestration),
                {"tasks": orchestration["tasks"]},
            ),
            self._build_stage(
                "aggregation",
                "Aggregation",
                f"Prepared the final response from {len(orchestration['tasks'])} planned task(s) using `{selected_model}`.",
                {"model": selected_model},
            ),
            self._build_stage(
                "final_response",
                "Final response",
                f"Generated the final answer with `{selected_model}`.",
            ),
        ]

        return {
            "response": response,
            "intent": orchestration["primary_intent"],
            "model": selected_model,
            "stages": stages,
            "orchestrator": orchestration,
        }

    def stream_response(self, message: str):
        cleaned_message = self._clean_message(message)
        preprocessing = self._preprocess(cleaned_message)
        orchestration = self.orchestrator.analyze(cleaned_message)
        selected_model = self._select_model(orchestration["final_aggregation_model"])
        knowledge_context = self._build_knowledge_context(
            cleaned_message,
            preprocessing["keywords"],
            orchestration,
        )
        semantic_profile = self._build_semantic_profile(preprocessing["keywords"])

        yield {
            "type": "stage",
            "stage": self._build_stage(
                "intake",
                "Query intake",
                "Accepted the user query and opened the NLP pipeline.",
            ),
        }
        yield {
            "type": "stage",
            "stage": self._build_stage(
                "preprocess",
                "Text preprocessing",
                f"Normalized {preprocessing['token_count']} tokens and extracted focus terms.",
                {"keywords": preprocessing["keywords"]},
            ),
        }
        yield {
            "type": "stage",
            "stage": self._build_stage(
                "orchestration",
                "Orchestration",
                self._orchestration_detail(orchestration),
                {
                    "intent": orchestration["primary_intent"],
                    "query_type": orchestration["query_type"],
                    "needs_rag": orchestration["needs_rag"],
                    "rag_mode": orchestration["rag_mode"],
                },
            ),
        }
        yield {
            "type": "stage",
            "stage": self._build_stage(
                "routing",
                "Task routing",
                self._routing_detail(orchestration, selected_model),
                {"model": selected_model, "tasks": orchestration["tasks"]},
            ),
        }
        yield {
            "type": "stage",
            "stage": self._build_stage(
                "retrieval",
                "Retrieval planning",
                self._retrieval_detail(orchestration),
                {"needs_rag": orchestration["needs_rag"], "rag_mode": orchestration["rag_mode"]},
            ),
        }
        yield {
            "type": "stage",
            "stage": self._build_stage(
                "task_execution",
                "Task execution",
                self._task_execution_detail(orchestration),
                {"tasks": orchestration["tasks"]},
            ),
        }
        yield {
            "type": "stage",
            "stage": {
                "id": "aggregation",
                "label": "Aggregation",
                "detail": f"Running `{selected_model}` on the prepared prompt.",
                "status": "running",
                "meta": {"model": selected_model},
            },
        }

        response = self._generate_model_response(
            cleaned_message,
            selected_model,
            orchestration,
            knowledge_context,
            semantic_profile,
        )

        yield {
            "type": "stage",
            "stage": self._build_stage(
                "aggregation",
                "Aggregation",
                f"Prepared the final response from {len(orchestration['tasks'])} planned task(s) using `{selected_model}`.",
                {"model": selected_model},
            ),
        }
        yield {
            "type": "stage",
            "stage": self._build_stage(
                "final_response",
                "Final response",
                f"Generated the final answer with `{selected_model}`.",
            ),
        }
        yield {
            "type": "final",
            "response": response,
            "intent": orchestration["primary_intent"],
            "model": selected_model,
            "orchestrator": orchestration,
        }

    def _clean_message(self, message: str) -> str:
        cleaned_message = message.strip()
        if not cleaned_message:
            raise ValueError("Message cannot be empty.")
        return cleaned_message

    def _preprocess(self, message: str) -> dict[str, Any]:
        normalized = re.sub(r"\s+", " ", message).strip().lower()
        tokens = re.findall(r"[a-zA-Z0-9_+#.\-]{2,}", normalized)
        frequencies = Counter(tokens)
        keywords = [token for token, _ in frequencies.most_common(6)]
        return {
            "normalized": normalized,
            "tokens": tokens,
            "token_count": len(tokens),
            "keywords": keywords,
        }

    def _analyze_intent(
        self,
        message: str,
        tokens: list[str],
        primary_intent: str,
    ) -> dict[str, Any]:
        lower_message = message.lower()
        code_score = sum(1 for token in tokens if token in self.code_keywords)
        text_score = sum(1 for token in tokens if token in self.subjective_keywords)

        if any(marker in lower_message for marker in ("```", "def ", "class ", "select ", "{", "};")):
            code_score += 3
        if any(phrase in lower_message for phrase in ("write code", "fix code", "debug", "implement")):
            code_score += 2
        if any(phrase in lower_message for phrase in ("explain", "opinion", "subjective", "essay")):
            text_score += 2

        intent = primary_intent
        detail = (
            f"Detected a {intent} query with code score {code_score} and text score {text_score}."
        )
        return {
            "intent": intent,
            "detail": detail,
            "code_score": code_score,
            "text_score": text_score,
        }

    def _select_model(self, intent: str) -> str:
        if intent in {"coding", self.code_model}:
            return self.code_model or self.fallback_model
        if intent in {"subjective", "explain", self.text_model}:
            return self.text_model or self.fallback_model
        return intent or self.fallback_model

    def _build_knowledge_context(
        self,
        message: str,
        keywords: list[str],
        orchestration: dict[str, Any],
    ) -> str:
        focus_terms = ", ".join(keywords) if keywords else "general reasoning"
        if orchestration["primary_intent"] == "coding":
            return (
                "Matched the prompt against the coding assistance profile, "
                f"focusing on: {focus_terms}."
            )
        return (
            "Matched the prompt against the study support profile, "
            f"focusing on: {focus_terms}."
        )

    def _build_semantic_profile(self, keywords: list[str]) -> dict[str, Any]:
        vector_preview = [
            sum(ord(character) for character in keyword) % 97
            for keyword in keywords[:4]
        ]
        focus_terms = ", ".join(keywords) if keywords else "broad context"
        return {
            "vector_preview": vector_preview,
            "summary": (
                "Built a lightweight semantic fingerprint from the focus terms: "
                f"{focus_terms}."
            ),
        }

    def _system_prompt(
        self,
        orchestration: dict[str, Any],
        knowledge_context: str,
        semantic_profile: dict[str, Any],
    ) -> str:
        primary_intent = orchestration["primary_intent"]
        if primary_intent == "coding":
            expertise = (
                "You are a precise coding assistant. Prioritize correct code, debugging steps, "
                "and practical implementation advice."
            )
        else:
            expertise = (
                "You are a study assistant. Provide clear, structured explanations, notes, "
                "comparisons, or practice material in polished prose."
            )

        task_summary = ", ".join(
            f"{task['task_type']} via {task['model']}" for task in orchestration["tasks"]
        )
        return (
            f"{expertise}\n"
            f"Query type: {orchestration['query_type']}\n"
            f"Primary intent: {primary_intent}\n"
            f"Secondary intents: {', '.join(orchestration['secondary_intents']) or 'none'}\n"
            f"Response strategy: {orchestration['response_strategy']}\n"
            f"Needs retrieval: {orchestration['needs_rag']} ({orchestration['rag_mode']})\n"
            f"Planned tasks: {task_summary}\n"
            f"Pipeline knowledge: {knowledge_context}\n"
            "Semantic fingerprint preview: "
            f"{semantic_profile['vector_preview']}\n"
            "Follow the task plan when composing the answer. "
            "If the user asks for code, include only the code needed. "
            "If the user asks for explanation, prefer crisp paragraphs. "
            "If the user asks for a quiz, include a clearly labeled quiz section."
        )

    def _generate_model_response(
        self,
        message: str,
        model: str,
        orchestration: dict[str, Any],
        knowledge_context: str,
        semantic_profile: dict[str, Any],
    ) -> str:
        system_prompt = self._system_prompt(orchestration, knowledge_context, semantic_profile)
        if ollama is not None:
            return self._generate_with_library(model, system_prompt, message)
        return self._generate_with_subprocess(model, system_prompt, message)

    def _generate_with_library(self, model: str, system_prompt: str, message: str) -> str:
        response: Any = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        )
        return response["message"]["content"].strip()

    def _generate_with_subprocess(self, model: str, system_prompt: str, message: str) -> str:
        combined_prompt = f"{system_prompt}\n\nUser request:\n{message}"
        completed = subprocess.run(
            ["ollama", "run", model, combined_prompt],
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    def _build_stage(
        self,
        stage_id: str,
        label: str,
        detail: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": stage_id,
            "label": label,
            "detail": detail,
            "status": "completed",
            "meta": meta or {},
        }

    def _orchestration_detail(self, orchestration: dict[str, Any]) -> str:
        return (
            f"Classified the request as `{orchestration['query_type']}` with primary intent "
            f"`{orchestration['primary_intent']}` and {len(orchestration['tasks'])} planned task(s)."
        )

    def _routing_detail(self, orchestration: dict[str, Any], selected_model: str) -> str:
        return (
            f"Planned {len(orchestration['tasks'])} task(s) and selected `{selected_model}` as the final "
            f"aggregation model."
        )

    def _retrieval_detail(self, orchestration: dict[str, Any]) -> str:
        if orchestration["needs_rag"]:
            return (
                f"Retrieval is required in `{orchestration['rag_mode']}` mode before answer synthesis."
            )
        return "No retrieval needed; the request can be answered from local reasoning."

    def _task_execution_detail(self, orchestration: dict[str, Any]) -> str:
        task_summaries = [
            f"{task['task_type']} on `{task['model']}`"
            for task in orchestration["tasks"]
        ]
        return "Executing planned tasks: " + ", ".join(task_summaries) + "."
