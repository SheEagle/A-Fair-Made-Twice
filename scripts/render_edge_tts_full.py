from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

import edge_tts


MOJIBAKE_FIXES = {
    "鈥檚": "'s",
    "鈥檛": "n't",
    "鈥檓": "'m",
    "鈥檙": "'r",
    "鈥檝": "'v",
    "鈥檇": "'d",
    "鈥": "'",
}

VOICE_OVERRIDES = {
    "lived": {
        "grief": {"voice": "en-GB-ThomasNeural", "rate": "-16%", "pitch": "-12Hz"},
        "melancholy": {"voice": "en-GB-ThomasNeural", "rate": "-13%", "pitch": "-10Hz"},
        "loneliness": {"voice": "en-GB-ThomasNeural", "rate": "-14%", "pitch": "-12Hz"},
        "absence": {"voice": "en-GB-ThomasNeural", "rate": "-18%", "pitch": "-14Hz"},
        "pity": {"voice": "en-GB-SoniaNeural", "rate": "-10%", "pitch": "-7Hz"},
        "dread": {"voice": "en-GB-SoniaNeural", "rate": "-10%", "pitch": "-8Hz"},
    },
    "staged": {
        "absence": {"voice": "en-GB-ThomasNeural", "rate": "-14%", "pitch": "-10Hz"},
        "critique": {"voice": "en-GB-SoniaNeural", "rate": "-8%", "pitch": "-6Hz"},
    },
    "official": {
        "silence": {"voice": "en-GB-ThomasNeural", "rate": "-16%", "pitch": "-12Hz"},
        "ceremony": {"voice": "en-GB-RyanNeural", "rate": "-10%", "pitch": "-8Hz"},
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def clean_text(text: str) -> str:
    cleaned = text
    for bad, good in MOJIBAKE_FIXES.items():
        cleaned = cleaned.replace(bad, good)
    return re.sub(r"\s+", " ", cleaned).strip()


def script_map(audio_row: dict[str, Any]) -> dict[str, str]:
    return {
        world: clean_text(str(item.get("script") or ""))
        for world, item in (audio_row.get("scripts") or {}).items()
        if world in {"official", "staged", "lived"}
    }


def audio_index(audio_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("exhibit_id") or ""): row for row in audio_rows}


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "untitled"


def voice_config(classification: dict[str, Any], world: str) -> dict[str, str]:
    item = classification.get(world) or {}
    label = str(item.get("class") or "neutral")
    override = VOICE_OVERRIDES.get(world, {}).get(label)
    if override:
        return override
    return {
        "voice": str(item.get("voice") or "en-US-JennyNeural"),
        "rate": str(item.get("rate") or "+0%"),
        "pitch": str(item.get("pitch") or "+0Hz"),
    }


async def render_one(text: str, out_path: Path, cfg: dict[str, str], retries: int = 3) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice=cfg["voice"], rate=cfg["rate"], pitch=cfg["pitch"])
            await communicate.save(str(out_path))
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(5 * attempt)
    raise RuntimeError(f"Edge TTS failed for {out_path}: {last_error}")


def existing_manifest_keys(path: Path) -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    if not path.exists():
        return done
    for row in read_jsonl(path):
        if row.get("status") == "ok":
            done.add((str(row.get("exhibit_id") or ""), str(row.get("world") or "")))
    return done


async def main_async(args: argparse.Namespace) -> None:
    audio_rows = audio_index(read_jsonl(args.audio_scripts))
    voice_rows = read_jsonl(args.voice_manifest)
    selected = voice_rows[: args.limit] if args.limit > 0 else voice_rows
    done = existing_manifest_keys(args.manifest)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    with args.manifest.open("a", encoding="utf-8") as manifest:
        for index, voice_row in enumerate(selected, start=1):
            exhibit_id = str(voice_row.get("exhibit_id") or "")
            audio_row = audio_rows.get(exhibit_id)
            if not audio_row:
                print(f"Edge TTS {index}/{len(selected)}: missing audio script {exhibit_id}")
                continue
            title = str(voice_row.get("title") or (audio_row.get("metadata") or {}).get("title") or "")
            scripts = script_map(audio_row)
            classification = voice_row.get("classification") or {}
            title_slug = safe_slug(title)

            for world in ("official", "staged", "lived"):
                if (exhibit_id, world) in done:
                    continue
                text = scripts.get(world, "")
                if not text:
                    continue
                label = str((classification.get(world) or {}).get("class") or "neutral")
                cfg = voice_config(classification, world)
                out_path = args.output_dir / f"{exhibit_id}_{title_slug}_{world}_{label}.mp3"
                try:
                    await render_one(text, out_path, cfg, retries=args.retries)
                    row = {
                        "status": "ok",
                        "exhibit_id": exhibit_id,
                        "title": title,
                        "world": world,
                        "class": label,
                        "path": str(out_path),
                        "voice": cfg["voice"],
                        "rate": cfg["rate"],
                        "pitch": cfg["pitch"],
                        "script": text,
                    }
                    done.add((exhibit_id, world))
                    print(f"Edge TTS {index}/{len(selected)}: wrote {exhibit_id}/{world}/{label}")
                except Exception as exc:  # noqa: BLE001
                    row = {
                        "status": "failed",
                        "exhibit_id": exhibit_id,
                        "title": title,
                        "world": world,
                        "class": label,
                        "error": str(exc),
                    }
                    print(f"Edge TTS {index}/{len(selected)}: failed {exhibit_id}/{world}: {exc}")
                manifest.write(json.dumps(row, ensure_ascii=False) + "\n")
                manifest.flush()
                if args.sleep > 0:
                    await asyncio.sleep(args.sleep)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render all three-world audio scripts with Edge TTS.")
    parser.add_argument(
        "--audio-scripts",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_scripts_trio_diverse_full.jsonl"),
    )
    parser.add_argument(
        "--voice-manifest",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_voice_manifest_refined.jsonl"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("assets/audio/edge_full_refined"))
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_edge_full_refined_manifest.jsonl"),
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.5)
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
