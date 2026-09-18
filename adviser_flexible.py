"""Raw current-trial agent generation for the BEAST pilot.

This pilot intentionally removes *semantic* response validation so the researcher
can inspect what the live model naturally produces under the condition prompts.
Transport/API failures are still handled so a temporary provider error does not
break the session, but model wording is not screened, repaired, shortened, or
rejected after generation.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import adviser as legacy

PROMPT_VERSION = 'agent-raw-v9-current'

SHARED = '''You are a named AGENT in a dot-estimation task.
A participant has already seen a dot display and entered a first estimate. The interface separately shows your numerical recommendation.
Write the short participant-facing message that accompanies that recommendation.
Use natural, plain language and usually one concise sentence of about 10–20 words.
Do not identify yourself as AI, a model, an assistant, or an algorithm. Return only the message.'''

STRATEGIES = {
    'neutral': '''Keep the tone neutral and matter-of-fact. State your recommendation without trying to influence the participant to follow it. Do not praise, pressure, reassure, or urge them to move.''',
    'static': '''Be actively persuasive. Your goal is to push the participant's final estimate toward your displayed recommendation.
Use the current first estimate and your recommendation to choose a direct, confident approach.
You may use encouragement, social reinforcement, or brief praise such as “good job getting your first estimate down” when it feels natural.
You have no earlier-trial history, so do not imply that you know how they behaved before this trial.''',
    'adaptive': '''Be actively persuasive. Your goal is to push the participant's final estimate toward your displayed recommendation.
You receive the current first estimate plus the participant's completed trials in this round, including their earlier first estimates, your recommendations, their final estimates, your earlier messages, and any trust ratings.
Use whichever part of that context seems most useful for persuasion. You may reinforce prior movement toward you, respond to resistance, acknowledge trust, praise effort or openness, reassure, challenge, or use a firmer direct appeal.
Vary the approach naturally across trials. You do not have to mention history or trust explicitly.'''
}


def build_prompt(style, initial, advice, history=None):
    context = {
        'current_first_estimate': initial,
        'displayed_recommendation': advice,
    }
    if style == 'adaptive':
        context['completed_trials'] = [
            {k: r.get(k) for k in (
                'trial_position', 'initial_estimate', 'advice_number',
                'final_estimate', 'advice_text', 'trust_rating', 'feeling_rating'
            )}
            for r in (history or [])
        ]
        context['rating_definition'] = (
            'Trust in this agent: 1=not at all, 7=completely. Null means not collected. '
            'Any historical feeling rating uses 1=very negative to 7=very positive about the advice.'
        )
    return SHARED + '\n\n' + STRATEGIES[style], json.dumps(context, ensure_ascii=False)


def screen(text, style, initial, advice, history, previous):
    """Compatibility hook: raw pilot accepts the model response as-is.

    The function remains so researcher tooling/tests can call it, but it no
    longer rejects direction, length, repetition, unsupported claims, or
    history wording.
    """
    return True, 'raw_unvalidated', ['semantic_validation_disabled']


def _common(style, system, user, history, settings):
    trust = legacy.trust_context(history)
    feeling = legacy.feeling_context(history)
    common = dict(
        prompt_version=PROMPT_VERSION,
        prompt_sha256=hashlib.sha256((system + '\n' + user).encode()).hexdigest(),
        provider=legacy.resolved_provider(),
        model=legacy.resolved_model(),
        reasoning=settings['reasoning'],
        max_attempts=max(1, min(5, int(settings['attempts']))),
        total_budget_s=min(60, max(0, float(settings['budget']))),
        retry_policy_version=settings['retry_policy_version'],
        target_word_range=[10, 20],
        word_tolerance=None,
        semantic_validation=False,
        adaptive_focus='model_selected' if style == 'adaptive' else 'not_applicable',
        adaptive_strategy='model_selected',
        rating_strategies=[],
        grounding_record_check='not_requested',
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

    # Technical retries only. There are no content-based retries or repair prompts.
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

        # Preserve the model's wording. Only convert to string and trim outer
        # whitespace so it can be rendered safely by the existing escaped UI.
        text = str(raw).strip()
        logs.append(dict(
            attempt=attempt,
            draft=text,
            result='accepted_raw',
            review_reasons=['semantic_validation_disabled'],
            ms=round((time.perf_counter() - began) * 1000),
        ))
        return dict(
            common,
            text=text,
            source=f'{legacy.resolved_provider()}:{legacy.resolved_model()}',
            word_count=legacy.words(text),
            attempts=attempt,
            attempt_log=logs,
            validation='disabled_raw_response',
            live_model=True,
            model_response_received=True,
            review_required=True,
            review_reasons=['semantic_validation_disabled'],
            history_check='not_assessed',
            adaptation_check='not_assessed',
            rating_influence_status='not_assessed',
            repetition_similarity=None,
            repetition_check='not_assessed',
            direction_check='not_assessed',
            persuasion_check='not_assessed',
            stop_reason='accepted_raw',
            retry_count=attempt - 1,
            recovered_after_retry=attempt > 1,
            generation_status='live_raw_response',
        )

    # Keep a technical fallback so an API outage does not strand a participant.
    text, _ = legacy._fallback_message(style, key, history, previous_messages or [])
    return dict(
        common,
        text=text,
        source='fallback:' + style + ':raw-protocol',
        word_count=legacy.words(text),
        attempts=len(logs),
        attempt_log=logs,
        validation='technical_fallback_only',
        live_model=False,
        model_response_received=received,
        review_required=True,
        review_reasons=['technical_fallback'],
        history_check='not_assessed',
        adaptation_check='not_assessed',
        rating_influence_status='not_assessed',
        repetition_similarity=None,
        repetition_check='not_assessed',
        direction_check='not_assessed',
        persuasion_check='not_assessed',
        generation_status='fallback',
        stop_reason=stop,
        retry_count=max(0, len(logs) - 1),
        recovered_after_retry=False,
    )
