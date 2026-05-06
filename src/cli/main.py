from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import typer

from src.config import AppSettings
from src.ingestion.dify_workflow import parse_dify_workflow
from src.ingestion.metadata import load_exhibits
from src.models import DifyWorkflowSpec

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _mark_stage(stage_timings: dict[str, float], stage_name: str, started_at: float) -> None:
    stage_timings[stage_name] = round(perf_counter() - started_at, 3)


def _can_reuse_chunk_cache(
    chunk_cache_path: Path,
    *,
    max_documents: int | None,
    max_chunks: int | None,
    max_chunks_per_document: int | None,
) -> bool:
    return (
        chunk_cache_path.exists()
        and max_documents is None
        and max_chunks is None
        and max_chunks_per_document is None
    )


def _read_cache_metadata(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cache_metadata(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_jsonl_if_present(path: Path) -> list[dict]:
    if not path.exists():
        return []
    from src.storage.files import read_jsonl

    return read_jsonl(path)


def _extraction_result_key(exhibit_id: str, discourse: str, chunk_id: str) -> str:
    return f"{exhibit_id}::{discourse}::{chunk_id}"


def _emit_progress(prefix: str, current: int, total: int) -> None:
    if total <= 0:
        typer.echo(f"{prefix}: {current}")
        return
    percent = (current / total) * 100
    typer.echo(f"{prefix}: {current}/{total} ({percent:.1f}%)")


def _retrieval_progress(current: int, total: int, exhibit, query_plan, exhibit_results=None) -> None:
    label = exhibit.exhibit_id
    if exhibit.title:
        label = f"{exhibit.exhibit_id} | {exhibit.title}"
    _emit_progress(f"Retrieval {label}", current, total)


def _settings(
    metadata_path: Path,
    texts_path: Path,
    outputs_path: Path,
    workflow_path: Path,
    llm_provider: str | None,
    query_provider: str | None,
    parser_provider: str | None,
    qdrant_collection: str | None,
    ollama_model: str,
    query_model: str | None,
    ollama_timeout_seconds: int | None,
    top_k: int | None,
    retrieval_candidate_k: int | None,
    enable_rerank: bool | None,
    reranker_model: str | None,
    rerank_batch_size: int | None,
    rerank_candidate_limit: int | None,
) -> AppSettings:
    settings = AppSettings.from_env(
        metadata_path=metadata_path,
        texts_path=texts_path,
        outputs_path=outputs_path,
        dify_workflow_path=workflow_path,
        ollama_model=ollama_model,
    )
    if llm_provider is not None:
        settings.llm_provider = llm_provider
    if query_provider is not None:
        settings.query_provider = query_provider
    if parser_provider is not None:
        settings.parser_provider = parser_provider
    if qdrant_collection is not None:
        settings.qdrant_collection = qdrant_collection
    if query_model is not None:
        settings.query_model = query_model
    if ollama_timeout_seconds is not None:
        settings.ollama_timeout_seconds = ollama_timeout_seconds
    if top_k is not None:
        settings.retrieval_top_k = top_k
    if retrieval_candidate_k is not None:
        settings.retrieval_candidate_k = retrieval_candidate_k
    if enable_rerank is not None:
        settings.enable_rerank = enable_rerank
    if reranker_model is not None:
        settings.reranker_model = reranker_model
    if rerank_batch_size is not None:
        settings.rerank_batch_size = rerank_batch_size
    if rerank_candidate_limit is not None:
        settings.rerank_candidate_limit = rerank_candidate_limit
    if settings.query_provider is None:
        settings.query_provider = settings.llm_provider
    return settings


def _load_workflow_spec(settings: AppSettings) -> DifyWorkflowSpec:
    spec = parse_dify_workflow(settings.dify_workflow_path)
    if spec.retrieval_top_k and not settings.retrieval_top_k:
        settings.retrieval_top_k = spec.retrieval_top_k
    return spec


def _translate_metadata_if_enabled(
    exhibits,
    settings: AppSettings,
    ollama_client,
) -> None:
    from src.llm.metadata_translation import MetadataTranslator

    if not settings.translate_metadata:
        for exhibit in exhibits:
            exhibit.english_metadata = {
                "title": exhibit.title,
                "country": exhibit.country,
                "location": exhibit.location,
                "medium": exhibit.medium,
                "collection": exhibit.collection,
                "geolocated": exhibit.geolocated,
            }
        return

    translator = MetadataTranslator(
        ollama_client,
        cache_path=settings.outputs_path / "metadata_translation_cache.json",
    )
    total_exhibits = len(exhibits)
    for index, exhibit in enumerate(exhibits, start=1):
        fallback_metadata = {
            "title": exhibit.title,
            "country": exhibit.country,
            "location": exhibit.location,
            "medium": exhibit.medium,
            "collection": exhibit.collection,
            "geolocated": exhibit.geolocated,
        }
        try:
            translated = translator.translate_exhibit(exhibit)
            merged = {
                key: translated.get(key) if translated.get(key) not in {None, ""} else fallback_metadata.get(key)
                for key in fallback_metadata
            }
            exhibit.english_metadata = merged
        except Exception:
            exhibit.english_metadata = fallback_metadata
        if index == 1 or index == total_exhibits or index % 10 == 0:
            _emit_progress("Metadata translation", index, total_exhibits)


@app.command("parse-dify")
def parse_dify(
    workflow_path: Path = typer.Option(Path("paris.yml"), exists=False, help="Path to the Dify workflow YAML."),
) -> None:
    spec = parse_dify_workflow(workflow_path)
    typer.echo(f"app_name: {spec.app_name}")
    typer.echo(f"retrieval_top_k: {spec.retrieval_top_k}")
    typer.echo(f"query_prompt_found: {bool(spec.query_prompt)}")
    typer.echo(f"extraction_prompt_found: {bool(spec.extraction_prompt)}")


@app.command()
def run(
    metadata_path: Path = typer.Option(Path("RestoredStereoManifest.csv"), exists=True),
    texts_path: Path = typer.Option(Path("text"), exists=True),
    outputs_path: Path = typer.Option(Path("outputs")),
    workflow_path: Path = typer.Option(Path("paris.yml"), exists=False),
    llm_provider: str | None = typer.Option(None, help="LLM provider: ollama or gemini."),
    query_provider: str | None = typer.Option(None, help="Query provider: ollama or gemini."),
    parser_provider: str | None = typer.Option(None, help="Document parser provider: mineru or local."),
    qdrant_collection: str | None = typer.Option(None, help="Override the Qdrant collection name for the new index."),
    ollama_model: str = typer.Option("qwen3:8b"),
    query_model: str | None = typer.Option(None, help="Optional dedicated Ollama model for query generation."),
    ollama_timeout_seconds: int | None = typer.Option(None, min=30, help="HTTP timeout for Ollama generate calls."),
    top_k: int | None = typer.Option(None, min=1),
    retrieval_candidate_k: int | None = typer.Option(None, min=1, help="Dense retrieval candidate count before reranking."),
    enable_rerank: bool | None = typer.Option(None, "--enable-rerank/--disable-rerank", help="Enable cross-encoder reranking after dense retrieval."),
    reranker_model: str | None = typer.Option(None, help="Cross-encoder reranker model name."),
    rerank_batch_size: int | None = typer.Option(None, min=1, help="Batch size for cross-encoder reranking."),
    rerank_candidate_limit: int | None = typer.Option(None, min=1, help="Maximum number of dense candidates passed into reranking."),
    exhibit_id: str | None = typer.Option(None, help="Run the pipeline for one exhibit id only."),
    max_exhibits: int | None = typer.Option(None, min=1, help="Limit the number of exhibits for smoke testing."),
    max_documents: int | None = typer.Option(None, min=1, help="Limit the number of source documents for smoke testing."),
    max_chunks: int | None = typer.Option(None, min=1, help="Limit the total chunk count for smoke testing."),
    max_chunks_per_document: int | None = typer.Option(None, min=1, help="Limit chunks per document for more balanced smoke tests."),
    reuse_chunks: bool = typer.Option(True, help="Reuse cached chunks.jsonl when available for full runs."),
    reuse_index: bool = typer.Option(True, help="Reuse an existing Qdrant collection instead of re-embedding/re-indexing."),
    use_ocr: bool = typer.Option(True, help="Use OCR fallback when PDF text quality is poor."),
    force_ocr: bool = typer.Option(False, help="Force OCR for PDFs even if the text layer looks usable."),
) -> None:
    from src.aggregation.embeddings import build_embedding_records
    from src.aggregation.profiles import aggregate_profile, aggregate_profiles
    from src.analysis.coordinates import compute_umap_coordinates
    from src.analysis.discourse import build_discourse_differences
    from src.analysis.similarity import build_similarity_rows
    from src.extraction.service import ExtractionService
    from src.ingestion.mineru import MINERU_CACHE_VERSION, MinerUClient
    from src.ingestion.text_extraction import TEXT_CACHE_VERSION
    from src.ingestion.documents import build_chunks, load_documents
    from src.llm.client import OllamaClient
    from src.models import DISCOURSE_TYPES, ExtractionResult, RetrievalResult
    from src.retrieval.embeddings import EmbeddingService
    from src.retrieval.pipeline import index_chunks, retrieve_for_exhibit
    from src.retrieval.query_generation import QueryGenerator
    from src.retrieval.reranking import CrossEncoderReranker
    from src.storage.files import append_jsonl, read_jsonl, write_csv, write_jsonl
    from src.storage.qdrant_store import QdrantStore
    from src.visualization.plotly_map import render_exhibit_map

    settings = _settings(
        metadata_path=metadata_path,
        texts_path=texts_path,
        outputs_path=outputs_path,
        workflow_path=workflow_path,
        llm_provider=llm_provider,
        query_provider=query_provider,
        parser_provider=parser_provider,
        qdrant_collection=qdrant_collection,
        ollama_model=ollama_model,
        query_model=query_model,
        ollama_timeout_seconds=ollama_timeout_seconds,
        top_k=top_k,
        retrieval_candidate_k=retrieval_candidate_k,
        enable_rerank=enable_rerank,
        reranker_model=reranker_model,
        rerank_batch_size=rerank_batch_size,
        rerank_candidate_limit=rerank_candidate_limit,
    )
    settings.use_ocr = use_ocr
    settings.force_ocr = force_ocr
    workflow_spec = _load_workflow_spec(settings)
    if top_k is None and workflow_spec.retrieval_top_k:
        settings.retrieval_top_k = workflow_spec.retrieval_top_k
    stage_timings: dict[str, float] = {}
    total_started_at = perf_counter()

    typer.echo("Loading metadata and translating normalized metadata into English...")
    stage_started_at = perf_counter()
    exhibits = load_exhibits(settings.metadata_path, only_include_flagged=settings.only_include_flagged)
    if exhibit_id is not None:
        exhibits = [exhibit for exhibit in exhibits if exhibit.exhibit_id == exhibit_id]
        if not exhibits:
            raise typer.BadParameter(f"Exhibit id '{exhibit_id}' was not found in metadata.")
    if max_exhibits is not None:
        exhibits = exhibits[:max_exhibits]
    ollama_client = OllamaClient(
        settings.gemini_base_url if settings.llm_provider == "gemini" else settings.ollama_url,
        settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        provider=settings.llm_provider,
        api_key=settings.gemini_api_key,
    )
    query_client = OllamaClient(
        settings.gemini_base_url if settings.query_provider == "gemini" else settings.ollama_url,
        settings.query_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        provider=settings.query_provider or settings.llm_provider,
        api_key=settings.gemini_api_key,
    )
    mineru_client = None
    if settings.parser_provider == "mineru":
        if not settings.mineru_api_token:
            raise typer.BadParameter("MINERU_API_TOKEN is required when parser_provider=mineru.")
        mineru_client = MinerUClient(
            api_token=settings.mineru_api_token,
            base_url=settings.mineru_base_url,
            model_version=settings.mineru_model_version,
            poll_interval_seconds=settings.mineru_poll_interval_seconds,
            timeout_seconds=settings.mineru_timeout_seconds,
            page_limit=settings.mineru_page_limit,
            enable_table=settings.mineru_enable_table,
            enable_formula=settings.mineru_enable_formula,
            force_ocr=True,
            cache_dir=settings.markdown_cache_dir,
            download_dir=settings.mineru_download_dir,
        )
    _translate_metadata_if_enabled(exhibits, settings, ollama_client)
    _mark_stage(stage_timings, "metadata_and_translation", stage_started_at)

    typer.echo("Loading source documents and building token-overlap chunks...")
    stage_started_at = perf_counter()
    documents = []
    document_count = 0
    chunk_cache_path = settings.outputs_path / "chunks.jsonl"
    chunk_metadata_path = settings.outputs_path / "chunks.meta.json"
    chunk_cache_metadata = {
        "text_cache_version": TEXT_CACHE_VERSION,
        "mineru_cache_version": MINERU_CACHE_VERSION,
        "parser_provider": settings.parser_provider,
        "embedding_model": settings.embedding_model,
        "chunk_size_tokens": settings.chunk_size_tokens,
        "chunk_overlap_tokens": settings.chunk_overlap_tokens,
        "texts_path": str(settings.texts_path),
    }
    if reuse_chunks and _can_reuse_chunk_cache(
        chunk_cache_path,
        max_documents=max_documents,
        max_chunks=max_chunks,
        max_chunks_per_document=max_chunks_per_document,
    ) and _read_cache_metadata(chunk_metadata_path) == chunk_cache_metadata:
        from src.models import ChunkRecord

        chunks = [ChunkRecord(**row) for row in read_jsonl(chunk_cache_path)]
        document_count = len({chunk.document_name for chunk in chunks})
    else:
        documents = load_documents(
            settings.texts_path,
            cache_dir=settings.document_text_cache_dir,
            parser_provider=settings.parser_provider,
            use_ocr=settings.use_ocr,
            force_ocr=settings.force_ocr,
            mineru_client=mineru_client,
        )
        if max_documents is not None:
            documents = documents[:max_documents]
        document_count = len(documents)
        chunks = build_chunks(
            documents=documents,
            tokenizer_name=settings.embedding_model,
            chunk_size=settings.chunk_size_tokens,
            overlap=settings.chunk_overlap_tokens,
        )
        if max_chunks_per_document is not None:
            limited_chunks = []
            counts_by_document: dict[str, int] = {}
            for chunk in chunks:
                current = counts_by_document.get(chunk.document_name, 0)
                if current >= max_chunks_per_document:
                    continue
                limited_chunks.append(chunk)
                counts_by_document[chunk.document_name] = current + 1
            chunks = limited_chunks
        if max_chunks is not None:
            chunks = chunks[:max_chunks]
        write_jsonl(
            chunk_cache_path,
            [chunk.model_dump(mode="json") for chunk in chunks],
        )
        _write_cache_metadata(chunk_metadata_path, chunk_cache_metadata)
    _mark_stage(stage_timings, "document_loading_and_chunking", stage_started_at)

    typer.echo("Indexing chunks in Qdrant with multilingual-e5-base embeddings...")
    stage_started_at = perf_counter()
    embedder = EmbeddingService(settings.embedding_model)
    store = QdrantStore(
        settings.qdrant_url,
        settings.qdrant_collection,
        timeout_seconds=settings.qdrant_timeout_seconds,
        upsert_retries=settings.qdrant_upsert_retries,
        retry_backoff_seconds=settings.qdrant_retry_backoff_seconds,
    )
    index_metadata_path = settings.outputs_path / "qdrant_index.meta.json"
    index_cache_metadata = {
        "collection": settings.qdrant_collection,
        "parser_provider": settings.parser_provider,
        "embedding_model": settings.embedding_model,
        "chunk_count": len(chunks),
        "text_cache_version": TEXT_CACHE_VERSION,
        "mineru_cache_version": MINERU_CACHE_VERSION,
    }
    should_reindex = True
    if reuse_index and max_documents is None and max_chunks is None and max_chunks_per_document is None:
        should_reindex = not (
            store.collection_exists()
            and store.point_count() == len(chunks)
            and _read_cache_metadata(index_metadata_path) == index_cache_metadata
        )
    if should_reindex:
        index_chunks(chunks, embedder, store, batch_size=settings.batch_size)
        _write_cache_metadata(index_metadata_path, index_cache_metadata)
    _mark_stage(stage_timings, "embedding_and_qdrant_indexing", stage_started_at)

    typer.echo("Generating English exhibit queries, retrieving chunks, and extracting exhibit-by-exhibit...")
    retrieval_elapsed = 0.0
    extraction_elapsed = 0.0
    query_generator = QueryGenerator(
        client=query_client,
        use_llm=settings.use_llm_for_queries,
        cache_path=settings.outputs_path / "generated_queries.jsonl",
    )
    reranker = None
    if settings.enable_rerank:
        try:
            reranker = CrossEncoderReranker(
                settings.reranker_model,
                batch_size=settings.rerank_batch_size,
            )
            typer.echo(
                f"Reranking enabled with {settings.reranker_model} "
                f"(candidate_k={max(settings.retrieval_top_k, settings.retrieval_candidate_k)}, rerank_limit={settings.rerank_candidate_limit}, top_k={settings.retrieval_top_k})."
            )
        except Exception as exc:
            typer.echo(f"Reranker unavailable ({exc}); continuing with dense retrieval only.")
    retrieval_results_path = settings.outputs_path / "retrieval_results.jsonl"
    retrieval_metadata_path = settings.outputs_path / "retrieval_results.meta.json"
    retrieval_metadata = {
        "collection": settings.qdrant_collection,
        "exhibit_ids": [exhibit.exhibit_id for exhibit in exhibits],
        "top_k": settings.retrieval_top_k,
        "retrieval_candidate_k": max(settings.retrieval_top_k, settings.retrieval_candidate_k),
        "enable_rerank": settings.enable_rerank,
        "reranker_model": settings.reranker_model if settings.enable_rerank else None,
    }
    if retrieval_results_path.exists() and _read_cache_metadata(retrieval_metadata_path) == retrieval_metadata:
        retrieval_results = [RetrievalResult(**row) for row in _read_jsonl_if_present(retrieval_results_path)]
        typer.echo(f"Retrieval cache reused: {len(retrieval_results)} discourse results loaded.")
    else:
        retrieval_results = []
        if retrieval_results_path.exists():
            retrieval_results_path.unlink()
        _write_cache_metadata(retrieval_metadata_path, retrieval_metadata)

    extraction_service = ExtractionService(
        client=ollama_client,
        temperature=settings.extraction_temperature,
        retries=settings.extraction_retries,
    )
    exhibit_lookup = {exhibit.exhibit_id: exhibit for exhibit in exhibits}
    extraction_results_path = settings.outputs_path / "extraction_results.jsonl"
    extraction_metadata_path = settings.outputs_path / "extraction_results.meta.json"
    extraction_metadata = {
        "llm_provider": settings.llm_provider,
        "model": settings.ollama_model,
        "temperature": settings.extraction_temperature,
        "retries": settings.extraction_retries,
        "retrieval": retrieval_metadata,
    }
    existing_extraction_rows: list[dict] = []
    if _read_cache_metadata(extraction_metadata_path) == extraction_metadata:
        existing_extraction_rows = _read_jsonl_if_present(extraction_results_path)
    elif extraction_results_path.exists():
        extraction_results_path.unlink()
    _write_cache_metadata(extraction_metadata_path, extraction_metadata)
    extraction_results = [ExtractionResult(**row) for row in existing_extraction_rows]
    processed_extraction_keys = {
        _extraction_result_key(result.exhibit_id, result.source_type, result.chunk_id)
        for result in extraction_results
    }
    profiles_path = settings.outputs_path / "exhibit_profiles.jsonl"
    existing_profile_rows = _read_jsonl_if_present(profiles_path)
    profiles_by_exhibit_id = {row["exhibit_id"]: row for row in existing_profile_rows if "exhibit_id" in row}
    retrieval_results_by_exhibit: dict[str, list[RetrievalResult]] = {}
    for retrieval_result in retrieval_results:
        retrieval_results_by_exhibit.setdefault(retrieval_result.exhibit_id, []).append(retrieval_result)
    completed_extraction_hits = len(processed_extraction_keys)
    if completed_extraction_hits:
        typer.echo(f"Extraction resume: {completed_extraction_hits} chunk-level results already present.")

    for index, exhibit in enumerate(exhibits, start=1):
        exhibit_retrieval_results = retrieval_results_by_exhibit.get(exhibit.exhibit_id, [])
        if len(exhibit_retrieval_results) != len(DISCOURSE_TYPES):
            retrieval_started_at = perf_counter()
            exhibit_retrieval_results = retrieve_for_exhibit(
                exhibit=exhibit,
                query_generator=query_generator,
                embedder=embedder,
                store=store,
                top_k=settings.retrieval_top_k,
                retrieval_candidate_k=max(settings.retrieval_top_k, settings.retrieval_candidate_k),
                reranker=reranker,
                rerank_candidate_limit=settings.rerank_candidate_limit,
            )
            retrieval_elapsed += perf_counter() - retrieval_started_at
            append_jsonl(
                retrieval_results_path,
                [result.model_dump(mode="json") for result in exhibit_retrieval_results],
            )
            retrieval_results.extend(exhibit_retrieval_results)
            retrieval_results_by_exhibit[exhibit.exhibit_id] = exhibit_retrieval_results
        _retrieval_progress(index, len(exhibits), exhibit, None, exhibit_retrieval_results)

        exhibit_total_hits = sum(len(result.hits) for result in exhibit_retrieval_results)
        exhibit_completed_hits = sum(
            1
            for retrieval_result in exhibit_retrieval_results
            for hit in retrieval_result.hits
            if _extraction_result_key(exhibit.exhibit_id, retrieval_result.discourse, hit.chunk_id) in processed_extraction_keys
        )
        if exhibit_completed_hits:
            _emit_progress(f"Extraction resume {exhibit.exhibit_id}", exhibit_completed_hits, exhibit_total_hits)

        extraction_started_at = perf_counter()
        exhibit_changed = False
        for retrieval_result in exhibit_retrieval_results:
            for hit in retrieval_result.hits:
                result_key = _extraction_result_key(exhibit.exhibit_id, retrieval_result.discourse, hit.chunk_id)
                if result_key in processed_extraction_keys:
                    continue
                extraction_result = extraction_service.extract_hit(
                    exhibit=exhibit,
                    discourse=retrieval_result.discourse,
                    query=retrieval_result.query,
                    hit=hit,
                )
                extraction_results.append(extraction_result)
                append_jsonl(
                    extraction_results_path,
                    [extraction_result.model_dump(mode="json")],
                )
                processed_extraction_keys.add(result_key)
                completed_extraction_hits += 1
                exhibit_completed_hits += 1
                exhibit_changed = True
                _emit_progress(f"Extraction {exhibit.exhibit_id}", exhibit_completed_hits, exhibit_total_hits)
        extraction_elapsed += perf_counter() - extraction_started_at

        if exhibit_changed or exhibit.exhibit_id not in profiles_by_exhibit_id:
            exhibit_results = [result for result in extraction_results if result.exhibit_id == exhibit.exhibit_id]
            profile = aggregate_profile(exhibit, exhibit_results)
            profiles_by_exhibit_id[exhibit.exhibit_id] = profile.model_dump(mode="json")
            write_jsonl(
                profiles_path,
                [profiles_by_exhibit_id[current_exhibit.exhibit_id] for current_exhibit in exhibits if current_exhibit.exhibit_id in profiles_by_exhibit_id],
            )
    stage_timings["query_generation_and_retrieval"] = round(retrieval_elapsed, 3)
    stage_timings["llm_extraction"] = round(extraction_elapsed, 3)

    typer.echo("Aggregating discourse-separated exhibit profiles and view texts...")
    stage_started_at = perf_counter()
    profiles = aggregate_profiles(exhibits, extraction_results)
    write_jsonl(
        profiles_path,
        [profile.model_dump(mode="json") for profile in profiles],
    )
    _mark_stage(stage_timings, "aggregation", stage_started_at)

    typer.echo("Building separate view-by-discourse exhibit embeddings...")
    stage_started_at = perf_counter()
    embedding_records = build_embedding_records(profiles, embedder)
    for discourse in DISCOURSE_TYPES:
        write_jsonl(
            settings.outputs_path / f"exhibit_embeddings_{discourse}.jsonl",
            [record.model_dump(mode="json") for record in embedding_records.get(discourse, [])],
        )
    _mark_stage(stage_timings, "view_embedding", stage_started_at)

    typer.echo("Projecting view-specific UMAP coordinates and computing analysis tables...")
    stage_started_at = perf_counter()
    umap_coordinates = compute_umap_coordinates(embedding_records, profiles)
    write_jsonl(
        settings.outputs_path / "umap_coordinates.jsonl",
        [item.model_dump(mode="json") for item in umap_coordinates],
    )

    similarity_rows = build_similarity_rows(embedding_records)
    write_csv(settings.outputs_path / "similarity_matrix.csv", similarity_rows)

    discourse_diffs = build_discourse_differences(profiles, embedding_records)
    write_csv(
        settings.outputs_path / "discourse_diff.csv",
        [
            {
                "exhibit_id": row.exhibit_id,
                "title": row.title,
                "view": row.view,
                "left_discourse": row.left_discourse,
                "right_discourse": row.right_discourse,
                "discourse_distance": row.discourse_distance,
                "left_field_count": row.left_field_count,
                "right_field_count": row.right_field_count,
                "only_in_left": " | ".join(row.only_in_left),
                "only_in_right": " | ".join(row.only_in_right),
            }
            for row in discourse_diffs
        ],
    )
    _mark_stage(stage_timings, "analysis", stage_started_at)

    typer.echo("Rendering the interactive Plotly map...")
    stage_started_at = perf_counter()
    render_exhibit_map(umap_coordinates, settings.outputs_path / "exhibit_map.html")
    _mark_stage(stage_timings, "visualization", stage_started_at)
    stage_timings["total"] = round(perf_counter() - total_started_at, 3)
    write_jsonl(
        settings.outputs_path / "stage_timings.jsonl",
        [
            {
                "exhibit_count": len(exhibits),
                "document_count": document_count,
                "chunk_count": len(chunks),
                "retrieval_result_count": len(retrieval_results),
                "retrieved_hit_count": sum(len(result.hits) for result in retrieval_results),
                "extraction_result_count": len(extraction_results),
                "timings_seconds": stage_timings,
            }
        ],
    )
    typer.echo(f"Pipeline complete. Outputs written to {settings.outputs_path}")


if __name__ == "__main__":
    app()
