from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


WORLD_TO_PROFILE_KEY = {
    "official": "official",
    "staged": "institutional",
    "lived": "personal",
}


@dataclass(frozen=True)
class VoicePreset:
    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"


OFFICIAL_PRESETS = {
    "classification": VoicePreset("en-GB-RyanNeural", "-4%", "-4Hz"),
    "ceremony": VoicePreset("en-GB-RyanNeural", "-10%", "-8Hz"),
    "technical": VoicePreset("en-US-GuyNeural", "-2%", "-2Hz"),
    "silence": VoicePreset("en-GB-ThomasNeural", "-14%", "-10Hz"),
}


STAGED_PRESETS = {
    "analysis": VoicePreset("en-GB-SoniaNeural", "-2%", "+0Hz"),
    "display": VoicePreset("en-GB-LibbyNeural", "-5%", "-2Hz"),
    "comparison": VoicePreset("en-US-AriaNeural", "+0%", "+2Hz"),
    "critique": VoicePreset("en-GB-SoniaNeural", "-8%", "-6Hz"),
    "absence": VoicePreset("en-GB-LibbyNeural", "-12%", "-8Hz"),
}


LIVED_PRESETS = {
    "wonder": VoicePreset("en-US-AriaNeural", "+2%", "+4Hz"),
    "awe": VoicePreset("en-GB-RyanNeural", "-7%", "-5Hz"),
    "delight": VoicePreset("en-US-AriaNeural", "+5%", "+6Hz"),
    "grief": VoicePreset("en-GB-LibbyNeural", "-14%", "-10Hz"),
    "pity": VoicePreset("en-GB-LibbyNeural", "-8%", "-4Hz"),
    "dread": VoicePreset("en-GB-SoniaNeural", "-10%", "-8Hz"),
    "loneliness": VoicePreset("en-US-JennyNeural", "-9%", "-7Hz"),
    "melancholy": VoicePreset("en-GB-LibbyNeural", "-9%", "-8Hz"),
    "unease": VoicePreset("en-GB-SoniaNeural", "-6%", "-4Hz"),
    "fatigue": VoicePreset("en-US-JennyNeural", "-10%", "-5Hz"),
    "absence": VoicePreset("en-GB-LibbyNeural", "-14%", "-10Hz"),
    "neutral": VoicePreset("en-US-JennyNeural", "+0%", "+0Hz"),
}


CATEGORY_KEYWORDS = {
    "official": {
        "classification": [
            "class",
            "category",
            "section",
            "catalogue",
            "country",
            "material",
            "collection",
            "exhibitor",
        ],
        "ceremony": [
            "prize",
            "medal",
            "award",
            "honour",
            "emperor",
            "imperial",
            "national",
            "ceremony",
            "reward",
        ],
        "technical": [
            "machine",
            "machinery",
            "process",
            "manufacturing",
            "structure",
            "construction",
            "steel",
            "iron",
            "glass",
            "material",
            "engine",
        ],
    },
    "staged": {
        "analysis": [
            "system",
            "expert",
            "institution",
            "committee",
            "commission",
            "classification",
            "role",
            "context",
        ],
        "display": [
            "display",
            "arranged",
            "staged",
            "gallery",
            "palais",
            "park",
            "garden",
            "pavilion",
            "placed",
            "located",
            "route",
        ],
        "comparison": [
            "compared",
            "comparative",
            "rival",
            "versus",
            "british",
            "french",
            "american",
            "similar",
            "contrast",
        ],
        "critique": [
            "suffer",
            "bewildered",
            "conflict",
            "contradiction",
            "problem",
            "lumped",
            "discipline",
            "power",
            "absence",
            "overlooked",
        ],
    },
    "lived": {
        "wonder": [
            "wonder",
            "admiration",
            "beautiful",
            "splendid",
            "marvel",
            "astonish",
            "attraction",
            "impressive",
        ],
        "awe": [
            "grand",
            "immense",
            "vast",
            "monumental",
            "sublime",
            "thunder",
            "empire",
            "colossal",
        ],
        "delight": [
            "pretty",
            "charming",
            "delight",
            "playful",
            "graceful",
            "flower",
            "garden",
            "coolness",
            "rest",
        ],
        "grief": [
            "grief",
            "sorrow",
            "mourning",
            "mourn",
            "tears",
            "weep",
            "weeping",
            "heartbreak",
            "heartbroken",
            "lament",
            "funeral",
            "bereavement",
            "someone else's grief",
        ],
        "pity": [
            "pity",
            "pitied",
            "pathetic",
            "fragile",
            "helpless",
            "wretched",
            "poor creature",
            "compassion",
            "tender",
            "small",
            "human anguish",
        ],
        "dread": [
            "dread",
            "terrifying",
            "terror",
            "danger",
            "dangerous",
            "killing",
            "wound",
            "ruin",
            "weapon",
            "cannon",
            "gun",
            "destruction",
            "threat",
            "shadow of the barrel",
            "air feel thin",
            "heavy with",
        ],
        "loneliness": [
            "lonely",
            "alone",
            "solitary",
            "empty",
            "hollow",
            "silence",
            "quiet",
            "distant",
            "forgotten",
            "deserted",
            "no one",
            "crowd noise seemed to drop away",
        ],
        "melancholy": [
            "death",
            "dying",
            "anguish",
            "suffering",
            "cold stone",
            "mortality",
            "last days",
            "tomb",
            "loss",
        ],
        "unease": [
            "bewildered",
            "maze",
            "strange",
            "nervous",
            "fatigue",
            "crowd",
            "deserted",
            "confusing",
            "uneasy",
        ],
        "fatigue": [
            "tired",
            "fatigue",
            "crowded",
            "walking",
            "maze",
            "alleys",
            "heat",
            "sun",
            "whole days",
        ],
    },
}


