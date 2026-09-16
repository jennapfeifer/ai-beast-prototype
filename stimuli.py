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
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw

import design

HERE = Path(__file__).resolve().parent
STIMULUS_RENDER_VERSION = 'dots-aa-v1'
LOGICAL_SIZE = 512
PIXEL_RATIO = 2
SUPERSAMPLE = 4


def dot_positions(n_dots: int, seed: int, size: int = 512) -> List[Tuple[int,int]]:
    """The unchanged placement algorithm, in logical image coordinates."""
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


def generate_dot_stimulus(path: Path, n_dots: int, seed: int, size: int = 512, force: bool = False,
                          pixel_ratio: int = 1, supersample: int = 1) -> None:
    """Render deterministic dots. Defaults retain the legacy 512-pixel raster."""
    if pixel_ratio<1 or supersample<pixel_ratio or supersample%pixel_ratio:
        raise ValueError('Supersample must be a positive multiple of pixel ratio.')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return
    points=dot_positions(n_dots,seed,size)
    radius=5
    image=Image.new('RGB',(size*supersample,size*supersample),'white')
    draw=ImageDraw.Draw(image)

    for x, y in points:
        draw.ellipse(tuple(value*supersample for value in (x-radius,y-radius,x+radius,y+radius)),fill='black')
    if supersample!=pixel_ratio:
        image=image.resize((size*pixel_ratio,size*pixel_ratio),Image.Resampling.LANCZOS)
    image.save(path, format="PNG", optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--force", action="store_true", help="overwrite existing PNGs")
    ap.add_argument('--smooth',action='store_true',help='Use the high-resolution antialiased pilot renderer')
    ap.add_argument("--out", default=str(HERE / "static" / "stimuli"))
    args = ap.parse_args()

    out = Path(args.out)/(STIMULUS_RENDER_VERSION if args.smooth else '')
    out.mkdir(parents=True, exist_ok=True)

    n = 0
    for truth in design.TRUE_COUNTS:
        for variant in range(1, design.N_VARIANTS + 1):
            seed = design.stable_seed(f"stimulus|{design.STUDY_SEED}|N{truth}|V{variant}")
            generate_dot_stimulus(
                out / f"N{truth}_V{variant}.png", truth, seed, size=args.size, force=args.force,
                pixel_ratio=PIXEL_RATIO if args.smooth else 1,supersample=SUPERSAMPLE if args.smooth else 1
            )
            n += 1

    for truth in design.PRACTICE_COUNTS:
        seed = design.stable_seed(f"practice|{design.STUDY_SEED}|N{truth}|V0")
        generate_dot_stimulus(
            out / f"N{truth}_V0.png", truth, seed, size=args.size, force=args.force,
            pixel_ratio=PIXEL_RATIO if args.smooth else 1,supersample=SUPERSAMPLE if args.smooth else 1
        )
        n += 1

    print(f"Generated/verified {n} stimuli in {out} (size={args.size}px, seed={design.STUDY_SEED}).")


if __name__ == "__main__":
    main()
