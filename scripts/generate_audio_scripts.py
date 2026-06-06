from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from google import genai


WORLD_SPECS = {
    "official": {
        "label": "The Official World",
        "voice": "Measured, ceremonial, archival, confident. Speaks through catalogues, nations, materials, classifications, and official order.",
    },
    "staged": {
        "label": "The Staged World",
        "voice": "Curatorial, analytical, institutional, slightly critical. Speaks through experts, systems, arrangements, and interpretive staging.",
    },
    "lived": {
        "label": "The Lived World",
        "voice": "Intimate, sensory, bodily, alert. Speaks through walking, fatigue, wonder, confusion, touch, crowding, and private memory.",
    },
}

WORLD_TO_PROFILE_KEY = {
    "official": "official",
    "staged": "institutional",
    "lived": "personal",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_descriptions(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    records: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            exhibit_id = str(row.get("exhibit_id") or "")
            if exhibit_id and row.get("description"):
                records[exhibit_id] = str(row["description"])
    return records


def find_profile(profiles: list[dict[str, Any]], exhibit_id: str | None) -> dict[str, Any]:
    if exhibit_id:
        for profile in profiles:
            if str(profile.get("exhibit_id")) == str(exhibit_id):
                return profile
        raise SystemExit(f"Exhibit not found: {exhibit_id}")
    return profiles[0]


def field_summary(profile: dict[str, Any], world: str, limit: int = 10) -> list[str]:
    profile_world = WORLD_TO_PROFILE_KEY[world]
    fields = (((profile.get("views") or {}).get(profile_world) or {}).get("overall") or {}).get("fields") or []
    ordered = sorted(fields, key=lambda item: float(item.get("confidence") or 0), reverse=True)
    out: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        field = str(item.get("field") or "").strip()
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f"{field}: {value}" if field else value)
        if len(out) >= limit:
            break
    return out


def metadata_summary(profile: dict[str, Any]) -> dict[str, Any]:
    metadata = profile.get("english_metadata") or profile.get("metadata") or {}
    raw_meta = (profile.get("metadata") or {}).get("raw_metadata") or {}
    return {
        "exhibit_id": str(profile.get("exhibit_id") or ""),
        "archive_id": str((profile.get("metadata") or {}).get("archive_id") or raw_meta.get("archive_id") or ""),
        "title": metadata.get("title") or (profile.get("metadata") or {}).get("title"),
        "medium": metadata.get("medium") or (profile.get("metadata") or {}).get("medium"),
        "country": metadata.get("country") or (profile.get("metadata") or {}).get("country"),
        "location": metadata.get("location") or (profile.get("metadata") or {}).get("location"),
        "collection": metadata.get("collection") or (profile.get("metadata") or {}).get("collection"),
        "notes": raw_meta.get("notes"),
    }


def build_prompt(profile: dict[str, Any], world: str, exhibit_description: str) -> str:
    spec = WORLD_SPECS[world]
    payload = {
        "world": spec["label"],
        "voice_style": spec["voice"],
        "metadata": metadata_summary(profile),
        "short_visual_description": exhibit_description,
        "extracted_information_for_this_world": field_summary(profile, world),
    }
    return (
        "You are writing ONE audio narration script for a museum demo about the 1867 Paris Universal Exposition.\n"
        "The script will be spoken aloud by a distinct audio agent.\n\n"
        "Requirements:\n"
        "- English only.\n"
        "- 65-95 words.\n"
        "- Vivid, narrative, and alive; not a flat label description.\n"
        "- Use the provided world perspective as the speaking position.\n"
        "- Do not invent unsupported historical facts.\n"
        "- If this world has little information, turn absence into a meaningful curatorial signal.\n"
        "- Avoid saying 'metadata', 'field', 'AI', 'OCR', 'embedding', or 'source type'.\n"
        "- Do not use bullet points.\n"
        "- Return strict JSON only: {\"script\": \"...\"}\n\n"
        "Audio source material:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def parse_script(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(cleaned)
        script = str(data.get("script") or "").strip()
    except json.JSONDecodeError:
        script = cleaned
    return " ".join(script.split())


def generate_script(client: genai.Client, model: str, prompt: str) -> str:
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "temperature": 0.65,
            "response_mime_type": "application/json",
        },
    )
    script = parse_script(response.text or "")
    if not script:
        raise RuntimeError("Gemini returned an empty script")
    return script


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate three-world audio scripts for one exhibit.")
    parser.add_argument("--profiles", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_profiles.jsonl"))
    parser.add_argument("--descriptions", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_descriptions_short.jsonl"))
    parser.add_argument("--fallback-descriptions", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_descriptions.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_scripts_sample.json"))
    parser.add_argument("--exhibit-id", default=None)
    parser.add_argument("--model", default=os.getenv("GEMINI_AUDIO_MODEL", "gemini-2.0-flash"))
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Missing GEMINI_API_KEY or GOOGLE_API_KEY")

    profiles = read_jsonl(args.profiles)
    profile = find_profile(profiles, args.exhibit_id)
    exhibit_id = str(profile.get("exhibit_id") or "")
    descriptions = load_descriptions(args.descriptions)
    if exhibit_id not in descriptions:
        descriptions.update(load_descriptions(args.fallback_descriptions))
    exhibit_description = descriptions.get(exhibit_id, "")

    client = genai.Client(api_key=api_key)
    result = {
        "exhibit_id": exhibit_id,
        "metadata": metadata_summary(profile),
        "model": args.model,
        "scripts": {},
    }
    for world in ("official", "staged", "lived"):
        prompt = build_prompt(profile, world, exhibit_description)
        result["scripts"][world] = {
            "label": WORLD_SPECS[world]["label"],
            "voice_style": WORLD_SPECS[world]["voice"],
            "script": generate_script(client, args.model, prompt),
        }
        print(f"Wrote {world} script")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved sample audio scripts to {args.output}")


if __name__ == "__main__":
    main()
