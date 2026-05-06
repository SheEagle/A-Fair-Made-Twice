from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from src.models import (
    DISCOURSE_TYPES,
    VIEW_NAMES,
    ExhibitProfile,
    ExhibitRecord,
    ExtractedField,
    ExtractionResult,
    ViewSummary,
)


def _empty_view_map() -> dict[str, dict[str, ViewSummary]]:
    return {
        discourse: {view: ViewSummary() for view in VIEW_NAMES}
        for discourse in DISCOURSE_TYPES
    }


def _make_metadata_payload(exhibit: ExhibitRecord) -> dict:
    payload = exhibit.model_dump()
    payload.pop("english_metadata", None)
    return payload


def _upsert_field(target: list[ExtractedField], candidate: ExtractedField) -> None:
    for index, existing in enumerate(target):
        if existing.signature == candidate.signature:
            if candidate.confidence > existing.confidence:
                target[index] = candidate
            return
    target.append(candidate)


def _sort_fields(fields: Iterable[ExtractedField]) -> list[ExtractedField]:
    return sorted(fields, key=lambda item: (-item.confidence, item.field, item.value))


def _build_view_text(
    exhibit_id: str,
    english_metadata: dict[str, str | None],
    discourse: str,
    view: str,
    fields: list[ExtractedField],
) -> str | None:
    if not fields:
        return None
    title = english_metadata.get("title") or exhibit_id
    country = english_metadata.get("country")
    location = english_metadata.get("location")
    medium = english_metadata.get("medium")
    lead_parts = [title]
    if medium:
        lead_parts.append(medium)
    if country:
        lead_parts.append(country)
    if location:
        lead_parts.append(location)

    lead = " | ".join(part for part in lead_parts if part)
    mood = f"{discourse.replace('_', ' ')} {view} reading"
    field_text = " ".join(f"{field.field}: {field.value}." for field in fields)
    return f"{lead}. {mood.capitalize()}. {field_text}".strip()


def aggregate_profiles(
    exhibits: list[ExhibitRecord],
    extraction_results: list[ExtractionResult],
) -> list[ExhibitProfile]:
    profiles = {
        exhibit.exhibit_id: ExhibitProfile(
            exhibit_id=exhibit.exhibit_id,
            metadata=_make_metadata_payload(exhibit),
            english_metadata=exhibit.english_metadata,
            views=_empty_view_map(),
        )
        for exhibit in exhibits
    }

    for result in extraction_results:
        profile = profiles[result.exhibit_id]
        discourse_views = profile.views[result.source_type]
        for extracted_field in result.fields:
            _upsert_field(discourse_views[extracted_field.view].fields, extracted_field)

    for profile in profiles.values():
        for discourse in DISCOURSE_TYPES:
            overall_fields: list[ExtractedField] = []
            for view in ("technical", "category", "exhibition", "perception"):
                view_summary = profile.views[discourse][view]
                view_summary.fields = _sort_fields(view_summary.fields)
                view_summary.text = _build_view_text(
                    exhibit_id=profile.exhibit_id,
                    english_metadata=profile.english_metadata,
                    discourse=discourse,
                    view=view,
                    fields=view_summary.fields,
                )
                for field in view_summary.fields:
                    _upsert_field(overall_fields, field)
            profile.views[discourse]["overall"].fields = _sort_fields(overall_fields)
            profile.views[discourse]["overall"].text = _build_view_text(
                exhibit_id=profile.exhibit_id,
                english_metadata=profile.english_metadata,
                discourse=discourse,
                view="overall",
                fields=profile.views[discourse]["overall"].fields,
            )
    return list(profiles.values())


def aggregate_profile(
    exhibit: ExhibitRecord,
    extraction_results: list[ExtractionResult],
) -> ExhibitProfile:
    return aggregate_profiles([exhibit], extraction_results)[0]
