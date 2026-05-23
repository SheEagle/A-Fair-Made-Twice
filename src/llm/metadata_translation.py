from __future__ import annotations

import json
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_fixed

from src.llm.client import OllamaClient
from src.llm.prompts import build_metadata_translation_prompt
from src.models import ExhibitRecord


class MetadataTranslator:
    def __init__(self, client: OllamaClient, cache_path: Path | None = None) -> None:
        self.client = client
        self.cache_path = cache_path
        self._cache: dict[str, dict[str, str | None]] = self._load_cache()

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1), reraise=True)
    def translate_exhibit(self, exhibit: ExhibitRecord) -> dict[str, str | None]:
        if exhibit.exhibit_id in self._cache:
            return self._cache[exhibit.exhibit_id]
        translated = self.client.generate_json(
            build_metadata_translation_prompt(exhibit),
            temperature=0.0,
        )
        result = {
            "title": translated.get("title"),
            "country": translated.get("country"),
            "location": translated.get("location"),
            "medium": translated.get("medium"),
            "collection": translated.get("collection"),
            "geolocated": translated.get("geolocated"),
        }
        self._cache[exhibit.exhibit_id] = result
        self._persist_cache()
        return result

    def _load_cache(self) -> dict[str, dict[str, str | None]]:
        if self.cache_path is None or not self.cache_path.exists():
            return {}
        rows = json.loads(self.cache_path.read_text(encoding="utf-8"))
        return {row["exhibit_id"]: row["english_metadata"] for row in rows}

    def _persist_cache(self) -> None:
        if self.cache_path is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {"exhibit_id": exhibit_id, "english_metadata": payload}
            for exhibit_id, payload in sorted(self._cache.items())
        ]
        self.cache_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
