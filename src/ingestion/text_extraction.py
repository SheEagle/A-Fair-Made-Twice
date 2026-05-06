from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import fitz
import numpy as np
from ftfy import fix_text
from langdetect import DetectorFactory, LangDetectException, detect
from PIL import Image

from src.storage.files import ensure_directory


DetectorFactory.seed = 0

SUPPORTED_OCR_LANGS = {
    "en": "en",
    "fr": "fr",
    "de": "de",
    "it": "it",
    "es": "es",
    "pt": "pt",
    "tr": "tr",
    "nl": "nl",
}
DEFAULT_OCR_LANGS = ("en", "fr", "de", "it", "es", "pt", "tr", "nl")
DEFAULT_EASYOCR_MODEL_DIR = Path("outputs/cache/easyocr-models")
DEFAULT_EASYOCR_USER_NETWORK_DIR = Path("outputs/cache/easyocr-user-network")
TEXT_CACHE_VERSION = 2


@lru_cache(maxsize=4)
def _easyocr_reader(
    languages: tuple[str, ...],
    model_storage_directory: str,
    user_network_directory: str,
):
    import easyocr

    ensure_directory(Path(model_storage_directory))
    ensure_directory(Path(user_network_directory))
    return easyocr.Reader(
        list(languages),
        gpu=False,
        verbose=False,
        model_storage_directory=model_storage_directory,
        user_network_directory=user_network_directory,
    )


def clean_text(text: str) -> str:
    fixed = fix_text(text or "")
    fixed = fixed.replace("\x00", " ")
    fixed = fixed.replace("\u00ad", "")
    fixed = re.sub(r"[ \t]+", " ", fixed)
    fixed = re.sub(r"\n[ \t]+", "\n", fixed)
    fixed = re.sub(r"\n{3,}", "\n\n", fixed)
    return fixed.strip()


def detect_language_hint(text: str) -> str | None:
    sample = clean_text(text)
    if len(sample) < 80:
        return None
    try:
        detected = detect(sample[:4000])
    except LangDetectException:
        return None
    return detected if detected in SUPPORTED_OCR_LANGS else None


def evaluate_text_quality(text: str) -> dict[str, float | int | bool]:
    cleaned = clean_text(text)
    sample = cleaned[:5000]
    total_chars = len(sample)
    if total_chars == 0:
        return {
            "quality_score": 0.0,
            "total_chars": 0,
            "word_count": 0,
            "needs_ocr": True,
        }

    letters = sum(char.isalpha() for char in sample)
    spaces = sum(char.isspace() for char in sample)
    replacement_chars = sample.count("\ufffd")
    mojibake_markers = len(re.findall(r"[ÃÂÐØÞßæœ][^\s]{0,2}", sample))
    suspicious_symbols = sum(
        1
        for char in sample
        if not char.isalnum() and not char.isspace() and char not in ".,;:!?()[]{}'\"-/%&"
    )
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{2,}", sample)
    word_count = len(words)
    lines = [line.strip() for line in sample.splitlines() if line.strip()]
    noisy_lines = [
        line
        for line in lines
        if sum(not (char.isalnum() or char.isspace()) for char in line) / max(len(line), 1) > 0.25
    ]
    artifact_words = re.findall(r"\b\S*[\^|$><]\S*\b", sample)

    alpha_ratio = letters / max(total_chars, 1)
    whitespace_ratio = spaces / max(total_chars, 1)
    suspicious_ratio = suspicious_symbols / max(total_chars, 1)
    replacement_ratio = replacement_chars / max(total_chars, 1)
    mojibake_ratio = mojibake_markers / max(word_count, 1)
    noisy_line_ratio = len(noisy_lines) / max(len(lines), 1)
    artifact_word_ratio = len(artifact_words) / max(word_count, 1)

    score = 1.0
    score -= max(0.0, 0.40 - alpha_ratio) * 1.8
    score -= max(0.0, suspicious_ratio - 0.08) * 4.0
    score -= replacement_ratio * 5.0
    score -= mojibake_ratio * 1.5
    score -= max(0.0, noisy_line_ratio - 0.05) * 3.0
    score -= artifact_word_ratio * 4.0
    if whitespace_ratio < 0.08:
        score -= 0.15
    if word_count < 80:
        score -= 0.2
    if total_chars < 500:
        score -= 0.2
    quality_score = max(0.0, min(1.0, round(score, 3)))
    needs_ocr = (
        quality_score < 0.72
        or total_chars < 500
        or word_count < 80
        or noisy_line_ratio > 0.12
        or artifact_word_ratio > 0.01
    )
    return {
        "quality_score": quality_score,
        "total_chars": total_chars,
        "word_count": word_count,
        "noisy_line_count": len(noisy_lines),
        "line_count": len(lines),
        "artifact_word_count": len(artifact_words),
        "needs_ocr": needs_ocr,
    }


