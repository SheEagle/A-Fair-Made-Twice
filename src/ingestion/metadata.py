from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.models import ExhibitRecord


FIELD_ALIASES = {
    "archive_id": ("archive_id",),
    "card_id": ("card_id", "id", "object_id"),
    "title": ("title", "name", "object_name"),
    "country": ("country", "nation"),
    "location": ("location", "section", "room"),
    "medium": ("medium", "object_type", "type"),
    "collection": ("collection",),
    "geolocated": ("geolocated", "geo_confidence"),
    "include": ("include",),
}


def _canonicalize_column(name: str) -> str:
    base = name.split(".")[0]
    return re.sub(r"[^a-z0-9]+", "_", base.strip().lower()).strip("_")


def _normalize_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def _resolve_field(raw_metadata: dict[str, Any], field_name: str) -> Any:
    canonical_map = {_canonicalize_column(key): value for key, value in raw_metadata.items()}
    for alias in FIELD_ALIASES[field_name]:
        canonical_alias = _canonicalize_column(alias)
        if canonical_alias in canonical_map:
            return canonical_map[canonical_alias]
    return None


def _should_include(raw_metadata: dict[str, Any], only_include_flagged: bool) -> bool:
    if not only_include_flagged:
        return True
    include_value = _resolve_field(raw_metadata, "include")
    if include_value is None:
        return True
    if isinstance(include_value, str):
        return include_value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(include_value)


def read_metadata_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported metadata file: {path}")


def load_exhibits(path: Path, only_include_flagged: bool = False) -> list[ExhibitRecord]:
    frame = read_metadata_frame(path)
    exhibits: list[ExhibitRecord] = []
    seen_exhibit_ids: set[str] = set()
    for row_index, (_, row) in enumerate(frame.iterrows()):
        raw_metadata = {str(column): _normalize_value(row[column]) for column in frame.columns}
        if not _should_include(raw_metadata, only_include_flagged):
            continue
        archive_id = _resolve_field(raw_metadata, "archive_id")
        card_id = _resolve_field(raw_metadata, "card_id")
        exhibit_id = str(card_id or archive_id or f"row-{row_index}")
        if exhibit_id in seen_exhibit_ids:
            continue
        seen_exhibit_ids.add(exhibit_id)
        exhibits.append(
            ExhibitRecord(
                exhibit_id=exhibit_id,
                archive_id=str(archive_id) if archive_id is not None else None,
                card_id=str(card_id) if card_id is not None else None,
                title=_resolve_field(raw_metadata, "title"),
                country=_resolve_field(raw_metadata, "country"),
                location=_resolve_field(raw_metadata, "location"),
                medium=_resolve_field(raw_metadata, "medium"),
                collection=_resolve_field(raw_metadata, "collection"),
                geolocated=_resolve_field(raw_metadata, "geolocated"),
                raw_metadata=raw_metadata,
            )
        )
    return exhibits
