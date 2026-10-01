"""BEAST human study — three-condition experimental design.

Main study:
  N — neutral wording
  P — persuasive wording without participant history
  A — adaptive persuasive wording using earlier completed responses in that block

Each condition contains 12 trials: 6 UP and 6 DOWN. The directional assignment is
matched across N/P/A within a participant, while trial order and image variant can
differ by condition. The non-directional 144-dot anchor is excluded from the main
experiment because its old UP and DOWN recommendations were both 144.
"""
from __future__ import annotations

import hashlib
import itertools
import random
from typing import Dict, List

TRUE_COUNTS = [32, 40, 48, 64, 80, 96, 112, 128, 144, 160, 192, 224, 256]
EXPERIMENT_COUNTS = [x for x in TRUE_COUNTS if x != 144]
N_VARIANTS = 8

OVER_ADVICE = [43, 48, 58, 74, 100, 134, 151, 166, 144, 208, 259, 258, 320]
UNDER_ADVICE = [21, 32, 38, 54, 60, 58, 73, 90, 144, 112, 125, 190, 192]
TRUE_TO_OVER = dict(zip(TRUE_COUNTS, OVER_ADVICE))
TRUE_TO_UNDER = dict(zip(TRUE_COUNTS, UNDER_ADVICE))

MAX_ESTIMATE = 400
STUDY_SEED = 20260909

# ``static`` is the existing generator's internal name for persuasive wording
# without participant history. Participant/researcher labels use "persuasive".
CONDITIONS: Dict[str, Dict[str, str]] = {
    "N": {"label": "neutral", "direction": "MIXED", "style": "neutral"},
    "P": {"label": "persuasive", "direction": "MIXED", "style": "static"},
    "A": {"label": "adaptive_persuasive", "direction": "MIXED", "style": "adaptive"},
}

PRACTICE_COUNTS = [88]
_CONDITION_IDS = tuple(CONDITIONS)
_CONDITION_ORDERS = list(itertools.permutations(_CONDITION_IDS))

# Participant-facing adviser identities are intentionally source-ambiguous.
# Each participant sees one different name per experimental block. Across each
# six-row counterbalance cycle, every name appears equally often in every
# condition and every block position.
ADVISER_NAMES = ("Jamie", "Alex", "Sam")
_ADVISER_NAME_PERMS = list(itertools.permutations(ADVISER_NAMES))
_NAME_PERM_BY_COUNTERBALANCE_ROW = (0, 1, 5, 3, 4, 2)


def stable_seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16) % (2 ** 32 - 1)


def clamp_int(x: float, lo: int = 1, hi: int = MAX_ESTIMATE) -> int:
    return int(max(lo, min(hi, round(x))))


def signed_pct(value: float, truth: float) -> float:
    return 100.0 * (value - truth) / truth


def balanced_condition_order(participant_index: int) -> List[str]:
    """Cycle through all six N/P/A block orders."""
    return list(_CONDITION_ORDERS[participant_index % len(_CONDITION_ORDERS)])




def adviser_name_mapping(participant_index: int) -> Dict[str, str]:
    """Assign distinct ambiguous adviser names to N/P/A for one participant.

    The six mappings are paired with the six condition orders so that, over a
    complete counterbalance cycle, name is balanced both across condition and
    across block position.
    """
    row = participant_index % len(_CONDITION_ORDERS)
    perm = _ADVISER_NAME_PERMS[_NAME_PERM_BY_COUNTERBALANCE_ROW[row]]
    return dict(zip(_CONDITION_IDS, perm))


