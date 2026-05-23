from __future__ import annotations

import numpy as np
import umap

from src.models import VIEW_NAMES, EmbeddingRecord, ExhibitProfile, UmapCoordinate


def _project(vectors: list[list[float]]) -> np.ndarray:
    if len(vectors) == 1:
        return np.array([[0.0, 0.0, 0.0]])
    if len(vectors) == 2:
        return np.array([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    reducer = umap.UMAP(
        n_components=3,
        metric="cosine",
        n_neighbors=max(2, min(10, len(vectors) - 1)),
        min_dist=0.15,
        random_state=42,
    )
    return reducer.fit_transform(np.array(vectors, dtype=float))


def compute_umap_coordinates(
    embedding_records: dict[str, list[EmbeddingRecord]],
    profiles: list[ExhibitProfile],
) -> list[UmapCoordinate]:
    profile_map = {profile.exhibit_id: profile for profile in profiles}
    coordinates: list[UmapCoordinate] = []
    for discourse, records in embedding_records.items():
        for view in VIEW_NAMES:
            active: list[tuple[EmbeddingRecord, list[float]]] = []
            for record in records:
                vector = record.embeddings.get(view)
                if vector is not None:
                    active.append((record, vector))
            if not active:
                continue
            projected = _project([vector for _, vector in active])
            for (record, _), point in zip(active, projected, strict=True):
                profile = profile_map[record.exhibit_id]
                coordinates.append(
                    UmapCoordinate(
                        exhibit_id=record.exhibit_id,
                        discourse=discourse,
                        view=view,
                        x=float(point[0]),
                        y=float(point[1]),
                        z=float(point[2]),
                        title=record.english_metadata.get("title"),
                        metadata=record.english_metadata,
                        extracted_fields=[
                            field.model_dump() for field in profile.views[discourse][view].fields
                        ],
                    )
                )
    return coordinates