class DocumentTextExtractor:
    def __init__(
        self,
        cache_dir: Path,
        *,
        use_ocr: bool = True,
        force_ocr: bool = False,
        easyocr_model_dir: Path = DEFAULT_EASYOCR_MODEL_DIR,
        easyocr_user_network_dir: Path = DEFAULT_EASYOCR_USER_NETWORK_DIR,
    ) -> None:
        self.cache_dir = cache_dir
        self.use_ocr = use_ocr
        self.force_ocr = force_ocr
        self.easyocr_model_dir = easyocr_model_dir
        self.easyocr_user_network_dir = easyocr_user_network_dir

    def load_text(self, path: Path, root_dir: Path) -> tuple[str, dict[str, Any]]:
        relative_path = path.relative_to(root_dir).with_suffix(".txt")
        cache_path = self.cache_dir / relative_path
        metadata_path = cache_path.with_suffix(".meta.json")
        if cache_path.exists():
            text = cache_path.read_text(encoding="utf-8", errors="ignore").strip()
            metadata = self._read_metadata(metadata_path)
            if text and metadata.get("cache_version") == TEXT_CACHE_VERSION:
                metadata.setdefault("cache_path", str(cache_path))
                metadata.setdefault("cache_hit", True)
                return text, metadata

        if path.suffix.lower() == ".pdf":
            text, metadata = self._extract_pdf_text(path)
        else:
            raw_text = path.read_text(encoding="utf-8", errors="ignore")
            text = clean_text(raw_text)
            metadata = {
                "source_path": str(path),
                "relative_path": path.relative_to(root_dir).as_posix(),
                "method": "text_file",
                "detected_language": detect_language_hint(text),
                "quality": evaluate_text_quality(text),
            }

        ensure_directory(cache_path.parent)
        cache_path.write_text(text, encoding="utf-8")
        metadata["cache_path"] = str(cache_path)
        metadata["cache_hit"] = False
        metadata["cache_version"] = TEXT_CACHE_VERSION
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return text, metadata

    @staticmethod
    def _read_metadata(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _extract_pdf_text(self, path: Path) -> tuple[str, dict[str, Any]]:
        with fitz.open(path) as document:
            page_count = len(document)
            preview_text = clean_text(
                "\n\n".join(document[index].get_text("text") for index in range(min(8, page_count)))
            )
            detected_language = detect_language_hint(preview_text)
            ocr_languages: list[str] = []
            ocr_reader = None
            ocr_page_count = 0
            final_pages: list[str] = []

            if self.use_ocr:
                preview_quality = evaluate_text_quality(preview_text)
                if self.force_ocr or bool(preview_quality["needs_ocr"]):
                    ocr_languages = self._select_ocr_languages(path, detected_language)

            for page in document:
                text_layer = clean_text(page.get_text("text"))
                page_quality = evaluate_text_quality(text_layer)
                final_page_text = text_layer

                if self.use_ocr and (self.force_ocr or self._page_needs_ocr(text_layer, page_quality)):
                    if not ocr_languages:
                        ocr_languages = self._select_ocr_languages(path, detected_language)
                    if ocr_reader is None:
                        ocr_reader = _easyocr_reader(
                            tuple(ocr_languages),
                            str(self.easyocr_model_dir),
                            str(self.easyocr_user_network_dir),
                        )
                    ocr_text = self._run_easyocr_on_page(page, ocr_reader)
                    ocr_quality = evaluate_text_quality(ocr_text)
                    if ocr_text and (
                        not text_layer
                        or bool(page_quality["needs_ocr"])
                        or ocr_quality["quality_score"] >= page_quality["quality_score"]
                    ):
                        final_page_text = ocr_text
                        ocr_page_count += 1

                if final_page_text:
                    final_pages.append(final_page_text)

            final_text = clean_text("\n\n".join(final_pages))
            quality = evaluate_text_quality(final_text)
            detected_language = detect_language_hint(final_text) or detected_language
            method = "text_layer"
            if ocr_page_count == len(document) and len(document) > 0:
                method = "easyocr"
            elif ocr_page_count > 0:
                method = "hybrid_easyocr"

        metadata = {
            "source_path": str(path),
            "method": method,
            "detected_language": detected_language,
            "quality": quality,
            "page_count": page_count,
            "ocr_page_count": ocr_page_count,
        }
        if ocr_languages:
            metadata["ocr_languages"] = ocr_languages
        return final_text, metadata

    @staticmethod
    def _page_needs_ocr(text: str, quality: dict[str, Any]) -> bool:
        line_count = max(int(quality.get("line_count", 0)), 1)
        word_count = max(int(quality.get("word_count", 0)), 1)
        noisy_ratio = int(quality.get("noisy_line_count", 0)) / line_count
        artifact_ratio = int(quality.get("artifact_word_count", 0)) / word_count

        if not text.strip():
            return True
        if float(quality["quality_score"]) < 0.38:
            return True
        if int(quality["total_chars"]) < 60 and int(quality["word_count"]) < 10:
            return True
        if noisy_ratio > 0.22 and float(quality["quality_score"]) < 0.5:
            return True
        if artifact_ratio > 0.02 and float(quality["quality_score"]) < 0.55:
            return True
        return False

    def _select_ocr_languages(self, path: Path, detected_language: str | None) -> list[str]:
        languages = ["en"]
        if detected_language and detected_language != "en":
            languages.append(detected_language)

        lowered_name = path.stem.lower()
        filename_hints = {
            "turquie": "fr",
            "universelle": "fr",
            "france": "fr",
            "deutsch": "de",
            "ottoman": "tr",
            "turkish": "tr",
        }
        for marker, language in filename_hints.items():
            if marker in lowered_name and language not in languages:
                languages.append(language)

        for fallback_language in DEFAULT_OCR_LANGS:
            if fallback_language not in languages:
                languages.append(fallback_language)
            if len(languages) >= 4:
                break
        return languages

    @staticmethod
    def _run_easyocr_on_page(page: fitz.Page, reader: Any) -> str:
        pixmap = page.get_pixmap(dpi=140, alpha=False)
        mode = "RGB" if pixmap.n < 4 else "RGBA"
        image = Image.frombytes(mode, [pixmap.width, pixmap.height], pixmap.samples)
        page_array = np.array(image)
        lines = reader.readtext(page_array, detail=0, paragraph=True)
        return clean_text("\n".join(lines))
