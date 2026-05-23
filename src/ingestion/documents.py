from __future__ import annotations

from pathlib import Path

from src.ingestion.chunking import TokenChunker
from src.ingestion.mineru import MinerUClient
from src.ingestion.text_extraction import DocumentTextExtractor
from src.models import ChunkRecord, DocumentRecord


SUPPORTED_TEXT_SUFFIXES = {".pdf", ".txt", ".md"}


def infer_source_type(path: Path) -> str:
    lowered = {part.lower() for part in path.parts}
    if "personal" in lowered:
        return "personal"
    if "institutional" in lowered:
        return "institutional"
    if "official" in lowered:
        return "official"
    raise ValueError(f"Cannot infer source type from path: {path}")


def load_documents(
    texts_path: Path,
    *,
    cache_dir: Path,
    parser_provider: str = "local",
    use_ocr: bool = True,
    force_ocr: bool = False,
    mineru_client: MinerUClient | None = None,
) -> list[DocumentRecord]:
    extractor = DocumentTextExtractor(cache_dir=cache_dir, use_ocr=use_ocr, force_ocr=force_ocr)
    documents: list[DocumentRecord] = []
    for path in sorted(texts_path.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_TEXT_SUFFIXES:
            continue
        if path.suffix.lower() == ".pdf" and parser_provider == "mineru":
            if mineru_client is None:
                raise ValueError("MinerU parser provider was selected but no MinerU client was configured.")
            text, _ = mineru_client.load_markdown(path, texts_path)
        elif path.suffix.lower() == ".pdf":
            text, _ = extractor.load_text(path, texts_path)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        relative_name = path.relative_to(texts_path).with_suffix("").as_posix()
        documents.append(
            DocumentRecord(
                document_name=relative_name,
                document_path=str(path),
                source_type=infer_source_type(path),
                text=text,
            )
        )
    return documents


def build_chunks(
    documents: list[DocumentRecord],
    tokenizer_name: str,
    chunk_size: int,
    overlap: int,
) -> list[ChunkRecord]:
    chunker = TokenChunker(tokenizer_name=tokenizer_name, chunk_size=chunk_size, overlap=overlap)
    chunks: list[ChunkRecord] = []
    for document in documents:
        for chunk_info in chunker.chunk_text(document.text):
            chunk_index = int(chunk_info["chunk_index"])
            chunks.append(
                ChunkRecord(
                    chunk_id=f"{document.document_name}:{chunk_index}",
                    document_name=document.document_name,
                    document_path=document.document_path,
                    source_type=document.source_type,
                    text=str(chunk_info["text"]),
                    chunk_index=chunk_index,
                    token_start=int(chunk_info["token_start"]),
                    token_end=int(chunk_info["token_end"]),
                )
            )
    return chunks
