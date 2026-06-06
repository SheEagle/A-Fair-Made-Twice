from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

try:
    from google import genai
except ImportError:  # pragma: no cover - optional SDK path
    genai = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


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


def write_js_assignment(path: Path, variable_name: str, payload: Any) -> None:
    path.write_text(
        f"window.{variable_name} = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
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


def prompt_for(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "").strip()
    description = str(row.get("description") or "").strip()
    return (
        "Rewrite this museum exhibit caption into ONE shorter English description.\n"
        "Target length: 22-34 words.\n"
        "Tone: vivid, concise, poetic, historically alert.\n"
        "Keep the strongest image or idea. Remove filler.\n"
        "Do not use bullet points. Do not mention AI, metadata, OCR, or models.\n"
        "Return strict JSON only: {\"description\": \"...\"}\n\n"
        f"Title: {title}\n"
        f"Original description: {description}"
    )


def call_gemini(
    *,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
    timeout: int,
    max_retries: int,
) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
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
                time.sleep(1.5 * (attempt + 1))
                continue
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise RuntimeError(f"No candidates returned: {data}")
            text = "".join(
                str(part.get("text") or "")
                for part in ((candidates[0].get("content") or {}).get("parts") or [])
            )
            description = parse_description(text)
            if not description:
                raise RuntimeError(f"Empty description: {data}")
            return description
        except Exception as exc:  # noqa: BLE001 - preserve checkpoint loop
            last_error = exc
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    raise RuntimeError(str(last_error))


def call_google_genai(
    *,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
    max_retries: int,
) -> str:
    if genai is None:
        raise RuntimeError("google-genai is not installed. Run: python -m pip install google-genai")

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                },
            )
            description = parse_description(response.text or "")
            if not description:
                raise RuntimeError(f"Empty description from {model}")
            return description
        except Exception as exc:  # noqa: BLE001 - preserve checkpoint loop
            last_error = exc
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    raise RuntimeError(str(last_error))


def compact_locally(text: str, max_words: int = 34) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" ,;:") + "."


def main() -> None:
    parser = argparse.ArgumentParser(description="Shorten generated exhibit descriptions.")
    parser.add_argument("--input-jsonl", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_descriptions.jsonl"))
    parser.add_argument("--output-jsonl", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_descriptions_short.jsonl"))
    parser.add_argument("--output-js", type=Path, default=Path("initial.descriptions.js"))
    parser.add_argument("--model", default=os.getenv("GEMINI_SHORT_MODEL", "gemini-2.0-flash-lite"))
    parser.add_argument("--api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--temperature", type=float, default=0.35)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--provider", choices=["sdk", "rest"], default="sdk")
    args = parser.parse_args()

    rows = read_jsonl(args.input_jsonl)
    if args.limit > 0:
        rows = rows[: args.limit]

    done = existing_records(args.output_jsonl)
    api_key = os.getenv(args.api_key_env) or os.getenv("GOOGLE_API_KEY")
    if not api_key and not args.local_only:
        raise SystemExit(f"Missing API key. Set ${args.api_key_env} or pass --local-only.")

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as out:
        for index, row in enumerate(rows, start=1):
            exhibit_id = str(row.get("exhibit_id") or "")
            if exhibit_id in done:
                print(f"Shorten {index}/{len(rows)}: skip exhibit {exhibit_id}")
                continue
            try:
                if args.local_only:
                    description = compact_locally(str(row.get("description") or ""))
                    model_used = "local-compact"
                else:
                    if args.provider == "sdk":
                        description = call_google_genai(
                            api_key=api_key or "",
                            model=args.model,
                            prompt=prompt_for(row),
                            temperature=args.temperature,
                            max_retries=args.max_retries,
                        )
                    else:
                        description = call_gemini(
                            api_key=api_key or "",
                            model=args.model,
                            prompt=prompt_for(row),
                            temperature=args.temperature,
                            timeout=args.timeout,
                            max_retries=args.max_retries,
                        )
                    model_used = args.model
                out_row = {
                    **row,
                    "source_description": row.get("description"),
                    "model": model_used,
                    "description": description,
                }
                out.write(json.dumps(out_row, ensure_ascii=False) + "\n")
                out.flush()
                done[exhibit_id] = out_row
                print(f"Shorten {index}/{len(rows)}: wrote exhibit {exhibit_id}")
            except Exception as exc:  # noqa: BLE001
                print(f"Shorten {index}/{len(rows)}: failed exhibit {exhibit_id}: {exc}")

    payload = {
        exhibit_id: item["description"]
        for exhibit_id, item in sorted(done.items(), key=lambda pair: pair[0])
        if item.get("description")
    }
    write_js_assignment(args.output_js, "EXHIBIT_DESCRIPTIONS", payload)
    print(f"Wrote {len(done)} short descriptions to {args.output_jsonl}")
    print(f"Updated browser payload at {args.output_js}")


if __name__ == "__main__":
    main()
