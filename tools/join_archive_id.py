import argparse
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


def _dedup_columns(columns: Iterable[object]) -> list[str]:
    """
    Make column names unique by appending ".1", ".2", ...
    Similar to pandas' internal deduping but without relying on private APIs.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for c in columns:
        base = str(c)
        if base not in seen:
            seen[base] = 0
            out.append(base)
            continue
        seen[base] += 1
        out.append(f"{base}.{seen[base]}")
    return out


def _pick_column(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None


def _pick_column_contains(df: pd.DataFrame, needles: Iterable[str]) -> Optional[str]:
    lowered = [(c, str(c).lower()) for c in df.columns]
    for needle in needles:
        for original, low in lowered:
            if needle.lower() in low:
                return original
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Join archive_id onto RestoredStereoManifest by matching card_id "
            "to an Originals Metadata table (Excel/CSV)."
        )
    )
    parser.add_argument(
        "--restored",
        default="RestoredStereoManifest.csv",
        help="Path to restored manifest CSV (default: RestoredStereoManifest.csv).",
    )
    parser.add_argument(
        "--originals",
        required=True,
        help="Path to originals metadata file (.xlsx/.xls/.csv).",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Excel sheet name (optional). If omitted, uses first sheet.",
    )
    parser.add_argument(
        "--out",
        default="RestoredStereo_withArchiveID.csv",
        help="Output CSV path.",
    )

    args = parser.parse_args()

    restored_path = Path(args.restored)
    originals_path = Path(args.originals)
    out_path = Path(args.out)

    if not restored_path.exists():
        raise SystemExit(f"Restored file not found: {restored_path}")
    if not originals_path.exists():
        raise SystemExit(f"Originals file not found: {originals_path}")

    restored = pd.read_csv(restored_path)

    # Some exports contain duplicated column names (e.g., archive_id twice).
    # pandas will disambiguate by appending ".1" etc, but only after read.
    restored.columns = _dedup_columns(restored.columns)

    card_col = _pick_column(
        restored,
        candidates=[
            "card_id",
            "card id",
            "cardid",
            "id",
            "original_meta_id",
            "original meta id",
            "meta_id",
        ],
    ) or _pick_column_contains(restored, needles=["card", "meta", "original"])

    if not card_col:
        raise SystemExit(
            "Could not detect card id column in restored file. "
            f"Columns: {list(restored.columns)}"
        )

    if originals_path.suffix.lower() in {".xlsx", ".xls", ".xlsm", ".xlsb", ".ods"}:
        sheet = 0 if args.sheet is None else args.sheet
        originals = pd.read_excel(originals_path, sheet_name=sheet)
    else:
        originals = pd.read_csv(originals_path)

    originals.columns = [str(c) for c in originals.columns]

    # Try to detect join key + archive id columns.
    originals_key = _pick_column(
        originals,
        candidates=[
            "original_meta_id",
            "original meta id",
            "meta_id",
            "meta id",
            "card_id",
            "card id",
            "expo_id",
            "expo id",
            "id",
        ],
    ) or _pick_column_contains(originals, needles=["meta", "card", "expo", "id"])

    archive_col = _pick_column(
        originals,
        candidates=[
            "archive_id",
            "archive id",
            "archiveid",
            "img_id",
            "img id",
            "image_id",
            "image id",
        ],
    ) or _pick_column_contains(originals, needles=["archive", "img", "image"])

    if not originals_key or not archive_col:
        raise SystemExit(
            "Could not detect originals join key and/or archive_id column.\n"
            f"Detected join key: {originals_key}\n"
            f"Detected archive column: {archive_col}\n"
            f"Originals columns: {list(originals.columns)}"
        )

    left = restored.copy()
    left["_join_key"] = left[card_col].astype(str).str.strip()

    right = originals[[originals_key, archive_col]].copy()
    right["_join_key"] = right[originals_key].astype(str).str.strip()
    right = right.drop_duplicates(subset=["_join_key"], keep="first")
    right = right[["_join_key", archive_col]]

    merged = left.merge(right, on="_join_key", how="left", suffixes=("", "_from_originals"))
    merged = merged.drop(columns=["_join_key"])

    # Normalize the originals archive column name.
    if archive_col in merged.columns and archive_col != "archive_id_from_originals":
        merged = merged.rename(columns={archive_col: "archive_id_from_originals"})

    # Resolve to a single archive_id column:
    # Prefer originals-derived archive id; otherwise fall back to any existing archive_id columns.
    candidates: list[str] = []
    if "archive_id_from_originals" in merged.columns:
        candidates.append("archive_id_from_originals")
    for c in ["archive_id", "archive_id.1", "archive_id.2"]:
        if c in merged.columns:
            candidates.append(c)

    if candidates:
        resolved = None
        for c in candidates:
            series = pd.to_numeric(merged[c], errors="coerce")
            resolved = series if resolved is None else resolved.combine_first(series)
        merged["archive_id"] = resolved.round().astype("Int64")

    # Drop duplicate/aux archive columns except the resolved archive_id.
    for c in list(merged.columns):
        if c in {"archive_id"}:
            continue
        if c == "archive_id_from_originals" or c.startswith("archive_id."):
            merged = merged.drop(columns=[c])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)

    print("OK")
    print(f"restored:  {restored_path}")
    print(f"originals: {originals_path}")
    print(f"output:    {out_path}")
    print(f"used card column: {card_col}")
    print(f"used originals key: {originals_key}")
    print(f"used archive column: {archive_col}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

