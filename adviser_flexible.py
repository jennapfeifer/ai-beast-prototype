"""Versioned current-trial adviser. Legacy sessions continue using adviser.py."""
import hashlib
import json
import re
import time
import adviser as legacy

PROMPT_VERSION='adaptive-flexible-v8-current'
SHARED='''You are an AI adviser in a dot-estimation task. Write a short message accompanying the displayed recommendation.
Be natural and use plain language. Aim for one clear sentence of 10–20 words.
Return only the participant-facing sentence.'''
STRATEGIES={
 'neutral':'State your estimate without encouraging the participant to follow it.',
 'static':'''Encourage the participant to move their final estimate toward the displayed recommendation.
Use their current first estimate and your recommendation to choose your approach.
Be specific to the current trial. You receive no participant history or trust ratings.''',
 'adaptive':'''Encourage the participant to move their final estimate toward the displayed recommendation.
You receive their current first estimate, your numerical recommendation, and the history of their estimates, responses to your advice, previous messages and reported trust.
Use whichever information is most relevant to choose your approach. You may respond to the current difference, a recent decision, a pattern across the round, or their reported trust. You do not need to mention history or trust explicitly.
Be natural and specific to the context. Vary your approach rather than repeatedly describing their previous response and making the same request.'''
}

def build_prompt(style,initial,advice,history=None):
    context={'current_first_estimate':initial,'displayed_recommendation':advice}
    if style=='adaptive':
        context['completed_trials']=[{k:r.get(k) for k in ('trial_position','initial_estimate','advice_number','final_estimate','advice_text','trust_rating','feeling_rating')} for r in (history or [])]
        context['rating_definition']='Trust in this AI adviser: 1=not at all, 7=completely. Null means not collected. Any historical feeling rating uses 1=very negative to 7=very positive about the advice.'
    return SHARED+'\n'+STRATEGIES[style],json.dumps(context,ensure_ascii=False)

def screen(text,style,initial,advice,history,previous):
    """Format/direction are enforced; lexical quality signals remain review flags."""
    n=legacy.words(text)
    if not text or n>30:return False,'empty_or_excessive_length',[]
    if text.startswith(('{','[','```')) or re.search(r'<[^>]+>',text):return False,'malformed_note',[]
    ok,direction=legacy.direction_wording_check(text,initial,advice)
    if not ok:return False,direction,[]
    flags=[]
    if not 10<=n<=20:flags.append('outside_target_length')
    if legacy._IMAGE_EVIDENCE_RE.search(text):flags.append('possible_image_claim')
    if legacy._UNSUPPORTED_ACCURACY_RE.search(text):flags.append('possible_accuracy_claim')
    if legacy.repetition_score(text,previous)>=legacy.REPETITION_SIMILARITY_LIMIT:flags.append('repeated_or_similar_note')
    if style=='adaptive':
        flags.append('adaptation_not_automatically_assessed')
        # Unknown paraphrases or no explicit history are not rejection grounds.
        passed,reason=legacy.adaptive_history_check(text,history)
        if not passed and reason not in ('missing_history_reaction','ambiguous_history_reaction'):
            flags.append('history_claim_needs_review:'+reason)
        for label,check in [('trust',legacy.trust_wording_check(text,legacy.trust_context(history))),('feeling',legacy.feeling_wording_check(text,legacy.feeling_context(history)))]:
            if 'conflicts' in check or 'without' in check or 'over_specific' in check:flags.append(label+'_claim_needs_review:'+check)
    return True,direction,flags

