from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


DISCOURSE_TO_WORLD = {
    "official": "official",
    "institutional": "staged",
    "personal": "lived",
}

VIEW_TO_FIELD = {
    "technical": "made",
    "category": "is",
    "exhibition": "belongs",
    "perception": "seen",
    "overall": "overall",
}

WORLD_TO_DISCOURSE = {world: discourse for discourse, world in DISCOURSE_TO_WORLD.items()}

WORLD_LABELS = {
    "official": "Official",
    "staged": "Staged",
    "lived": "Lived",
}

VIEW_LABELS = {
    "technical": "Technical",
    "category": "Category",
    "exhibition": "Exhibition",
    "perception": "Perception",
    "overall": "Overall",
}

PALETTE = [
    "#4fc3f7",
    "#c5b4fb",
    "#80cbc4",
    "#ffcc80",
    "#ff8ea8",
    "#9ccc65",
    "#ffd54f",
    "#90caf9",
]

HUE_BY_MEDIUM_KEYWORD = {
    "architecture": 34,
    "machine": 18,
    "machinery": 18,
    "sculpture": 220,
    "painting": 280,
    "textile": 140,
    "perfume": 12,
    "ceramic": 32,
    "metal": 16,
    "photograph": 300,
    "stereograph": 300,
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_js_assignment(path: Path, variable_name: str, payload: Any) -> None:
    path.write_text(
        f"window.{variable_name} = {json.dumps(payload, ensure_ascii=False)};\n",
        encoding="utf-8",
    )


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_xyz(coords: dict[tuple[str, str], tuple[float, float, float]]) -> dict[tuple[str, str], tuple[float, float, float]]:
    if not coords:
        return {}

    xs = [xyz[0] for xyz in coords.values()]
    ys = [xyz[1] for xyz in coords.values()]
    zs = [xyz[2] for xyz in coords.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    span_z = max(max_z - min_z, 1e-9)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    center_z = (min_z + max_z) / 2.0
    scale = max(span_x, span_y, span_z) / 5.2
    scale = scale or 1.0

    normalized: dict[tuple[str, str], tuple[float, float, float]] = {}
    for key, (x, y, z) in coords.items():
        normalized[key] = ((x - center_x) / scale, (y - center_y) / scale, (z - center_z) / scale)
    return normalized


def cosine_similarity(vec_a: list[float] | None, vec_b: list[float] | None) -> float | None:
    if not vec_a or not vec_b:
        return None
    if len(vec_a) != len(vec_b):
        return None
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return None
    return dot / (norm_a * norm_b)


def stable_color(seed: str) -> str:
    digest = hashlib.md5(seed.encode("utf-8")).digest()
    return PALETTE[digest[0] % len(PALETTE)]


def medium_hue(medium: str) -> int:
    medium_lower = (medium or "").lower()
    for keyword, hue in HUE_BY_MEDIUM_KEYWORD.items():
        if keyword in medium_lower:
            return hue
    digest = hashlib.md5(medium_lower.encode("utf-8")).digest()
    return 10 + (digest[0] % 320)


def field_items(field_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "key": record.get("field") or "Field",
            "val": record.get("value") or "",
            "evidence": record.get("evidence") or "",
            "confidence": record.get("confidence"),
        }
        for record in field_records
        if record.get("value")
    ]


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--outputs-path",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2"),
    )
    parser.add_argument("--html-path", type=Path, default=Path("initial.html"))
    parser.add_argument("--data-path", type=Path, default=Path("initial.data.js"))
    parser.add_argument("--embeddings-path", type=Path, default=Path("initial.embeddings.js"))
    return parser.parse_args()


