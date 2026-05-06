from __future__ import annotations

import re

from src.llm.client import OllamaClient
from src.llm.prompts import build_extraction_prompt
from pydantic import ValidationError

from src.models import ExhibitRecord, ExtractedField, ExtractionResult, RetrievalResult


class ExtractionService:
    def __init__(
        self,
        client: OllamaClient,
        *,
        temperature: float = 0.2,
        retries: int = 2,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.retries = retries

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _anchor_tokens(self, exhibit: ExhibitRecord) -> tuple[list[str], list[str], list[str]]:
        metadata = exhibit.english_metadata or {}
        title_source = " ".join(filter(None, [metadata.get("title"), exhibit.title]))
        country_source = " ".join(filter(None, [metadata.get("country"), exhibit.country]))
        medium_source = " ".join(filter(None, [metadata.get("medium"), exhibit.medium]))

        title_tokens = [
            token
            for token in self._normalize(title_source).split()
            if len(token) > 2 and token not in {"the", "and", "with", "days", "last"}
        ]
        country_tokens = [
            token
            for token in self._normalize(country_source).split()
            if len(token) > 2 and token not in {"park", "parc", "section", "fine", "arts"}
        ]
        medium_tokens = [
            token
            for token in self._normalize(medium_source).split()
            if len(token) > 3 and token not in {"object", "display"}
        ]
        return title_tokens, country_tokens, medium_tokens

    def _is_exhibit_anchored(self, exhibit: ExhibitRecord, chunk_text: str) -> bool:
        normalized_chunk = self._normalize(chunk_text)
        title_tokens, country_tokens, medium_tokens = self._anchor_tokens(exhibit)

        has_title = any(token in normalized_chunk for token in title_tokens)
        has_country = any(token in normalized_chunk for token in country_tokens)
        has_medium = any(token in normalized_chunk for token in medium_tokens)

        if has_title:
            return True
        if has_country and has_medium:
            return True
        if len(country_tokens) >= 2 and sum(token in normalized_chunk for token in country_tokens) >= 2:
            return True
        return False

    def extract_for_result(
        self,
        exhibit: ExhibitRecord,
        retrieval_result: RetrievalResult,
    ) -> list[ExtractionResult]:
        outputs: list[ExtractionResult] = []
        for hit in retrieval_result.hits:
            outputs.append(
                self._extract_single_chunk(
                    exhibit=exhibit,
                    discourse=retrieval_result.discourse,
                    query=retrieval_result.query,
                    hit=hit,
                )
            )
        return outputs

    def extract_hit(
        self,
        *,
        exhibit: ExhibitRecord,
        discourse: str,
        query: str,
        hit,
    ) -> ExtractionResult:
        return self._extract_single_chunk(
            exhibit=exhibit,
            discourse=discourse,
            query=query,
            hit=hit,
        )

    def _extract_single_chunk(
        self,
        *,
        exhibit: ExhibitRecord,
        discourse: str,
        query: str,
        hit,
    ) -> ExtractionResult:
        last_error: Exception | None = None
        for _ in range(self.retries + 1):
            try:
                payload = self.client.generate_json(
                    build_extraction_prompt(exhibit, hit.text, discourse),
                    temperature=self.temperature,
                )
                match_level = str(payload.get("match_level", "none")).strip().lower()
                if match_level not in {"exact", "related", "none"}:
                    match_level = "none"
                raw_fields = payload.get("fields") or []
                fields = self._validated_fields(raw_fields) if match_level != "none" else []
                if match_level != "none" and not self._is_exhibit_anchored(exhibit, hit.text):
                    match_level = "none"
                    fields = []
                return ExtractionResult(
                    exhibit_id=exhibit.exhibit_id,
                    chunk_id=hit.chunk_id,
                    document_name=hit.document_name,
                    source_type=hit.source_type,
                    query=query,
                    match_level=match_level,
                    fields=fields,
                )
            except Exception as exc:
                last_error = exc
        return ExtractionResult(
            exhibit_id=exhibit.exhibit_id,
            chunk_id=hit.chunk_id,
            document_name=hit.document_name,
            source_type=hit.source_type,
            query=query,
            match_level="none",
            fields=[],
        )

    @staticmethod
    def _validated_fields(raw_fields: list[dict]) -> list[ExtractedField]:
        fields: list[ExtractedField] = []
        for field_payload in raw_fields:
            try:
                fields.append(ExtractedField(**field_payload))
            except ValidationError:
                continue
        return fields
