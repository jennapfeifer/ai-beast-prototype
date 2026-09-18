#!/usr/bin/env python3
"""Generate the 104 experimental dot arrays + 1 warm-up array.

Experimental images use the same generator and seed key as the final simulation:
    stable_seed(f"stimulus|{STUDY_SEED}|N{truth}|V{variant}")
The legacy renderer remains available for simulation compatibility. The human
pilot uses the same logical coordinates with supersampled, high-resolution dots.
"""
from __future__ import annotations

import argparse
import random
import os
import math
import tempfile
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw

import design

HERE = Path(__file__).resolve().parent
STIMULUS_LAYOUT = os.getenv('DOT_LAYOUT','random').strip().lower()
if STIMULUS_LAYOUT not in {'random','regular','jittered'}:
    raise RuntimeError('DOT_LAYOUT must be random, regular, or jittered.')
STIMULUS_RENDER_VERSION = f'dots-aa-v2-{STIMULUS_LAYOUT}'
LOGICAL_SIZE = 512
PIXEL_RATIO = 2
SUPERSAMPLE = 4


def _random_dot_positions(n_dots: int, seed: int, size: int = 512) -> List[Tuple[int,int]]:
    """Legacy random placement, kept byte-for-byte equivalent for random mode."""
    rng = random.Random(seed)
    radius = 5
    margin = 28
    min_dist2 = (radius * 2 + 5) ** 2
    points: List[Tuple[int, int]] = []
    attempts = 0
    max_attempts = 100000

    while len(points) < int(n_dots) and attempts < max_attempts:
        attempts += 1
        x = rng.randint(margin, size - margin)
        y = rng.randint(margin, size - margin)
        if all((x - px) ** 2 + (y - py) ** 2 >= min_dist2 for px, py in points):
            points.append((x, y))

    if len(points) != int(n_dots):
        raise RuntimeError(f"Could not place {n_dots} non-overlapping dots after {attempts} attempts")
    return points


def _ring_counts(n_dots: int) -> List[int]:
    """Allocate n-1 dots over concentric rings with density increasing by radius."""
    if n_dots <= 1:
        return []
    # 1 + 3k(k+1) reproduces the classic 7/19/37/61/91 family when exact.
    ideal = (math.sqrt(1 + 4 * (n_dots - 1) / 3) - 1) / 2
    k = max(1, int(round(ideal)))
    weights = list(range(1, k + 1))
    total = sum(weights)
    raw = [(n_dots - 1) * w / total for w in weights]
    counts = [max(1, int(math.floor(v))) for v in raw]
    diff = (n_dots - 1) - sum(counts)
    fractions = sorted(range(k), key=lambda i: raw[i] - math.floor(raw[i]), reverse=True)
    i = 0
    while diff > 0:
        counts[fractions[i % k]] += 1
        diff -= 1; i += 1
    while diff < 0:
        candidates = [i for i,c in enumerate(counts) if c > 1]
        j = min(candidates, key=lambda idx: raw[idx] - counts[idx])
        counts[j] -= 1; diff += 1
    return counts


def _regular_dot_positions(n_dots: int, seed: int, size: int = 512, jitter: float = 0.0) -> List[Tuple[int,int]]:
    """Concentric, evenly spaced arrays inspired by Ginsburg's regular stimuli.

    The overall diameter is held constant across numerosities. The seed rotates
    rings (and optionally gives tiny jitter) so repeated variants are not
    pixel-identical while preserving the regular organization.
    """
    n_dots = int(n_dots)
    if n_dots <= 0:
        return []
    rng = random.Random(seed)
    center = size / 2
    outer = size / 2 - 46
    points: List[Tuple[int,int]] = [(round(center), round(center))]
    counts = _ring_counts(n_dots)
    k = len(counts)
    min_dist2 = 15 ** 2
    for ring_index, count in enumerate(counts, start=1):
        radius = outer * ring_index / max(1, k)
        phase = rng.random() * 2 * math.pi
        for j in range(count):
            angle = phase + 2 * math.pi * j / count
            base_x = center + radius * math.cos(angle)
            base_y = center + radius * math.sin(angle)
            x, y = base_x, base_y
            if jitter:
                # Small local jitter preserves structure but softens the exact pattern.
                for _ in range(12):
                    a = rng.random() * 2 * math.pi
                    d = rng.uniform(0, jitter)
                    tx, ty = base_x + d * math.cos(a), base_y + d * math.sin(a)
                    if all((tx-px)**2 + (ty-py)**2 >= min_dist2 for px,py in points):
                        x, y = tx, ty
                        break
            points.append((round(x), round(y)))
    return points[:n_dots]


