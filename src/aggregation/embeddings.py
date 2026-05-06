from __future__ import annotations

from collections import defaultdict

from src.models import DISCOURSE_TYPES, VIEW_NAMES, EmbeddingRecord, ExhibitProfile
from src.retrieval.embeddings import EmbeddingService


def build_embedding_records(
    profiles: list[ExhibitProfile],
    embedder: EmbeddingService,
) -> dict[str, list[EmbeddingRecord]]:
    by_discourse: dict[str, list[EmbeddingRecord]] = {}
    for discourse in DISCOURSE_TYPES:
        records = [
            EmbeddingRecord(
                exhibit_id=profile.exhibit_id,
                discourse=discourse,
                english_metadata=profile.english_metadata,
                view_texts={view: profile.views[discourse][view].text for view in VIEW_NAMES},
                embeddings={view: None for view in VIEW_NAMES},
            )
            for profile in profiles
        ]
        for view in VIEW_NAMES:
            active_indices = [index for index, record in enumerate(records) if record.view_texts.get(view)]
            if not active_indices:
                continue
            vectors = embedder.encode_passages([records[index].view_texts[view] for index in active_indices])
            for index, vector in zip(active_indices, vectors, strict=True):
                records[index].embeddings[view] = vector
        by_discourse[discourse] = records
    return by_discourse
