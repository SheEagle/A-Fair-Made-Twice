from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.audio.classification import is_absent, presets_for, world_text  # noqa: E402


WORLD_CLASSES = {
    "official": ["classification", "ceremony", "technical", "silence"],
    "staged": ["analysis", "display", "comparison", "critique", "absence"],
    "lived": [
        "wonder",
        "awe",
        "delight",
        "grief",
        "pity",
        "dread",
        "loneliness",
        "melancholy",
        "unease",
        "fatigue",
        "absence",
        "neutral",
    ],
}

WORLD_TO_PROFILE_KEY = {
    "official": "official",
    "staged": "institutional",
    "lived": "personal",
}

NO_INFORMATION_REASON = {
    "official": "Official records contain little exhibit-specific detail, so silence should remain audible.",
    "staged": "Institutional commentary is sparse, so the staged voice should preserve absence.",
    "lived": "Personal accounts are missing or thin, so the lived voice should acknowledge absence.",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()


def existing_ids(path: Path) -> set[str]:
    return {str(row.get("exhibit_id") or "") for row in read_jsonl(path)}


def profile_index(profiles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(profile.get("exhibit_id") or ""): profile for profile in profiles}


def script_map(audio_row: dict[str, Any]) -> dict[str, str]:
    return {
        world: str(item.get("script") or "")
        for world, item in (audio_row.get("scripts") or {}).items()
        if world in WORLD_CLASSES
    }


def title_for(profile: dict[str, Any], audio_row: dict[str, Any]) -> str:
    metadata = audio_row.get("metadata") or profile.get("english_metadata") or profile.get("metadata") or {}
    return str(metadata.get("title") or "")


def fields_summary(profile: dict[str, Any], world: str, max_fields: int = 8) -> list[dict[str, str]]:
    profile_key = WORLD_TO_PROFILE_KEY[world]
    seen: set[tuple[str, str]] = set()
    fields: list[dict[str, str]] = []
    views = ((profile.get("views") or {}).get(profile_key) or {})
    for view_name in ("technical", "category", "exhibition", "perception", "overall"):
        entry = views.get(view_name) or {}
        for field in entry.get("fields") or []:
            key = (str(field.get("field") or ""), str(field.get("value") or ""))
            if key in seen or not key[1]:
                continue
            seen.add(key)
            fields.append(
                {
                    "view": view_name,
                    "field": key[0],
                    "value": key[1],
                }
            )
            if len(fields) >= max_fields:
                return fields
    return fields


def build_prompt(profile: dict[str, Any], audio_row: dict[str, Any]) -> str:
    scripts = script_map(audio_row)
    metadata = audio_row.get("metadata") or profile.get("english_metadata") or profile.get("metadata") or {}
    payload = {
        "exhibit_id": str(profile.get("exhibit_id") or audio_row.get("exhibit_id") or ""),
        "metadata": {
            "title": metadata.get("title"),
            "medium": metadata.get("medium"),
            "country": metadata.get("country"),
            "location": metadata.get("location"),
        },
        "worlds": {
            world: {
                "audio_script": scripts.get(world, ""),
                "extracted_fields": fields_summary(profile, world),
            }
            for world in ("official", "staged", "lived")
        },
    }
    return (
        "You are classifying audio direction for a critical digital museum installation about the 1867 Paris Exposition.\n"
        "Classify each world separately, but compare the three worlds so their voices remain distinct.\n\n"
        "World meanings:\n"
        "- official: institutional authority, catalogue voice, classification, prizes, state confidence, or official silence.\n"
        "- staged: expert/critic/curatorial interpretation, display logic, comparison, critique, or interpretive absence.\n"
        "- lived: visitor sensation, bodily reaction, fatigue, wonder, unease, pleasure, memory, or personal absence.\n\n"
        "Allowed classes:\n"
        f"- official: {', '.join(WORLD_CLASSES['official'])}\n"
        f"- staged: {', '.join(WORLD_CLASSES['staged'])}\n"
        f"- lived: {', '.join(WORLD_CLASSES['lived'])}\n\n"
        "Return JSON only with exactly this shape:\n"
        "{\n"
        '  "official": {"class": "...", "intensity": 1, "voice_direction": "...", "pacing": "...", "background_cue": "...", "reason": "..."},\n'
        '  "staged": {"class": "...", "intensity": 1, "voice_direction": "...", "pacing": "...", "background_cue": "...", "reason": "..."},\n'
        '  "lived": {"class": "...", "intensity": 1, "voice_direction": "...", "pacing": "...", "background_cue": "...", "reason": "..."}\n'
        "}\n\n"
        "Rules:\n"
        "- class must be one of the allowed classes for that world.\n"
        "- intensity is 1 to 5.\n"
        "- voice_direction should be concise and performable by a voice actor or ElevenLabs.\n"
        "- background_cue should be concrete, short, and related to the 1867 exposition atmosphere.\n"
        "- reason should explain the signal in one short English sentence.\n"
        "- If a world has no information, use official:silence, staged:absence, or lived:absence.\n"
        "- Do not invent facts beyond the provided scripts and extracted fields.\n\n"
        "Input:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def parse_response(text: str) -> dict[str, dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Gemini response is not an object")
    return data


def preset_payload(world: str, label: str) -> dict[str, str]:
    preset = presets_for(world)[label]
    return {
        "voice": preset.voice,
        "rate": preset.rate,
        "pitch": preset.pitch,
    }


def normalize_item(world: str, item: dict[str, Any]) -> dict[str, Any]:
    allowed = WORLD_CLASSES[world]
    label = str(item.get("class") or "").strip().lower()
    if label not in allowed:
        label = {"official": "classification", "staged": "analysis", "lived": "neutral"}[world]
    try:
        intensity = int(item.get("intensity", 3))
    except (TypeError, ValueError):
        intensity = 3
    intensity = max(1, min(5, intensity))
    result = {
        "world": world,
        "class": label,
        "confidence": round(0.58 + intensity * 0.07, 3),
        "intensity": intensity,
        "voice_direction": str(item.get("voice_direction") or "").strip(),
        "pacing": str(item.get("pacing") or "").strip(),
        "background_cue": str(item.get("background_cue") or "").strip(),
        "reason": str(item.get("reason") or "").strip(),
        "classifier": "gemini_flash",
    }
    result.update(preset_payload(world, label))
    return result


def absent_item(world: str) -> dict[str, Any]:
    label = "silence" if world == "official" else "absence"
    item = {
        "class": label,
        "intensity": 2,
        "voice_direction": "quiet, sparse, deliberately restrained",
        "pacing": "slow with long pauses",
        "background_cue": "distant exhibition hall air, almost empty",
        "reason": NO_INFORMATION_REASON[world],
    }
    return normalize_item(world, item)


def generate_content_rest(api_key: str, model: str, prompt: str, timeout: int) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = requests.post(
        url,
        params={"key": api_key},
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.25,
                "topP": 0.8,
                "responseMimeType": "application/json",
            },
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data.get('promptFeedback') or data}")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text = "".join(str(part.get("text") or "") for part in parts)
    if not text.strip():
        raise RuntimeError(f"Gemini returned empty content: {data}")
    return text


