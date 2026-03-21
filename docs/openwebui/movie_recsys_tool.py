

from __future__ import annotations

import json
import re
from typing import Any

import requests
from pydantic import BaseModel, Field


class Function:
    class Valves(BaseModel):
        api_base_url: str = Field(
            default="http://host.docker.internal:8000",
            description="Base URL of backend API reachable from Open WebUI container.",
        )
        active_user_id: int = Field(
            default=1,
            description="User profile selected in Open WebUI Ventiles panel.",
        )
        default_user_id: int = Field(
            default=1,
            description="Default user ID if user_id is not explicitly passed in tool call.",
        )
        default_top_k: int = Field(
            default=20,
            description="How many candidates to request before LLM filtering.",
        )
        timeout_seconds: int = Field(default=60, description="HTTP timeout in seconds.")
        translate_descriptions_to_ru: bool = Field(
            default=True,
            description="Automatically translate movie descriptions to Russian in output.",
        )
        translation_timeout_seconds: int = Field(
            default=8,
            description="Timeout for translation request in seconds.",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()
        self._active_user_id: int | None = None

    @staticmethod
    def _parse_explanation(explanation: str) -> dict[str, Any]:
        if not explanation:
            return {"recommendations": []}

        cleaned = explanation.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0]

        try:
            data = json.loads(cleaned.strip())
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        return {"recommendations": []}

    @staticmethod
    def _has_cyrillic(text: str) -> bool:
        return bool(re.search(r"[А-Яа-яЁё]", text or ""))

    def _translate_to_russian(self, text: str) -> str:
        if not text:
            return text
        if self._has_cyrillic(text):
            return text

        try:
            response = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": "ru",
                    "dt": "t",
                    "q": text,
                },
                timeout=int(self.valves.translation_timeout_seconds),
            )
            response.raise_for_status()
            payload = response.json()
            translated_chunks = payload[0] if payload and isinstance(payload, list) else []
            translated = "".join(chunk[0] for chunk in translated_chunks if chunk and chunk[0])
            return translated or text
        except Exception:
            return text

    def recommend_movies(
        self,
        query_text: str,
        user_id: int | None = None,
        top_k: int | None = None,
    ) -> str:
        """
        Recommend movies for a query and a selected user profile.

        Selection order for user profile:
            1) explicit `user_id` argument
            2) `active_user_id` from Valves UI
            3) previously selected profile from `set_active_user_id`
            4) `default_user_id` from Valves

        Args:
            query_text: Natural language query from user.
            user_id: User profile ID. If omitted, default_user_id is used.
            top_k: Candidate count. If omitted, default_top_k is used.
        """
        if not query_text or not query_text.strip():
            return "Ошибка: пустой запрос."

        if user_id is not None:
            effective_user_id = int(user_id)
        elif int(self.valves.active_user_id) > 0:
            effective_user_id = int(self.valves.active_user_id)
        elif self._active_user_id is not None:
            effective_user_id = int(self._active_user_id)
        else:
            effective_user_id = int(self.valves.default_user_id)

        effective_top_k = int(top_k) if top_k is not None else int(self.valves.default_top_k)

        url = f"{self.valves.api_base_url.rstrip('/')}/api/v1/recommend"
        payload = {
            "user_id": effective_user_id,
            "query_text": query_text.strip(),
            "top_k": effective_top_k,
        }

        try:
            response = requests.post(url, json=payload, timeout=self.valves.timeout_seconds)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return f"Ошибка API: {exc}"

        history = data.get("user_history", []) or []
        parsed = self._parse_explanation(data.get("explanation", ""))
        llm_recs = parsed.get("recommendations", []) or []
        fallback = data.get("recommendations", []) or []

        lines: list[str] = []
        lines.append("Гибридная рекомендательная система фильмов (FAISS + ALS + LLM)")
        lines.append("-")
        lines.append(f"ID пользователя: {effective_user_id}")
        lines.append(f"Запрос: {query_text.strip()}")
        lines.append("")

        if history:
            lines.append("История пользователя:")
            for title in history[:5]:
                lines.append(f"- {title}")
            lines.append("")

        if llm_recs:
            lines.append("Рекомендованные фильмы:")
            for idx, item in enumerate(llm_recs[:10], start=1):
                title = item.get("title", "Untitled")
                reason = item.get("reason", "Relevant to your preferences")
                description = item.get("description", "")
                if self.valves.translate_descriptions_to_ru:
                    description = self._translate_to_russian(description)
                lines.append(f"{idx}. {title}")
                if description:
                    lines.append(f"   Описание: {description}")
                lines.append(f"   Почему подходит: {reason}")
        else:
            lines.append("Точных совпадений по LLM не найдено. Резервный список:")
            for idx, item in enumerate(fallback[:10], start=1):
                title = item.get("title", "Untitled")
                overview = item.get("overview", "")
                if self.valves.translate_descriptions_to_ru:
                    overview = self._translate_to_russian(overview)
                lines.append(f"{idx}. {title}")
                if overview:
                    lines.append(f"   Описание: {overview}")

        return "\n".join(lines)

    def set_active_user_id(self, user_id: int) -> str:
        """
        Set active user profile for subsequent recommendation calls.

        Args:
            user_id: Profile id from your ratings/history dataset.
        """
        uid = int(user_id)
        if uid <= 0:
            return "Ошибка: user_id должен быть положительным."

        self._active_user_id = uid
        return (
            f"Активный профиль пользователя установлен: {uid}. "
            "Следующие вызовы recommend_movies будут использовать этот профиль, если не передан user_id явно."
        )

    def get_active_user_id(self) -> str:
        """
        Return current active user profile and fallback profile.
        """
        if self._active_user_id is None:
            return (
                "Активный профиль пользователя не выбран. "
                "Укажи Вентили -> active_user_id в панели Open WebUI. "
                f"Текущий default_user_id: {int(self.valves.default_user_id)}."
            )
        return f"Текущий активный профиль пользователя: {int(self._active_user_id)}."

    def healthcheck_backend(self) -> str:
        """
        Check backend availability for the recommendation API.
        """
        url = f"{self.valves.api_base_url.rstrip('/')}/docs"
        try:
            response = requests.get(url, timeout=self.valves.timeout_seconds)
            return f"Backend доступен: {url} (HTTP {response.status_code})"
        except Exception as exc:
            return f"Backend недоступен: {exc}"


