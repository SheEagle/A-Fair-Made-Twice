from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.audio.classification import classify_all_worlds  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify audio voice modes for a sample exhibit.")
    parser.add_argument("--profiles", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_profiles.jsonl"))
    parser.add_argument("--audio-script", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_scripts_sample.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_classification_sample.json"))
    args = parser.parse_args()

    audio = json.loads(args.audio_script.read_text(encoding="utf-8"))
    exhibit_id = str(audio["exhibit_id"])
    profile = next((row for row in read_jsonl(args.profiles) if str(row.get("exhibit_id")) == exhibit_id), None)
    if profile is None:
        raise SystemExit(f"Profile not found: {exhibit_id}")

    scripts = {
        world: item.get("script", "")
        for world, item in (audio.get("scripts") or {}).items()
    }
    result = {
        "exhibit_id": exhibit_id,
        "classification": classify_all_worlds(profile, scripts),
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
