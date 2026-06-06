from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from typing import Any


VOICE_RECOMMENDATIONS = {
    ("official", "classification"): ("Official Archive", "formal, clear, low-emotion archival reader"),
    ("official", "technical"): ("Official Archive", "formal, precise, engineering-document tone"),
    ("official", "ceremony"): ("Official Ceremony", "slower, solemn, institutional ceremony"),
    ("official", "silence"): ("Sparse Record", "slow, hollow, low-energy absence voice"),
    ("staged", "analysis"): ("Expert Analyst", "mature, observant, critical but calm"),
    ("staged", "display"): ("Expert Analyst", "curatorial guide with spatial attention"),
    ("staged", "comparison"): ("Comparative Critic", "sharper, comparative, interpretive"),
    ("staged", "critique"): ("Comparative Critic", "critical, controlled, not theatrical"),
    ("staged", "absence"): ("Sparse Record", "slow, hollow, low-energy absence voice"),
    ("lived", "wonder"): ("Visitor Wonder", "bright, curious, breathy visitor encounter"),
    ("lived", "delight"): ("Visitor Wonder", "warm, animated, lightly delighted"),
    ("lived", "awe"): ("Visitor Awe / Unease", "lower, slower, pressured wonder"),
    ("lived", "unease"): ("Visitor Awe / Unease", "tense, intimate, slightly unstable"),
    ("lived", "melancholy"): ("Visitor Melancholy / Fatigue", "soft, slow, reflective"),
    ("lived", "fatigue"): ("Visitor Melancholy / Fatigue", "tired, private, close-mic feeling"),
    ("lived", "neutral"): ("Visitor Melancholy / Fatigue", "natural visitor voice, understated"),
    ("lived", "absence"): ("Sparse Record", "slow, hollow, low-energy absence voice"),
}


WORLD_ORDER = {"official": 0, "staged": 1, "lived": 2}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def flatten_rows(manifest_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in manifest_rows:
        exhibit_id = str(item.get("exhibit_id") or "")
        title = str(item.get("title") or "")
        classifications = item.get("classification") or {}
        scripts = item.get("scripts") or {}
        for world in ("official", "staged", "lived"):
            label = str((classifications.get(world) or {}).get("class") or "neutral")
            voice_name, voice_note = VOICE_RECOMMENDATIONS.get((world, label), ("Custom", "choose a suitable voice"))
            script = str(scripts.get(world) or "")
            out.append(
                {
                    "exhibit_id": exhibit_id,
                    "title": title,
                    "world": world,
                    "class": label,
                    "recommended_voice": voice_name,
                    "voice_note": voice_note,
                    "suggested_filename": f"{exhibit_id}_{world}_{label}.mp3",
                    "script": script,
                }
            )
    return sorted(out, key=lambda row: (row["exhibit_id"], WORLD_ORDER.get(row["world"], 9)))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "exhibit_id",
        "title",
        "world",
        "class",
        "recommended_voice",
        "voice_note",
        "suggested_filename",
        "script",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_html(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["recommended_voice"], []).append(row)

    sections: list[str] = []
    for voice_name, group in grouped.items():
        sections.append(f"<section><h2>{html.escape(voice_name)} <span>{len(group)} clips</span></h2>")
        sections.append("<table><thead><tr><th>Exhibit</th><th>World</th><th>Class</th><th>Filename</th><th>Script</th></tr></thead><tbody>")
        for row in group:
            sections.append(
                "<tr>"
                f"<td><strong>{html.escape(row['exhibit_id'])}</strong><br>{html.escape(row['title'])}</td>"
                f"<td>{html.escape(row['world'])}</td>"
                f"<td>{html.escape(row['class'])}<br><small>{html.escape(row['voice_note'])}</small></td>"
                f"<td><code>{html.escape(row['suggested_filename'])}</code></td>"
                f"<td><textarea readonly>{html.escape(row['script'])}</textarea></td>"
                "</tr>"
            )
        sections.append("</tbody></table></section>")

    content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Audio Web Generation Table</title>
  <style>
    body {{
      margin: 0;
      padding: 32px;
      background: #101015;
      color: #f3eadc;
      font-family: Georgia, "Times New Roman", serif;
    }}
    h1 {{ margin: 0 0 8px; font-size: 34px; }}
    p {{ color: #bfb4a4; max-width: 880px; line-height: 1.5; }}
    section {{ margin: 34px 0 54px; }}
    h2 {{ color: #e9c98f; letter-spacing: .04em; }}
    h2 span {{ color: #8f877c; font-size: 16px; font-weight: normal; }}
    table {{ width: 100%; border-collapse: collapse; background: rgba(255,255,255,.035); }}
    th, td {{ border-top: 1px solid rgba(255,255,255,.12); padding: 12px; vertical-align: top; }}
    th {{ color: #9fb7d9; text-align: left; font-size: 13px; letter-spacing: .12em; text-transform: uppercase; }}
    td {{ font-size: 15px; }}
    small {{ color: #a9a097; }}
    code {{ color: #d9e7ff; }}
    textarea {{
      width: 100%;
      min-height: 92px;
      resize: vertical;
      background: #07080d;
      color: #f4efe8;
      border: 1px solid rgba(255,255,255,.18);
      border-radius: 8px;
      padding: 10px;
      font: 14px/1.45 Georgia, "Times New Roman", serif;
    }}
  </style>
</head>
<body>
  <h1>Audio Web Generation Table</h1>
  <p>Use this table for manual ElevenLabs generation. Choose the recommended voice preset, copy the script from the textarea, generate the MP3, and save it with the suggested filename.</p>
  {''.join(sections)}
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export audio scripts into CSV/HTML for manual ElevenLabs web generation.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_voice_manifest.jsonl"),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_web_generation_table.csv"),
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_web_generation_table.html"),
    )
    args = parser.parse_args()

    rows = flatten_rows(read_jsonl(args.manifest))
    write_csv(args.csv, rows)
    write_html(args.html, rows)
    print(f"Wrote {len(rows)} rows to {args.csv}")
    print(f"Wrote HTML table to {args.html}")


if __name__ == "__main__":
    main()
