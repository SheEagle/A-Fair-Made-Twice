from __future__ import annotations

import argparse
from pathlib import Path

from src.analysis.coordinates import compute_umap_coordinates
from src.models import DISCOURSE_TYPES, EmbeddingRecord, ExhibitProfile
from src.storage.files import read_jsonl, write_jsonl


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--outputs-path",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2"),
    )
    return parser.parse_args()


def main() -> None:
    args = build_args()
    outputs_path = args.outputs_path

    profiles = [
        ExhibitProfile.model_validate(row)
        for row in read_jsonl(outputs_path / "exhibit_profiles.jsonl")
    ]
    embedding_records: dict[str, list[EmbeddingRecord]] = {}
    for discourse in DISCOURSE_TYPES:
        embedding_records[discourse] = [
            EmbeddingRecord.model_validate(row)
            for row in read_jsonl(outputs_path / f"exhibit_embeddings_{discourse}.jsonl")
        ]

    coordinates = compute_umap_coordinates(embedding_records, profiles)
    write_jsonl(
        outputs_path / "umap_coordinates.jsonl",
        [coordinate.model_dump(mode="json") for coordinate in coordinates],
    )
    print(f"Wrote {len(coordinates)} 3D UMAP coordinates to {outputs_path / 'umap_coordinates.jsonl'}")


if __name__ == "__main__":
    main()