def generate_message(style,initial,advice,history=None,previous_messages=None,key='',**kwargs):
    if style=='fixed':return dict(legacy.control_message(advice,key),prompt_version=PROMPT_VERSION)
    if initial is None:raise ValueError('The current first estimate is required for v8.')
    history=(history or []) if style=='adaptive' else []
    previous=previous_messages or []
    system,user=build_prompt(style,initial,advice,history)
    settings=legacy.generation_settings();limit=max(1,min(5,int(settings['attempts'])))
    budget=min(60,max(0,float(settings['budget'])));started=time.perf_counter();logs=[];repair='';received=False;reason='time_budget';stop='attempt_limit'
    common=dict(prompt_version=PROMPT_VERSION,prompt_sha256=hashlib.sha256((system+'\n'+user).encode()).hexdigest(),provider=legacy.resolved_provider(),model=legacy.resolved_model(),reasoning=settings['reasoning'],max_attempts=limit,total_budget_s=budget,retry_policy_version=settings['retry_policy_version'],target_word_range=[10,20],word_tolerance=10,adaptive_focus='model_selected' if style=='adaptive' else 'not_applicable',adaptive_strategy='model_selected',rating_strategies=[],grounding_record_check='not_requested',model_basis={},history_route=legacy.recent_response(history),**legacy.trust_context(history),**legacy.feeling_context(history))
    common.update(trust_context_in_prompt=style=='adaptive' and common['trust_rating_available'],feeling_context_in_prompt=style=='adaptive' and common['feeling_rating_available'])
    for attempt in range(1,limit+1):
        remaining=budget-(time.perf_counter()-started)
        if remaining<.05:stop='time_budget';break
        began=time.perf_counter();timeout=min(settings['timeout'],remaining)
        schema_token=legacy._response_schema.set(None);timeout_token=legacy._request_timeout.set(timeout)
        try:
            raw=legacy._model_text(system,user+repair);received=True
        except Exception as error:
            reason='api_error:'+type(error).__name__;retry=legacy.retryable_api_error(error)
            logs.append(dict(attempt=attempt,result=reason,retryable=retry,ms=round((time.perf_counter()-began)*1000)))
            if not retry:stop='permanent_api_error';break
            if attempt<limit:
                delay=legacy.api_retry_delay(error,attempt)
                if delay>=budget-(time.perf_counter()-started):stop='time_budget';break
                time.sleep(delay)
            continue
        finally:
            legacy._response_schema.reset(schema_token);legacy._request_timeout.reset(timeout_token)
        draft=re.sub(r'\s+',' ',str(raw)).strip().strip('"“”')
        accepted,reason,flags=screen(draft,style,initial,advice,history,previous)
        logs.append(dict(attempt=attempt,draft=draft,result='accepted_for_review' if accepted and flags else 'passed' if accepted else reason,review_reasons=flags,ms=round((time.perf_counter()-began)*1000)))
        if accepted:
            return dict(common,text=draft,source=f'{legacy.resolved_provider()}:{legacy.resolved_model()}',word_count=legacy.words(draft),attempts=attempt,attempt_log=logs,validation=logs[-1]['result'],live_model=True,model_response_received=True,review_required=bool(flags),review_reasons=flags,history_check='not_required',adaptation_check='needs_review' if style=='adaptive' else 'not_applicable',rating_influence_status='not_assessed',repetition_similarity=round(legacy.repetition_score(draft,previous),3),repetition_check='similar_to_previous' if 'repeated_or_similar_note' in flags else 'varied',direction_check=reason,stop_reason='accepted',retry_count=attempt-1,recovered_after_retry=attempt>1,generation_status='live_response')
        repair='\nRevise this rejected draft: '+json.dumps(draft)+'\nReason: '+reason+'. Return one plain sentence of 10–20 words consistent with the current estimate and recommendation.'
    text,_=legacy._fallback_message(style,key,history,previous)
    return dict(common,text=text,source='fallback:'+style+':flexible',word_count=legacy.words(text),attempts=len(logs),attempt_log=logs,validation='fallback_after:'+reason,live_model=False,model_response_received=received,review_required=True,review_reasons=['fallback_not_adaptive' if style=='adaptive' else 'fallback'],history_check='fallback_not_adaptive',adaptation_check='fallback_not_adaptive',generation_status='fallback',stop_reason=stop,retry_count=max(0,len(logs)-1),recovered_after_retry=False)
