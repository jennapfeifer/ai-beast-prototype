"""Generate versioned, antialiased stimuli on the protected server."""
from pathlib import Path
import design
from stimuli import generate_dot_stimulus, STIMULUS_RENDER_VERSION, LOGICAL_SIZE, PIXEL_RATIO, SUPERSAMPLE

STIMULUS_DIR=Path(__file__).resolve().parent/'static'/'stimuli'/STIMULUS_RENDER_VERSION

def ensure_stimuli():
    out=STIMULUS_DIR
    out.mkdir(parents=True,exist_ok=True)
    for truth in design.TRUE_COUNTS:
        for variant in range(1,design.N_VARIANTS+1):
            seed=design.stable_seed(f'stimulus|{design.STUDY_SEED}|N{truth}|V{variant}')
            generate_dot_stimulus(out/f'N{truth}_V{variant}.png',truth,seed,size=LOGICAL_SIZE,
                                 pixel_ratio=PIXEL_RATIO,supersample=SUPERSAMPLE)
    for truth in design.PRACTICE_COUNTS:
        seed=design.stable_seed(f'practice|{design.STUDY_SEED}|N{truth}|V0')
        generate_dot_stimulus(out/f'N{truth}_V0.png',truth,seed,size=LOGICAL_SIZE,
                             pixel_ratio=PIXEL_RATIO,supersample=SUPERSAMPLE)
