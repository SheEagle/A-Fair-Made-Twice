from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.models import ChunkRecord, DISCOURSE_TYPES, ExhibitRecord, RetrievalResult
from src.retrieval.embeddings import EmbeddingService
from src.retrieval.query_generation import QueryGenerator
from src.retrieval.reranking import CrossEncoderReranker
from src.storage.qdrant_store import QdrantStore


def index_chunks(
    chunks: list[ChunkRecord],
    embedder: EmbeddingService,
    store: QdrantStore,
    batch_size: int = 16,
) -> None:
    store.ensure_collection(embedder.dimension)
    existing_count = min(store.point_count(), len(chunks))
    for batch_start in range(existing_count, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        vectors = embedder.encode_passages([chunk.text for chunk in batch])
        store.upsert_chunks(batch, vectors)


def retrieve_for_exhibits(
    exhibits: list[ExhibitRecord],
    query_generator: QueryGenerator,
    embedder: EmbeddingService,
    store: QdrantStore,
    top_k: int,
    retrieval_candidate_k: int,
    reranker: CrossEncoderReranker | None = None,
    rerank_candidate_limit: int | None = None,
    progress_callback=None,
) -> list[RetrievalResult]:
    results: list[RetrievalResult] = []
    total_exhibits = len(exhibits)
    for index, exhibit in enumerate(exhibits, start=1):
        exhibit_results = retrieve_for_exhibit(
            exhibit=exhibit,
            query_generator=query_generator,
            embedder=embedder,
            store=store,
            top_k=top_k,
            retrieval_candidate_k=retrieval_candidate_k,
            reranker=reranker,
            rerank_candidate_limit=rerank_candidate_limit,
        )
        results.extend(exhibit_results)
        if progress_callback is not None:
            progress_callback(index, total_exhibits, exhibit, exhibit_results[0], exhibit_results)
    return results


def retrieve_for_exhibit(
    exhibit: ExhibitRecord,
    query_generator: QueryGenerator,
    embedder: EmbeddingService,
    store: QdrantStore,
    top_k: int,
    retrieval_candidate_k: int,
    reranker: CrossEncoderReranker | None = None,
    rerank_candidate_limit: int | None = None,
) -> list[RetrievalResult]:
    query_plan = query_generator.build_query_plan(exhibit)
    all_queries = [query_plan.query, *query_plan.query_variants]
    query_vectors = embedder.encode_queries(all_queries)
    dense_hits_by_discourse: dict[str, list] = {}
    global_dense_hits: list = []
    search_tasks = [
        (discourse, query_vector)
        for discourse in DISCOURSE_TYPES
        for query_vector in query_vectors
    ]
    merged_hits_by_discourse = {discourse: OrderedDict() for discourse in DISCOURSE_TYPES}
    with ThreadPoolExecutor(max_workers=min(8, len(search_tasks) or 1)) as executor:
        future_map = {
            executor.submit(store.search, query_vector=query_vector, discourse=discourse, top_k=retrieval_candidate_k): discourse
            for discourse, query_vector in search_tasks
        }
        for future in as_completed(future_map):
            discourse = future_map[future]
            hits = future.result()
            merged_hits = merged_hits_by_discourse[discourse]
            for hit in hits:
                existing = merged_hits.get(hit.chunk_id)
                if existing is None or hit.score > existing.score:
                    merged_hits[hit.chunk_id] = hit

    for discourse in DISCOURSE_TYPES:
        merged_hits = merged_hits_by_discourse[discourse]
        dense_ranked_hits = sorted(merged_hits.values(), key=lambda item: item.score, reverse=True)
        dense_hits_by_discourse[discourse] = dense_ranked_hits
        global_dense_hits.extend(dense_ranked_hits)

    selected_hits_by_discourse: dict[str, list]
    if reranker is not None:
        rerank_source_hits = global_dense_hits
        if rerank_candidate_limit is not None and len(global_dense_hits) > rerank_candidate_limit:
            rerank_source_hits = sorted(
                global_dense_hits,
                key=lambda item: item.dense_score if item.dense_score is not None else item.score,
                reverse=True,
            )[:rerank_candidate_limit]
        globally_reranked_hits = reranker.rerank(
            query_plan.query,
            rerank_source_hits,
            top_k=max(top_k, len(rerank_source_hits)),
        )
        selected_hits_by_discourse = _allocate_reranked_hits(
            globally_reranked_hits,
            top_k=top_k,
        )
    else:
        selected_hits_by_discourse = {
            discourse: dense_hits_by_discourse.get(discourse, [])[:top_k]
            for discourse in DISCOURSE_TYPES
        }

    exhibit_results: list[RetrievalResult] = []
    for discourse in DISCOURSE_TYPES:
        ranked_hits = selected_hits_by_discourse.get(discourse, [])
        exhibit_results.append(
            RetrievalResult(
                exhibit_id=exhibit.exhibit_id,
                discourse=discourse,
                query=query_plan.query,
                query_variants=query_plan.query_variants,
                query_source=query_plan.query_source,
                hits=ranked_hits,
            )
        )
    return exhibit_results


def _allocate_reranked_hits(globally_reranked_hits: list, top_k: int) -> dict[str, list]:
    selected: list = []
    minimum_per_discourse = 2 if top_k >= len(DISCOURSE_TYPES) * 2 else 1

    for discourse in DISCOURSE_TYPES:
        discourse_hits = [hit for hit in globally_reranked_hits if hit.source_type == discourse]
        for hit in discourse_hits[:minimum_per_discourse]:
            if len(selected) >= top_k:
                break
            if all(existing.chunk_id != hit.chunk_id for existing in selected):
                selected.append(hit)

    if len(selected) < top_k:
        for hit in globally_reranked_hits:
            if len(selected) >= top_k:
                break
            if all(existing.chunk_id != hit.chunk_id for existing in selected):
                selected.append(hit)

    allocated = {discourse: [] for discourse in DISCOURSE_TYPES}
    for hit in selected:
        allocated[hit.source_type].append(hit)
    return allocated
