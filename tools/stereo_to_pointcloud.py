"""Convert restored stereo image pairs into colored PLY point clouds.

The script accepts pairs named like ``0000_c_l.png`` and ``0000_c_r.png``.
Without a calibration file the output is in relative units: provide
``--focal-px`` and ``--baseline`` if you know the stereo camera parameters.
"""

from __future__ import annotations

import argparse
import random
import re
import struct
from pathlib import Path

import cv2
import numpy as np


PAIR_RE = re.compile(r"^(?P<id>\d+)_(?P<variant>[^_]+)_l\.(?P<ext>png|jpg|jpeg|tif|tiff)$", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build colored .ply point clouds from left/right stereo PNG pairs."
    )
    parser.add_argument("--input-dir", type=Path, default=Path("Restored"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/pointclouds"))
    parser.add_argument("--variant", default="c", help="Pair variant to process, e.g. c or n.")
    parser.add_argument("--ids", nargs="*", help="Only process these numeric ids, e.g. 0000 0002.")
    parser.add_argument("--downscale", type=float, default=0.5, help="Resize factor before matching.")
    parser.add_argument("--focal-px", type=float, default=None, help="Focal length in pixels after full resolution.")
    parser.add_argument("--baseline", type=float, default=1.0, help="Stereo baseline in desired output units.")
    parser.add_argument("--num-disparities", type=int, default=160, help="Must be divisible by 16.")
    parser.add_argument("--block-size", type=int, default=7, help="Odd SGBM block size.")
    parser.add_argument("--min-disparity", type=int, default=0)
    parser.add_argument("--max-depth", type=float, default=None, help="Drop points beyond this Z value.")
    parser.add_argument("--max-points", type=int, default=600_000, help="Randomly sample if cloud is larger.")
    parser.add_argument("--ascii", action="store_true", help="Write ASCII PLY instead of binary.")
    return parser.parse_args()


def discover_pairs(input_dir: Path, variant: str, ids: set[str] | None) -> list[tuple[str, Path, Path]]:
    pairs: list[tuple[str, Path, Path]] = []
    for left in sorted(input_dir.iterdir()):
        match = PAIR_RE.match(left.name)
        if not match or match.group("variant") != variant:
            continue
        pair_id = match.group("id")
        if ids is not None and pair_id not in ids:
            continue
        right = left.with_name(f"{pair_id}_{variant}_r.{match.group('ext')}")
        if right.exists():
            pairs.append((pair_id, left, right))
    return pairs


def read_pair(left_path: Path, right_path: Path, downscale: float) -> tuple[np.ndarray, np.ndarray]:
    left = cv2.imread(str(left_path), cv2.IMREAD_COLOR)
    right = cv2.imread(str(right_path), cv2.IMREAD_COLOR)
    if left is None:
        raise ValueError(f"Could not read {left_path}")
    if right is None:
        raise ValueError(f"Could not read {right_path}")
    if left.shape[:2] != right.shape[:2]:
        raise ValueError(f"Image sizes differ: {left_path.name} vs {right_path.name}")
    if downscale != 1.0:
        size = (int(left.shape[1] * downscale), int(left.shape[0] * downscale))
        left = cv2.resize(left, size, interpolation=cv2.INTER_AREA)
        right = cv2.resize(right, size, interpolation=cv2.INTER_AREA)
    return left, right


def compute_disparity(left: np.ndarray, right: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    num_disparities = max(16, int(np.ceil(args.num_disparities / 16)) * 16)
    block_size = args.block_size if args.block_size % 2 else args.block_size + 1
    gray_l = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
    gray_r = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
    matcher = cv2.StereoSGBM_create(
        minDisparity=args.min_disparity,
        numDisparities=num_disparities,
        blockSize=block_size,
        P1=8 * 3 * block_size**2,
        P2=32 * 3 * block_size**2,
        disp12MaxDiff=1,
        uniquenessRatio=8,
        speckleWindowSize=80,
        speckleRange=2,
        preFilterCap=63,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
    )
    return matcher.compute(gray_l, gray_r).astype(np.float32) / 16.0


def disparity_to_points(
    left: np.ndarray,
    disparity: np.ndarray,
    full_res_focal_px: float | None,
    downscale: float,
    baseline: float,
    max_depth: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    height, width = disparity.shape
    focal_px = (full_res_focal_px * downscale) if full_res_focal_px else width * 0.8
    cx = width / 2.0
    cy = height / 2.0

    mask = np.isfinite(disparity) & (disparity > 0.5)
    z = np.zeros_like(disparity, dtype=np.float32)
    z[mask] = (focal_px * baseline) / disparity[mask]
    if max_depth is not None:
        mask &= z <= max_depth

    ys, xs = np.nonzero(mask)
    zs = z[ys, xs]
    points = np.column_stack(
        (
            (xs.astype(np.float32) - cx) * zs / focal_px,
            -(ys.astype(np.float32) - cy) * zs / focal_px,
            zs,
        )
    ).astype(np.float32)
    colors = cv2.cvtColor(left, cv2.COLOR_BGR2RGB)[ys, xs].astype(np.uint8)
    return points, colors


def sample_points(points: np.ndarray, colors: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    if max_points <= 0 or len(points) <= max_points:
        return points, colors
    rng = random.Random(42)
    indices = np.array(rng.sample(range(len(points)), max_points), dtype=np.int64)
    return points[indices], colors[indices]


def write_ply(path: Path, points: np.ndarray, colors: np.ndarray, ascii_mode: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "ply\n"
        f"format {'ascii 1.0' if ascii_mode else 'binary_little_endian 1.0'}\n"
        f"element vertex {len(points)}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    )
    with path.open("wb") as handle:
        handle.write(header.encode("ascii"))
        if ascii_mode:
            for point, color in zip(points, colors):
                handle.write(
                    f"{point[0]:.6f} {point[1]:.6f} {point[2]:.6f} {color[0]} {color[1]} {color[2]}\n".encode(
                        "ascii"
                    )
                )
        else:
            for point, color in zip(points, colors):
                handle.write(struct.pack("<fffBBB", point[0], point[1], point[2], int(color[0]), int(color[1]), int(color[2])))


def main() -> None:
    args = parse_args()
    if not args.input_dir.exists():
        raise SystemExit(f"Input directory not found: {args.input_dir}")
    if args.downscale <= 0:
        raise SystemExit("--downscale must be positive")

    ids = {item.zfill(4) for item in args.ids} if args.ids else None
    pairs = discover_pairs(args.input_dir, args.variant, ids)
    if not pairs:
        raise SystemExit(f"No '*_{args.variant}_l' stereo pairs found in {args.input_dir}")

    for pair_id, left_path, right_path in pairs:
        print(f"[{pair_id}] reading {left_path.name} + {right_path.name}")
        left, right = read_pair(left_path, right_path, args.downscale)
        disparity = compute_disparity(left, right, args)
        points, colors = disparity_to_points(
            left, disparity, args.focal_px, args.downscale, args.baseline, args.max_depth
        )
        points, colors = sample_points(points, colors, args.max_points)
        out_path = args.output_dir / f"{pair_id}_{args.variant}.ply"
        write_ply(out_path, points, colors, args.ascii)
        print(f"[{pair_id}] wrote {out_path} with {len(points):,} points")


if __name__ == "__main__":
    main()
