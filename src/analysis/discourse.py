from __future__ import annotations

import numpy as np

from src.models import DISCOURSE_PAIRS, VIEW_NAMES, DiscourseDifference, EmbeddingRecord, ExhibitProfile


def _field_labels(fields) -> list[str]:
    return [f"{field.field}: {field.value}" for field in fields]


def _cosine_distance(left: list[float] | None, right: list[float] | None) -> float | None:
    if left is None or right is None:
        return None
    left_vec = np.array(left, dtype=float)
    right_vec = np.array(right, dtype=float)
    similarity = float(np.dot(left_vec, right_vec))
    return float(1.0 - similarity)


def build_discourse_differences(
    profiles: list[ExhibitProfile],
    embedding_records: dict[str, list[EmbeddingRecord]],
) -> list[DiscourseDifference]:
    discourse_lookups = {
        discourse: {record.exhibit_id: record for record in records}
        for discourse, records in embedding_records.items()
    }
    rows: list[DiscourseDifference] = []
    for profile in profiles:
        for left_discourse, right_discourse in DISCOURSE_PAIRS:
            left_record = discourse_lookups.get(left_discourse, {}).get(profile.exhibit_id)
            right_record = discourse_lookups.get(right_discourse, {}).get(profile.exhibit_id)
            for view in VIEW_NAMES:
                left_fields = profile.views[left_discourse][view].fields
                right_fields = profile.views[right_discourse][view].fields
                if not left_fields and not right_fields:
                    continue
                left_labels = set(_field_labels(left_fields))
                right_labels = set(_field_labels(right_fields))
                rows.append(
                    DiscourseDifference(
                        exhibit_id=profile.exhibit_id,
                        title=profile.english_metadata.get("title"),
                        view=view,
                        left_discourse=left_discourse,
                        right_discourse=right_discourse,
                        discourse_distance=_cosine_distance(
                            left_record.embeddings.get(view) if left_record else None,
                            right_record.embeddings.get(view) if right_record else None,
                        ),
                        left_field_count=len(left_fields),
                        right_field_count=len(right_fields),
                        only_in_left=sorted(left_labels - right_labels),
                        only_in_right=sorted(right_labels - left_labels),
                    )
                )
    return rows
