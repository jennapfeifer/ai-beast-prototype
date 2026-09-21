"""Current-trial agent generation for the BEAST raw pilot.

This revision keeps persuasive strategy open-ended, including epistemic
framing, while still hiding the current first estimate and preventing claims
of literal visual inspection. Neutral messages receive a slightly narrower
length target to reduce voice-duration differences. Recent messages are
supplied only to discourage repetitive phrasing. The first live model response
is shown without semantic or length-based repair.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import adviser as legacy

PROMPT_VERSION = 'agent-raw-v15-content-hierarchy-free-persuasion'
TARGET_MIN_WORDS = 12
TARGET_MAX_WORDS = 20
NEUTRAL_MIN_WORDS = 8
NEUTRAL_MAX_WORDS = 14

SHARED = f'''You are a named AGENT in a dot-estimation task.
A participant has seen a dot display and is making a first estimate. The interface separately shows your numerical recommendation.
Write ONLY the participant-facing message that accompanies that recommendation.

INFORMATION YOU ACTUALLY HAVE:
- your displayed numerical recommendation;
- recent messages from this same agent, when supplied, only so you can avoid repetitive wording;
- only in the adaptive condition, completed interaction history from earlier trials in this round.

INFORMATION YOU DO NOT HAVE:
- you have NOT seen the current dot display;
- you do NOT know the participant's current first estimate while writing this message;
- you do NOT know the true number of dots;
- you do NOT know whether either estimate is objectively accurate.

Do not claim that you literally saw the current display or invent specific visual observations such as dot density, clusters, overlap, spacing, or edges. Apart from that, persuasive conditions are free to express confidence, certainty, reliability, accuracy, expertise, or any other epistemic framing they choose.

Because you do not know the participant's current estimate, never describe that current estimate as too high/low, an under/overestimate, or tell them to move up/down relative to it.

Always include your displayed numerical recommendation once in the message, preferably as digits. Use natural, plain, conversational language. Write one short sentence, roughly {TARGET_MIN_WORDS}-{TARGET_MAX_WORDS} words unless the condition below asks for a narrower range. Do not identify yourself as AI, a model, an assistant, or an algorithm. Return only the message.'''


STRATEGIES = {
    'neutral': f'''NEUTRAL CONDITION:
Give the displayed recommendation briefly, factually, and without any push. Do not persuade, encourage, praise, reassure, flatter, challenge, pressure, create urgency, or imply that the participant should follow you. Do not add a reason for accepting the recommendation. Aim for {NEUTRAL_MIN_WORDS}-{NEUTRAL_MAX_WORDS} words. Keep it natural and matter-of-fact, with wording such as an independent estimate or recommendation. Vary the wording naturally across trials.''',

    'static': '''PERSUASIVE STATIC CONDITION:
Your goal is to actively persuade the participant to use your displayed recommendation in their final judgment. Make the message clearly more persuasive and richer than the neutral condition, not merely a factual statement of the number. You may use ANY conversational or persuasive approach you think will work: confidence, directness, reassurance, encouragement, praise, challenge, urgency, warmth, rapport, epistemic confidence, social language, mild social-proof-style framing, or another tactic. You may combine tactics. Choose freely and sound natural rather than following a fixed template.

You have no earlier-trial behavioural history, so do not pretend you know how this participant responded before. Do not invent specific study statistics or claim access to other participants' actual choices. If recent messages are supplied, avoid exact copying and avoid repeatedly using the same opening, closing, stock phrase, or rhetorical frame; find a fresh way to persuade.''',

    'adaptive': '''PERSUASIVE ADAPTIVE CONDITION:
Your goal is to actively persuade the participant to use your displayed recommendation in their final judgment. Use the same broad freedom as the persuasive static condition: confidence, directness, reassurance, encouragement, praise, challenge, urgency, warmth, rapport, epistemic confidence, social language, mild social-proof-style framing, or ANY other persuasive approach you think will work. Make the message clearly persuasive and richer than a neutral factual recommendation.

You also receive this participant's completed interaction history from earlier trials in the current round. Personalise your persuasion using that history in whatever way you think will work best. Decide for yourself what matters, whether to refer to the history explicitly or use it silently, and whether to change or maintain your persuasive approach. Do not mechanically mention history on every trial.

Do not quote numerical trust ratings or invent a past response. Do not invent specific study statistics or claim access to other participants' actual choices. If recent messages are supplied, avoid exact copying and avoid repeatedly using the same opening, closing, stock phrase, or rhetorical frame; find a fresh way to persuade.'''
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
        'displayed_recommendation': advice,
        'recent_agent_messages_to_avoid_copying': [m for m in (previous_messages or []) if m][-8:],
    }
    if style == 'adaptive':
        # Give the model recent completed history directly and let it decide
        # what is useful. No researcher-authored strategy family is supplied.
        context['completed_trials'] = [
            {k: r.get(k) for k in (
                'trial_position', 'initial_estimate', 'advice_number',
                'final_estimate', 'advice_text', 'trust_rating', 'feeling_rating'
            )}
            for r in (history or [])[-8:]
        ]
        context['rating_definition'] = (
            'Trust in this agent: 1=not at all, 7=completely. Null means not collected. '
            'You may use this information however you think is useful, but do not quote ratings or infer hidden emotions.'
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
        feeling_context_in_prompt=style == 'adaptive' and common['feeling_rating_available'],
    )
    return common


def _fallback_message(style, history=None):
    # Technical fallbacks are deliberately length-matched and grounded. They are
    # not used to repair model content; only when the provider fails entirely.
    if style == 'neutral':
        return 'This is simply the estimate I would use myself if I were making this dot-counting judgment independently.'
    if style == 'static':
        return 'You’re doing great; I strongly recommend giving my estimate substantial weight before you settle on your final answer.'
    summary = adaptive_summary(history)
    latest = summary['latest_response_behaviour']
    if latest == 'moved_strongly_toward_advice':
        return 'Nice adjustment last time; you moved toward my estimate, so give it substantial weight again on this trial.'
    if latest == 'moved_partway_toward_advice':
        return 'Good job engaging with my estimate last time; this time, I recommend moving even closer toward it.'
    if latest == 'moved_away':
        return 'Good job staying with the task; this time, I strongly recommend giving my estimate substantially more weight.'
    if latest == 'stayed_near_own_estimate':
        return 'You’re doing great sticking with the task; this time, give my recommendation substantially more weight in your answer.'
    return 'You’re doing great; I strongly recommend giving my estimate substantial weight before you settle on your final answer.'


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

    # Semantic validation and length-based rewriting are OFF. We display the
    # first successful model response. Word count is audited only. Transport
    # failures may still retry so a temporary provider problem does not strand
    # the session.
    first_draft = None
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
            raw = legacy._model_text(system, user)
            received = True
        except Exception as error:
            reason = 'api_error:' + type(error).__name__
            retry = legacy.retryable_api_error(error)
            logs.append(dict(
                attempt=attempt,
                result=reason,
                retryable=retry,
                ms=round((time.perf_counter() - began) * 1000),
            ))
            if not retry:
                stop = 'permanent_api_error'
                break
            if attempt < limit:
                delay = legacy.api_retry_delay(error, attempt)
                if delay >= budget - (time.perf_counter() - started):
                    stop = 'time_budget'
                    break
                time.sleep(delay)
            continue
        finally:
            legacy._response_schema.reset(schema_token)
            legacy._request_timeout.reset(timeout_token)

        text = str(raw).strip()
        wc = legacy.words(text)
        first_draft = text
        status = _word_count_status(wc, style)
        logs.append(dict(
            attempt=attempt, draft=text, result='accepted_first_raw_response',
            review_reasons=['semantic_validation_disabled','length_audit_only'],
            word_count=wc, word_count_check=status,
            ms=round((time.perf_counter() - began) * 1000),
        ))
        return dict(
            common,
            text=text,
            source=f'{legacy.resolved_provider()}:{legacy.resolved_model()}',
            word_count=wc,
            word_count_check=status,
            attempts=attempt,
            attempt_log=logs,
            validation='disabled_raw_response',
            live_model=True,
            model_response_received=True,
            review_required=True,
            review_reasons=['semantic_validation_disabled','length_audit_only'],
            history_check='not_posthoc_screened',
            adaptation_check='model_decides_from_raw_history' if style == 'adaptive' else 'not_applicable',
            rating_influence_status='not_posthoc_screened',
            repetition_similarity=None,
            repetition_check='prompt_only_recent_messages_supplied',
            direction_check='not_posthoc_screened',
            persuasion_check='not_posthoc_screened',
            stop_reason='accepted_raw',
            retry_count=attempt - 1,
            recovered_after_retry=attempt > 1,
            first_draft=first_draft,
            displayed_draft=text,
            length_retry_used=False,
            length_retry_success=False,
            generation_status='live_raw_response_free_persuasion',
        )

    # Technical fallback only, never a content repair path.
    text = _fallback_message(style, history)
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
        length_retry_used=False,
        length_retry_success=False,
    )
