from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from google import genai


WORLD_TO_PROFILE_KEY = {
    "official": "official",
    "staged": "institutional",
    "lived": "personal",
}

WORLD_SPECS = {
    "official": {
        "label": "The Official World",
        "function": "The official committee or catalogue speaks from its own authority, presenting the exhibit as part of order, nation, section, material, and record.",
        "sound": (
            "official first-person plural or impersonal institutional voice; confident, orderly, controlled; "
            "it speaks as the record, not as a later critic"
        ),
    },
    "staged": {
        "label": "The Staged World",
        "function": "A specialist commentator or critic analyzes how the exhibit is displayed, interpreted, compared, and made meaningful.",
        "sound": (
            "expert commentary; analytical, critical, observant; speaks about staging from outside official authority; "
            "no first-person feeling, no bodily diary, no visitor memory"
        ),
    },
    "lived": {
        "label": "The Lived World",
        "function": "A visitor speaks from direct encounter, bodily sensation, memory, fatigue, surprise, attraction, or neglect.",
        "sound": "first-person visitor memory; intimate, sensory, partial, emotional, restless, vulnerable; no curatorial theory",
    },
}

PATTERN_BANK = {
    "official": [
        "decree_voice: speak as the committee placing the object into the public record",
        "catalogue_address: speak as the catalogue announcing what deserves recognition",
        "national_register: speak as an official register aligning object, nation, maker, and material",
        "administrative_ceremony: speak as an institution turning the object into orderly evidence",
        "public_instruction: speak as the exhibition teaching the visitor how the object should be read",
    ],
    "staged": [
        "attention_path: identify one curatorial operation, then explain how it directs attention",
        "contrast_scene: analyze a contrast between object, section, material, nation, or surrounding exhibits",
        "apparatus_reveal: reveal the exhibition apparatus that turns the object into an argument",
        "critical_walkthrough: give a compact expert reading of the display mechanism, not a personal visit",
        "comparison_engine: show how comparison with other objects, nations, or spaces manufactures meaning",
    ],
    "lived": [
        "body_first: begin from breath, skin, posture, dizziness, heat, coolness, or hesitation, not sore feet",
        "emotion_first: begin from an unexpected feeling such as unease, attraction, shame, curiosity, tenderness, irritation, or disbelief",
        "crowd_first: begin from passing bodies, obstruction, noise, proximity, overheard fragments, or losing sight of the object",
        "detail_first: begin from one visual detail that catches the visitor before they understand the object",
        "memory_afterimage: begin from what the visitor remembers after moving away: a shape, sound, color, gesture, or discomfort",
    ],
}

STAGED_LENSES = [
    "spatial_lens: read how placement, adjacency, route, or section changes the object's meaning",
    "material_lens: read how material, scale, surface, weight, or technique is made persuasive",
    "comparison_lens: read the object through comparison with nations, neighboring exhibits, categories, or rival claims",
    "labor_lens: read what kinds of work, skill, extraction, or bodily effort are made visible or hidden",
    "classification_lens: read how naming, category, taxonomy, and catalogue order reduce complexity",
    "spectacle_lens: read how the object becomes theatrical, spectacular, intimidating, charming, or consumable",
    "technology_lens: read how mechanism, precision, industry, or engineering is translated into cultural value",
    "colonial_lens: read how empire, geography, collecting, or national prestige shape the display, only when supported",
]

STAGED_FORMS = [
    "comparative diagnosis",
    "slow expert walkthrough",
    "sharp critical aside",
    "miniature lecture",
    "curatorial x-ray",
    "one-object case study",
    "display autopsy",
    "quiet institutional critique",
]

LIVED_PERSONAS = [
    "hurried visitor trying not to lose the group",
    "curious visitor drawn in by one unexpected detail",
    "tired visitor looking for shade or quiet, but not talking about sore feet",
    "skeptical visitor who is unsure whether to admire the object",
    "awed visitor who cannot decide whether the object is beautiful or frightening",
    "distracted visitor who remembers fragments rather than a full explanation",
    "social visitor overhearing someone else and changing their mind",
    "restless visitor who wants to move on but keeps looking back",
]