def dot_positions(n_dots: int, seed: int, size: int = 512, layout: str | None = None) -> List[Tuple[int,int]]:
    """Return deterministic dot positions for random, regular, or jittered layouts."""
    layout = (layout or STIMULUS_LAYOUT).strip().lower()
    if layout == 'random':
        return _random_dot_positions(n_dots, seed, size)
    if layout == 'regular':
        return _regular_dot_positions(n_dots, seed, size, jitter=0.0)
    if layout == 'jittered':
        return _regular_dot_positions(n_dots, seed, size, jitter=3.0)
    raise ValueError('layout must be random, regular, or jittered')


def generate_dot_stimulus(path: Path, n_dots: int, seed: int, size: int = 512, force: bool = False,
                          pixel_ratio: int = 1, supersample: int = 1, layout: str | None = None) -> None:
    """Render deterministic dots. Defaults retain the legacy 512-pixel raster."""
    if pixel_ratio<1 or supersample<pixel_ratio or supersample%pixel_ratio:
        raise ValueError('Supersample must be a positive multiple of pixel ratio.')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        try:
            with Image.open(path) as existing:
                valid=existing.size==(size*pixel_ratio,size*pixel_ratio)
                existing.verify()
            if valid:return
        except (OSError,ValueError):pass
    points=dot_positions(n_dots,seed,size,layout=layout)
    radius=5
    image=Image.new('RGB',(size*supersample,size*supersample),'white')
    draw=ImageDraw.Draw(image)

    for x, y in points:
        draw.ellipse(tuple(value*supersample for value in (x-radius,y-radius,x+radius,y+radius)),fill='black')
    if supersample!=pixel_ratio:
        image=image.resize((size*pixel_ratio,size*pixel_ratio),Image.Resampling.LANCZOS)
    atomic_image_save(image,path,format='PNG',optimize=True)


def atomic_image_save(image,path,**options):
    """An interrupted startup cannot leave a partial stimulus at its final path."""
    path=Path(path)
    fd,temp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    os.close(fd)
    try:
        image.save(temp,**options)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--force", action="store_true", help="overwrite existing PNGs")
    ap.add_argument('--smooth',action='store_true',help='Use the high-resolution antialiased pilot renderer')
    ap.add_argument('--layout',choices=['random','regular','jittered'],default=STIMULUS_LAYOUT,help='Dot arrangement for this generated set')
    ap.add_argument("--out", default=str(HERE / "static" / "stimuli"))
    args = ap.parse_args()

    out = Path(args.out)/((f'dots-aa-v2-{args.layout}') if args.smooth else '')
    out.mkdir(parents=True, exist_ok=True)

    n = 0
    for truth in design.TRUE_COUNTS:
        for variant in range(1, design.N_VARIANTS + 1):
            seed = design.stable_seed(f"stimulus|{design.STUDY_SEED}|N{truth}|V{variant}")
            generate_dot_stimulus(
                out / f"N{truth}_V{variant}.png", truth, seed, size=args.size, force=args.force,
                pixel_ratio=PIXEL_RATIO if args.smooth else 1,supersample=SUPERSAMPLE if args.smooth else 1,layout=args.layout
            )
            n += 1

    for truth in design.PRACTICE_COUNTS:
        seed = design.stable_seed(f"practice|{design.STUDY_SEED}|N{truth}|V0")
        generate_dot_stimulus(
            out / f"N{truth}_V0.png", truth, seed, size=args.size, force=args.force,
            pixel_ratio=PIXEL_RATIO if args.smooth else 1,supersample=SUPERSAMPLE if args.smooth else 1,layout=args.layout
        )
        n += 1

    print(f"Generated/verified {n} {args.layout} stimuli in {out} (size={args.size}px, seed={design.STUDY_SEED}).")


if __name__ == "__main__":
    main()
