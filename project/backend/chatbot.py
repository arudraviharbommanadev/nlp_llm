import os
import re
import subprocess
from collections import Counter
from typing import Any

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
        intent_summary = self._analyze_intent(cleaned_message, preprocessing["tokens"])
        selected_model = self._select_model(intent_summary["intent"])
        knowledge_context = self._build_knowledge_context(
            cleaned_message,
            preprocessing["keywords"],
            intent_summary["intent"],
        )
        semantic_profile = self._build_semantic_profile(preprocessing["keywords"])
        response = self._generate_model_response(
            cleaned_message,
            selected_model,
            intent_summary["intent"],
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
                "intent",
                "Intent analysis",
                intent_summary["detail"],
                {
                    "intent": intent_summary["intent"],
                    "code_score": intent_summary["code_score"],
                    "text_score": intent_summary["text_score"],
                },
            ),
            self._build_stage(
                "routing",
                "Model routing",
                f"Assigned the request to `{selected_model}` for {intent_summary['intent']} reasoning.",
                {"model": selected_model},
            ),
            self._build_stage(
                "knowledge",
                "Knowledge base analysis",
                knowledge_context,
            ),
            self._build_stage(
                "semantic",
                "Embedding analysis",
                semantic_profile["summary"],
                {"vector_preview": semantic_profile["vector_preview"]},
            ),
            self._build_stage(
                "generation",
                "Response generation",
                f"Generated the final answer with `{selected_model}`.",
            ),
        ]

        return {
            "response": response,
            "intent": intent_summary["intent"],
            "model": selected_model,
            "stages": stages,
        }

    def stream_response(self, message: str):
        cleaned_message = self._clean_message(message)
        preprocessing = self._preprocess(cleaned_message)
        intent_summary = self._analyze_intent(cleaned_message, preprocessing["tokens"])
        selected_model = self._select_model(intent_summary["intent"])
        knowledge_context = self._build_knowledge_context(
            cleaned_message,
            preprocessing["keywords"],
            intent_summary["intent"],
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
                "intent",
                "Intent analysis",
                intent_summary["detail"],
                {
                    "intent": intent_summary["intent"],
                    "code_score": intent_summary["code_score"],
                    "text_score": intent_summary["text_score"],
                },
            ),
        }
        yield {
            "type": "stage",
            "stage": self._build_stage(
                "routing",
                "Model routing",
                f"Assigned the request to `{selected_model}` for {intent_summary['intent']} reasoning.",
                {"model": selected_model},
            ),
        }
        yield {
            "type": "stage",
            "stage": self._build_stage(
                "knowledge",
                "Knowledge base analysis",
                knowledge_context,
            ),
        }
        yield {
            "type": "stage",
            "stage": self._build_stage(
                "semantic",
                "Embedding analysis",
                semantic_profile["summary"],
                {"vector_preview": semantic_profile["vector_preview"]},
            ),
        }
        yield {
            "type": "stage",
            "stage": {
                "id": "generation",
                "label": "Response generation",
                "detail": f"Running `{selected_model}` on the prepared prompt.",
                "status": "running",
                "meta": {"model": selected_model},
            },
        }

        response = self._generate_model_response(
            cleaned_message,
            selected_model,
            intent_summary["intent"],
            knowledge_context,
            semantic_profile,
        )

        yield {
            "type": "stage",
            "stage": self._build_stage(
                "generation",
                "Response generation",
                f"Generated the final answer with `{selected_model}`.",
            ),
        }
        yield {
            "type": "final",
            "response": response,
            "intent": intent_summary["intent"],
            "model": selected_model,
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

    def _analyze_intent(self, message: str, tokens: list[str]) -> dict[str, Any]:
        lower_message = message.lower()
        code_score = sum(1 for token in tokens if token in self.code_keywords)
        text_score = sum(1 for token in tokens if token in self.subjective_keywords)

        if any(marker in lower_message for marker in ("```", "def ", "class ", "select ", "{", "};")):
            code_score += 3
        if any(phrase in lower_message for phrase in ("write code", "fix code", "debug", "implement")):
            code_score += 2
        if any(phrase in lower_message for phrase in ("explain", "opinion", "subjective", "essay")):
            text_score += 2

        intent = "coding" if code_score > text_score else "subjective"
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
        if intent == "coding":
            return self.code_model or self.fallback_model
        if intent == "subjective":
            return self.text_model or self.fallback_model
        return self.fallback_model

    def _build_knowledge_context(
        self,
        message: str,
        keywords: list[str],
        intent: str,
    ) -> str:
        focus_terms = ", ".join(keywords) if keywords else "general reasoning"
        if intent == "coding":
            return (
                "Matched the prompt against the coding assistance knowledge profile, "
                f"focusing on: {focus_terms}."
            )
        return (
            "Matched the prompt against the text-first reasoning profile, "
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
        intent: str,
        knowledge_context: str,
        semantic_profile: dict[str, Any],
    ) -> str:
        if intent == "coding":
            expertise = (
                "You are a precise coding assistant. Prioritize correct code, debugging steps, "
                "and practical implementation advice."
            )
        else:
            expertise = (
                "You are a text-oriented reasoning assistant. Provide clear, structured, "
                "subjective or explanatory answers in polished prose."
            )

        return (
            f"{expertise}\n"
            f"Pipeline knowledge: {knowledge_context}\n"
            "Semantic fingerprint preview: "
            f"{semantic_profile['vector_preview']}\n"
            "If the user asks for code, include only the code needed. "
            "If the user asks for explanation, prefer crisp paragraphs."
        )

    def _generate_model_response(
        self,
        message: str,
        model: str,
        intent: str,
        knowledge_context: str,
        semantic_profile: dict[str, Any],
    ) -> str:
        system_prompt = self._system_prompt(intent, knowledge_context, semantic_profile)
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
