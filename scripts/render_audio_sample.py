from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

import edge_tts


VOICE_CONFIG = {
    "official": {
        "voice": "en-GB-RyanNeural",
        "rate": "-8%",
        "pitch": "-6Hz",
    },
    "staged": {
        "voice": "en-GB-SoniaNeural",
        "rate": "-2%",
        "pitch": "+0Hz",
    },
    "lived": {
        "voice": "en-US-JennyNeural",
        "rate": "+1%",
        "pitch": "+5Hz",
    },
}


MOJIBAKE_FIXES = {
    "鈥檚": "'s",
    "鈥?": "'",
    "鈥檛": "n't",
    "鈥渟": '"',
    "鈥": "'",
    "茅": "e",
    "脿": "a",
    "猫": "e",
    "莽": "c",
}


def clean_text(text: str) -> str:
    cleaned = text
    for bad, good in MOJIBAKE_FIXES.items():
        cleaned = cleaned.replace(bad, good)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


async def render_one(text: str, out_path: Path, voice: str, rate: str, pitch: str) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))


async def main_async(args: argparse.Namespace) -> None:
    data = json.loads(args.input.read_text(encoding="utf-8"))
    exhibit_id = str(data.get("exhibit_id") or "sample")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "exhibit_id": exhibit_id,
        "source": str(args.input),
        "audio": {},
    }

    for world, item in (data.get("scripts") or {}).items():
        if world not in VOICE_CONFIG:
            continue
        script = clean_text(str(item.get("script") or ""))
        cfg = VOICE_CONFIG[world]
        out_path = args.output_dir / f"{exhibit_id}_{world}.mp3"
        await render_one(script, out_path, **cfg)
        manifest["audio"][world] = {
            "path": str(out_path),
            "voice": cfg["voice"],
            "rate": cfg["rate"],
            "pitch": cfg["pitch"],
            "script": script,
        }
        print(f"Rendered {world}: {out_path}")

    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved audio manifest to {args.manifest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render sample three-world audio scripts to mp3.")
    parser.add_argument("--input", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_scripts_sample.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("assets/audio/sample"))
    parser.add_argument("--manifest", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_sample_manifest.json"))
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