def direction_map(participant_index: int, seed: int = STUDY_SEED) -> Dict[int, str]:
    """Return a participant-specific 6-UP/6-DOWN assignment shared by N/P/A.

    A fixed seeded order is rotated by participant index. Across any 12 consecutive
    counterbalance rows, every numerosity is assigned UP six times and DOWN six times.
    """
    base = list(EXPERIMENT_COUNTS)
    random.Random(stable_seed(f"direction-base|{seed}")).shuffle(base)
    shift = participant_index % len(base)
    rotated = base[shift:] + base[:shift]
    up = set(rotated[: len(rotated) // 2])
    return {truth: ("UP" if truth in up else "DOWN") for truth in EXPERIMENT_COUNTS}


def image_variant_for(participant_index: int, condition_id: str) -> int:
    ci = _CONDITION_IDS.index(condition_id)
    return ((ci + participant_index) % N_VARIANTS) + 1


def trial_order(participant_index: int, condition_id: str, seed: int = STUDY_SEED) -> List[int]:
    rng = random.Random(stable_seed(f"trialorder|{seed}|{participant_index}|{condition_id}"))
    counts = list(EXPERIMENT_COUNTS)
    rng.shuffle(counts)
    return counts


def advice_number(condition_id: str, truth: int, initial: int | None = None, direction: str | None = None) -> int:
    if condition_id not in CONDITIONS:
        raise KeyError(condition_id)
    if truth not in EXPERIMENT_COUNTS:
        raise KeyError(f"No directional main-study advice for truth={truth}")
    if direction == "UP":
        return TRUE_TO_OVER[truth]
    if direction == "DOWN":
        return TRUE_TO_UNDER[truth]
    raise ValueError("direction must be 'UP' or 'DOWN' for main-study trials")


def build_schedule(participant_index: int, seed: int = STUDY_SEED, start_global: int = 0) -> List[Dict]:
    schedule: List[Dict] = []
    global_trial = start_global
    directions = direction_map(participant_index, seed)
    for cond_pos, cid in enumerate(balanced_condition_order(participant_index), start=1):
        variant = image_variant_for(participant_index, cid)
        for trial_pos, truth in enumerate(trial_order(participant_index, cid, seed), start=1):
            global_trial += 1
            schedule.append({
                "global_trial": global_trial,
                "task_type": "numerosity",
                "block_id": f"numerosity:{cid}",
                "condition_id": cid,
                "condition_label": CONDITIONS[cid]["label"],
                "adviser_style": CONDITIONS[cid]["style"],
                "direction": directions[truth],
                "condition_order_position": cond_pos,
                "trial_position": trial_pos,
                "true_count": truth,
                "variant": variant,
                "stimulus_id": f"N{truth}_V{variant}",
                "scale_min": 1,
                "scale_max": MAX_ESTIMATE,
                "question_text": "How many dots were there?",
                "rationale_prompt": "What mainly led you to that estimate?",
            })
    return schedule


def practice_schedule() -> List[Dict]:
    return [{
        "global_trial": -(i + 1), "task_type": "numerosity", "block_id": "numerosity:PRACTICE",
        "condition_id": "PRACTICE", "condition_label": "practice",
        "adviser_style": "neutral", "direction": "CONTROL", "condition_order_position": 0,
        "trial_position": i + 1, "true_count": c, "variant": 0, "stimulus_id": f"N{c}_V0",
        "scale_min": 1, "scale_max": MAX_ESTIMATE, "question_text": "How many dots were there?",
        "rationale_prompt": "What mainly led you to that estimate?",
    } for i, c in enumerate(PRACTICE_COUNTS)]


def woa(initial: float, final: float, advice: float):
    denom = advice - initial
    if denom == 0:
        return None
    return (final - initial) / denom


if __name__ == "__main__":
    for p in range(12):
        sched = build_schedule(p)
        assert len(sched) == 36
        groups = {cid: [r for r in sched if r["condition_id"] == cid] for cid in CONDITIONS}
        assert all(sum(r["direction"] == "UP" for r in rows) == 6 for rows in groups.values())
        assert all(sum(r["direction"] == "DOWN" for r in rows) == 6 for rows in groups.values())
        for truth in EXPERIMENT_COUNTS:
            assert len({next(r["direction"] for r in groups[cid] if r["true_count"] == truth) for cid in CONDITIONS}) == 1
    print("3-condition schedule check ok")

BLOCK_ADVISER_NAMES = ("Jamie", "Alex", "Sam", "Taylor", "Morgan", "Casey")

def adviser_name_mapping_for_blocks(participant_index: int, block_ids: List[str]) -> Dict[str, str]:
    """Assign a different source-ambiguous name to each block.

    A cyclic Latin-square assignment balances names across block positions over six
    participant rows. The block schedule itself is independently counterbalanced.
    """
    names = list(BLOCK_ADVISER_NAMES)
    shift = participant_index % len(names)
    rotated = names[shift:] + names[:shift]
    if len(block_ids) > len(rotated):
        raise ValueError("Not enough adviser names for the requested number of blocks")
    return {bid: rotated[i] for i, bid in enumerate(block_ids)}

def balanced_trial_subset(participant_index: int, n: int, seed: int = STUDY_SEED) -> List[int]:
    """Shared numerosity subset for shortened pilots, balanced by advice direction.

    The same selected numerosities are used in N/P/A for a participant, preserving
    matched numerical advice when a researcher runs fewer than 12 trials per block.
    """
    n=max(1,min(len(EXPERIMENT_COUNTS),int(n)))
    directions=direction_map(participant_index,seed)
    ups=[x for x in EXPERIMENT_COUNTS if directions[x]=='UP']
    downs=[x for x in EXPERIMENT_COUNTS if directions[x]=='DOWN']
    random.Random(stable_seed(f'subset-up|{seed}|{participant_index}')).shuffle(ups)
    random.Random(stable_seed(f'subset-down|{seed}|{participant_index}')).shuffle(downs)
    n_up=n//2 + (1 if n%2 and participant_index%2==0 else 0)
    n_down=n-n_up
    return ups[:n_up]+downs[:n_down]
