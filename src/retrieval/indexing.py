from __future__ import annotations

from src.models import ChunkRecord


def chunk_lookup(chunks: list[ChunkRecord]) -> dict[str, ChunkRecord]:
    return {chunk.chunk_id: chunk for chunk in chunks}
