from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any

import requests


WORLD_LABELS = {
    "official": "The Official World",
    "institutional": "The Staged World",
    "personal": "The Lived World",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_js_assignment(path: Path, variable_name: str, payload: Any) -> None:
    path.write_text(
        f"window.{variable_name} = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )


def existing_records(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            exhibit_id = str(row.get("exhibit_id") or "")
            if exhibit_id and row.get("description"):
                records[exhibit_id] = row
    return records


def archive_id(profile: dict[str, Any]) -> str:
    metadata = profile.get("metadata") or {}
    raw = metadata.get("archive_id")
    if raw in (None, ""):
        raw = (metadata.get("raw_metadata") or {}).get("archive_id")
    return str(raw or "").strip()


def image_path_for(profile: dict[str, Any], image_root: Path) -> Path | None:
    aid = archive_id(profile)
    if not aid:
        return None
    stem = f"{aid.zfill(4)}_c_l"
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = image_root / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def image_part(path: Path) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"inline_data": {"mime_type": mime_type, "data": data}}


def compact_metadata(profile: dict[str, Any]) -> dict[str, Any]:
    metadata = profile.get("english_metadata") or profile.get("metadata") or {}
    keep = [
        "title",
        "country",
        "location",
        "medium",
        "collection",
        "geolocated",
        "archive_id",
        "card_id",
    ]
    compact = {key: metadata.get(key) for key in keep if metadata.get(key) not in (None, "")}
    if "archive_id" not in compact:
        compact["archive_id"] = archive_id(profile)
    if "card_id" not in compact:
        compact["card_id"] = str((profile.get("metadata") or {}).get("card_id") or profile.get("exhibit_id") or "")
    return compact


def strongest_fields(profile: dict[str, Any], limit_per_world: int = 8) -> dict[str, list[str]]:
    views = profile.get("views") or {}
    out: dict[str, list[str]] = {}
    for discourse, label in WORLD_LABELS.items():
        fields = ((views.get(discourse) or {}).get("overall") or {}).get("fields") or []
        ordered = sorted(
            fields,
            key=lambda item: float(item.get("confidence") or 0),
            reverse=True,
        )
        values: list[str] = []
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
            values.append(f"{field}: {value}" if field else value)
            if len(values) >= limit_per_world:
                break
        out[label] = values
    return out


def build_prompt(profile: dict[str, Any]) -> str:
    payload = {
        "exhibit_id": str(profile.get("exhibit_id") or ""),
        "metadata": compact_metadata(profile),
        "extracted_readings": strongest_fields(profile),
    }
    return (
        "You are writing museum-facing exhibit copy for a critical, immersive demo "
        "about the Paris Universal Exposition of 1867.\n\n"
        "Write ONE concise English description for the selected exhibit.\n"
        "Audience: museum visitors.\n"
        "Tone: vivid, intelligent, slightly poetic, historically grounded, not academic.\n"
        "Length: 45-75 words.\n"
        "Use the image if provided, but do not invent specific facts not supported by the metadata or extracted readings.\n"
        "Avoid generic phrases such as 'this exhibit showcases'.\n"
        "Do not mention metadata, embeddings, OCR, AI, worlds, or source types.\n"
        "Do not use bullet points.\n"
        "Return strict JSON only: {\"description\": \"...\"}\n\n"
        "Source material:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def parse_description(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        data = json.loads(cleaned)
        description = str(data.get("description") or "").strip()
    except json.JSONDecodeError:
        description = cleaned
    return " ".join(description.split())


def call_gemini(
    *,
    api_key: str,
    model: str,
    prompt: str,
    image_path: Path | None,
    temperature: float,
    timeout: int,
    max_retries: int,
) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    parts: list[dict[str, Any]] = [{"text": prompt}]
    if image_path:
        parts.append(image_part(image_path))

    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "response_mime_type": "application/json",
        },
    }

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=body, timeout=timeout)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < max_retries:
                time.sleep(2.0 * (attempt + 1))
                continue
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise RuntimeError(f"No Gemini candidates returned: {data}")
            parts_out = ((candidates[0].get("content") or {}).get("parts") or [])
            text = "".join(str(part.get("text") or "") for part in parts_out)
            description = parse_description(text)
            if not description:
                raise RuntimeError(f"Empty Gemini description: {data}")
            return description
        except Exception as exc:  # noqa: BLE001 - keep checkpoint loop robust
            last_error = exc
            if attempt < max_retries:
                time.sleep(2.0 * (attempt + 1))
                continue
            break
    raise RuntimeError(str(last_error))


