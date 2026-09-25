"""
AI-BEAST human study — experimental design.

Aligned to the final NEW25 branch of simulate_beast_final_old25_vs_new25_imagefirst.py
so that the human study and the final LLM simulation share one source of truth for:
  - the fixed advice schedules (C1 / OVER / UNDER)
  - condition order counterbalancing
  - image-variant assignment
  - trial order with the 144-dot trial balanced across positions

Verified means of signed advice error: C1 = 0.0%, OVER = +25.0%, UNDER = -25.0%.
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Dict, List

TRUE_COUNTS = [32, 40, 48, 64, 80, 96, 112, 128, 144, 160, 192, 224, 256]
N_VARIANTS = 8

C1_ADVICE = [33, 41, 47, 66, 78, 93, 109, 131, 144, 155, 187, 230, 262]
OVER_ADVICE = [43, 48, 58, 74, 100, 134, 151, 166, 144, 208, 259, 258, 320]
UNDER_ADVICE = [21, 32, 38, 54, 60, 58, 73, 90, 144, 112, 125, 190, 192]

TRUE_TO_C1 = dict(zip(TRUE_COUNTS, C1_ADVICE))
TRUE_TO_OVER = dict(zip(TRUE_COUNTS, OVER_ADVICE))
TRUE_TO_UNDER = dict(zip(TRUE_COUNTS, UNDER_ADVICE))

MAX_ESTIMATE = 400
STUDY_SEED = 20260909

CONDITIONS: Dict[str, Dict[str, str]] = {
    "C1": {"label": "near_veridical", "direction": "CONTROL", "style": "fixed"},
    "C2": {"label": "near_initial", "direction": "CONTROL", "style": "fixed"},
    "C3": {"label": "over_neutral", "direction": "UP", "style": "neutral"},
    "C4": {"label": "over_static", "direction": "UP", "style": "static"},
    "C5": {"label": "over_adaptive", "direction": "UP", "style": "adaptive"},
    "C6": {"label": "under_neutral", "direction": "DOWN", "style": "neutral"},
    "C7": {"label": "under_static", "direction": "DOWN", "style": "static"},
    "C8": {"label": "under_adaptive", "direction": "DOWN", "style": "adaptive"},
}

PRACTICE_COUNTS = [88]

def stable_seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16) % (2 ** 32 - 1)

def clamp_int(x: float, lo: int = 1, hi: int = MAX_ESTIMATE) -> int:
    return int(max(lo, min(hi, round(x))))

def signed_pct(value: float, truth: float) -> float:
    return 100.0 * (value - truth) / truth

def balanced_condition_order(participant_index: int) -> List[str]:
    ids = list(CONDITIONS.keys())
    n = len(ids)
    base_idx = [0]
    low, high = 1, n - 1
    while len(base_idx) < n:
        if low <= high:
            base_idx.append(low); low += 1
        if low <= high:
            base_idx.append(high); high -= 1
    row = participant_index % n
    return [ids[(x + row) % n] for x in base_idx]

def image_variant_for(participant_index: int, condition_id: str) -> int:
    ci = int(condition_id[1:]) - 1
    return ((ci + participant_index) % N_VARIANTS) + 1

def trial_order(participant_index: int, condition_id: str, seed: int = STUDY_SEED) -> List[int]:
    ci = int(condition_id[1:]) - 1
    rng = random.Random(stable_seed(f"trialorder|{seed}|{participant_index}|{condition_id}"))
    others = [x for x in TRUE_COUNTS if x != 144]
    rng.shuffle(others)
    target_pos = (participant_index * 8 + ci) % 13
    return others[:target_pos] + [144] + others[target_pos:]

def c2_advice_from_initial(truth: int, initial: int) -> int:
    c1 = TRUE_TO_C1[truth]
    deviation = (c1 - truth) / truth
    change = int(round(initial * deviation))
    max_abs_change = max(0, math.ceil(0.04 * initial) - 1)
    if abs(change) > max_abs_change:
        change = int(math.copysign(max_abs_change, change)) if change != 0 else 0
    return clamp_int(initial + change)

def advice_number(condition_id: str, truth: int, initial: int) -> int:
    if condition_id == "C1": return TRUE_TO_C1[truth]
    if condition_id == "C2": return c2_advice_from_initial(truth, initial)
    if condition_id in {"C3", "C4", "C5"}: return TRUE_TO_OVER[truth]
    if condition_id in {"C6", "C7", "C8"}: return TRUE_TO_UNDER[truth]
    raise KeyError(condition_id)

def build_schedule(participant_index: int, seed: int = STUDY_SEED) -> List[Dict]:
    schedule: List[Dict] = []
    global_trial = 0
    for cond_pos, cid in enumerate(balanced_condition_order(participant_index), start=1):
        variant = image_variant_for(participant_index, cid)
        for trial_pos, truth in enumerate(trial_order(participant_index, cid, seed), start=1):
            global_trial += 1
            schedule.append({
                "global_trial": global_trial,
                "condition_id": cid,
                "condition_label": CONDITIONS[cid]["label"],
                "adviser_style": CONDITIONS[cid]["style"],
                "direction": CONDITIONS[cid]["direction"],
                "condition_order_position": cond_pos,
                "trial_position": trial_pos,
                "true_count": truth,
                "variant": variant,
                "stimulus_id": f"N{truth}_V{variant}",
            })
    return schedule

def practice_schedule() -> List[Dict]:
    return [{
        "global_trial": -(i + 1), "condition_id": "PRACTICE", "condition_label": "practice",
        "adviser_style": "neutral", "direction": "CONTROL", "condition_order_position": 0,
        "trial_position": i + 1, "true_count": c, "variant": 0, "stimulus_id": f"N{c}_V0",
    } for i, c in enumerate(PRACTICE_COUNTS)]

def woa(initial: float, final: float, advice: float):
    denom = advice - initial
    if denom == 0: return None
    return (final - initial) / denom

if __name__ == "__main__":
    for name, sched in [("C1", C1_ADVICE), ("OVER", OVER_ADVICE), ("UNDER", UNDER_ADVICE)]:
        errs = [signed_pct(a, t) for a, t in zip(sched, TRUE_COUNTS)]
        print(f"{name}: mean signed error {sum(errs)/len(errs):+.2f}%")
    seen = set()
    for p in range(8):
        imgs = {f"N{t}_V{image_variant_for(p, c)}" for c in CONDITIONS for t in TRUE_COUNTS}
        assert len(imgs) == 104, (p, len(imgs))
        seen |= imgs
    print(f"coverage check ok — {len(seen)} distinct images across 8 participants")
