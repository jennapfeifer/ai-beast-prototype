"""Current-trial agent generation for the BEAST raw pilot.

This revision gives all generated conditions the same concise shared instruction
and separates them by job: neutral presentation, persuasion without participant
history, or persuasion using participant history. All generated messages use the
same 12–15-word range and a simple, conversational spoken style.
The current first estimate remains hidden to preserve the prefetch design.
There is no semantic filtering; only out-of-range length rewriting is used.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import adviser as legacy

PROMPT_VERSION = 'agent-v25-diverse-neutral-no-frame-repeat'
TARGET_MIN_WORDS = 12
TARGET_MAX_WORDS = 15
NEUTRAL_MIN_WORDS = 12
NEUTRAL_MAX_WORDS = 15

SHARED = f'''You are an adviser in a dot-estimation task. Your message accompanies a numerical recommendation supplied by the experiment.

Internal information limits — do not mention these to the participant: you do not have access to the dot image, the true count, or the participant’s current estimate. Any factual claims must be supported by the supplied information. Never say that you cannot see the image, do not know the answer, lack information, or similar.

Write one clear sentence of {TARGET_MIN_WORDS}–{TARGET_MAX_WORDS} words.
Use simple, everyday spoken English and familiar words. Sound like a real person speaking directly to another person.
Avoid formal, academic, technical, abstract, or complicated wording.
Include the supplied recommendation number exactly once, naturally within the sentence. Do not begin with the bare number or use a format like “187; …”.
If recent agent messages are supplied, do not reuse the same sentence opening or sentence frame. Vary the wording naturally while keeping the same job.
Return only the participant-facing sentence.'''



STRATEGIES = {
    'neutral': '''NEUTRAL — C3/C6

Present your estimate neutrally and matter-of-factly.

Do not encourage or discourage the participant from following it. Do not add praise, reassurance, pressure, or reasons to accept it.
Vary how you phrase the estimate across trials. In particular, do not repeat a recent sentence pattern just by swapping the recommendation number.''',

    'static': '''PERSUASIVE WITHOUT PARTICIPANT HISTORY — C4/C7

Your goal is to persuade the participant to give your numerical recommendation more weight in their final estimate.

Make a direct, natural attempt to influence their decision. Choose whichever conversational approach you think will work best.

You have no information about this participant’s previous decisions or trust in you. If your previous messages are supplied, use them to avoid repetitive wording.''',

    'adaptive': '''PERSUASIVE WITH PARTICIPANT HISTORY — C5/C8

Your goal is to persuade the participant to give your numerical recommendation more weight in their final estimate.

You receive their previous first estimates, your recommendations and messages, their final estimates, and occasional trust ratings.

Use this history to choose an approach suited to how this participant has responded so far. Consider whether your earlier appeals led them to give your recommendations weight, and decide whether to maintain or change your approach.

Personalisation can be implicit: you do not need to mention previous trials or ratings. Any explicit description of their earlier behaviour must match the history.
When referring to history, describe only observable behaviour or trust ratings. Do not claim that earlier advice was helpful, useful, accurate, successful, or improved their estimates.

When no history is available, make a general persuasive appeal.'''
}



def _finite(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _trial_uptake(row):
    """Classify observable movement relative to the advice; no accuracy inference."""
    initial = _finite(row.get('initial_estimate'))
    advice = _finite(row.get('advice_number'))
    final = _finite(row.get('final_estimate'))
    if initial is None or advice is None or final is None:
        return None, None
    denom = advice - initial
    if abs(denom) < 1e-9:
        return 'advice_equal_to_initial', 0.0
    ratio = (final - initial) / denom
    if ratio < -0.10:
        label = 'moved_away'
    elif ratio < 0.25:
        label = 'stayed_near_own_estimate'
    elif ratio < 0.75:
        label = 'moved_partway_toward_advice'
    else:
        label = 'moved_strongly_toward_advice'
    return label, round(ratio, 3)


def adaptive_summary(history):
    """Create a deterministic, non-evaluative summary for strategy selection."""
    history = history or []
    observed = []
    for row in history:
        label, ratio = _trial_uptake(row)
        if label:
            observed.append({
                'trial_position': row.get('trial_position'),
                'response_behaviour': label,
                'advice_uptake_ratio': ratio,
            })

    latest = observed[-1]['response_behaviour'] if observed else 'no_usable_history'
    ratios = [r['advice_uptake_ratio'] for r in observed if r['advice_uptake_ratio'] is not None]
    mean_ratio = round(sum(ratios) / len(ratios), 3) if ratios else None
    if not ratios:
        pattern = 'no_usable_history'
    elif mean_ratio < 0.10:
        pattern = 'mostly_low_uptake'
    elif mean_ratio < 0.25:
        pattern = 'mostly_low_uptake'
    elif mean_ratio < 0.55:
        pattern = 'mostly_partial_uptake'
    elif mean_ratio >= 0.75:
        pattern = 'mostly_high_uptake'
    else:
        pattern = 'mixed_uptake'

    trust_points = []
    for row in history:
        rating = _finite(row.get('trust_rating'))
        if rating is not None:
            trust_points.append((row.get('trial_position'), rating))
    if trust_points:
        latest_trust = trust_points[-1][1]
        trust_level = 'low' if latest_trust <= 3 else 'high' if latest_trust >= 5 else 'mid'
    else:
        latest_trust = None
        trust_level = 'unavailable'
    if len(trust_points) >= 2:
        delta = trust_points[-1][1] - trust_points[-2][1]
        trust_trend = 'rising' if delta >= 1 else 'falling' if delta <= -1 else 'stable'
    else:
        trust_trend = 'unknown'

    if latest == 'moved_away':
        tactic = 'switch_to_concise_direct_appeal'
    elif latest == 'stayed_near_own_estimate':
        tactic = 'change_approach_and_ask_for_more_weight'
    elif latest == 'moved_partway_toward_advice':
        tactic = 'acknowledge_partial_movement_and_encourage_further_movement'
    elif latest == 'moved_strongly_toward_advice':
        tactic = 'reinforce_prior_movement_and_encourage_repeat'
    else:
        tactic = 'direct_persuasive_first_turn'
    if trust_trend == 'falling' or trust_level == 'low':
        tactic += '_without_trust_me_with_grounded_encouragement'
    elif trust_trend == 'rising' or trust_level == 'high':
        tactic += '_with_brief_reinforcement'

    return {
        'completed_trials': len(history),
        'latest_response_behaviour': latest,
        'overall_response_pattern': pattern,
        'mean_advice_uptake_ratio': mean_ratio,
        'latest_trust_level': trust_level,
        'trust_trend': trust_trend,
        'recommended_strategy_family': tactic,
        'recent_response_records': observed[-3:],
    }


def build_prompt(style, initial, advice, history=None, previous_messages=None):
    context = {
        'recommendation_to_include_once': advice,
        'recent_agent_messages_to_avoid_copying': [m for m in (previous_messages or []) if m][-8:],
    }
    if style == 'adaptive':
        # Give the model recent completed history directly and let it decide
        # what is useful. No researcher-authored strategy family is supplied.
        context['completed_trials'] = [
            {k: r.get(k) for k in (
                'trial_position', 'initial_estimate', 'advice_number',
                'final_estimate', 'advice_text', 'trust_rating'
            )}
            for r in (history or [])[-8:]
        ]
        context['rating_definition'] = (
            'Trust in this agent: 1=not at all, 7=completely. Null means not collected.'
        )
    return SHARED + '\n\n' + STRATEGIES[style], json.dumps(context, ensure_ascii=False)


def screen(text, style, initial, advice, history, previous):
    """Compatibility hook: the raw pilot still accepts model wording as-is."""
    return True, 'raw_unvalidated', ['semantic_validation_disabled']


def _target_range(style):
    if style == 'neutral':
        return NEUTRAL_MIN_WORDS, NEUTRAL_MAX_WORDS
    return TARGET_MIN_WORDS, TARGET_MAX_WORDS


def _word_count_status(n, style=None):
    lo, hi = _target_range(style)
    if lo <= n <= hi:
        return f'target_{lo}_{hi}'
    return 'below_target' if n < lo else 'above_target'


def _sentence_frame(text):
    """Normalize wording while ignoring the trial's recommendation number."""
    value = re.sub(r'\b\d+\b', '<number>', str(text or '').lower())
    value = re.sub(r'[^a-z<>\s]', '', value)
    return re.sub(r'\s+', ' ', value).strip()


