"""Generate versioned, antialiased stimuli on the protected server."""
from pathlib import Path
from PIL import Image
import design
from stimuli import generate_dot_stimulus, atomic_image_save, STIMULUS_RENDER_VERSION, LOGICAL_SIZE, PIXEL_RATIO, SUPERSAMPLE

STIMULUS_DIR=Path(__file__).resolve().parent/'static'/'stimuli'/STIMULUS_RENDER_VERSION

def ensure_webp(png):
    target=png.with_suffix('.webp')
    if target.exists() and target.stat().st_mtime_ns>=png.stat().st_mtime_ns:
        try:
            with Image.open(target) as image:
                valid=image.size==(LOGICAL_SIZE*PIXEL_RATIO,)*2
                image.load()
            if valid:return
        except (OSError,ValueError):pass
    with Image.open(png) as image:
        atomic_image_save(image.convert('RGB'),target,format='WEBP',lossless=True,method=3)


def ensure_stimulus(stimulus_id, truth, variant):
    """Generate/verify just one deterministic stimulus and return its WebP path."""
    out=STIMULUS_DIR
    out.mkdir(parents=True,exist_ok=True)
    truth=int(truth); variant=int(variant)
    if variant == 0:
        seed=design.stable_seed(f'practice|{design.STUDY_SEED}|N{truth}|V0')
    else:
        seed=design.stable_seed(f'stimulus|{design.STUDY_SEED}|N{truth}|V{variant}')
    png=out/f'{stimulus_id}.png'
    generate_dot_stimulus(png,truth,seed,size=LOGICAL_SIZE,pixel_ratio=PIXEL_RATIO,supersample=SUPERSAMPLE)
    ensure_webp(png)
    return png.with_suffix('.webp')

def ensure_stimuli():
    out=STIMULUS_DIR
    out.mkdir(parents=True,exist_ok=True)
    # Warm practice first because it is the first image a participant can request.
    for truth in design.PRACTICE_COUNTS:
        ensure_stimulus(f'N{truth}_V0',truth,0)
    for truth in design.TRUE_COUNTS:
        for variant in range(1,design.N_VARIANTS+1):
            ensure_stimulus(f'N{truth}_V{variant}',truth,variant)