LIVED_ENTRY_POINTS = [
    "sound first: start from a clang, murmur, hush, echo, scrape, wheel, bell, or swallowed sentence",
    "touch first: start from imagined coldness, polish, dust, heat, roughness, glass, metal, cloth, or stone",
    "sight first: start from glare, shadow, color, scale, gesture, label, crowd blockage, or a tiny detail",
    "misreading first: start with the visitor misunderstanding the object, then noticing something changes",
    "social first: start from someone nearby laughing, pointing, blocking the view, whispering, or moving away",
    "memory first: start after leaving, with one fragment returning unexpectedly",
    "body first: start from breath, neck, hands, throat, pulse, posture, or heat, not walking fatigue",
    "emotion first: start from attraction, suspicion, embarrassment, tenderness, dread, boredom, or surprise",
]

RHYTHMS = [
    "short opening, longer middle, sharp final turn",
    "one vivid opening image, two reflective sentences, quiet ending",
    "fragmented beginning, flowing middle, critical closing line",
    "slow descriptive opening, sudden contrast, unresolved ending",
    "direct address opening, analytical middle, sensory closing",
]

ENDING_MODES = [
    "end by naming what this world emphasizes",
    "end by naming what this world erases",
    "end with a quiet critical question",
    "end with a controlled image rather than explanation",
    "end by revealing how attention has been shaped",
]

