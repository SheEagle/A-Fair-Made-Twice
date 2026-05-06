from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    metadata_path: Path = Field(default=Path("RestoredStereoManifest.csv"))
    texts_path: Path = Field(default=Path("text"))
    outputs_path: Path = Field(default=Path("outputs"))
    document_text_cache_dir: Path = Field(default=Path("outputs/cache/document_text"))
    markdown_cache_dir: Path = Field(default=Path("outputs/cache/mineru_markdown"))
    mineru_download_dir: Path = Field(default=Path("outputs/cache/mineru_downloads"))
    dify_workflow_path: Path = Field(default=Path("paris.yml"))

    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_collection: str = Field(default="museum_exhibit_chunks_mineru")
    qdrant_timeout_seconds: int = Field(default=300)
    qdrant_upsert_retries: int = Field(default=6)
    qdrant_retry_backoff_seconds: int = Field(default=5)

    llm_provider: str = Field(default="ollama")
    query_provider: str | None = Field(default=None)
    parser_provider: str = Field(default="mineru")

    ollama_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="qwen3:8b")
    ollama_timeout_seconds: int = Field(default=600)
    query_model: str = Field(default="qwen3:8b")
    gemini_api_key: str | None = Field(default=None)
    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta")
    mineru_api_token: str | None = Field(default=None)
    mineru_base_url: str = Field(default="https://mineru.net")
    mineru_model_version: str = Field(default="vlm")
    mineru_poll_interval_seconds: int = Field(default=5)
    mineru_timeout_seconds: int = Field(default=120)
    mineru_page_limit: int = Field(default=200)
    mineru_enable_table: bool = Field(default=True)
    mineru_enable_formula: bool = Field(default=True)

    embedding_model: str = Field(default="intfloat/multilingual-e5-base")
    reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3")

    chunk_size_tokens: int = Field(default=400)
    chunk_overlap_tokens: int = Field(default=60)
    retrieval_top_k: int = Field(default=6)
    retrieval_candidate_k: int = Field(default=18)
    enable_rerank: bool = Field(default=True)
    rerank_batch_size: int = Field(default=8)
    rerank_candidate_limit: int = Field(default=24)
    extraction_temperature: float = Field(default=0.2)
    extraction_retries: int = Field(default=2)
    batch_size: int = Field(default=4)
    translate_metadata: bool = Field(default=True)
    use_llm_for_queries: bool = Field(default=True)
    only_include_flagged: bool = Field(default=False)
    use_ocr: bool = Field(default=True)
    force_ocr: bool = Field(default=False)

    @classmethod
    def from_env(cls, **overrides: object) -> "AppSettings":
        env_values = {
            "metadata_path": os.getenv("MUSEUM_METADATA_PATH"),
            "texts_path": os.getenv("MUSEUM_TEXTS_PATH"),
            "outputs_path": os.getenv("MUSEUM_OUTPUTS_PATH"),
            "document_text_cache_dir": os.getenv("DOCUMENT_TEXT_CACHE_DIR"),
            "markdown_cache_dir": os.getenv("MARKDOWN_CACHE_DIR"),
            "mineru_download_dir": os.getenv("MINERU_DOWNLOAD_DIR"),
            "dify_workflow_path": os.getenv("MUSEUM_DIFY_WORKFLOW"),
            "qdrant_url": os.getenv("QDRANT_URL"),
            "qdrant_collection": os.getenv("QDRANT_COLLECTION"),
            "qdrant_timeout_seconds": os.getenv("QDRANT_TIMEOUT_SECONDS"),
            "qdrant_upsert_retries": os.getenv("QDRANT_UPSERT_RETRIES"),
            "qdrant_retry_backoff_seconds": os.getenv("QDRANT_RETRY_BACKOFF_SECONDS"),
            "llm_provider": os.getenv("LLM_PROVIDER"),
            "query_provider": os.getenv("QUERY_PROVIDER"),
            "parser_provider": os.getenv("PARSER_PROVIDER"),
            "ollama_url": os.getenv("OLLAMA_URL"),
            "ollama_model": os.getenv("OLLAMA_MODEL"),
            "ollama_timeout_seconds": os.getenv("OLLAMA_TIMEOUT_SECONDS"),
            "query_model": os.getenv("QUERY_MODEL"),
            "gemini_api_key": os.getenv("GEMINI_API_KEY"),
            "gemini_base_url": os.getenv("GEMINI_BASE_URL"),
            "mineru_api_token": os.getenv("MINERU_API_TOKEN"),
            "mineru_base_url": os.getenv("MINERU_BASE_URL"),
            "mineru_model_version": os.getenv("MINERU_MODEL_VERSION"),
            "mineru_poll_interval_seconds": os.getenv("MINERU_POLL_INTERVAL_SECONDS"),
            "mineru_timeout_seconds": os.getenv("MINERU_TIMEOUT_SECONDS"),
            "mineru_page_limit": os.getenv("MINERU_PAGE_LIMIT"),
            "mineru_enable_table": os.getenv("MINERU_ENABLE_TABLE"),
            "mineru_enable_formula": os.getenv("MINERU_ENABLE_FORMULA"),
            "embedding_model": os.getenv("EMBEDDING_MODEL"),
            "reranker_model": os.getenv("RERANKER_MODEL"),
            "chunk_size_tokens": os.getenv("CHUNK_SIZE_TOKENS"),
            "chunk_overlap_tokens": os.getenv("CHUNK_OVERLAP_TOKENS"),
            "retrieval_top_k": os.getenv("RETRIEVAL_TOP_K"),
            "retrieval_candidate_k": os.getenv("RETRIEVAL_CANDIDATE_K"),
            "enable_rerank": os.getenv("ENABLE_RERANK"),
            "rerank_batch_size": os.getenv("RERANK_BATCH_SIZE"),
            "rerank_candidate_limit": os.getenv("RERANK_CANDIDATE_LIMIT"),
            "extraction_temperature": os.getenv("EXTRACTION_TEMPERATURE"),
            "extraction_retries": os.getenv("EXTRACTION_RETRIES"),
            "batch_size": os.getenv("BATCH_SIZE"),
            "translate_metadata": os.getenv("TRANSLATE_METADATA"),
            "use_llm_for_queries": os.getenv("USE_LLM_FOR_QUERIES"),
            "only_include_flagged": os.getenv("ONLY_INCLUDE_FLAGGED"),
            "use_ocr": os.getenv("USE_OCR"),
            "force_ocr": os.getenv("FORCE_OCR"),
        }
        cleaned: dict[str, object] = {}
        for key, value in env_values.items():
            if value is None or value == "":
                continue
            if key in {
                "chunk_size_tokens",
                "chunk_overlap_tokens",
                "retrieval_top_k",
                "retrieval_candidate_k",
                "rerank_batch_size",
                "rerank_candidate_limit",
                "extraction_retries",
                "batch_size",
                "ollama_timeout_seconds",
                "mineru_poll_interval_seconds",
                "mineru_timeout_seconds",
                "mineru_page_limit",
                "qdrant_timeout_seconds",
                "qdrant_upsert_retries",
                "qdrant_retry_backoff_seconds",
            }:
                cleaned[key] = int(value)
            elif key == "extraction_temperature":
                cleaned[key] = float(value)
            elif key in {
                "translate_metadata",
                "use_llm_for_queries",
                "only_include_flagged",
                "enable_rerank",
                "use_ocr",
                "force_ocr",
                "mineru_enable_table",
                "mineru_enable_formula",
            }:
                cleaned[key] = value.strip().lower() in {"1", "true", "yes", "y"}
            else:
                cleaned[key] = value
        cleaned.update(overrides)
        return cls(**cleaned)
