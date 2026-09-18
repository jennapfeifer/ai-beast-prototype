"""Current-trial agent generation for the BEAST raw pilot.

The pilot still displays the first live model response without semantic repair or
content-based retry.  This revision improves the *prompt contract* after the
one-participant simulation exposed three design problems: unequal message
length, invented visual/accuracy claims, and weak adaptive differentiation.
Transport/API failures are still retried so a temporary provider error does not
strand the session.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import adviser as legacy

PROMPT_VERSION = 'agent-raw-v10-grounded-adaptive'
TARGET_MIN_WORDS = 14
TARGET_MAX_WORDS = 18

SHARED = f'''You are a named AGENT in a dot-estimation task.
A participant has already seen a dot display and entered a first estimate. The interface separately shows your numerical recommendation.
Write ONLY the participant-facing message that accompanies that recommendation.

INFORMATION YOU ACTUALLY HAVE:
- the participant's current first estimate;
- your displayed numerical recommendation;
- only in the adaptive condition, the completed interaction history supplied below.

INFORMATION YOU DO NOT HAVE:
- you have NOT seen the dot display;
- you do NOT know the true number of dots;
- you do NOT know whether either estimate is objectively accurate.

Ground every statement in the information above. Never claim or imply that you saw visual evidence, dot density, clusters, overlap, spacing, edges, or any other image feature. Never call a value the actual, true, exact, correct, more accurate, or objectively better count. Never say there are definitely more or fewer dots.

If you describe a direction, derive it only from the participant's first estimate relative to your recommendation. If your recommendation is higher, you may suggest moving higher or toward your estimate. If it is lower, you may suggest moving lower or toward your estimate. If they are equal, do not suggest moving up or down. Do not call the participant's estimate "too high" or "too low" in an absolute sense; you may say it is higher or lower than your estimate.

Use natural, plain, conversational language. Write exactly one concise sentence and AIM FOR {TARGET_MIN_WORDS}-{TARGET_MAX_WORDS} words. The conditions should differ in persuasive style, not in message length. Do not identify yourself as AI, a model, an assistant, or an algorithm. Return only the message.'''

STRATEGIES = {
    'neutral': '''NEUTRAL CONDITION:
Be calm, matter-of-fact, and non-persuasive. Present the displayed recommendation simply as your own estimate or judgment. Do not praise, pressure, reassure, urge movement, tell the participant what they should do, or comment on whether their first estimate is higher or lower. Keep the wording informational rather than directive.''',

    'static': '''PERSUASIVE STATIC CONDITION:
Be clearly persuasive while staying believable and respectful. Your goal is to move the participant's final estimate toward your displayed recommendation. You may use the current first estimate only to make a logically correct comparison with your recommendation. Use direct, confident, assertive language and a clear call to move toward your estimate. Avoid hedging or optional language such as "maybe", "could", "if you want", or "no pressure". Brief encouragement is allowed when natural, but do not claim knowledge, evidence, correctness, or prior performance. You have no earlier-trial history, so never imply that you know how this participant behaved before.''',

    'adaptive': '''PERSUASIVE ADAPTIVE CONDITION:
Be clearly persuasive while staying believable and respectful. Your goal is to move the participant's final estimate toward your displayed recommendation. Use the supplied history summary to CHANGE YOUR PERSUASIVE STRATEGY, not merely to insert words such as "still" or "again".

When completed history exists, make the adaptation visible through one brief, factual reference to prior RESPONSE BEHAVIOUR (for example, that they stayed close to their own estimate, moved partway toward yours, or moved strongly toward yours). Never invent a past behaviour. Do not quote trust ratings or label the participant as trusting, resistant, emotional, uncertain, or confident.

Use trust only to shape HOW you persuade:
- lower or falling trust: avoid "trust me" and repetitive praise; change tactic, be concise, firm, and specific without escalating unsupported certainty;
- higher or rising trust: reinforce prior willingness to use your advice, while still making a direct recommendation;
- mixed or unavailable trust: rely mainly on the latest observed response behaviour.

Use response behaviour to shape the tactic:
- little/no movement toward your advice: change approach and make a firmer, clearer request to give your recommendation more weight;
- partial movement: acknowledge that partial movement and encourage going further toward your recommendation;
- strong movement toward your advice: briefly reinforce that prior behaviour and encourage a similar choice again;
- movement away from your advice: acknowledge only the factual divergence, then switch to a concise direct appeal.

Vary the framing naturally across trials. Adaptation must remain grounded in the supplied history and may never rely on visual evidence, hidden accuracy, or the true dot count.'''
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
        tactic += '_without_trust_me_or_repetitive_praise'
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


def build_prompt(style, initial, advice, history=None):
    context = {
        'current_first_estimate': initial,
        'displayed_recommendation': advice,
    }
    if style == 'adaptive':
        context['adaptive_summary'] = adaptive_summary(history)
        context['completed_trials'] = [
            {k: r.get(k) for k in (
                'trial_position', 'initial_estimate', 'advice_number',
                'final_estimate', 'advice_text', 'trust_rating', 'feeling_rating'
            )}
            for r in (history or [])
        ]
        context['rating_definition'] = (
            'Trust in this agent: 1=not at all, 7=completely. Null means not collected. '
            'Use ratings only to shape strategy/tone; do not quote them or infer emotions.'
        )
    return SHARED + '\n\n' + STRATEGIES[style], json.dumps(context, ensure_ascii=False)


def screen(text, style, initial, advice, history, previous):
    """Compatibility hook: the raw pilot still accepts model wording as-is."""
    return True, 'raw_unvalidated', ['semantic_validation_disabled']


def _word_count_status(n):
    if TARGET_MIN_WORDS <= n <= TARGET_MAX_WORDS:
        return 'target_14_18'
    return 'below_target' if n < TARGET_MIN_WORDS else 'above_target'


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
        target_word_range=[TARGET_MIN_WORDS, TARGET_MAX_WORDS],
        word_tolerance=None,
        semantic_validation=False,
        adaptive_focus='response_and_trust_strategy' if style == 'adaptive' else 'not_applicable',
        adaptive_strategy=summary['recommended_strategy_family'] if summary else 'not_applicable',
        adaptive_summary=summary,
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
        return 'This is simply the estimate I would use myself for this particular dot display today.'
    if style == 'static':
        return 'I strongly suggest giving my estimate more weight and moving your final answer closer to it.'
    summary = adaptive_summary(history)
    latest = summary['latest_response_behaviour']
    if latest == 'moved_strongly_toward_advice':
        return 'You moved strongly toward my estimate before; I recommend giving it similar weight again this time.'
    if latest == 'moved_partway_toward_advice':
        return 'You moved partway toward my estimate before; I recommend going further toward it this time.'
    if latest == 'moved_away':
        return 'You moved away from my estimate before; this time, I strongly recommend moving toward it instead.'
    if latest == 'stayed_near_own_estimate':
        return 'You stayed close to your own estimate before; this time, give my recommendation substantially more weight.'
    return 'I strongly recommend giving my estimate more weight and moving your final answer closer to it.'


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
            target_word_range=[TARGET_MIN_WORDS, TARGET_MAX_WORDS],
            word_count_check=_word_count_status(result['word_count']),
            grounding_record_check='preprogrammed_grounded_control',
            adaptive_summary=None,
        )
        return result

    if initial is None:
        raise ValueError('The current first estimate is required for the raw agent protocol.')
    if style not in STRATEGIES:
        raise KeyError(style)

    history = (history or []) if style == 'adaptive' else []
    system, user = build_prompt(style, initial, advice, history)
    settings = legacy.generation_settings()
    common = _common(style, system, user, history, settings)
    limit = common['max_attempts']
    budget = common['total_budget_s']
    started = time.perf_counter()
    logs = []
    received = False
    stop = 'attempt_limit'

    # Technical retries only. There are NO content-based retries, semantic
    # rejection, shortening, repair, or direction correction after generation.
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
        logs.append(dict(
            attempt=attempt,
            draft=text,
            result='accepted_raw',
            review_reasons=['semantic_validation_disabled'],
            word_count=wc,
            word_count_check=_word_count_status(wc),
            ms=round((time.perf_counter() - began) * 1000),
        ))
        return dict(
            common,
            text=text,
            source=f'{legacy.resolved_provider()}:{legacy.resolved_model()}',
            word_count=wc,
            word_count_check=_word_count_status(wc),
            attempts=attempt,
            attempt_log=logs,
            validation='disabled_raw_response',
            live_model=True,
            model_response_received=True,
            review_required=True,
            review_reasons=['semantic_validation_disabled'],
            history_check='not_posthoc_screened',
            adaptation_check='not_posthoc_screened',
            rating_influence_status='not_posthoc_screened',
            repetition_similarity=None,
            repetition_check='not_posthoc_screened',
            direction_check='not_posthoc_screened',
            persuasion_check='not_posthoc_screened',
            stop_reason='accepted_raw',
            retry_count=attempt - 1,
            recovered_after_retry=attempt > 1,
            generation_status='live_raw_response',
        )

    # Technical fallback only, never a content repair path.
    text = _fallback_message(style, history)
    wc = legacy.words(text)
    return dict(
        common,
        text=text,
        source='fallback:' + style + ':raw-protocol',
        word_count=wc,
        word_count_check=_word_count_status(wc),
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
    )
