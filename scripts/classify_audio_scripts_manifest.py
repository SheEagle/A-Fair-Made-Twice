from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.audio.classification import classify_all_worlds  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def profile_index(profiles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(profile.get("exhibit_id") or ""): profile for profile in profiles}


def script_map(audio_row: dict[str, Any]) -> dict[str, str]:
    return {
        world: str(item.get("script") or "")
        for world, item in (audio_row.get("scripts") or {}).items()
        if world in {"official", "staged", "lived"}
    }


def title_for(profile: dict[str, Any], audio_row: dict[str, Any]) -> str:
    metadata = audio_row.get("metadata") or profile.get("english_metadata") or profile.get("metadata") or {}
    return str(metadata.get("title") or "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify generated audio scripts into voice/emotion classes.")
    parser.add_argument(
        "--audio-scripts",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_scripts_trio_diverse_full.jsonl"),
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_profiles.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_voice_manifest.jsonl"),
    )
    parser.add_argument("--summary", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_voice_summary.json"))
    args = parser.parse_args()

    profiles = profile_index(read_jsonl(args.profiles))
    audio_rows = read_jsonl(args.audio_scripts)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, dict[str, int]] = {"official": {}, "staged": {}, "lived": {}}
    missing_profiles: list[str] = []

    with args.output.open("w", encoding="utf-8") as out:
        for audio_row in audio_rows:
            exhibit_id = str(audio_row.get("exhibit_id") or "")
            profile = profiles.get(exhibit_id)
            if not profile:
                missing_profiles.append(exhibit_id)
                continue
            scripts = script_map(audio_row)
            classification = classify_all_worlds(profile, scripts)
            for world, item in classification.items():
                label = str(item["class"])
                counts[world][label] = counts[world].get(label, 0) + 1
            out.write(
                json.dumps(
                    {
                        "exhibit_id": exhibit_id,
                        "title": title_for(profile, audio_row),
                        "classification": classification,
                        "scripts": scripts,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    summary = {
        "audio_script_count": len(audio_rows),
        "classified_count": len(audio_rows) - len(missing_profiles),
        "missing_profiles": missing_profiles,
        "class_counts": counts,
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved manifest to {args.output}")
    print(f"Saved summary to {args.summary}")


if __name__ == "__main__":
    main()