def main() -> None:
    args = build_args()
    outputs_path = args.outputs_path

    profiles = read_jsonl(outputs_path / "exhibit_profiles.jsonl")
    umap_rows = read_jsonl(outputs_path / "umap_coordinates.jsonl")

    embeddings_by_world: dict[str, dict[str, dict[str, list[float] | None]]] = {
        "official": {},
        "staged": {},
        "lived": {},
    }

    for discourse, world in DISCOURSE_TO_WORLD.items():
        embed_path = outputs_path / f"exhibit_embeddings_{discourse}.jsonl"
        for row in read_jsonl(embed_path):
            exhibit_id = str(row["exhibit_id"])
            embeddings_by_world[world][exhibit_id] = row.get("embeddings", {})

    index_by_exhibit_id: dict[str, int] = {}
    exhibits: list[dict[str, Any]] = []
    raw_embedding_payload: dict[str, Any] = {}

    coords_by_world_view: dict[tuple[str, str], dict[tuple[str, str], tuple[float, float, float]]] = {}
    for row in umap_rows:
        world = DISCOURSE_TO_WORLD.get(row["discourse"])
        view = row["view"]
        if not world:
            continue
        coords_by_world_view.setdefault((world, view), {})[(str(row["exhibit_id"]), view)] = (
            safe_float(row["x"]),
            safe_float(row["y"]),
            safe_float(row.get("z")),
        )

    normalized_coords = {
        key: normalize_xyz(value)
        for key, value in coords_by_world_view.items()
    }

    divergence_by_world_view: dict[tuple[str, str], dict[str, float]] = {}
    for world in ("official", "staged", "lived"):
        world_embeddings = embeddings_by_world[world]
        for view in ("technical", "category", "exhibition", "perception"):
            field = VIEW_TO_FIELD[view]
            per_exhibit: dict[str, float] = {}
            distances: list[float] = []
            for exhibit_id, vectors in world_embeddings.items():
                sim = cosine_similarity(vectors.get(view), vectors.get("overall"))
                if sim is None:
                    continue
                distance = 1.0 - sim
                per_exhibit[exhibit_id] = distance
                distances.append(distance)
            if distances:
                min_d, max_d = min(distances), max(distances)
                span = max(max_d - min_d, 1e-9)
                divergence_by_world_view[(world, field)] = {
                    exhibit_id: ((distance - min_d) / span - 0.5) * 1.2
                    for exhibit_id, distance in per_exhibit.items()
                }
            else:
                divergence_by_world_view[(world, field)] = {}

    for idx, profile in enumerate(profiles):
        exhibit_id = str(profile["exhibit_id"])
        index_by_exhibit_id[exhibit_id] = idx
        metadata = profile["metadata"]
        raw_metadata = metadata.get("raw_metadata") or {}
        medium = metadata.get("medium") or "Unknown"
        title = metadata.get("title") or exhibit_id

        exhibit_record: dict[str, Any] = {
            "id": idx,
            "exhibitId": exhibit_id,
            "archiveId": str(metadata.get("archive_id", "")),
            "cardId": str(metadata.get("card_id", exhibit_id)),
            "name": title,
            "country": metadata.get("country"),
            "location": metadata.get("location"),
            "collection": metadata.get("collection"),
            "geolocated": metadata.get("geolocated"),
            "notes": raw_metadata.get("notes"),
            "include": raw_metadata.get("include", True),
            "type": medium,
            "color": stable_color(title + medium),
            "thumbHue": medium_hue(medium),
            "rawMetadata": raw_metadata,
            "pos": {"official": {}, "staged": {}, "lived": {}},
            "narratives": {"official": {}, "staged": {}, "lived": {}},
            "similar": {"official": {}, "staged": {}, "lived": {}},
            "simReason": {"official": {}, "staged": {}, "lived": {}},
        }

        for world, discourse in WORLD_TO_DISCOURSE.items():
            view_bundle = (profile.get("views") or {}).get(discourse) or {}
            for view, field_key in VIEW_TO_FIELD.items():
                if view == "overall":
                    continue
                entry = view_bundle.get(view) or {}
                exhibit_record["narratives"][world][field_key] = field_items(entry.get("fields") or [])
            overall_entry = view_bundle.get("overall") or {}
            exhibit_record["narratives"][world]["overall"] = field_items(overall_entry.get("fields") or [])

            for view, field_key in VIEW_TO_FIELD.items():
                if view == "overall":
                    continue
                coord_key = (world, view)
                specific = normalized_coords.get(coord_key, {}).get((exhibit_id, view))
                fallback = normalized_coords.get((world, "overall"), {}).get((exhibit_id, "overall"))
                official_specific = normalized_coords.get(("official", view), {}).get((exhibit_id, view))
                official_overall = normalized_coords.get(("official", "overall"), {}).get((exhibit_id, "overall"))
                x, y, z = specific or fallback or official_specific or official_overall or (0.0, 0.0, 0.0)
                z += divergence_by_world_view.get((world, field_key), {}).get(exhibit_id, 0.0) * 0.25
                exhibit_record["pos"][world][field_key] = [round(x, 6), round(y, 6), round(z, 6)]

            overall_specific = normalized_coords.get((world, "overall"), {}).get((exhibit_id, "overall"))
            official_overall = normalized_coords.get(("official", "overall"), {}).get((exhibit_id, "overall"))
            if overall_specific:
                overall_xy = overall_specific
            elif official_overall:
                overall_xy = official_overall
            else:
                sub_positions = [
                    exhibit_record["pos"][world][field_key]
                    for field_key in ("made", "is", "belongs", "seen")
                    if any(abs(component) > 1e-9 for component in exhibit_record["pos"][world][field_key][:2])
                ]
                if sub_positions:
                    overall_xy = (
                        sum(position[0] for position in sub_positions) / len(sub_positions),
                        sum(position[1] for position in sub_positions) / len(sub_positions),
                        sum(position[2] for position in sub_positions) / len(sub_positions),
                    )
                else:
                    overall_xy = (0.0, 0.0, 0.0)
            exhibit_record["pos"][world]["overall"] = [
                round(overall_xy[0], 6),
                round(overall_xy[1], 6),
                round(overall_xy[2], 6),
            ]

        exhibits.append(exhibit_record)
        raw_embedding_payload[exhibit_id] = {
            "official": embeddings_by_world["official"].get(exhibit_id, {}),
            "staged": embeddings_by_world["staged"].get(exhibit_id, {}),
            "lived": embeddings_by_world["lived"].get(exhibit_id, {}),
        }

    # Compute nearest neighbors in each world/view embedding space.
    for world in ("official", "staged", "lived"):
        world_vectors = embeddings_by_world[world]
        for view, field_key in VIEW_TO_FIELD.items():
            rows: list[tuple[str, list[float]]] = []
            if view == "overall":
                target_view = "overall"
            else:
                target_view = view
            for exhibit_id, bundle in world_vectors.items():
                vector = bundle.get(target_view)
                if vector:
                    rows.append((exhibit_id, vector))
            for exhibit_id, vector in rows:
                scored: list[tuple[str, float]] = []
                for other_id, other_vector in rows:
                    if other_id == exhibit_id:
                        continue
                    sim = cosine_similarity(vector, other_vector)
                    if sim is None:
                        continue
                    scored.append((other_id, sim))
                scored.sort(key=lambda item: item[1], reverse=True)
                top = scored[:5]
                exhibit_index = index_by_exhibit_id.get(exhibit_id)
                if exhibit_index is None:
                    continue
                exhibits[exhibit_index]["similar"][world][field_key] = [
                    index_by_exhibit_id[other_id]
                    for other_id, _ in top
                    if other_id in index_by_exhibit_id
                ]
                exhibits[exhibit_index]["simReason"][world][field_key] = {
                    str(index_by_exhibit_id[other_id]): f"{WORLD_LABELS[world]} {VIEW_LABELS[target_view]} affinity ({score:.2f})"
                    for other_id, score in top
                    if other_id in index_by_exhibit_id
                }

    # Ensure all keys exist even when empty.
    empty_fields = ["made", "is", "belongs", "seen", "overall"]
    for exhibit in exhibits:
        for world in ("official", "staged", "lived"):
            for key in empty_fields:
                exhibit["narratives"][world].setdefault(key, [])
                exhibit["similar"][world].setdefault(key, [])
                exhibit["simReason"][world].setdefault(key, {})
                exhibit["pos"][world].setdefault(key, [0.0, 0.0, 0.0])

    write_js_assignment(args.data_path, "REAL_EXHIBITS", exhibits)
    write_js_assignment(args.embeddings_path, "REAL_EMBEDDINGS", raw_embedding_payload)

    summary = {
        "exhibits": len(exhibits),
        "data_path": str(args.data_path),
        "embeddings_path": str(args.embeddings_path),
        "source_outputs": str(outputs_path),
        "html_path": str(args.html_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
