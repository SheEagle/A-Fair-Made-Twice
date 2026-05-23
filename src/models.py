from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


DISCOURSE_TYPES = ("official", "personal", "institutional")
VIEW_NAMES = ("technical", "category", "exhibition", "perception", "overall")
DISCOURSE_PAIRS = (
    ("official", "personal"),
    ("official", "institutional"),
    ("personal", "institutional"),
)

FIELD_TO_VIEW = {
    "Manufacturing Process": "technical",
    "Structural Feature": "technical",
    "Material": "technical",
    "Category Context": "category",
    "Functional Role": "category",
    "Comparative Context": "category",
    "Exhibition Context": "exhibition",
    "National Context": "exhibition",
    "Discursive Role": "exhibition",
    "Audience Impression": "perception",
    "Evaluation": "perception",
    "Popularity": "perception",
    "Sensory Description": "perception",
}

VIEW_TO_FIELDS = {
    view: [field for field, mapped_view in FIELD_TO_VIEW.items() if mapped_view == view]
    for view in ("technical", "category", "exhibition", "perception")
}


class ExhibitRecord(BaseModel):
    exhibit_id: str
    archive_id: str | None = None
    card_id: str | None = None
    title: str | None = None
    country: str | None = None
    location: str | None = None
    medium: str | None = None
    collection: str | None = None
    geolocated: str | None = None
    raw_metadata: dict[str, Any]
    english_metadata: dict[str, str | None] = Field(default_factory=dict)


class DocumentRecord(BaseModel):
    document_name: str
    document_path: str
    source_type: str
    text: str

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        if value not in DISCOURSE_TYPES:
            allowed = ", ".join(DISCOURSE_TYPES)
            raise ValueError(f"Unsupported source_type '{value}'. Allowed: {allowed}")
        return value


class ChunkRecord(BaseModel):
    chunk_id: str
    document_name: str
    document_path: str
    source_type: str
    text: str
    chunk_index: int
    token_start: int
    token_end: int

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        if value not in DISCOURSE_TYPES:
            allowed = ", ".join(DISCOURSE_TYPES)
            raise ValueError(f"Unsupported source_type '{value}'. Allowed: {allowed}")
        return value


class RetrievalHit(BaseModel):
    chunk_id: str
    document_name: str
    source_type: str
    score: float
    text: str
    dense_score: float | None = None
    rerank_score: float | None = None

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        if value not in DISCOURSE_TYPES:
            allowed = ", ".join(DISCOURSE_TYPES)
            raise ValueError(f"Unsupported source_type '{value}'. Allowed: {allowed}")
        return value


class RetrievalResult(BaseModel):
    exhibit_id: str
    discourse: str
    query: str
    query_variants: list[str] = Field(default_factory=list)
    query_source: Literal["cache", "llm", "heuristic"] = "heuristic"
    hits: list[RetrievalHit]

    @field_validator("discourse")
    @classmethod
    def validate_discourse(cls, value: str) -> str:
        if value not in DISCOURSE_TYPES:
            allowed = ", ".join(DISCOURSE_TYPES)
            raise ValueError(f"Unsupported discourse '{value}'. Allowed: {allowed}")
        return value


class QueryPlan(BaseModel):
    exhibit_id: str
    query: str
    query_variants: list[str] = Field(default_factory=list)
    query_source: Literal["cache", "llm", "heuristic"] = "heuristic"


class ExtractedField(BaseModel):
    field: str
    value: str
    evidence: str
    confidence: float

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        if value not in FIELD_TO_VIEW:
            allowed = ", ".join(sorted(FIELD_TO_VIEW))
            raise ValueError(f"Unsupported field '{value}'. Allowed: {allowed}")
        return value

    @field_validator("value", "evidence")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, value))

    @property
    def view(self) -> str:
        return FIELD_TO_VIEW[self.field]

    @property
    def signature(self) -> tuple[str, str]:
        return (self.field.lower(), self.value.lower())


class ExtractionResult(BaseModel):
    exhibit_id: str
    chunk_id: str
    document_name: str
    source_type: str
    query: str
    match_level: Literal["exact", "related", "none"]
    fields: list[ExtractedField] = Field(default_factory=list)

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        if value not in DISCOURSE_TYPES:
            allowed = ", ".join(DISCOURSE_TYPES)
            raise ValueError(f"Unsupported source_type '{value}'. Allowed: {allowed}")
        return value


class ViewSummary(BaseModel):
    fields: list[ExtractedField] = Field(default_factory=list)
    text: str | None = None


class ExhibitProfile(BaseModel):
    exhibit_id: str
    metadata: dict[str, Any]
    english_metadata: dict[str, str | None] = Field(default_factory=dict)
    views: dict[str, dict[str, ViewSummary]]


class EmbeddingRecord(BaseModel):
    exhibit_id: str
    discourse: str
    english_metadata: dict[str, str | None] = Field(default_factory=dict)
    view_texts: dict[str, str | None]
    embeddings: dict[str, list[float] | None]

    @field_validator("discourse")
    @classmethod
    def validate_discourse(cls, value: str) -> str:
        if value not in DISCOURSE_TYPES:
            allowed = ", ".join(DISCOURSE_TYPES)
            raise ValueError(f"Unsupported discourse '{value}'. Allowed: {allowed}")
        return value


class UmapCoordinate(BaseModel):
    exhibit_id: str
    discourse: str
    view: Literal["technical", "category", "exhibition", "perception", "overall"]
    x: float
    y: float
    z: float = 0.0
    title: str | None = None
    metadata: dict[str, str | None] = Field(default_factory=dict)
    extracted_fields: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("discourse")
    @classmethod
    def validate_discourse(cls, value: str) -> str:
        if value not in DISCOURSE_TYPES:
            allowed = ", ".join(DISCOURSE_TYPES)
            raise ValueError(f"Unsupported discourse '{value}'. Allowed: {allowed}")
        return value


class DiscourseDifference(BaseModel):
    exhibit_id: str
    title: str | None = None
    view: str
    left_discourse: str
    right_discourse: str
    discourse_distance: float | None = None
    left_field_count: int = 0
    right_field_count: int = 0
    only_in_left: list[str] = Field(default_factory=list)
    only_in_right: list[str] = Field(default_factory=list)

    @field_validator("left_discourse", "right_discourse")
    @classmethod
    def validate_pair_discourse(cls, value: str) -> str:
        if value not in DISCOURSE_TYPES:
            allowed = ", ".join(DISCOURSE_TYPES)
            raise ValueError(f"Unsupported discourse '{value}'. Allowed: {allowed}")
        return value


class DifyWorkflowSpec(BaseModel):
    app_name: str | None = None
    query_prompt: str | None = None
    extraction_prompt: str | None = None
    retrieval_top_k: int | None = None