def call_model_queue(
    *,
    api_key: str,
    models: list[str],
    prompt: str,
    image_path: Path | None,
    temperature: float,
    timeout: int,
    max_retries: int,
) -> tuple[str, str]:
    errors: list[str] = []
    for model in models:
        try:
            description = call_gemini(
                api_key=api_key,
                model=model,
                prompt=prompt,
                image_path=image_path,
                temperature=temperature,
                timeout=timeout,
                max_retries=max_retries,
            )
            return description, model
        except Exception as exc:  # noqa: BLE001 - model fallback must be resilient
            errors.append(f"{model}: {exc}")
            continue
    raise RuntimeError("All models failed. " + " | ".join(errors))


def fallback_description(profile: dict[str, Any]) -> str:
    meta = compact_metadata(profile)
    title = meta.get("title") or f"Exhibit {profile.get('exhibit_id')}"
    medium = meta.get("medium") or "object"
    location = meta.get("location") or "the exposition"
    fields = strongest_fields(profile, limit_per_world=2)
    fragments = [value for values in fields.values() for value in values]
    if fragments:
        return (
            f"{title} draws the visitor toward a {medium.lower()} shaped by competing forms of attention. "
            f"In {location}, it gathers traces of {fragments[0].split(':')[-1].strip().lower()}, "
            "turning a catalogued object into a small argument about what the exposition chose to display, praise, or overlook."
        )
    return (
        f"{title} appears as a quiet {medium.lower()} within {location}. "
        "Its sparse record is part of its force: a reminder that absence, too, is a curatorial signal."
    )


def build_js_payload(records: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        exhibit_id: row["description"]
        for exhibit_id, row in sorted(records.items(), key=lambda item: item[0])
        if row.get("description")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate visitor-facing exhibit descriptions with Gemini.")
    parser.add_argument("--profiles", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_profiles.jsonl"))
    parser.add_argument("--image-root", type=Path, default=Path("Restored"))
    parser.add_argument("--output-jsonl", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_descriptions.jsonl"))
    parser.add_argument("--output-js", type=Path, default=Path("initial.descriptions.js"))
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"))
    parser.add_argument(
        "--fallback-models",
        default=os.getenv("GEMINI_FALLBACK_MODELS", "gemma-3-27b-it"),
        help="Comma-separated fallback models tried after --model.",
    )
    parser.add_argument("--api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit for testing. 0 means all exhibits.")
    parser.add_argument("--temperature", type=float, default=0.55)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--fallback-only", action="store_true", help="Generate local placeholder descriptions without API calls.")
    args = parser.parse_args()

    profiles = read_jsonl(args.profiles)
    if args.limit > 0:
        profiles = profiles[: args.limit]

    records = existing_records(args.output_jsonl)
    api_key = os.getenv(args.api_key_env) or os.getenv("GOOGLE_API_KEY")
    if not api_key and not args.fallback_only:
        raise SystemExit(
            f"Missing API key. Set ${args.api_key_env} or $GOOGLE_API_KEY, "
            "or pass --fallback-only for local placeholder copy."
        )
    models = [args.model] + [
        item.strip()
        for item in args.fallback_models.split(",")
        if item.strip() and item.strip() != args.model
    ]

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    completed = len(records)
    total = len(profiles)
    with args.output_jsonl.open("a", encoding="utf-8") as out:
        for index, profile in enumerate(profiles, start=1):
            exhibit_id = str(profile.get("exhibit_id") or "")
            if exhibit_id in records:
                print(f"Description {index}/{total}: skip exhibit {exhibit_id}")
                continue

            img = image_path_for(profile, args.image_root)
            try:
                if args.fallback_only:
                    description = fallback_description(profile)
                    model_used = "local-fallback"
                else:
                    description, model_used = call_model_queue(
                        api_key=api_key or "",
                        models=models,
                        prompt=build_prompt(profile),
                        image_path=img,
                        temperature=args.temperature,
                        timeout=args.timeout,
                        max_retries=args.max_retries,
                    )
                row = {
                    "exhibit_id": exhibit_id,
                    "archive_id": archive_id(profile),
                    "title": compact_metadata(profile).get("title"),
                    "image_path": str(img) if img else None,
                    "model": model_used,
                    "description": description,
                }
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                records[exhibit_id] = row
                completed += 1
                print(f"Description {index}/{total}: wrote exhibit {exhibit_id} ({completed} total)")
            except Exception as exc:  # noqa: BLE001 - keep going and preserve checkpoint
                print(f"Description {index}/{total}: failed exhibit {exhibit_id}: {exc}")

    write_js_assignment(args.output_js, "EXHIBIT_DESCRIPTIONS", build_js_payload(records))
    print(f"Wrote {len(records)} descriptions to {args.output_jsonl}")
    print(f"Wrote browser payload to {args.output_js}")


if __name__ == "__main__":
    main()
