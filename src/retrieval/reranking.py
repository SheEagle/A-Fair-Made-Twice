from __future__ import annotations

from sentence_transformers import CrossEncoder

from src.models import RetrievalHit


class CrossEncoderReranker:
    def __init__(self, model_name: str, *, batch_size: int = 8) -> None:
        try:
            self.model = CrossEncoder(model_name, local_files_only=True)
        except Exception:
            self.model = CrossEncoder(model_name)
        self.batch_size = batch_size

    def rerank(self, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        if not hits:
            return []
        pairs = [(query, hit.text) for hit in hits]
        scores = self.model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        rescored_hits: list[RetrievalHit] = []
        for hit, score in zip(hits, scores, strict=True):
            rerank_score = float(score)
            rescored_hits.append(
                hit.model_copy(
                    update={
                        "score": rerank_score,
                        "dense_score": hit.dense_score if hit.dense_score is not None else hit.score,
                        "rerank_score": rerank_score,
                    }
                )
            )
        rescored_hits.sort(key=lambda item: item.score, reverse=True)
        return rescored_hits[:top_k]