def classify_with_gemini(api_key: str, model: str, profile: dict[str, Any], audio_row: dict[str, Any], timeout: int) -> dict[str, Any]:
    prompt = build_prompt(profile, audio_row)
    parsed = parse_response(generate_content_rest(api_key, model, prompt, timeout))
    classification: dict[str, Any] = {}
    scripts = script_map(audio_row)
    for world in ("official", "staged", "lived"):
        text = world_text(profile, world, scripts.get(world))
        if is_absent(profile, world, text):
            classification[world] = absent_item(world)
        else:
            classification[world] = normalize_item(world, parsed.get(world) or {})
    return classification


def is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "quota exceeded" in text


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify three-world audio scripts with Gemini Flash.")
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
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_voice_manifest_gemini_flash.jsonl"),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_voice_summary_gemini_flash.json"),
    )
    parser.add_argument("--model", default=os.getenv("GEMINI_CLASSIFY_MODEL", "gemini-2.5-flash"))
    parser.add_argument("--request-timeout", type=int, default=75)
    parser.add_argument("--exhibit-ids", default="", help="Comma-separated exhibit IDs to classify.")
    parser.add_argument("--skip-ids", default="", help="Comma-separated exhibit IDs to skip during this run.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Missing GEMINI_API_KEY or GOOGLE_API_KEY")

    profiles = profile_index(read_jsonl(args.profiles))
    audio_rows = read_jsonl(args.audio_scripts)
    skip_ids = {item.strip() for item in args.skip_ids.split(",") if item.strip()}
    if args.exhibit_ids:
        wanted = {item.strip() for item in args.exhibit_ids.split(",") if item.strip()}
        selected = [row for row in audio_rows if str(row.get("exhibit_id") or "") in wanted]
    else:
        selected = audio_rows if args.all else audio_rows[: args.limit or 3]
    if skip_ids:
        selected = [row for row in selected if str(row.get("exhibit_id") or "") not in skip_ids]
    done = existing_ids(args.output)

    counts: dict[str, dict[str, int]] = {"official": {}, "staged": {}, "lived": {}}
    for row in read_jsonl(args.output):
        for world, item in (row.get("classification") or {}).items():
            label = str(item.get("class") or "")
            if world in counts and label:
                counts[world][label] = counts[world].get(label, 0) + 1

    written = 0
    skipped = 0
    failed: list[str] = []
    for index, audio_row in enumerate(selected, start=1):
        exhibit_id = str(audio_row.get("exhibit_id") or "")
        if exhibit_id in done:
            skipped += 1
            print(f"Gemini classify {index}/{len(selected)}: skip exhibit {exhibit_id}")
            continue
        profile = profiles.get(exhibit_id)
        if not profile:
            failed.append(exhibit_id)
            print(f"Gemini classify {index}/{len(selected)}: missing profile {exhibit_id}")
            continue
        for attempt in range(1, 5):
            try:
                classification = classify_with_gemini(api_key, args.model, profile, audio_row, args.request_timeout)
                for world, item in classification.items():
                    label = str(item["class"])
                    counts[world][label] = counts[world].get(label, 0) + 1
                write_jsonl_row(
                    args.output,
                    {
                        "exhibit_id": exhibit_id,
                        "title": title_for(profile, audio_row),
                        "model": args.model,
                        "classification": classification,
                        "scripts": script_map(audio_row),
                    },
                )
                done.add(exhibit_id)
                written += 1
                print(f"Gemini classify {index}/{len(selected)}: wrote exhibit {exhibit_id}")
                break
            except Exception as exc:  # noqa: BLE001 - batch classifier should checkpoint and continue
                if is_rate_limit_error(exc) and attempt < 4:
                    wait_seconds = 65
                    print(
                        f"Gemini classify {index}/{len(selected)}: rate limited for exhibit {exhibit_id}; "
                        f"sleep {wait_seconds}s then retry {attempt + 1}/4"
                    )
                    time.sleep(wait_seconds)
                    continue
                failed.append(exhibit_id)
                print(f"Gemini classify {index}/{len(selected)}: failed exhibit {exhibit_id}: {exc}")
                break

    summary = {
        "model": args.model,
        "input_count": len(audio_rows),
        "selected_count": len(selected),
        "existing_before_or_skipped": skipped,
        "written_this_run": written,
        "failed": failed,
        "class_counts": counts,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved manifest to {args.output}")
    print(f"Saved summary to {args.summary}")


if __name__ == "__main__":
    main()
