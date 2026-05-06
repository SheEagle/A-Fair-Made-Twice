from __future__ import annotations

from textwrap import dedent

from src.models import ExhibitRecord


def build_metadata_translation_prompt(exhibit: ExhibitRecord) -> str:
    return dedent(
        f"""
        Convert the following exhibit metadata values into concise English.

        Rules:
        - Return JSON only.
        - Preserve meaning exactly.
        - Do not invent missing values.
        - Keep empty values as null.
        - Do not add explanations.

        Input:
        {{
          "title": {exhibit.title!r},
          "country": {exhibit.country!r},
          "location": {exhibit.location!r},
          "medium": {exhibit.medium!r},
          "collection": {exhibit.collection!r},
          "geolocated": {exhibit.geolocated!r}
        }}

        Output JSON schema:
        {{
          "title": "English title or null",
          "country": "English country or null",
          "location": "English location or null",
          "medium": "English medium or null",
          "collection": "English collection or null",
          "geolocated": "English geolocation confidence or null"
        }}
        """
    ).strip()


def build_query_prompt(exhibit: ExhibitRecord) -> str:
    metadata = exhibit.english_metadata or {}
    return dedent(
        f"""
        You are an information retrieval expert.

        Task:
        Generate exhibit-centered English search queries for retrieving passages about one museum exhibit.
        The same query set will be reused across all discourse channels, so it must stay exhibit-centered and perspective-neutral.

        Core rules:
        - The main subject must be the exhibit itself, not the generic Paris exposition background.
        - Do not use generic event-only phrases such as universal exposition, exhibition, catalogue, section, or British section unless they are needed as weak fallback context.
        - Prefer the exhibit title, object noun, distinctive proper names, and specific national or spatial identity.
        - Location can be used as a secondary hint, for example "located in Parc", but it must not dominate the query.
        - The primary query must contain at least one distinctive title keyword or object noun from the title.
        - Never end a query with a dangling stopword such as "at", "the", "of", or "in".
        - Do not use collection names unless they are part of the exhibit title itself.
        - Ignore generic medium words such as machine, object, item, or artifact when better exhibit nouns exist.
        - Use natural language phrases likely to appear in prose.
        - Remove catalogue noise, entry numbers, and inventory wording.
        - Return one primary query and two alternate phrasings for fallback retrieval.

        Exhibit metadata:
        Exhibit ID: {exhibit.exhibit_id}
        Title: {metadata.get("title") or exhibit.title or ""}
        Medium: {metadata.get("medium") or exhibit.medium or ""}
        Location: {metadata.get("location") or exhibit.location or ""}
        Country: {metadata.get("country") or exhibit.country or ""}
        Collection: {metadata.get("collection") or exhibit.collection or ""}

        Output JSON only:
        {{
          "primary_query": "3 to 10 English words",
          "alternate_queries": [
            "3 to 10 English words",
            "3 to 10 English words"
          ]
        }}
        """
    ).strip()


def build_extraction_prompt(exhibit: ExhibitRecord, chunk_text: str, discourse: str) -> str:
    metadata = exhibit.english_metadata or {}
    return dedent(
        f"""
        You will receive one exhibit record and one text chunk.

        Your task:
        1. Judge whether the chunk is exact, related, or none for the exhibit.
        2. Extract only supported information.
        3. Keep all value fields in concise English.
        4. Keep evidence copied verbatim in the original language from the chunk.

        Exhibit metadata:
        - exhibit_id: {exhibit.exhibit_id}
        - title_original: {exhibit.title or ""}
        - title_english: {metadata.get("title") or ""}
        - country_english: {metadata.get("country") or exhibit.country or ""}
        - location_english: {metadata.get("location") or exhibit.location or ""}
        - medium_english: {metadata.get("medium") or exhibit.medium or ""}
        - collection_english: {metadata.get("collection") or exhibit.collection or ""}
        - discourse: {discourse}

        Chunk:
        {chunk_text}

        Match levels:
        - exact: clearly about this specific exhibit
        - related: still materially about this exhibit, or about the same very narrow object/site/group in a way that directly helps interpret this exhibit
        - none: no meaningful relation

        Allowed fields:
        Technical view:
        - Manufacturing Process
        - Structural Feature
        - Material

        Category view:
        - Category Context
        - Functional Role
        - Comparative Context

        Exhibition view:
        - Exhibition Context
        - National Context
        - Discursive Role

        Perception view:
        - Audience Impression
        - Evaluation
        - Popularity
        - Sensory Description

        Strict rules:
        - Use only this chunk as evidence.
        - If no relation exists, return "none" with an empty field list.
        - Generic Paris exposition background is not enough.
        - Generic national pavilion background is not enough.
        - Generic section, catalogue, or commissioner text is not enough.
        - The chunk must be anchored to the exhibit itself, or to a very tight object/site group that clearly includes this exhibit.
        - If the chunk only mentions the wider fair, a different national section, a general building plan, or broad exhibition logistics, return "none".
        - Every extracted field must include field, value, evidence, and confidence.
        - value must be concise English, preferably object + feature/action.
        - value should feel vivid, specific, and curator-friendly rather than dry catalog shorthand.
        - Use compact, expressive phrasing with a little texture or force, but keep it under about 4 to 10 words.
        - Good style: "Marble emperor collapsing into the chair", "Bronze surface crowded with arabesques", "Crowd-stopping monument of imperial decline".
        - Bad style: "Sculpture", "Object is made of marble", "The text describes a sculpture in a chair".
        - Do not write meta-language such as "the text describes".
        - evidence must remain in the original chunk language.
        - Do not translate evidence.
        - Do not output bilingual values.
        - Confidence must be between 0.0 and 1.0.

        Return JSON only with this schema:
        {{
          "match_level": "exact | related | none",
          "fields": [
            {{
              "field": "Allowed field name",
              "value": "Concise English fact",
              "evidence": "Original-language evidence",
              "confidence": 0.0
            }}
          ]
        }}
        """
    ).strip()
