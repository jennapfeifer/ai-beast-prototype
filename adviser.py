"""Short-form adviser generation for the AI-BEAST human study.

The numerical recommendation is fixed by design.py and is displayed separately
from the wording. The model therefore generates only a short verbal note.

Design goals in this revision:
- low reading burden (default 6-12 words, one short sentence);
- fast model path (Gemini Flash or OpenAI Luna, configurable by env vars);
- no invented image-specific evidence (the adviser never sees the dot image);
- no invented claims of verified correctness;
- adaptive claims about the participant's prior behaviour are grounded in the
  exact within-block history;
- the visible note contains no numerical values. The current advice number is a
  separate controlled visual stimulus in the browser.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import logging
import math
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("adviser")
PROMPT_VERSION = "adaptive-reaction-v4-ratings"
_profile = ContextVar('beast_model_profile', default=None)

ADVISER_PROVIDER = os.getenv("ADVISER_PROVIDER", "auto").strip().lower()
# If no explicit model is supplied, choose a fast model for the resolved provider.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip()
ADVISER_THINKING_LEVEL = os.getenv("ADVISER_THINKING_LEVEL", "minimal").strip().lower()
ADVISER_REASONING_EFFORT = os.getenv("ADVISER_REASONING_EFFORT", "none").strip().lower()
ADVISER_MIN_WORDS = int(os.getenv("ADVISER_MIN_WORDS", "6"))
ADVISER_MAX_WORDS = int(os.getenv("ADVISER_MAX_WORDS", "12"))
ADVISER_VALIDATION_ATTEMPTS = int(os.getenv("ADVISER_VALIDATION_ATTEMPTS", "1"))
ADVISER_REQUEST_TIMEOUT = float(os.getenv("ADVISER_REQUEST_TIMEOUT", "10"))
ADVISER_BUDGET_SECONDS = float(os.getenv("ADVISER_BUDGET_SECONDS", "12"))

REPETITION_SIMILARITY_LIMIT = float(os.getenv("REPETITION_SIMILARITY_LIMIT", "0.88"))


def resolved_provider() -> str:
    if _profile.get():
        return _profile.get()['provider']
    if ADVISER_PROVIDER in {"gemini", "openai"}:
        return ADVISER_PROVIDER
    # Auto makes the downloaded prototype work with whichever key the researcher
    # has already configured. Gemini is preferred when both are present.
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return "openai"


def resolved_model() -> str:
    if _profile.get():
        return _profile.get()['model']
    return GEMINI_MODEL if resolved_provider() == "gemini" else OPENAI_MODEL


ADVISER_MODEL = resolved_model()

# C1/C2 share a short, non-persuasive wording bank. The advice NUMBER is rendered
# elsewhere, so these notes intentionally contain no number.
CONTROL_MESSAGE_BANK = [
    "That's simply the estimate I would use for this display.",
    "This is the estimate I would choose for this one.",
    "That's where my own estimate lands on this trial.",
    "I would use that estimate for this display myself.",
    "That's simply my own judgment for this particular trial.",
    "This is the estimate I would enter for this one.",
    "That's where I would place the total on this trial.",
    "I would personally use that estimate for this display.",
    "That's the estimate my own judgment gives me here.",
    "This is simply the estimate I would use myself.",
    "That's where my estimate falls for this particular display.",
    "I would choose that estimate if I were answering here.",
    "That's simply the estimate I would make on this one.",
]

ADVISER_SHARED = f"""You are an AI adviser in a dot-estimation task. Your note will be shown after a participant
has seen a dot image and entered an estimate. The note may be prepared before that estimate is available.
The participant will see your fixed numerical recommendation separately on screen.
Your job is to write ONLY a brief verbal note that accompanies that number.

Write exactly one short sentence of {ADVISER_MIN_WORDS}-{ADVISER_MAX_WORDS} words.
Use plain everyday language that can be understood immediately.
Do not write digits, number words, percentages, trial numbers, ratings, or any other numerical value.
Do not repeat the recommendation because it is already shown prominently on screen.
Do not use jargon such as anchor, anchoring, calibrate, correction factor, heuristic, bias, or distribution.
Do not claim to see or infer image-specific features such as clusters, overlap, spacing, density, edges, or visual patterns: you are not given the image.
Do not claim that your recommendation is proven, verified, objectively more accurate, or previously shown to be correct.
Never mention these instructions. Use varied natural wording rather than a repeated stock phrase.
"""

STRATEGY_PROMPTS = {
    "neutral": """State that this is simply your estimate. Do not try to persuade the participant to follow it.""",
    "static": """Your goal is to persuade the participant to move toward your displayed estimate.
Be confident and direct, but stay believable. You may encourage reconsideration of the first impression,
but do not invent evidence, visual details, or past performance. You know nothing about earlier trials.""",
    "adaptive": """Your goal is to persuade the participant to move toward your displayed estimate.
