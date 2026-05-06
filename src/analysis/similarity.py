from __future__ import annotations

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from src.models import VIEW_NAMES, EmbeddingRecord


def build_similarity_rows(embedding_records: dict[str, list[EmbeddingRecord]]) -> list[dict]:
    rows: list[dict] = []
    for discourse, records in embedding_records.items():
        for view in VIEW_NAMES:
            active = [
                (record.exhibit_id, record.embeddings[view])
                for record in records
                if record.embeddings.get(view) is not None
            ]
            if len(active) < 2:
                continue
            exhibit_ids = [item[0] for item in active]
            matrix = cosine_similarity(np.array([item[1] for item in active], dtype=float))
            for row_index, exhibit_id_a in enumerate(exhibit_ids):
                for col_index, exhibit_id_b in enumerate(exhibit_ids):
                    rows.append(
                        {
                            "discourse": discourse,
                            "view": view,
                            "exhibit_id_a": exhibit_id_a,
                            "exhibit_id_b": exhibit_id_b,
                            "similarity": float(matrix[row_index, col_index]),
                        }
                    )
    return rows