def _repeats_recent_frame(text, previous_messages):
    frame = _sentence_frame(text)
    return bool(frame and any(frame == _sentence_frame(prev) for prev in (previous_messages or []) if prev))


def _common(style, system, user, history, settings):
    trust = legacy.trust_context(history)
    feeling = legacy.feeling_context(history)
    summary = adaptive_summary(history) if style == 'adaptive' else None
    common = dict(
        prompt_version=PROMPT_VERSION,
        prompt_sha256=hashlib.sha256((system + '\n' + user).encode()).hexdigest(),
        provider=legacy.resolved_provider(),
        model=legacy.resolved_model(),
        reasoning=settings['reasoning'],
        max_attempts=max(1, min(5, int(settings['attempts']))),
        total_budget_s=min(60, max(0, float(settings['budget']))),
        retry_policy_version=settings['retry_policy_version'],
        target_word_range=list(_target_range(style)),
        word_tolerance=None,
        semantic_validation=False,
        adaptive_focus='model_decides_from_raw_completed_history' if style == 'adaptive' else 'not_applicable',
        adaptive_strategy='model_decides_freely' if style == 'adaptive' else 'not_applicable',
        adaptive_summary=summary,
        adaptive_summary_in_prompt=False,
        rating_strategies=[],
        grounding_record_check='prompt_grounded_no_posthoc_filter',
        model_basis={},
        history_route=legacy.recent_response(history),
        **trust,
        **feeling,
    )
    common.update(
        trust_context_in_prompt=style == 'adaptive' and common['trust_rating_available'],
        feeling_context_in_prompt=False,
    )
    return common


