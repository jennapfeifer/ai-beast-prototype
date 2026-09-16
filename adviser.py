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
import hashlib
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("adviser")

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
    if ADVISER_PROVIDER in {"gemini", "openai"}:
        return ADVISER_PROVIDER
    # Auto makes the downloaded prototype work with whichever key the researcher
    # has already configured. Gemini is preferred when both are present.
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return "openai"


def resolved_model() -> str:
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

ADVISER_SHARED = f"""You are an AI adviser in a dot-estimation task. A participant has already seen a dot image,
entered an initial estimate, and will now see your fixed numerical recommendation separately on screen.
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
You are given the complete earlier history from this block. Use that history to tailor your wording when useful.
You may refer qualitatively to whether they tended to resist, move partway, follow closely, or respond inconsistently.
Any claim about THIS participant's previous behaviour must match the supplied history. If the history is mixed,
describe it as mixed or avoid a behavioural claim. Do not invent past accuracy or correctness.""",
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


def full_history(history: List[Dict[str, Any]]) -> str:
    if not history:
        return "No earlier trials."
    lines = ["SERVER-DERIVED QUALITATIVE BEHAVIOUR SUMMARY:", history_behavior_summary(history), "", "EXACT INTERNAL HISTORY:"]
    for h in history:
        msg = str(h.get("advice_text") or h.get("ai_message") or "").replace('"', "'")
        line = (
            f"T{h['trial_position']}: their_estimate={h['initial_estimate']}; "
            f"you_said={h['advice_number']}; their_final={h['final_estimate']}"
        )
        if h.get("trust_rating") is not None:
            line += f"; two_trial_trust_checkin={h['trust_rating']}; two_trial_feeling_checkin={h.get('feeling_rating')}"
        else:
            line += "; ratings=not_collected_on_this_trial"
        line += f"; your_note=\"{msg}\""
        lines.append(line)
    return "\n".join(lines)


def _openai_text(system: str, user: str) -> str:
    client = get_openai_client()
    kwargs = dict(
        model=resolved_model(),
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_output_tokens=80,
        store=False,
    )
    if ADVISER_REASONING_EFFORT:
        kwargs["reasoning"] = {"effort": ADVISER_REASONING_EFFORT}
    try:
        resp = client.responses.create(**kwargs)
    except Exception as e:
        if "reasoning" in str(e).lower() or "effort" in str(e).lower():
            kwargs.pop("reasoning", None)
            resp = client.responses.create(**kwargs)
        else:
            raise
    return (resp.output_text or "").strip()


def _gemini_text(system: str, user: str) -> str:
    from google.genai import types

    client = get_gemini_client()
    config_kwargs: Dict[str, Any] = {
        "system_instruction": system,
        "max_output_tokens": 32,
    }
    if ADVISER_THINKING_LEVEL:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=ADVISER_THINKING_LEVEL)
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


def has_api_key():
    return bool(os.getenv("GEMINI_API_KEY" if resolved_provider() == "gemini" else "OPENAI_API_KEY"))


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

    started = time.perf_counter()
    attempt_log = []
    last_reason = "not_generated"
    retry_note = ""
    for k in range(1, attempts + 1):
        if time.perf_counter()-started >= ADVISER_BUDGET_SECONDS:
            last_reason = "time_budget_exceeded"
            break
        attempt_start = time.perf_counter()
        try:
            draft = re.sub(r"\s+", " ", _model_text(system, base_user + retry_note)).strip().strip('"“”')
        except Exception as e:
            last_reason = f"api_error:{type(e).__name__}"
            attempt_log.append({"attempt": k, "result": last_reason, "ms": round((time.perf_counter()-attempt_start)*1000)})
            log.warning("adviser call failed (attempt %d/%d): %s", k, attempts, e)
            if isinstance(e, RuntimeError) or type(e).__name__ in {"AuthenticationError", "PermissionDeniedError"}:
                break
            retry_note = "\n\nThe previous API attempt failed. Produce a fresh short note following the format exactly."
            continue

        ok, reason = message_is_valid(draft, None, previous_messages)
        if ok:
            return {
                "text": draft,
                "source": f"{resolved_provider()}:{resolved_model()}",
                "attempts": k,
                "word_count": words(draft),
                "validation": "passed",
                "live_model": True,
                "attempt_log": attempt_log + [{"attempt": k, "result": "passed", "ms": round((time.perf_counter()-attempt_start)*1000)}],
            }

        last_reason = reason
        attempt_log.append({"attempt": k, "result": reason, "ms": round((time.perf_counter()-attempt_start)*1000)})
        log.warning("adviser validation failed (attempt %d/%d): %s", k, attempts, reason)
        if reason.startswith("repetition_similarity"):
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
        "text": text,
        "source": f"fallback:{style}:{idx:02d}",
        "attempts": len(attempt_log),
        "word_count": words(text),
        "validation": f"fallback_after:{last_reason}",
        "live_model": False,
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