NO_INFORMATION_SCRIPTS = {
    "official": (
        "The official record thins out here. The object remains present, but barely administered: no ceremony, no confident praise, no stable place in the catalogue. "
        "Its silence tells us how unevenly authority distributes attention."
    ),
    "staged": (
        "The exhibition apparatus leaves few traces around this object. No expert voice steps forward, no display logic fully explains why it matters. "
        "What remains is not neutrality, but a gap in the machinery of meaning."
    ),
    "lived": (
        "No visitor seems to leave a sentence here. The object was present, but perhaps not felt, not remembered, not caught by the moving crowd. "
        "Absence becomes a record of attention itself."
    ),
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_descriptions(*paths: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                exhibit_id = str(row.get("exhibit_id") or "")
                if exhibit_id and row.get("description"):
                    records.setdefault(exhibit_id, str(row["description"]))
    return records


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def existing_jsonl(path: Path) -> dict[str, dict[str, Any]]:
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
            if exhibit_id and row.get("scripts"):
                records[exhibit_id] = row
    return records


def find_profile(profiles: list[dict[str, Any]], exhibit_id: str | None) -> dict[str, Any]:
    if exhibit_id:
        for profile in profiles:
            if str(profile.get("exhibit_id")) == str(exhibit_id):
                return profile
        raise SystemExit(f"Exhibit not found: {exhibit_id}")
    return profiles[0]


def metadata_summary(profile: dict[str, Any]) -> dict[str, Any]:
    metadata = profile.get("english_metadata") or profile.get("metadata") or {}
    raw_meta = (profile.get("metadata") or {}).get("raw_metadata") or {}
    return {
        "exhibit_id": str(profile.get("exhibit_id") or ""),
        "archive_id": str((profile.get("metadata") or {}).get("archive_id") or raw_meta.get("archive_id") or ""),
        "title": clean_text(metadata.get("title") or (profile.get("metadata") or {}).get("title") or ""),
        "medium": clean_text(metadata.get("medium") or (profile.get("metadata") or {}).get("medium") or ""),
        "country": clean_text(metadata.get("country") or (profile.get("metadata") or {}).get("country") or ""),
        "location": clean_text(metadata.get("location") or (profile.get("metadata") or {}).get("location") or ""),
        "collection": clean_text(metadata.get("collection") or (profile.get("metadata") or {}).get("collection") or ""),
        "notes": clean_text(raw_meta.get("notes") or ""),
    }


def world_fields(profile: dict[str, Any], world: str, limit: int = 10) -> list[str]:
    profile_key = WORLD_TO_PROFILE_KEY[world]
    views = (profile.get("views") or {}).get(profile_key) or {}
    fields = ((views.get("overall") or {}).get("fields") or [])
    if not fields:
        for view_name in ("perception", "exhibition", "technical", "category"):
            fields.extend((views.get(view_name) or {}).get("fields") or [])
    ordered = sorted(fields, key=lambda item: float(item.get("confidence") or 0), reverse=True)
    out: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        value = clean_text(str(item.get("value") or ""))
        field = clean_text(str(item.get("field") or ""))
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


def has_information(profile: dict[str, Any], world: str) -> bool:
    fields = world_fields(profile, world, limit=3)
    return len(fields) > 0


def build_prompt(profile: dict[str, Any], visual_description: str, missing_worlds: list[str]) -> str:
    patterns = style_plan(str(profile.get("exhibit_id") or ""))
    title = metadata_summary(profile).get("title") or ""
    info = {
        "metadata": metadata_summary(profile),
        "visual_description": clean_text(visual_description),
        "style_plan": patterns,
        "worlds": {
            world: {
                "label": spec["label"],
                "narrative_function": spec["function"],
                "voice": spec["sound"],
                "available_information": world_fields(profile, world),
            }
            for world, spec in WORLD_SPECS.items()
        },
        "missing_worlds": missing_worlds,
        "fixed_no_information_scripts": {
            world: NO_INFORMATION_SCRIPTS[world]
            for world in missing_worlds
        },
    }
    return (
        "Generate THREE distinct English audio narration scripts for one museum exhibit.\n"
        "You must write the three scripts together so they strongly differ from one another.\n\n"
        "The goal is not to introduce the object neutrally. The goal is to let three social positions speak around it:\n"
        "1. official institution\n"
        "2. specialist commentator\n"
        "3. visitor witness\n\n"
        "World difference requirements:\n"
        "- official speaks AS the official institution, not ABOUT it. It should sound like an authorized voice addressing the public from inside the 1867 exhibition apparatus.\n"
        "- official presents, records, classifies, authorizes, praises, and instructs. It may use 'we' as the commission, jury, catalogue, or exhibition administration.\n"
        "- official has narrative momentum: it should sound like an official ceremonial announcement or catalogue note spoken aloud, not a neutral third-person summary.\n"
        "- staged speaks from a specialist commentator's perspective. It analyzes how display, expertise, comparison, and arrangement produce meaning. It can be critical.\n"
        "- lived speaks from a visitor's perspective. It describes bodily encounter, emotion, attention, fatigue, wonder, uncertainty, or neglect.\n"
        "- staged and lived must be maximally different: staged explains a system; lived remembers an encounter.\n\n"
        "Voice separation rules:\n"
        "- official MUST use either first-person plural institutional voice ('we record', 'we place', 'we recognize') or direct institutional declaration ('The Commission records...').\n"
        "- official must NOT sound like a museum educator, outside historian, critic, or omniscient narrator.\n"
        "- official should sound like a 19th-century exhibition catalogue, jury note, or official report: formal, declarative, institutional, not promotional.\n"
        "- official should be sincere, authoritative, and orderly: not ironic, not satirical, not self-critical, not a later historian, not contemporary museum PR.\n"
        "- official should include one concrete act of authority: placing, classifying, admitting, recognizing, listing, presenting, assigning, or recording the object.\n"
        "- official must avoid modern PR phrases such as 'our commitment', 'highest standards', 'curated to uphold', 'definitive record', or 'centerpiece'.\n"
        "- official must not use 'prize', 'medal', 'award', 'secure', 'secured', 'stabilize', 'commodity', or 'performance' unless those exact terms appear in the provided official information.\n"
        "- official must NOT read like a database entry. Do not use field-list phrasing such as 'Material: marble. Subject: Napoleon.'\n"
        "- official should use formal exhibition-report language: we present, we record, we identify, we place, we recognize, we include, we describe.\n"
        "- official must avoid suspiciously theoretical or critical verbs such as domesticate, sanitize, discipline, control, erase, manage, weaponize.\n"
        "- official's criticality should emerge indirectly through what the official voice emphasizes or omits, not through open self-critique.\n"
        "- official may narrow the account to official scope, but it must not confess its own omissions or sound knowingly critical of itself.\n"
        "- staged must NOT sound official and must NOT sound like a visitor diary. It should sound like a specialist commentator analyzing the staging from the outside.\n"
        "- staged should have a guide-like narrative arc: begin with one display choice, follow how it directs attention, then reveal the interpretation or power relation it produces.\n"
        "- staged should avoid claiming exact lighting, route, or placement unless provided. Use 'the display', 'the framing', 'the exhibition logic', 'the surviving commentary suggests'.\n"
        "- staged must not mention lighting unless lighting is explicitly present in the input.\n"
        "- staged should be narrative, not essay-like: let the commentator guide the listener through how attention is being arranged, step by step.\n"
        "- staged may use phrases like 'look at how', 'notice how', 'the display asks us to', but should remain critical rather than touristic.\n"
        "- staged must not use first-person singular. Forbidden in staged: I, me, my, we feel, my skin, my throat, my breath, I remember, I linger, I cannot look away.\n"
        "- staged should mostly use nouns like display, arrangement, section, apparatus, comparison, category, sequence, framing, commentary, exhibition logic, national narrative.\n"
        "- lived must use first person. It should sound embodied, unstable, and sensory.\n"
        "- lived is NOT a professional analysis. It should be a private encounter: partial, immediate, sometimes wrong, sometimes distracted.\n"
        "- lived must avoid curatorial-theory vocabulary. Forbidden in lived: display, framing, exhibition logic, apparatus, produces, directs attention, national narrative, official record, classification.\n"
        "- lived should use ordinary visitor language: I saw, I heard, I thought, I wanted, I moved closer, I almost missed it, someone beside me, the crowd, the heat, the smell, the shine, the silence.\n"
        "- lived must NOT open with or repeat generic fatigue formulas such as 'my feet ache', 'my legs ached', 'my shoulders ache', 'after walking all day', or 'from pacing the galleries'.\n"
        "- lived may include fatigue only if it is not the main opening device, and it must use varied concrete sensations instead: breath, throat, heat, crowd pressure, dust, glare, silence, smell, touch, hesitation, or memory.\n"
        "- lived should not use the same sensory motif as another lived script unless the object strongly demands it.\n"
        "- The three scripts must not share opening sentence patterns or repeated phrases.\n"
        "- Avoid grand generic phrases such as 'testament to', 'stands as', 'serves as', 'within the grand order', or 'curated centerpiece'.\n"
        "- Forbidden official phrases: 'our commitment', 'testament to', 'we choose to pass over', 'we omit', 'we leave unspoken', 'we erase', 'we conceal'.\n\n"
        "Critical narrative requirements:\n"
        "- Do not merely describe the exhibit.\n"
        "- Each script must reveal a relation of power, attention, or absence.\n"
        "- Show how this world produces meaning around the exhibit.\n"
        "- Let the three voices disagree, emphasize different things, or leave different things out.\n"
        "- Make each script feel like a small scene, not a label.\n"
        "- End with a subtle critical turn for staged and lived only: what is emphasized, erased, arranged, controlled, or left unfelt?\n"
        "- For official, end by tightening the official frame: classification, recognition, public order, material value, national section, or administrative scope.\n\n"
        "Field consistency requirements:\n"
        f"- The exhibit title is: {title!r}. Keep all scripts anchored to this exhibit.\n"
        "- If extracted information appears to refer to another object, ignore that extracted information.\n"
        "- If the available fields conflict with one another, rely on metadata and visual_description first.\n"
        "- Do not borrow named subjects, artworks, or people from unrelated extracted fields.\n"
        "- Do not mention Napoleon, Gozzoli, frescoes, pelicans, or embroidery unless they are clearly part of this exhibit's title, metadata, or visual_description.\n\n"
        "Variation requirements:\n"
        "- Follow the provided style_plan for each world.\n"
        "- Treat style_plan as mandatory, not decorative. The selected lens, form, persona, and entry point must visibly shape the scripts.\n"
        "- Across a batch, avoid defaulting to the same staged structure or the same lived emotion. The hash-based style_plan is there to make neighboring exhibits sound different.\n"
        "- Do not reuse the same opening structure across the three scripts.\n"
        "- Avoid repetitive starts like 'The display...', 'The record...', or 'This work...' in every exhibit.\n"
        "- For staged, do not always begin with 'Notice how'. Choose openings according to staged_form and staged_lens.\n"
        "- For staged, avoid overusing the formula 'the display frames... directs our attention... produces...'. Use other analytic constructions.\n"
        "- For official, avoid third-person report openings like 'The commissioners record...' more than rarely; prefer the institution speaking directly as 'we'.\n"
        "- For lived, follow lived_persona and lived_entry_point. Do not always make the visitor exhausted or solemn.\n"
        "- For lived, forbidden repeated phrases include: 'my feet ache', 'my legs ached', 'my shoulders ache', 'stops me cold', 'the room's air', 'I walk away feeling'.\n"
        "- For lived, avoid overusing 'I remember', 'I linger', 'I cannot look away', 'my throat', 'my skin', or 'the crowd fades'.\n"
        "- Vary sentence rhythm according to style_plan.sentence_rhythm.\n\n"
        "Script requirements:\n"
        "- 55-85 words per script.\n"
        "- English only.\n"
        "- Vivid and narrative, not a flat label.\n"
        "- official should sound like an official 1867 entry spoken aloud: confident, selective, administratively elegant, historically formal.\n"
        "- staged should be 3 sentences when possible: observation, mechanism, consequence. Use analytic verbs: frame, compare, interpret, expose, produce, mediate, direct attention.\n"
        "- lived should be 4-6 shorter sentences when possible. It may be fragmentary, intimate, and uncertain. It must not explain the exhibit like an expert.\n"
        "- Do not invent unsupported facts.\n"
        "- Do not treat exhibit_id as a catalogue number.\n"
        "- Do not claim awards, acquisitions, exact placement, or government ownership unless explicitly present in the input.\n"
        "- Do not mention metadata, OCR, AI, embedding, source type, or field names.\n"
        "- If a world is listed in missing_worlds, copy the exact fixed script for that world.\n"
        "- Make the three scripts different in vocabulary, rhythm, viewpoint, and emotional temperature.\n"
        "- Return strict JSON only with keys official, staged, lived. Each value must be an object: {\"script\": \"...\"}.\n\n"
        f"Input:\n{json.dumps(info, ensure_ascii=False, indent=2)}"
    )


def parse_response(text: str) -> dict[str, dict[str, str]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    data = json.loads(cleaned)
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and any(world in data[0] for world in ("official", "staged", "lived")):
            data = data[0]
        else:
            mapped: dict[str, dict[str, str]] = {}
            for item in data:
                if not isinstance(item, dict):
                    continue
                label = clean_text(item.get("world") or item.get("label") or item.get("name") or "").lower()
                script = clean_text(item.get("script") or item.get("text") or item.get("narration") or "")
                for world in ("official", "staged", "lived"):
                    if world in label:
                        mapped[world] = {"script": script}
            data = mapped
    if not isinstance(data, dict):
        raise RuntimeError("Model returned JSON that is not an object or supported list")
    return {
        world: {"script": clean_text(str((data.get(world) or {}).get("script") or ""))}
        for world in ("official", "staged", "lived")
    }


FORBIDDEN_BY_WORLD = {
    "official": [
        "our commitment",
        "testament to",
        "stands as",
        "serves as",
        "curated centerpiece",
        "we choose to pass over",
        "we omit",
        "we leave unspoken",
        "we erase",
        "we conceal",
        "political implications",
        "messy, unrefined labor",
    ],
    "staged": [
        "my feet ache",
        "my legs ached",
        "my shoulders ache",
        "notice how the display",
        "the display frames",
        "directs our attention",
        "the exhibition logic produces",
        "my skin",
        "my throat",
        "my breath",
        "i remember",
        "i linger",
        "i cannot look away",
        "i stare",
        "i felt",
        "i feel",
    ],
    "lived": [
        "the display",
        "the framing",
        "exhibition logic",
        "apparatus",
        "produces",
        "directs attention",
        "national narrative",
        "official record",
        "classification",
        "curatorial",
        "my feet ache",
        "my legs ached",
        "my shoulders ache",
        "i linger",
        "i cannot look away",
        "the crowd fades",
        "after walking all day",
        "from pacing the galleries",
        "from walking the gravel paths",
        "stops me cold",
        "the room's air",
        "i walk away feeling",
    ],
}


def validate_scripts(scripts: dict[str, dict[str, str]], missing_worlds: list[str] | None = None) -> list[str]:
    missing = set(missing_worlds or [])
    problems: list[str] = []
    official = scripts.get("official", {}).get("script", "")
    staged = scripts.get("staged", {}).get("script", "")
    lived = scripts.get("lived", {}).get("script", "")
    if "official" not in missing and "we " not in official.lower() and "commission" not in official.lower() and "catalogue" not in official.lower():
        problems.append("official must speak from inside the institution, preferably with direct institutional voice")
    if "staged" not in missing and re.search(r"\b(i|me|my|mine)\b", staged, flags=re.IGNORECASE):
        problems.append("staged must not use first-person visitor language")
    if "lived" not in missing and not re.search(r"\b(i|me|my|mine)\b", lived, flags=re.IGNORECASE):
        problems.append("lived must use first-person visitor language")
    for world, phrases in FORBIDDEN_BY_WORLD.items():
        if world in missing:
            continue
        script = scripts.get(world, {}).get("script", "")
        lowered = script.lower()
        for phrase in phrases:
            if phrase in lowered:
                problems.append(f"{world} uses forbidden phrase: {phrase}")
    return problems


def is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "quota exceeded" in text


def generate_trio(
    client: genai.Client,
    model: str,
    prompt: str,
    missing_worlds: list[str] | None = None,
) -> dict[str, dict[str, str]]:
    feedback = ""
    last_problems: list[str] = []
    for attempt in range(3):
        response = client.models.generate_content(
            model=model,
            contents=prompt + feedback,
            config={
                "temperature": 0.95,
                "top_p": 0.92,
                "response_mime_type": "application/json",
            },
        )
        scripts = parse_response(response.text or "{}")
        for world, item in scripts.items():
            if not item["script"]:
                raise RuntimeError(f"Missing script for {world}")
        last_problems = validate_scripts(scripts, missing_worlds)
        if not last_problems:
            return scripts
        feedback = (
            "\n\nYour previous answer violated these constraints:\n"
            + "\n".join(f"- {problem}" for problem in last_problems)
            + "\nRewrite all three scripts and return JSON only."
        )
    raise RuntimeError("Script validation failed after retries: " + "; ".join(last_problems))


MOJIBAKE_FIXES = {
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "鈥檚": "'s",
    "鈥檛": "n't",
    "鈥檓": "'m",
    "鈥檙": "'r",
    "鈥檝": "'v",
    "鈥檇": "'d",
    "鈥檒": "'l",
    "鈥?": "'",
    "鈥": "'",
    "閳ユ獨": "'s",
    "閳ユ獩": "n't",
}


def clean_text(value: Any) -> str:
    text = str(value or "")
    for bad, good in MOJIBAKE_FIXES.items():
        text = text.replace(bad, good)
    return re.sub(r"\s+", " ", text).strip()


def style_plan(exhibit_id: str) -> dict[str, str]:
    seed = int(hashlib.sha256(exhibit_id.encode("utf-8")).hexdigest()[:8], 16)
    return {
        "official_pattern": PATTERN_BANK["official"][seed % len(PATTERN_BANK["official"])],
        "staged_pattern": PATTERN_BANK["staged"][(seed // 7) % len(PATTERN_BANK["staged"])],
        "staged_lens": STAGED_LENSES[(seed // 11) % len(STAGED_LENSES)],
        "staged_form": STAGED_FORMS[(seed // 19) % len(STAGED_FORMS)],
        "lived_pattern": PATTERN_BANK["lived"][(seed // 13) % len(PATTERN_BANK["lived"])],
        "lived_persona": LIVED_PERSONAS[(seed // 29) % len(LIVED_PERSONAS)],
        "lived_entry_point": LIVED_ENTRY_POINTS[(seed // 31) % len(LIVED_ENTRY_POINTS)],
        "sentence_rhythm": RHYTHMS[(seed // 17) % len(RHYTHMS)],
        "ending_mode": ENDING_MODES[(seed // 23) % len(ENDING_MODES)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate strongly differentiated three-world audio scripts in one Gemini call.")
    parser.add_argument("--profiles", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_profiles.jsonl"))
    parser.add_argument("--descriptions", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_descriptions.jsonl"))
    parser.add_argument("--fallback-descriptions", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/exhibit_descriptions_short.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_scripts_trio_sample.json"))
    parser.add_argument("--output-jsonl", type=Path, default=Path("outputs/mineru_triview_gemini_rerank_merge_full_v2/audio_scripts_trio.jsonl"))
    parser.add_argument("--exhibit-id", default=None)
    parser.add_argument("--exhibit-ids", default="", help="Comma-separated exhibit IDs to generate as a small checkpointed batch.")
    parser.add_argument("--model", default=os.getenv("GEMINI_AUDIO_MODEL", "gemini-3.1-flash-lite-preview"))
    parser.add_argument("--all", action="store_true", help="Generate scripts for all exhibits with checkpointed JSONL output.")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Missing GEMINI_API_KEY or GOOGLE_API_KEY")

    profiles = read_jsonl(args.profiles)
    descriptions = load_descriptions(args.descriptions, args.fallback_descriptions)
    client = genai.Client(api_key=api_key)

    def generate_for_profile(profile: dict[str, Any]) -> dict[str, Any]:
        exhibit_id = str(profile.get("exhibit_id") or "")
        missing_worlds = [world for world in ("official", "staged", "lived") if not has_information(profile, world)]
        prompt = build_prompt(profile, descriptions.get(exhibit_id, ""), missing_worlds)
        scripts = generate_trio(client, args.model, prompt, missing_worlds)
        for world in missing_worlds:
            scripts[world]["script"] = NO_INFORMATION_SCRIPTS[world]
        return {
            "exhibit_id": exhibit_id,
            "metadata": metadata_summary(profile),
            "model": args.model,
            "missing_worlds": missing_worlds,
            "scripts": {
                world: {
                    "label": WORLD_SPECS[world]["label"],
                    "script": scripts[world]["script"],
                }
                for world in ("official", "staged", "lived")
            },
        }

    if args.all or args.exhibit_ids:
        if args.exhibit_ids:
            wanted = {item.strip() for item in args.exhibit_ids.split(",") if item.strip()}
            selected = [profile for profile in profiles if str(profile.get("exhibit_id") or "") in wanted]
            missing = sorted(wanted - {str(profile.get("exhibit_id") or "") for profile in selected})
            if missing:
                raise SystemExit(f"Exhibit IDs not found: {', '.join(missing)}")
        else:
            selected = profiles[: args.limit] if args.limit > 0 else profiles
        done = existing_jsonl(args.output_jsonl)
        args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.output_jsonl.open("a", encoding="utf-8") as out:
            for index, profile in enumerate(selected, start=1):
                exhibit_id = str(profile.get("exhibit_id") or "")
                if exhibit_id in done:
                    print(f"Audio scripts {index}/{len(selected)}: skip exhibit {exhibit_id}")
                    continue
                for attempt in range(1, 6):
                    try:
                        result = generate_for_profile(profile)
                        out.write(json.dumps(result, ensure_ascii=False) + "\n")
                        out.flush()
                        done[exhibit_id] = result
                        print(f"Audio scripts {index}/{len(selected)}: wrote exhibit {exhibit_id}")
                        break
                    except Exception as exc:  # noqa: BLE001 - keep checkpoint batch running
                        if is_rate_limit_error(exc) and attempt < 5:
                            wait_seconds = 65
                            print(
                                f"Audio scripts {index}/{len(selected)}: rate limited for exhibit {exhibit_id}; "
                                f"sleep {wait_seconds}s then retry {attempt + 1}/5"
                            )
                            time.sleep(wait_seconds)
                            continue
                        print(f"Audio scripts {index}/{len(selected)}: failed exhibit {exhibit_id}: {exc}")
                        break
        print(f"Wrote {len(done)} audio script records to {args.output_jsonl}")
        return

    profile = find_profile(profiles, args.exhibit_id)
    result = generate_for_profile(profile)
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
