from __future__ import annotations

import re
from pathlib import Path

from src.llm.client import OllamaClient
from src.llm.prompts import build_query_prompt
from src.models import ExhibitRecord, QueryPlan
from src.storage.files import read_jsonl, write_jsonl


COUNTRY_ADJECTIVES = {
    "france": "french",
    "french": "french",
    "prussia": "prussian",
    "prussian": "prussian",
    "germany": "german",
    "german": "german",
    "italy": "italian",
    "italian": "italian",
    "austria": "austrian",
    "austrian": "austrian",
    "ottoman": "ottoman",
    "turkey": "ottoman",
    "egypt": "egyptian",
    "egyptian": "egyptian",
    "britain": "british",
    "british": "british",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

NOISE_WORDS = {
    "section",
    "entry",
    "catalogue",
    "catalog",
    "number",
    "no",
    "view",
    "alt",
    "gallery",
    "international",
    "universal",
    "exposition",
    "exhibition",
    "fair",
    "display",
    "object",
    "museum",
    "collection",
    "francois",
    "brunet",
}

WEAK_LOCATION_WORDS = {
    "parc",
    "park",
    "palais",
    "hall",
    "gallery",
    "building",
    "grounds",
    "section",
}


class QueryGenerator:
    def __init__(
        self,
        client: OllamaClient | None = None,
        use_llm: bool = True,
        cache_path: Path | None = None,
    ) -> None:
        self.client = client
        self.use_llm = use_llm
        self.cache_path = cache_path
        self._cache = self._load_cache(cache_path)

    def build_query_plan(self, exhibit: ExhibitRecord) -> QueryPlan:
        cache_key = exhibit.exhibit_id
        cached = self._cache.get(cache_key)
        if cached:
            return QueryPlan(
                exhibit_id=exhibit.exhibit_id,
                query=cached.query,
                query_variants=cached.query_variants,
                query_source="cache",
            )

        plan: QueryPlan
        if self.client and self.use_llm:
            try:
                plan = self._llm_plan(exhibit)
            except Exception:
                plan = self._heuristic_plan(exhibit)
        else:
            plan = self._heuristic_plan(exhibit)

        self._cache[cache_key] = plan
        self._persist_cache()
        return plan

    def _llm_plan(self, exhibit: ExhibitRecord) -> QueryPlan:
        payload = self.client.generate_json(build_query_prompt(exhibit), temperature=0.0)
        primary = self._normalize_query(payload.get("primary_query", ""))
        alternates = payload.get("alternate_queries") or []
        normalized_alternates = [self._normalize_query(item) for item in alternates]
        normalized_alternates = [item for item in normalized_alternates if item]
        if not primary:
            return self._heuristic_plan(exhibit)
        variants = self._dedupe_queries([primary, *normalized_alternates])
        variants = [query for query in variants if self._is_valid_query(query, exhibit)]
        if not variants:
            return self._heuristic_plan(exhibit)
        return QueryPlan(
            exhibit_id=exhibit.exhibit_id,
            query=variants[0],
            query_variants=variants[1:],
            query_source="llm",
        )

    def _heuristic_plan(self, exhibit: ExhibitRecord) -> QueryPlan:
        metadata = exhibit.english_metadata or {}
        title = metadata.get("title") or exhibit.title or ""
        medium = metadata.get("medium") or exhibit.medium or ""
        location = metadata.get("location") or exhibit.location or ""
        country = metadata.get("country") or exhibit.country or ""

        title_tokens = self._tokenize(title, drop_weak_locations=False)
        medium_tokens = self._tokenize(medium, drop_weak_locations=False)
        country_tokens = self._tokenize(country, drop_weak_locations=True)
        location_tokens = self._tokenize(location, drop_weak_locations=True)
        title_anchor_tokens = self._strong_title_tokens(title_tokens)
        medium_tokens = [token for token in medium_tokens if token not in {"machine", "object", "item", "artifact"}]

        primary_tokens: list[str] = []
        primary_tokens.extend(title_anchor_tokens[:4] or title_tokens[:4])
        if country_tokens:
            adjective = COUNTRY_ADJECTIVES.get(country_tokens[0], country_tokens[0])
            if adjective not in primary_tokens:
                primary_tokens.insert(0, adjective)
        for token in medium_tokens:
            if token not in primary_tokens:
                primary_tokens.append(token)
        if len(primary_tokens) < 3:
            primary_tokens.append("exhibit")
        primary = self._normalize_query(" ".join(primary_tokens)) or self._fallback_query()

        alternates: list[str] = []
        alt_one_tokens = [*country_tokens[:2], *(title_anchor_tokens[:4] or title_tokens[:4]), *medium_tokens[:2]]
        alt_two_tokens = [*(title_anchor_tokens[:4] or title_tokens[:4]), *medium_tokens[:2]]
        if location_tokens:
            alt_two_tokens.extend(["located", "in", *location_tokens[:2]])
        alt_three_tokens = [*(title_anchor_tokens[:4] or title_tokens[:4])]
        if country_tokens:
            alt_three_tokens.extend(["from", *country_tokens[:2]])

        for raw in (" ".join(alt_one_tokens), " ".join(alt_two_tokens), " ".join(alt_three_tokens)):
            normalized = self._normalize_query(raw)
            if normalized and self._is_valid_query(normalized, exhibit):
                alternates.append(normalized)

        variants = self._dedupe_queries([primary, *alternates])
        variants = [query for query in variants if self._is_valid_query(query, exhibit)]
        if not variants:
            variants = [self._fallback_query()]
        return QueryPlan(
            exhibit_id=exhibit.exhibit_id,
            query=variants[0],
            query_variants=variants[1:],
            query_source="heuristic",
        )

    @staticmethod
    def _fallback_query() -> str:
        return "museum exhibit object"

    @staticmethod
    def _strong_title_tokens(tokens: list[str]) -> list[str]:
        return [token for token in tokens if token not in {"view", "alt", "photo", "stereo"}]

    def _tokenize(self, value: str, *, drop_weak_locations: bool) -> list[str]:
        value = re.sub(r"\b\d+\b", " ", value.lower())
        value = re.sub(r"[^a-z0-9\s-]", " ", value)
        value = value.replace("-", " ")
        tokens = [token for token in value.split() if len(token) > 1 and token not in NOISE_WORDS]
        if drop_weak_locations:
            tokens = [token for token in tokens if token not in WEAK_LOCATION_WORDS]
        return tokens

    def _normalize_query(self, candidate: str) -> str:
        candidate = candidate.replace("\n", " ").strip()
        candidate = re.sub(r"\s+", " ", candidate)
        candidate = re.sub(
            r"(?i)\b(universal exposition|universal exhibition|paris exhibition|catalogue|catalog|section|francois brunet|collection)\b",
            " ",
            candidate,
        )
        candidate = re.sub(r"(?i)\b(machine|object|item|artifact)\b$", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        tokens = candidate.split()[:10]
        while tokens and tokens[-1].lower() in STOPWORDS:
            tokens.pop()
        return " ".join(tokens)

    def _is_valid_query(self, candidate: str, exhibit: ExhibitRecord) -> bool:
        tokens = candidate.lower().split()
        if len(tokens) < 3:
            return False
        if tokens[-1] in STOPWORDS:
            return False
        title = exhibit.english_metadata.get("title") if exhibit.english_metadata else exhibit.title
        title_tokens = self._strong_title_tokens(self._tokenize(title or "", drop_weak_locations=False))
        if title_tokens and not any(token in tokens for token in title_tokens[:4]):
            return False
        if any(token in {"collection", "francois", "brunet"} for token in tokens):
            return False
        return True

    @staticmethod
    def _dedupe_queries(queries: list[str]) -> list[str]:
        unique: list[str] = []
        for query in queries:
            cleaned = query.strip()
            if cleaned and cleaned not in unique:
                unique.append(cleaned)
        return unique

    def _load_cache(self, cache_path: Path | None) -> dict[str, QueryPlan]:
        if cache_path is None or not cache_path.exists():
            return {}
        cache: dict[str, QueryPlan] = {}
        for row in read_jsonl(cache_path):
            row = dict(row)
            row.pop("discourse", None)
            plan = QueryPlan(**row)
            cache[plan.exhibit_id] = plan
        return cache

    def _persist_cache(self) -> None:
        if self.cache_path is None:
            return
        rows = [plan.model_dump(mode="json") for _, plan in sorted(self._cache.items())]
        write_jsonl(self.cache_path, rows)