class Tools(Function):
    """Compatibility alias for Open WebUI versions that look for Tools class."""


class Pipe(Function):
    """Compatibility class for Open WebUI Functions section (expects Pipe/Filter/Action)."""

    class UserValves(BaseModel):
        active_user_id: int = Field(
            default=1,
            description="Active recommendation profile in chat UI (Ventiles).",
        )

    def pipes(self):
        return [
            {
                "id": "movie-recsys-pipe",
                "name": "Movie RecSys Hybrid",
            }
        ]

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return " ".join(parts).strip()
        return str(content or "").strip()

    def pipe(
        self,
        body: dict,
        __user__: dict | None = None,
        __request__: Any = None,
        __task__: str | None = None,
    ) -> str:
        # Open WebUI can call pipe for auxiliary tasks (title/tags generation).
        # Do not run recommendation flow for those tasks to avoid hanging chat state.
        if __task__ and str(__task__).lower() not in {"", "default", "chat", "conversation"}:
            return ""

        messages = body.get("messages", []) if isinstance(body, dict) else []
        query_text = ""

        for msg in reversed(messages):
            if msg.get("role") == "user":
                query_text = self._extract_text(msg.get("content", ""))
                break

        if not query_text:
            return "Не найден текст пользовательского запроса."

        # Allow user profile in chat text, e.g. "user_id=42: мрачный sci-fi"
        match = re.search(r"(?:user[_ ]?id)\s*[:=]\s*(\d+)", query_text, flags=re.IGNORECASE)
        parsed_user_id = int(match.group(1)) if match else None

        ui_user_id = None
        if isinstance(__user__, dict):
            valves = __user__.get("valves")
            if valves is not None and hasattr(valves, "active_user_id"):
                try:
                    ui_user_id = int(valves.active_user_id)
                except Exception:
                    ui_user_id = None

        effective_user_id = parsed_user_id if parsed_user_id is not None else ui_user_id

        cleaned_query = re.sub(r"(?:user[_ ]?id)\s*[:=]\s*\d+", "", query_text, flags=re.IGNORECASE)
        cleaned_query = cleaned_query.strip(" :,-") or query_text

        return self.recommend_movies(query_text=cleaned_query, user_id=effective_user_id)
