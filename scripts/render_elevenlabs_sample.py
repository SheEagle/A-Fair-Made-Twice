from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests
import edge_tts

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.audio.classification import classify_all_worlds  # noqa: E402


MOJIBAKE_FIXES = {
    "鈥檚": "'s",
    "鈥檛": "n't",
    "鈥?": "'",
    "鈥": "'",
    "茅": "e",
    "脿": "a",
    "猫": "e",
    "莽": "c",
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
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def list_voices(api_key: str, base_url: str) -> None:
    response = requests.get(
        f"{base_url}/v1/voices",
        headers={"xi-api-key": api_key},
        timeout=45,
    )
    response.raise_for_status()
    voices = response.json().get("voices") or []
    for voice in voices:
        print(f"{voice.get('voice_id')}\t{voice.get('name')}\t{voice.get('category')}")


def find_profile(profiles: list[dict[str, Any]], exhibit_id: str) -> dict[str, Any]:
    for profile in profiles:
        if str(profile.get("exhibit_id")) == str(exhibit_id):
            return profile
    raise SystemExit(f"Profile not found: {exhibit_id}")


def script_map(audio: dict[str, Any]) -> dict[str, str]:
    return {
        world: clean_text(str(item.get("script") or ""))
        for world, item in (audio.get("scripts") or {}).items()
    }


def voice_settings(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "stability": float(config.get("stability", 0.60)),
        "similarity_boost": float(config.get("similarity_boost", 0.80)),
        "style": float(config.get("style", 0.20)),
        "use_speaker_boost": bool(config.get("use_speaker_boost", True)),
    }


def synthesize_elevenlabs(
    *,
    api_key: str,
    base_url: str,
    voice_id: str,
    text: str,
    output_path: Path,
    model_id: str,
    output_format: str,
    settings: dict[str, Any],
) -> None:
    url = f"{base_url}/v1/text-to-speech/{voice_id}"
    body = {
        "text": text,
        "model_id": model_id,
        "output_format": output_format,
        "voice_settings": settings,
    }
    response = requests.post(
        url,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json=body,
        timeout=180,
    )
    response.raise_for_status()
    output_path.write_bytes(response.content)


async def synthesize_edge_tts(
    *,
    text: str,
    output_path: Path,
    voice: str,
    rate: str,
    pitch: str,
) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(output_path))


def should_use_edge_tts(world: str, label: str, text: str) -> bool:
    if label in {"absence", "silence"}:
        return True
    lowered = text.lower()
    no_info_markers = [
        "no extracted text",
        "no information",
        "little usable",
        "information is sparse",
        "record is sparse",
        "absence",
    ]
    return any(marker in lowered for marker in no_info_markers)


def edge_voice_for(world: str, label: str) -> dict[str, str]:
    if world == "official":
        return {"voice": "en-GB-ThomasNeural", "rate": "-14%", "pitch": "-10Hz"}
    if world == "staged":
        return {"voice": "en-GB-LibbyNeural", "rate": "-12%", "pitch": "-8Hz"}
    return {"voice": "en-GB-LibbyNeural", "rate": "-14%", "pitch": "-10Hz"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Render sample three-world audio with ElevenLabs.")
    parser.add_argument("--audio-script", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_scripts_sample.json"))
    parser.add_argument("--profiles", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_profiles.jsonl"))
    parser.add_argument("--voice-map", type=Path, default=Path("config/elevenlabs_voice_map.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("assets/audio/elevenlabs_sample"))
    parser.add_argument("--manifest", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_elevenlabs_sample_manifest.json"))
    parser.add_argument("--model-id", default="eleven_multilingual_v2")
    parser.add_argument("--output-format", default="mp3_44100_128")
    parser.add_argument("--base-url", default="https://api.elevenlabs.io")
    parser.add_argument("--list-voices", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise SystemExit("Missing ELEVENLABS_API_KEY")

    if args.list_voices:
        list_voices(api_key, args.base_url)
        return

    audio = json.loads(args.audio_script.read_text(encoding="utf-8"))
    exhibit_id = str(audio.get("exhibit_id") or "")
    profile = find_profile(read_jsonl(args.profiles), exhibit_id)
    scripts = script_map(audio)
    classification = classify_all_worlds(profile, scripts)
    voice_map = json.loads(args.voice_map.read_text(encoding="utf-8"))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "exhibit_id": exhibit_id,
        "provider": "elevenlabs",
        "model_id": args.model_id,
        "audio": {},
        "classification": classification,
    }

    for world, text in scripts.items():
        label = classification[world]["class"]
        config = voice_map.get(world, {}).get(label)
        if not config:
            raise SystemExit(f"No ElevenLabs voice config for {world}/{label}")
        output_path = args.output_dir / f"{exhibit_id}_{world}_{label}.mp3"
        if should_use_edge_tts(world, label, text):
            edge_cfg = edge_voice_for(world, label)
            import asyncio

            asyncio.run(
                synthesize_edge_tts(
                    text=text,
                    output_path=output_path,
                    voice=edge_cfg["voice"],
                    rate=edge_cfg["rate"],
                    pitch=edge_cfg["pitch"],
                )
            )
            provider = "edge-tts"
            render_voice = edge_cfg["voice"]
            render_settings = edge_cfg
        else:
            synthesize_elevenlabs(
                api_key=api_key,
                base_url=args.base_url,
                voice_id=str(config["voice_id"]),
                text=text,
                output_path=output_path,
                model_id=args.model_id,
                output_format=args.output_format,
                settings=voice_settings(config),
            )
            provider = "elevenlabs"
            render_voice = str(config["voice_id"])
            render_settings = voice_settings(config)
        manifest["audio"][world] = {
            "path": str(output_path),
            "class": label,
            "provider": provider,
            "voice_id": render_voice,
            "voice_settings": render_settings,
            "script": text,
        }
        print(f"Rendered {world}/{label} with {provider}: {output_path}")

    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved ElevenLabs manifest to {args.manifest}")


if __name__ == "__main__":
    main()
