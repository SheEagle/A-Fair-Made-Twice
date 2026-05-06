from __future__ import annotations

import json
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import fitz
import requests

from src.storage.files import ensure_directory


MINERU_CACHE_VERSION = 1


class MinerUClient:
    def __init__(
        self,
        *,
        api_token: str,
        base_url: str = "https://mineru.net",
        model_version: str = "vlm",
        poll_interval_seconds: int = 5,
        timeout_seconds: int = 120,
        page_limit: int = 200,
        enable_table: bool = True,
        enable_formula: bool = True,
        force_ocr: bool = True,
        cache_dir: Path,
        download_dir: Path,
        request_retries: int = 8,
        retry_backoff_seconds: int = 5,
    ) -> None:
        if not api_token:
            raise ValueError("MinerU API token is required.")
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.model_version = model_version
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.page_limit = page_limit
        self.enable_table = enable_table
        self.enable_formula = enable_formula
        self.force_ocr = force_ocr
        self.cache_dir = cache_dir
        self.download_dir = download_dir
        self.request_retries = request_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def load_markdown(self, path: Path, root_dir: Path) -> tuple[str, dict[str, Any]]:
        relative_path = path.relative_to(root_dir).with_suffix(".md")
        cache_path = self.cache_dir / relative_path
        metadata_path = cache_path.with_suffix(".meta.json")
        source_signature = self._source_signature(path)
        if cache_path.exists() and metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if (
                metadata.get("cache_version") == MINERU_CACHE_VERSION
                and metadata.get("source_signature") == source_signature
            ):
                return cache_path.read_text(encoding="utf-8"), metadata

        text, metadata = self._parse_pdf_to_markdown(path)
        ensure_directory(cache_path.parent)
        cache_path.write_text(text, encoding="utf-8")
        metadata["cache_version"] = MINERU_CACHE_VERSION
        metadata["cache_path"] = str(cache_path)
        metadata["source_signature"] = source_signature
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return text, metadata

    def _parse_pdf_to_markdown(self, path: Path) -> tuple[str, dict[str, Any]]:
        page_count = self._page_count(path)
        language = self._infer_language(path)
        segments = self._segment_ranges(page_count)
        markdown_parts: list[str] = []
        segment_metadata: list[dict[str, Any]] = []

        for segment_index, (start_page, end_page) in enumerate(segments, start=1):
            with self._segment_pdf(path, start_page, end_page) as segment_path:
                batch_id = self._submit_file_batch(
                    segment_path,
                    data_id=f"{path.stem}-segment-{segment_index}",
                    language=language,
                )
                result = self._poll_batch_result(batch_id)
                zip_url = result["full_zip_url"]
                zip_path = self._download_zip(zip_url, path.stem, segment_index)
                markdown_text = self._extract_full_markdown(zip_path)
                markdown_parts.append(markdown_text.strip())
                segment_metadata.append(
                    {
                        "segment_index": segment_index,
                        "page_range": f"{start_page}-{end_page}",
                        "batch_id": batch_id,
                        "zip_url": zip_url,
                        "zip_path": str(zip_path),
                    }
                )

        combined = "\n\n".join(part for part in markdown_parts if part).strip()
        return combined, {
            "source_path": str(path),
            "method": "mineru_markdown",
            "model_version": self.model_version,
            "language": language,
            "page_count": page_count,
            "segment_count": len(segments),
            "segments": segment_metadata,
        }

    def _submit_file_batch(self, path: Path, *, data_id: str, language: str) -> str:
        endpoint = f"{self.base_url}/api/v4/file-urls/batch"
        response = self._request_with_retries(
            "post",
            endpoint,
            headers=self._headers(),
            json={
                "files": [
                    {
                        "name": path.name,
                        "data_id": data_id,
                        "is_ocr": self.force_ocr,
                    }
                ],
                "model_version": self.model_version,
                "language": language,
                "enable_table": self.enable_table,
                "enable_formula": self.enable_formula,
            },
        )
        payload = self._expect_json(response)
        batch_id = payload["data"]["batch_id"]
        file_url = payload["data"]["file_urls"][0]
        with path.open("rb") as handle:
            upload_response = self._request_with_retries("put", file_url, data=handle)
        upload_response.raise_for_status()
        return str(batch_id)

    def _poll_batch_result(self, batch_id: str) -> dict[str, Any]:
        endpoint = f"{self.base_url}/api/v4/extract-results/batch/{batch_id}"
        deadline = time.time() + 60 * 30
        while time.time() < deadline:
            try:
                response = self._request_with_retries("get", endpoint, headers=self._headers())
            except requests.RequestException:
                time.sleep(self.poll_interval_seconds)
                continue
            payload = self._expect_json(response)
            results = payload["data"]["extract_result"]
            if not results:
                time.sleep(self.poll_interval_seconds)
                continue
            result = results[0]
            state = result["state"]
            if state == "done":
                return result
            if state == "failed":
                raise RuntimeError(f"MinerU parsing failed for batch {batch_id}: {result.get('err_msg')}")
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError(f"MinerU batch {batch_id} did not complete within 30 minutes.")

    def _download_zip(self, zip_url: str, stem: str, segment_index: int) -> Path:
        ensure_directory(self.download_dir)
        zip_path = self.download_dir / f"{stem}.segment-{segment_index}.zip"
        response = self._request_with_retries("get", zip_url)
        response.raise_for_status()
        zip_path.write_bytes(response.content)
        return zip_path

    @staticmethod
    def _extract_full_markdown(zip_path: Path) -> str:
        with zipfile.ZipFile(zip_path) as archive:
            member_name = next((name for name in archive.namelist() if name.endswith("full.md")), None)
            if member_name is None:
                raise FileNotFoundError(f"full.md not found in MinerU archive: {zip_path}")
            with archive.open(member_name) as handle:
                return handle.read().decode("utf-8", errors="ignore")

    @staticmethod
    def _page_count(path: Path) -> int:
        with fitz.open(path) as document:
            return len(document)

    def _segment_ranges(self, page_count: int) -> list[tuple[int, int]]:
        if page_count <= self.page_limit:
            return [(1, page_count)]
        ranges: list[tuple[int, int]] = []
        start = 1
        while start <= page_count:
            end = min(page_count, start + self.page_limit - 1)
            ranges.append((start, end))
            start = end + 1
        return ranges

    def _segment_pdf(self, path: Path, start_page: int, end_page: int):
        source = fitz.open(path)
        target = fitz.open()
        try:
            target.insert_pdf(source, from_page=start_page - 1, to_page=end_page - 1)
            temp_dir = ensure_directory(self.download_dir / "segments")
            temp_file = tempfile.NamedTemporaryFile(
                suffix=f".{start_page}-{end_page}.pdf",
                prefix=f"{path.stem}.",
                dir=temp_dir,
                delete=False,
            )
            temp_path = Path(temp_file.name)
            temp_file.close()
            target.save(temp_path)
            return _TempPathContext(temp_path)
        finally:
            target.close()
            source.close()

    @staticmethod
    def _infer_language(path: Path) -> str:
        lowered = path.stem.lower()
        if lowered.endswith("-en"):
            return "en"
        if any(lowered.endswith(suffix) for suffix in ("-fr", "-de", "-it", "-es", "-pt", "-nl", "-tr")):
            return "latin"
        return "latin"

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}",
        }

    def _request_with_retries(self, method: str, url: str, **kwargs) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.request_retries + 1):
            try:
                return requests.request(method, url, timeout=self.timeout_seconds, **kwargs)
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.request_retries:
                    break
                time.sleep(self.retry_backoff_seconds * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Request failed without an exception: {method.upper()} {url}")

    @staticmethod
    def _source_signature(path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "size": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
        }

    @staticmethod
    def _expect_json(response: requests.Response) -> dict[str, Any]:
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"MinerU API error: {payload}")
        return payload


class _TempPathContext:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> Path:
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
