from __future__ import annotations

from transformers import AutoTokenizer


class TokenChunker:
    def __init__(self, tokenizer_name: str, chunk_size: int, overlap: int) -> None:
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                tokenizer_name,
                use_fast=True,
                local_files_only=True,
            )
        except Exception:
            self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, use_fast=True)
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.step = max(1, chunk_size - overlap)

    def chunk_text(self, text: str) -> list[dict[str, int | str]]:
        token_ids = self.tokenizer.encode(text, add_special_tokens=False)
        if not token_ids:
            return []
        chunks: list[dict[str, int | str]] = []
        for chunk_index, start in enumerate(range(0, len(token_ids), self.step)):
            end = min(len(token_ids), start + self.chunk_size)
            chunk_ids = token_ids[start:end]
            chunk_text = self.tokenizer.decode(
                chunk_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            ).strip()
            if chunk_text:
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "token_start": start,
                        "token_end": end,
                        "text": chunk_text,
                    }
                )
            if end >= len(token_ids):
                break
        return chunks
