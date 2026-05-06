from __future__ import annotations

import json
import re
import time
from typing import Any

import requests


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int = 240,
        *,
        provider: str = "ollama",
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.provider = provider
        self.api_key = api_key
        self.gemini_retry_attempts = 6

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        model: str | None = None,
        format_json: bool = False,
    ) -> str:
        selected_model = model or self.model
        if self.provider == "gemini":
            return self._generate_gemini(
                prompt,
                system=system,
                temperature=temperature,
                model=selected_model,
                format_json=format_json,
            )
        return self._generate_ollama(
            prompt,
            system=system,
            temperature=temperature,
            model=selected_model,
            format_json=format_json,
        )

    def _generate_ollama(
        self,
        prompt: str,
        *,
        system: str | None,
        temperature: float,
        model: str,
        format_json: bool,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        if format_json:
            payload["format"] = "json"
        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        return self._clean_response_text(str(body.get("response", "")))

    def _generate_gemini(
        self,
        prompt: str,
        *,
        system: str | None,
        temperature: float,
        model: str,
        format_json: bool,
    ) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required when provider='gemini'.")
        text = prompt if not system else f"{system}\n\n{prompt}"
        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "responseMimeType": "application/json" if format_json else "text/plain",
        }
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": generation_config,
        }
        response = self._post_gemini(model=model, payload=payload)
        if response.status_code >= 400 and format_json:
            # Some hosted Gemma variants reject forced JSON mime mode. Fall back to
            # plain text generation and keep the prompt-level JSON contract.
            payload["generationConfig"] = {"temperature": temperature}
            response = self._post_gemini(model=model, payload=payload)
        if response.status_code >= 400:
            raise requests.HTTPError(
                f"{response.status_code} Client Error: {response.text}",
                response=response,
            )
        body = response.json()
        return self._clean_response_text(self._extract_gemini_text(body))

    def _post_gemini(self, *, model: str, payload: dict[str, Any]) -> requests.Response:
        last_response: requests.Response | None = None
        for attempt in range(self.gemini_retry_attempts + 1):
            response = requests.post(
                f"{self.base_url}/models/{model}:generateContent",
                params={"key": self.api_key},
                json=payload,
                timeout=self.timeout_seconds,
            )
            last_response = response
            if response.status_code not in {429, 500, 503}:
                return response
            if attempt >= self.gemini_retry_attempts:
                return response
            time.sleep(self._gemini_retry_delay_seconds(response, attempt))
        return last_response if last_response is not None else requests.Response()

    @staticmethod
    def _gemini_retry_delay_seconds(response: requests.Response, attempt: int) -> float:
        try:
            body = response.json()
        except ValueError:
            body = {}
        details = body.get("error", {}).get("details") or []
        for item in details:
            retry_delay = item.get("retryDelay")
            if isinstance(retry_delay, str) and retry_delay.endswith("s"):
                try:
                    return max(1.0, float(retry_delay[:-1]))
                except ValueError:
                    pass
        message = body.get("error", {}).get("message", "")
        match = re.search(r"retry in ([0-9.]+)s", message, flags=re.IGNORECASE)
        if match:
            return max(1.0, float(match.group(1)))
        return min(60.0, 5.0 * (attempt + 1))

    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        model: str | None = None,
    ) -> dict[str, Any]:
        text = self.generate(
            prompt,
            system=system,
            temperature=temperature,
            model=model,
            format_json=True,
        )
        return self._extract_json(text)

    @staticmethod
    def _clean_response_text(text: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return cleaned

    @staticmethod
    def _extract_gemini_text(body: dict[str, Any]) -> str:
        candidates = body.get("candidates") or []
        if not candidates:
            prompt_feedback = body.get("promptFeedback")
            raise ValueError(f"Gemini returned no candidates: {prompt_feedback}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts)
        if not text:
            raise ValueError(f"Gemini returned empty content: {body}")
        return text

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                repaired = re.sub(r'\\u(?![0-9a-fA-F]{4})', r"\\\\u", candidate)
                repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", repaired)
                return json.loads(repaired)