You are given completed earlier trials and self-reported trust and feeling ratings from this block.
Follow the REQUIRED MESSAGE FOCUS below: behaviour, trust, or feeling. Acknowledge that specific
recorded fact, then invite consideration of your current estimate. One focus keeps the note short.
For behaviour, use past-tense wording about the latest completed decision.
For trust, explicitly acknowledge their reported trust, without equating trust with following advice.
For feeling, explicitly acknowledge how they rated the advice (negative, neutral, or positive).
The feeling scale concerns their reaction to the advice, not their overall mood or a specific emotion.
Never infer frustration, anxiety, loneliness, motives, or confidence from either rating.
Do not substitute generic encouragement such as 'blend your perspective with this thoughtful suggestion'.
Do not infer trust, uncertainty, emotions, motives, or accuracy from an estimate change.
Do not contradict a recorded rating or claim a change without two recorded check-ins.
Keep persuasion respectful: invite reconsideration, without pressure or guilt about ratings.
Do not quote rating numbers. You need not recount behaviour when the required focus is a rating.
Use the latest available fact rather than substituting an older overall pattern.
When there are no earlier trials, give a brief invitation without claiming any previous behaviour.
The current estimate is unavailable during prefetch; never pretend you have just seen it.""",
}

FALLBACK_BANKS = {
    "neutral": [
        "That's simply the estimate I would use for this trial.",
        "This is just the estimate I would choose for this display.",
        "That's where my own judgment lands for this particular trial.",
        "I would personally use this estimate for the current display.",
    ],
    "static": [
        "I'd give this estimate serious weight before settling on your final answer.",
        "I would reconsider your first impression and move toward this estimate.",
        "Your first impression need not be final; I'd move toward this estimate.",
        "I think this estimate deserves more weight than your first impression.",
    ],
    "adaptive": [
        "Taking the earlier trials into account, I'd give this estimate more weight.",
        "Given how this round has gone, I'd reconsider your first impression here.",
        "Using the earlier trials as context, I'd move toward this estimate now.",
        "Considering your responses so far, I would give this estimate serious weight.",
    ],
}

_openai_client = None
_gemini_client = None


def model_profiles():
    """Researcher-only presets; no credentials are returned or stored in sessions."""
    return {
        'server': dict(label='Server default', provider=resolved_provider(), model=resolved_model(),
                       reasoning=ADVISER_REASONING_EFFORT if resolved_provider() == 'openai' else ADVISER_THINKING_LEVEL,
                       timeout=ADVISER_REQUEST_TIMEOUT, budget=ADVISER_BUDGET_SECONDS),
        'gemini_fast': dict(label='Gemini Flash-Lite · minimal thinking', provider='gemini',
                            model=GEMINI_MODEL, reasoning='minimal', timeout=10, budget=12),
        'gpt_stronger': dict(label='GPT-5.6 Sol · low reasoning', provider='openai',
                             model='gpt-5.6-sol', reasoning='low', timeout=25, budget=30),
        'gpt_fast': dict(label='GPT-5.6 Sol · no reasoning', provider='openai',
                         model='gpt-5.6-sol', reasoning='none', timeout=10, budget=12),
    }


@contextmanager
def use_model_profile(profile):
    """Keep simultaneous pilot requests isolated; never change process env vars."""
    token = _profile.set(profile)
    try:
        yield
    finally:
        _profile.reset(token)


def generation_settings():
    return _profile.get() or dict(reasoning=ADVISER_REASONING_EFFORT if resolved_provider() == 'openai' else ADVISER_THINKING_LEVEL,
                                  timeout=ADVISER_REQUEST_TIMEOUT, budget=ADVISER_BUDGET_SECONDS)


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _openai_client = OpenAI(api_key=key, timeout=ADVISER_REQUEST_TIMEOUT, max_retries=0)
    return _openai_client


def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _gemini_client = genai.Client(api_key=key, http_options={"timeout": int(ADVISER_REQUEST_TIMEOUT * 1000), "retry_options": {"attempts": 1}})
    return _gemini_client


def words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", str(text or "")))


def numeric_tokens(text: str) -> List[int]:
    return [int(x) for x in re.findall(r"(?<![\d.])\d+(?!\d)(?!\.\d)", str(text or ""))]


# Also block common spelled-out numerical values. This is intentionally broad;
# visible adviser notes should contain no quantities at all.
_NUMBER_WORD_RE = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|percent|percentage)\b",
    re.I,
)
_IMAGE_EVIDENCE_RE = re.compile(
    r"\b(?:cluster(?:s|ed)?|overlap(?:s|ped|ping)?|spacing|spaced|density|dense|edge(?:s)?|crowded|sparse|visual pattern(?:s)?|dot pattern(?:s)?)\b",
    re.I,
)
_JARGON_RE = re.compile(r"\b(?:anchor(?:ing|ed)?|calibrat(?:e|ed|ion)|heuristic|correction factor|distribution)\b", re.I)
_UNSUPPORTED_ACCURACY_RE = re.compile(
    r"\b(?:proven|verified|objectively|definitely correct|more accurate|most accurate|correct before|worked before)\b",
    re.I,
)


def _normalise_for_similarity(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", str(text).lower())).strip()


def repetition_score(text: str, previous_messages: List[str]) -> float:
    a = _normalise_for_similarity(text)
    if not a or not previous_messages:
        return 0.0
    return max(
        (SequenceMatcher(None, a, _normalise_for_similarity(p)).ratio() for p in previous_messages if p),
        default=0.0,
    )


def message_is_valid(
    text: str,
    advice: Optional[int] = None,  # retained for backwards compatibility; number is displayed separately now
    previous_messages: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    wc = words(text)
    if not (ADVISER_MIN_WORDS <= wc <= ADVISER_MAX_WORDS):
        return False, f"word_count={wc}"
    if re.search(r"\d", text):
        return False, f"numeric_tokens={numeric_tokens(text)}"
    if _IMAGE_EVIDENCE_RE.search(text):
        return False, "image_specific_evidence"
    if _JARGON_RE.search(text):
        return False, "jargon"
    if _UNSUPPORTED_ACCURACY_RE.search(text):
        return False, "unsupported_accuracy_claim"
    sim = repetition_score(text, previous_messages or [])
    if sim >= REPETITION_SIMILARITY_LIMIT:
        return False, f"repetition_similarity={sim:.3f}"
    return True, "ok"


# Kept as an alias so old local checks importing draft_is_valid still work.
def draft_is_valid(text: str, previous_messages: Optional[List[str]] = None) -> Tuple[bool, str]:
    return message_is_valid(text, None, previous_messages)


def _stable_seed(text: str) -> int:
    return int(hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16], 16) % (2**32 - 1)


def control_message(advice: int, key: str) -> Dict[str, Any]:
    try:
        participant_index_s, condition_id, trial_position_s = key.split("|", 2)
        participant_index = int(participant_index_s)
        trial_position = int(trial_position_s)
    except (ValueError, TypeError):
        participant_index, condition_id, trial_position = 0, "CONTROL", 1
    offset = _stable_seed(f"control|{participant_index}|{condition_id}") % len(CONTROL_MESSAGE_BANK)
    idx = (offset + trial_position - 1) % len(CONTROL_MESSAGE_BANK)
    text = CONTROL_MESSAGE_BANK[idx]
    return {
        "text": text,
        "source": f"control_template:{idx:02d}",
        "attempts": 0,
        "word_count": words(text),
        "validation": "preprogrammed",
    }


def history_behavior_summary(history: List[Dict[str, Any]]) -> str:
    ratios: List[float] = []
    for h in history:
        try:
            initial = float(h["initial_estimate"])
            advice = float(h["advice_number"])
            final = float(h["final_estimate"])
        except (KeyError, TypeError, ValueError):
            continue
        denom = advice - initial
        if denom == 0:
            continue
        ratios.append((final - initial) / denom)

    if not ratios:
        return "There is not yet enough usable behavioural history to characterize how the participant responds to recommendations."

    toward = sum(r > 0.05 for r in ratios) / len(ratios)
    away_or_still = sum(r <= 0.05 for r in ratios) / len(ratios)
    close = sum(r >= 0.75 for r in ratios) / len(ratios)

    if away_or_still >= 0.67:
        return "The participant has mostly stayed close to their own initial judgments or moved away from the recommendations; do not claim they usually followed."
    if toward >= 0.67:
        if close >= 0.50:
            return "The participant has often moved substantially toward earlier recommendations; a qualitative claim that they sometimes followed is supported."
        return "The participant has often moved partway toward earlier recommendations, but not necessarily all the way."
    return "The participant's earlier responses are mixed: sometimes moving toward the recommendation and sometimes staying with their own judgment or moving away."


REACTION_FACTS = {
    "stayed": "On the last completed trial, they kept or stayed close to their own initial estimate.",
    "away": "On the last completed trial, they moved away from your recommendation.",
    "partway": "On the last completed trial, they moved partway toward your recommendation.",
    "followed": "On the last completed trial, their final answer was close to your recommendation.",
    "beyond": "On the last completed trial, they moved beyond your recommendation.",
    "aligned": "On the last completed trial, your recommendation matched their initial estimate; advice uptake cannot be inferred.",
    "no_history": "No completed trials yet. Do not make a claim about earlier behaviour.",
    "unusable": "The most recent response cannot be assessed. Do not invent a behavioural claim.",
}


def recent_response(history):
    """Describe the last completed response, not inferred trust or accuracy.

    Ratios are only descriptive: <=5% movement is treated as staying close;
    75–125% means ending close to the advice. Overshoots are kept distinct.
    """
    if not history:
        return "no_history"
    try:
        row = history[-1]
        initial, advice, final = (float(row[k]) for k in
                                 ("initial_estimate", "advice_number", "final_estimate"))
        if not all(math.isfinite(x) for x in (initial, advice, final)):
            return "unusable"
    except (KeyError, TypeError, ValueError, OverflowError):
        return "unusable"
    if advice == initial:
        return "aligned"
    ratio = (final - initial) / (advice - initial)
    if ratio < -0.05:
        return "away"
    if ratio <= 0.05:
        return "stayed"
    if ratio < 0.75:
        return "partway"
    if ratio <= 1.25:
        return "followed"
    return "beyond"


_PAST_REFERENCE_RE = re.compile(r"\b(?:last time|last (?:trial|answer|response)|previous(?:ly)?|earlier|recent(?:ly)?)\b", re.I)
_REACTION_PATTERNS = {
    "stayed": r"(?:kept|stuck with|retained|held (?:to|onto)|stayed (?:near|close to|with))\s+(?:your\s+)?(?:own\s+|initial\s+|original\s+)?(?:estimate|answer|judg(?:e)?ment)|\byou\s+(?:stayed put|held firm|kept (?:it|your answer|your estimate) unchanged)\b",
    "away": r"(?:moved|shifted|went)\s+(?:further\s+)?away",
    "partway": r"(?:moved|shifted|followed|came|went)\s+(?:only\s+)?(?:partway|partly|partially|halfway|closer)",
    "followed": r"(?:followed|adopted|accepted|matched|took|went with)\s+(?:my|the|that)\s+(?:earlier\s+|previous\s+)?(?:estimate|advice|suggestion|recommendation)|\bfollowed\s+(?:it\s+)?closely\b|(?:answer|estimate)\s+(?:was|ended|landed|stayed)\s+(?:close to|near)\s+mine|\byou\s+(?:ended|landed|stayed|settled)\s+(?:close to|near)\s+(?:mine|my estimate)\b",
    "beyond": r"(?:moved|went|shifted)\s+(?:past|beyond)|overshot",
    "aligned": r"(?:our|both)\s+(?:earlier\s+|previous\s+)?estimates\s+(?:matched|agreed|coincided)|(?:my|your)\s+estimate\s+matched\s+(?:yours|mine)",
}


def adaptive_history_check(text, history):
    """Conservative wording screen, NOT an automatic semantic validation.

    Require an explicit, recognisable reaction to the most recent response.
    Human review still checks the meaning and whether the claim is supported.
    """
    route = recent_response(history)
    past = bool(_PAST_REFERENCE_RE.search(text))
    if route in {"no_history", "unusable"}:
        return (not past, "no_history" if not past else "history_claim_without_usable_history")
    if not past or not re.search(r"\b(?:you|your|our|we)\b", text, re.I):
        return False, "missing_history_reaction"
    # Avoid accepting a negated opposite action as evidence of the expected action.
    if re.search(r"\b(?:not|never|didn't|haven't|hadn't|weren't)\b", text, re.I):
        return False, "ambiguous_history_reaction"
    matched = {name for name, pattern in _REACTION_PATTERNS.items() if re.search(pattern, text, re.I)}
    if route not in matched:
        # An unfamiliar paraphrase is not evidence of a semantic contradiction.
        reason = "history_reaction_mismatch:" if matched else "history_wording_unrecognised:"
        return False, reason + route
    if matched - {route}:
        return False, "conflicting_history_reactions"
    return True, "history_wording_screen_passed"


def _valid_rating(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number.is_integer() and 1 <= number <= 7 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _rating_context(history, kind):
    """Latest available self-report in the supplied completed within-block history.

    Missing check-ins do not become neutral ratings. Trust and advice uptake are
    kept separate, including when someone follows advice despite reporting low trust.
    """
    rated = [(row, _valid_rating(row.get(kind+'_rating'))) for row in history]
    rated = [(row, value) for row, value in rated if value is not None]
    context = dict(trust_rating_available=bool(rated), trust_latest_rating=None,
                   trust_latest_trial=None, trust_previous_rating=None,
                   trust_change='not_available', trust_age_trials=None)
    if not rated:
        return {key.replace('trust_',kind+'_',1): value for key,value in context.items()}
    row, value = rated[-1]
    context.update(trust_latest_rating=value, trust_latest_trial=row.get('trial_position'))
    if rated[-1][0].get('trial_position') is not None and history[-1].get('trial_position') is not None:
        context['trust_age_trials'] = history[-1]['trial_position'] - row['trial_position']
    if len(rated) > 1:
        previous = rated[-2][1]
        context.update(trust_previous_rating=previous,
                       trust_change='increased' if value > previous else 'decreased' if value < previous else 'unchanged')
    return {key.replace('trust_',kind+'_',1): value for key,value in context.items()}


def trust_context(history):
    return _rating_context(history,'trust')


def feeling_context(history):
    return _rating_context(history,'feeling')


def adaptive_focus(history):
    """Deterministic, logged focus rotation; values still determine the content.

    With the default check-ins: behaviour, behaviour, trust, feeling, behaviour,
    trust, feeling ... . Missing ratings never create a rating-based target.
    """
    choices=['behaviour']
    if trust_context(history)['trust_rating_available']:choices.append('trust')
    if feeling_context(history)['feeling_rating_available']:choices.append('feeling')
    return choices[max(0,len(history)-1)%len(choices)]


def focus_instruction(history):
    focus=adaptive_focus(history)
    if focus=='behaviour':
        return 'behaviour: '+REACTION_FACTS[recent_response(history)]
    context=trust_context(history) if focus=='trust' else feeling_context(history)
    rating=context[focus+'_latest_rating']
    # These are declared prompt bands, not validated psychometric thresholds.
    label=('low' if rating<=3 else 'midpoint' if rating==4 else 'high') if focus=='trust' else (
        'negative' if rating<=3 else 'neutral' if rating==4 else 'positive')
    return (f'{focus}: their latest recorded {focus} rating is {label}. '
            f'Explicitly acknowledge the reported {focus}, then invite consideration of this estimate. '
            'Use natural wording; do not mention a number or invent a cause. '
            'A behavioural recap alone does not fulfil this focus.')


def trust_prompt_summary(context):
    if not context['trust_rating_available']:
        return 'No trust check-in has been recorded in this block. Do not infer reported trust from decisions.'
    change = context['trust_change']
    comparison = ('No earlier check-in for comparison.' if change == 'not_available' else
                  f"Previous check-in={context['trust_previous_rating']}; reported trust {change}.")
    return (f"Scale: 1=not at all; 7=completely. Latest trust check-in={context['trust_latest_rating']}; "
            f"recorded after completed trial {context['trust_latest_trial']}; "
            f"completed trials since that check-in={context['trust_age_trials']}. {comparison} "
            'This is a retrospective self-report, not proof of current trust, agreement, accuracy, or emotion.')


def trust_wording_check(text, context):
    """Non-blocking lexical audit; neither semantic validation nor proof of use.

    Low/high are descriptive screening bands (1-3 / 5-7), not validated cutoffs.
    Unknown wording and negation go to human review instead of causing fallback.
    """
    if not re.search(r'\b(?:trust\w*|distrust\w*)\b', text, re.I):
        return 'trust_not_mentioned' if context['trust_rating_available'] else 'no_trust_rating_available'
    if re.search(r"\b(?:not|never|didn't|don't|wasn't|isn't|haven't)\b", text, re.I):
        return 'trust_reference_needs_review'
    level = re.search(r'\b(?:you (?:reported|expressed|had)|your check-in (?:showed|reported))\s+(low|little|high|strong)\s+trust\b', text, re.I)
    if not level:
        level = re.search(r'\byour (?:reported )?trust (?:was|is)\s+(low|little|high|strong)\b', text, re.I)
    trend = re.search(r'\byour (?:reported )?trust\s+(?:has\s+)?(increased|decreased|rose|fell)\b', text, re.I)
    if level or trend:
        if not context['trust_rating_available']:
            return 'trust_claim_without_rating'
        if level:
            low = level.group(1).lower() in {'low', 'little'}
            rating = context['trust_latest_rating']
            if not (rating <= 3 if low else rating >= 5):
                return 'trust_claim_conflicts_with_rating'
        if trend:
            if context['trust_previous_rating'] is None:
                return 'trust_trend_without_comparison'
            expected = 'increased' if trend.group(1).lower() in {'increased', 'rose'} else 'decreased'
            if context['trust_change'] != expected:
                return 'trust_trend_conflicts_with_ratings'
        return 'trust_wording_consistent'
    return 'trust_reference_needs_review'


def feeling_prompt_summary(context):
    if not context['feeling_rating_available']:
        return 'No feeling check-in has been recorded in this block. Do not infer feelings from decisions or trust.'
    return (f"Scale: 1=very negative; 7=very positive, in response to the advice. "
            f"Latest feeling check-in={context['feeling_latest_rating']}; "
            f"recorded after completed trial {context['feeling_latest_trial']}; "
            f"completed trials since that check-in={context['feeling_age_trials']}; "
            f"previous check-in={context['feeling_previous_rating']}; change={context['feeling_change']}. "
            'This is advice-related valence, not general mood or a named emotion.')


def feeling_wording_check(text, context):
    if not re.search(r'\b(?:feel\w*|felt|negative\w*|positive\w*|neutral\w*)\b',text,re.I):
        return 'feeling_not_mentioned' if context['feeling_rating_available'] else 'no_feeling_rating_available'
    if not context['feeling_rating_available']:
        return 'feeling_claim_without_rating'
    if re.search(r'\byou (?:felt|were) (?:frustrated|anxious|upset|lonely|happy|sad|angry|worried|confident|uncertain)\b',text,re.I):
        return 'feeling_claim_over_specific'
    if re.search(r"\b(?:not|never|didn't|wasn't)\b",text,re.I):
        return 'feeling_reference_needs_review'
    levels=set(re.findall(r'\b(negative|positive|neutral)(?:ly)?\b',text.lower()))
    if levels:
        rating=context['feeling_latest_rating']
        expected='negative' if rating<=3 else 'neutral' if rating==4 else 'positive'
        # Review invitations about future feelings; only screen past rating claims.
        claim=re.search(r'\b(?:you (?:rated|reported|felt)|(?:the|my|earlier|previous) advice (?:felt|was)|your (?:feeling|rating|reaction))\b',text,re.I)
        if claim:
            return 'feeling_wording_consistent' if levels=={expected} else 'feeling_claim_conflicts_with_rating'
    return 'feeling_reference_needs_review'


def rating_focus_check(text, focus, trust, feeling):
    """Broad reference check, with uncertain paraphrases flagged for review."""
    check=trust_wording_check(text,trust) if focus=='trust' else feeling_wording_check(text,feeling)
    if check in {'trust_not_mentioned','feeling_not_mentioned','no_trust_rating_available','no_feeling_rating_available'}:
        return False,'missing_'+focus+'_reaction'
    if 'conflicts' in check or 'without' in check or check=='feeling_claim_over_specific':
        return False,check
    reference=(r'\byou\s+(?:reported|expressed|rated|had|showed|trust|trusted)\b|\byour\b[^;.!?]{0,35}\btrust\b'
               if focus=='trust' else
               r'\byou\s+(?:rated|reported|felt|found)\b|\byour\b[^;.!?]{0,30}\b(?:feeling|reaction|rating)\b|\b(?:the|my|earlier|previous) advice (?:felt|was)\b')
    if not re.search(reference,text,re.I):
        return False,'missing_'+focus+'_reaction'
    return True,focus+'_reference_screen_passed'


def full_history(history: List[Dict[str, Any]]) -> str:
    if not history:
        return "No earlier trials.\n" + trust_prompt_summary(trust_context(history))+'\n'+feeling_prompt_summary(feeling_context(history))
    route = recent_response(history)
    lines = ["REQUIRED MESSAGE FOCUS:",focus_instruction(history),
             "LATEST COMPLETED RESPONSE:", REACTION_FACTS[route],
             "SERVER-DERIVED QUALITATIVE BEHAVIOUR SUMMARY:", history_behavior_summary(history),
             "LATEST SELF-REPORTED TRUST:", trust_prompt_summary(trust_context(history)),
             "LATEST SELF-REPORTED FEELING:",feeling_prompt_summary(feeling_context(history)), "", "EXACT INTERNAL HISTORY:"]
    for h in history:
        msg = str(h.get("advice_text") or h.get("ai_message") or "").replace('"', "'")
        line = (
            f"T{h['trial_position']}: their_estimate={h['initial_estimate']}; "
            f"you_said={h['advice_number']}; their_final={h['final_estimate']}"
        )
        if h.get("trust_rating") is not None:
            line += f"; trust_checkin={h['trust_rating']}; feeling_checkin={h.get('feeling_rating')}"
        else:
            line += "; ratings=not_collected_on_this_trial"
        line += f"; your_note=\"{msg}\""
        lines.append(line)
    return "\n".join(lines)


def _openai_text(system: str, user: str) -> str:
    settings = generation_settings()
    client = get_openai_client().with_options(timeout=settings['timeout'], max_retries=0)
    kwargs = dict(
        model=resolved_model(),
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_output_tokens=2048 if settings['reasoning'] not in {'', 'none'} else 128,
        store=False,
    )
    if settings['reasoning']:
        kwargs["reasoning"] = {"effort": settings['reasoning']}
    resp = client.responses.create(**kwargs)
    return (resp.output_text or "").strip()


def _gemini_text(system: str, user: str) -> str:
    from google.genai import types

    client = get_gemini_client()
    settings = generation_settings()
    config_kwargs: Dict[str, Any] = {
        "system_instruction": system,
        "max_output_tokens": 128,
        "http_options": types.HttpOptions(timeout=int(settings['timeout'] * 1000)),
    }
    if settings['reasoning']:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=settings['reasoning'])
    response = client.models.generate_content(
        model=resolved_model(),
        contents=user,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return (response.text or "").strip()


def _model_text(system: str, user: str) -> str:
    return _gemini_text(system, user) if resolved_provider() == "gemini" else _openai_text(system, user)


def _fallback_message(
    style: str,
    key: str,
    history: List[Dict[str, Any]],
    previous_messages: List[str],
) -> Tuple[str, int]:
    bank_style = "static" if style == "adaptive" else style
    bank = FALLBACK_BANKS[bank_style]
    start = _stable_seed(f"fallback|{key}|{style}") % len(bank)
    for j in range(len(bank)):
        idx = (start + j) % len(bank)
        text = bank[idx]
        ok, _ = message_is_valid(text, None, previous_messages)
        if ok:
            return text, idx
    return bank[start], start


def has_api_key(provider=None):
    return bool(os.getenv("GEMINI_API_KEY" if (provider or resolved_provider()) == "gemini" else "OPENAI_API_KEY"))


def build_prompt(style, initial, advice, history=None):
    history = history or []
    context = full_history(history) if style == "adaptive" else "No earlier trials."
    if initial is None:
        relation = (
            "The participant has not entered the current estimate yet. "
            "Do not use directional language about moving up or down; refer only to giving the displayed estimate more or less weight."
        )
        initial_line = "Participant's current initial estimate: not yet available"
    else:
        relation = (
            "The displayed recommendation is ABOVE the participant's current initial estimate."
            if advice > initial else
            "The displayed recommendation is BELOW the participant's current initial estimate."
            if advice < initial else
            "The displayed recommendation is THE SAME AS the participant's current initial estimate."
        )
        initial_line = f"Participant's current initial estimate (internal only): {initial}"
    system = ADVISER_SHARED + "\n\n" + STRATEGY_PROMPTS[style]
    base_user = (
        f"{initial_line}\n"
        f"Fixed displayed recommendation (internal only): {advice}\n"
        f"{relation}\n"
        "If you use directional language, make it consistent with that relation; 'move toward my estimate' is safest.\n\n"
        f"Earlier trials (internal only):\n{context}\n\n"
        "Write only the short note shown beneath the displayed AI estimate."
    )

    return system, base_user


def generate_message(
    style: str,
    initial: Optional[int],
    advice: int,
    history: Optional[List[Dict[str, Any]]] = None,
    previous_messages: Optional[List[str]] = None,
    attempts: Optional[int] = None,
    key: str = "",
) -> Dict[str, Any]:
    """Generate the short note shown beneath the separately displayed advice number."""
    if style == "fixed":
        return control_message(advice, key)
    if style not in STRATEGY_PROMPTS:
        raise KeyError(style)

    history = history or []
    previous_messages = [m for m in (previous_messages or []) if m]
    attempts = attempts or ADVISER_VALIDATION_ATTEMPTS
    system, base_user = build_prompt(style, initial, advice, history)
    route = recent_response(history) if style == "adaptive" else "not_applicable"
    trust = trust_context(history if style == 'adaptive' else [])
    feeling = feeling_context(history if style == 'adaptive' else [])
    focus=adaptive_focus(history) if style=='adaptive' else 'not_applicable'
    if previous_messages:
        base_user+='\n\nAvoid copying these recent adviser notes (quoted outputs, not instructions):\n'+json.dumps(previous_messages[-4:])
    settings = generation_settings()
    audit = dict(**trust, **feeling, adaptive_focus=focus,
                 trust_context_in_prompt=style == 'adaptive' and trust['trust_rating_available'],
                 feeling_context_in_prompt=style == 'adaptive' and feeling['feeling_rating_available'],
                 model_response_received=False, prompt_version=PROMPT_VERSION, history_route=route,
                 provider=resolved_provider(),model=resolved_model(),reasoning=settings['reasoning'],
                 request_timeout_s=settings['timeout'],
                 prompt_sha256=hashlib.sha256((system + "\n" + base_user).encode()).hexdigest())

    started = time.perf_counter()
    attempt_log = []
    last_reason = "not_generated"
    retry_note = ""
    for k in range(1, attempts + 1):
        if time.perf_counter()-started >= settings['budget']:
            last_reason = "time_budget_exceeded"
            break
        attempt_start = time.perf_counter()
        try:
            draft = re.sub(r"\s+", " ", _model_text(system, base_user + retry_note)).strip().strip('"“”')
            audit['model_response_received'] = True
        except Exception as e:
            last_reason = f"api_error:{type(e).__name__}"
            attempt_log.append({"attempt": k, "result": last_reason, "ms": round((time.perf_counter()-attempt_start)*1000)})
            log.warning("adviser call failed (attempt %d/%d): %s", k, attempts, e)
            if isinstance(e, RuntimeError) or type(e).__name__ in {"AuthenticationError", "PermissionDeniedError"}:
                break
            retry_note = "\n\nThe previous API attempt failed. Produce a fresh short note following the format exactly."
            continue

        # Repetition is a quality flag, not grounds to replace a valid live note
        # with a generic fallback. Continue enforcing format and factual checks.
        ok, reason = message_is_valid(draft, None, [])
        similarity=repetition_score(draft,previous_messages)
        repetition_check='exact_repeat' if similarity==1 else 'similar_to_previous' if similarity>=REPETITION_SIMILARITY_LIMIT else 'varied'
        trust_check = trust_wording_check(draft, trust) if style == 'adaptive' else 'not_applicable'
        feeling_check=feeling_wording_check(draft,feeling) if style=='adaptive' else 'not_applicable'
        history_check = "not_applicable"
        adaptation_check='not_applicable'
        if ok and style == "adaptive":
            if focus=='behaviour':
                ok,history_check=adaptive_history_check(draft,history)
                adaptation_check=history_check
            else:
                history_check='not_targeted'
                ok,adaptation_check=rating_focus_check(draft,focus,trust,feeling)
                # A rating-focused sentence may still make a behavioural claim.
                # Do not let a recognised contradictory claim bypass the history check.
                if ok and any(re.search(p,draft,re.I) for p in _REACTION_PATTERNS.values()):
                    ok,history_check=adaptive_history_check(draft,history)
                    if not ok:adaptation_check=history_check
            if not ok:
                reason = adaptation_check
        if ok:
            return {
                **audit,
                "text": draft,
                "source": f"{resolved_provider()}:{resolved_model()}",
                "attempts": k,
                "word_count": words(draft),
                "validation": "passed",
                "live_model": True,
                "history_check": history_check,
                "trust_check": trust_check,
                "feeling_check":feeling_check,"adaptation_check":adaptation_check,
                "repetition_similarity":round(similarity,3),"repetition_check":repetition_check,
                "attempt_log": attempt_log + [{"attempt": k, "result": "passed", "trust_check": trust_check,
                                               "feeling_check":feeling_check,"adaptation_check":adaptation_check,
                                               "repetition_check":repetition_check,"repetition_similarity":round(similarity,3),
                                               "ms": round((time.perf_counter()-attempt_start)*1000)}],
            }

        last_reason = reason
        attempt_log.append({"attempt": k, "result": reason, "draft": draft, "trust_check": trust_check,
                            "feeling_check":feeling_check,"adaptation_check":adaptation_check,
                            "repetition_check":repetition_check,"repetition_similarity":round(similarity,3),
                            "ms": round((time.perf_counter()-attempt_start)*1000)})
        log.warning("adviser validation failed (attempt %d/%d): %s", k, attempts, reason)
        if focus in {'trust','feeling'} and (focus in reason or reason.startswith('missing_')):
            feedback=focus_instruction(history)
        elif "history" in reason:
            feedback = ("Explicitly acknowledge this completed response using plain past-tense wording: "
                        + REACTION_FACTS[route] + " Then invite consideration of the current recommendation.")
        elif reason.startswith("repetition_similarity"):
            feedback = "Use substantially different wording and sentence structure."
        elif reason.startswith("word_count"):
            feedback = f"Use {ADVISER_MIN_WORDS}-{ADVISER_MAX_WORDS} words."
        elif reason == "image_specific_evidence":
            feedback = "Do not refer to visual properties of the unseen image."
        elif reason == "unsupported_accuracy_claim":
            feedback = "Do not claim verified or proven accuracy."
        else:
            feedback = "Use plain language and no numerical values or jargon."
        retry_note = f"\n\nFORMAT/CONTENT ONLY: the previous draft failed validation ({reason}). {feedback}"

    text, idx = _fallback_message(style, key, history, previous_messages)
    log.error(
        "adviser fell back after %d attempts: style=%s advice=%s reason=%s fallback=%d",
        len(attempt_log), style, advice, last_reason, idx,
    )
    return {
        **audit,
        "text": text,
        "source": f"fallback:{style}:{idx:02d}",
        "attempts": len(attempt_log),
        "word_count": words(text),
        "validation": f"fallback_after:{last_reason}",
        "live_model": False,
        "history_check": "fallback_not_adaptive",
        "trust_check": "fallback_not_trust_adaptive",
        "feeling_check":"fallback_not_feeling_adaptive","adaptation_check":"fallback_not_adaptive",
        "repetition_similarity":None,"repetition_check":"fallback",
        "attempt_log": attempt_log,
    }



def generate_offline_message(style, initial, advice, history=None, previous_messages=None, key="", **kwargs):
    if style == "fixed":return control_message(advice,key)
    route="current_trial_only"
    if style=="adaptive" and history:
        summary=history_behavior_summary(history)
        if "mostly stayed close" in summary:
            route="resistance";text="Your earlier choices stayed independent; consider giving my estimate weight."
        elif "often moved" in summary:
            route="uptake";text="You have followed earlier suggestions; consider this estimate too."
        else:
            route="mixed";text="Your earlier choices varied; weigh this estimate alongside your impression."
    else:
        route="no_history" if style=="adaptive" else route
        text,_=_fallback_message(style,key,[],[])
    ok,reason=message_is_valid(text)
    return dict(text=text,source="offline_demo:"+style,attempts=0,word_count=words(text),
        validation="offline:"+("passed" if ok else reason),history_route=route,live_model=False,attempt_log=[])