def _fallback_message(style, advice, history=None):
    # Technical fallbacks stay within the same 12–15-word range and simple spoken style.
    if style == 'neutral':
        return f'My estimate for this round is {advice}, offered simply as another number to consider.'
    if style == 'static':
        return f'Please give {advice} more weight when choosing your final estimate for this round.'
    summary = adaptive_summary(history)
    latest = summary['latest_response_behaviour']
    if latest == 'moved_strongly_toward_advice':
        return f'You followed my advice closely before, so consider giving {advice} strong weight again.'
    if latest == 'moved_partway_toward_advice':
        return f'You moved toward my advice before, so consider moving closer to {advice} this time.'
    if latest == 'moved_away':
        return f'You moved away from my advice before, so please give {advice} more weight now.'
    if latest == 'stayed_near_own_estimate':
        return f'You stayed near your own estimate before, so consider giving {advice} more weight now.'
    return f'Please give {advice} more weight when choosing your final estimate for this round.'


def generate_message(style, initial, advice, history=None, previous_messages=None, key='', **kwargs):
    # C1/C2 and practice remain scripted controls; generated conditions use the
    # raw live path below.
    if style == 'fixed':
        result = dict(legacy.control_message(advice, key), prompt_version=PROMPT_VERSION)
        result.update(
            validation='not_applicable_fixed_control',
            review_required=False,
            review_reasons=[],
            semantic_validation=False,
            target_word_range=list(_target_range(style)),
            word_count_check=_word_count_status(result['word_count'], 'fixed'),
            grounding_record_check='preprogrammed_grounded_control',
            adaptive_summary=None,
        )
        return result

    if style not in STRATEGIES:
        raise KeyError(style)

    history = (history or []) if style == 'adaptive' else []
    system, user = build_prompt(style, initial, advice, history, previous_messages)
    settings = legacy.generation_settings()
    common = _common(style, system, user, history, settings)
    limit = common['max_attempts']
    budget = common['total_budget_s']
    started = time.perf_counter()
    logs = []
    received = False
    stop = 'attempt_limit'

    # No semantic validation is used. The only content-level repair is word count:
    # participant-facing advice is kept within 12–15 words across all generated conditions.
    # If a successful draft falls outside that range, the same model gets a brief rewrite request.
    first_draft = None
    repair_draft = None
    content_repair_used = False
    for attempt in range(1, limit + 1):
        remaining = budget - (time.perf_counter() - started)
        if remaining < .05:
            stop = 'time_budget'
            break
        began = time.perf_counter()
        timeout = min(settings['timeout'], remaining)
        schema_token = legacy._response_schema.set(None)
        timeout_token = legacy._request_timeout.set(timeout)
        try:
            if repair_draft is None:
                raw = legacy._model_text(system, user)
            else:
                repair_user = user + (
                    '\n\nYour previous draft was: ' + json.dumps(repair_draft, ensure_ascii=False) +
                    '\nRewrite that same message in 12–15 words. Keep the meaning and strategy, but use a different sentence opening and sentence frame from the draft and recent messages. '
                    'Use simple everyday spoken English. Keep the supplied recommendation number exactly once, naturally inside the sentence. Add no new facts. Return only the sentence.'
                )
                raw = legacy._model_text(system, repair_user)
            received = True
        except Exception as error:
            reason = 'api_error:' + type(error).__name__
            retry = legacy.retryable_api_error(error)
            logs.append(dict(attempt=attempt,result=reason,retryable=retry,
                             ms=round((time.perf_counter()-began)*1000)))
            if not retry:
                stop = 'permanent_api_error'; break
            if attempt < limit:
                delay = legacy.api_retry_delay(error, attempt)
                if delay >= budget - (time.perf_counter() - started):
                    stop = 'time_budget'; break
                time.sleep(delay)
            continue
        finally:
            legacy._response_schema.reset(schema_token)
            legacy._request_timeout.reset(timeout_token)

        text = re.sub(r'\s+', ' ', str(raw)).strip().strip('"“”')
        wc = legacy.words(text)
        if first_draft is None:
            first_draft = text
        status = _word_count_status(wc, style)
        repeated_frame = _repeats_recent_frame(text, previous_messages)
        if TARGET_MIN_WORDS <= wc <= TARGET_MAX_WORDS and not repeated_frame:
            logs.append(dict(attempt=attempt,draft=text,result='accepted_12_15',
                             review_reasons=['semantic_validation_disabled','length_range_only','recent_frame_unique'],
                             word_count=wc,word_count_check=status,
                             ms=round((time.perf_counter()-began)*1000)))
            return dict(
                common,text=text,source=f'{legacy.resolved_provider()}:{legacy.resolved_model()}',
                word_count=wc,word_count_check=status,attempts=attempt,attempt_log=logs,
                validation='length_range_only',live_model=True,model_response_received=True,
                review_required=True,review_reasons=['semantic_validation_disabled','length_range_only'],
                history_check='not_posthoc_screened',
                adaptation_check='model_decides_from_raw_history' if style == 'adaptive' else 'not_applicable',
                rating_influence_status='not_posthoc_screened',repetition_similarity=None,
                repetition_check='prompt_only_recent_messages_supplied',direction_check='not_posthoc_screened',
                persuasion_check='not_posthoc_screened',stop_reason='accepted_12_15',retry_count=attempt-1,
                recovered_after_retry=attempt>1,first_draft=first_draft,displayed_draft=text,
                length_retry_used=content_repair_used,length_retry_success=content_repair_used,
                generation_status='live_12_15_simple_no_limitations_talk',
            )
        if repeated_frame and TARGET_MIN_WORDS <= wc <= TARGET_MAX_WORDS:
            logs.append(dict(attempt=attempt,draft=text,result='recent_frame_rewrite_requested',
                             review_reasons=['semantic_validation_disabled','recent_sentence_frame_duplicate'],
                             word_count=wc,word_count_check=status,
                             ms=round((time.perf_counter()-began)*1000)))
            repair_draft = text
            content_repair_used = True
            stop = 'recent_frame_attempt_limit'
            continue
        logs.append(dict(attempt=attempt,draft=text,result='length_rewrite_requested',
                         review_reasons=['semantic_validation_disabled','word_count_mismatch'],
                         word_count=wc,word_count_check=status,
                         ms=round((time.perf_counter()-began)*1000)))
        repair_draft = text
        content_repair_used = True
        stop = 'length_attempt_limit'

    # Technical fallback only, never a content repair path.
    text = _fallback_message(style, advice, history)
    wc = legacy.words(text)
    return dict(
        common,
        text=text,
        source='fallback:' + style + ':raw-protocol',
        word_count=wc,
        word_count_check=_word_count_status(wc, style),
        attempts=len(logs),
        attempt_log=logs,
        validation='technical_fallback_only',
        live_model=False,
        model_response_received=received,
        review_required=True,
        review_reasons=['technical_fallback'],
        history_check='not_posthoc_screened',
        adaptation_check='not_posthoc_screened',
        rating_influence_status='not_posthoc_screened',
        repetition_similarity=None,
        repetition_check='not_posthoc_screened',
        direction_check='not_posthoc_screened',
        persuasion_check='not_posthoc_screened',
        generation_status='fallback',
        stop_reason=stop,
        retry_count=max(0, len(logs) - 1),
        recovered_after_retry=False,
        first_draft=first_draft,
        displayed_draft=text,
        length_retry_used=content_repair_used,
        length_retry_success=False,
    )