def classify_world(profile: dict[str, Any], world: str, script: str | None = None) -> dict[str, Any]:
    if world == "official":
        return classify_official(profile, script)
    if world == "staged":
        return classify_staged(profile, script)
    if world == "lived":
        return classify_lived(profile, script)
    raise ValueError(f"Unknown world: {world}")


def classify_all_worlds(profile: dict[str, Any], scripts: dict[str, str] | None = None) -> dict[str, Any]:
    scripts = scripts or {}
    return {
        world: classify_world(profile, world, scripts.get(world))
        for world in ("official", "staged", "lived")
    }


def classify_official(profile: dict[str, Any], script: str | None = None) -> dict[str, Any]:
    text = world_text(profile, "official", script)
    if is_absent(profile, "official", text):
        return result("official", "silence", 0.92, "Official record has little usable exhibit-specific detail.")
    scores = score_categories(text, CATEGORY_KEYWORDS["official"])
    label, score = choose(scores, default="classification")
    confidence = confidence_from_score(score, text)
    return result("official", label, confidence, reason_for("official", label, scores))


def classify_staged(profile: dict[str, Any], script: str | None = None) -> dict[str, Any]:
    text = world_text(profile, "staged", script)
    if is_absent(profile, "staged", text):
        return result("staged", "absence", 0.92, "Institutional framing is sparse, so the voice should preserve absence.")
    scores = score_categories(text, CATEGORY_KEYWORDS["staged"])
    label, score = choose(scores, default="analysis")
    confidence = confidence_from_score(score, text)
    return result("staged", label, confidence, reason_for("staged", label, scores))


def classify_lived(profile: dict[str, Any], script: str | None = None) -> dict[str, Any]:
    text = world_text(profile, "lived", script)
    if is_absent(profile, "lived", text):
        return result("lived", "absence", 0.94, "Personal accounts are missing or thin; absence should become audible.")
    scores = score_categories(text, CATEGORY_KEYWORDS["lived"])
    label, score = choose(scores, default="neutral")
    confidence = confidence_from_score(score, text)
    return result("lived", label, confidence, reason_for("lived", label, scores))


def result(world: str, label: str, confidence: float, reason: str) -> dict[str, Any]:
    preset = presets_for(world)[label]
    return {
        "world": world,
        "class": label,
        "confidence": round(confidence, 3),
        "reason": reason,
        "voice": preset.voice,
        "rate": preset.rate,
        "pitch": preset.pitch,
    }


def presets_for(world: str) -> dict[str, VoicePreset]:
    if world == "official":
        return OFFICIAL_PRESETS
    if world == "staged":
        return STAGED_PRESETS
    if world == "lived":
        return LIVED_PRESETS
    raise ValueError(world)


def world_text(profile: dict[str, Any], world: str, script: str | None = None) -> str:
    profile_key = WORLD_TO_PROFILE_KEY[world]
    chunks: list[str] = []
    if script:
        chunks.append(script)

    views = ((profile.get("views") or {}).get(profile_key) or {})
    for view_name in ("perception", "overall", "exhibition", "technical", "category"):
        entry = views.get(view_name) or {}
        if entry.get("text"):
            chunks.append(str(entry["text"]))
        for field in entry.get("fields") or []:
            chunks.append(str(field.get("field") or ""))
            chunks.append(str(field.get("value") or ""))

    metadata = profile.get("english_metadata") or profile.get("metadata") or {}
    for key in ("title", "medium", "country", "location"):
        if metadata.get(key):
            chunks.append(str(metadata[key]))
    return normalize(" ".join(chunks))


def is_absent(profile: dict[str, Any], world: str, text: str) -> bool:
    profile_key = WORLD_TO_PROFILE_KEY[world]
    views = ((profile.get("views") or {}).get(profile_key) or {})
    field_count = 0
    for entry in views.values():
        field_count += len((entry or {}).get("fields") or [])
    word_count = len(text.split())
    return field_count == 0 or word_count < 24


def score_categories(text: str, categories: dict[str, list[str]]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for label, keywords in categories.items():
        score = 0
        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
            if " " in keyword:
                score += text.count(keyword.lower()) * 2
            else:
                score += len(re.findall(pattern, text))
        scores[label] = score
    return scores


def choose(scores: dict[str, int], default: str) -> tuple[str, int]:
    if not scores:
        return default, 0
    label, score = max(scores.items(), key=lambda item: (item[1], item[0]))
    if score <= 0:
        return default, 0
    return label, score


def confidence_from_score(score: int, text: str) -> float:
    if score <= 0:
        return 0.42
    density = score / max(len(text.split()), 1)
    return min(0.96, 0.56 + score * 0.08 + density * 2.5)


def reason_for(world: str, label: str, scores: dict[str, int]) -> str:
    nonzero = {key: value for key, value in scores.items() if value > 0}
    if not nonzero:
        return f"No strong signal was found, so {world} uses the default {label} voice."
    ranked = sorted(nonzero.items(), key=lambda item: item[1], reverse=True)
    evidence = ", ".join(f"{key}={value}" for key, value in ranked[:3])
    return f"{label} has the strongest {world} signal ({evidence})."


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()
