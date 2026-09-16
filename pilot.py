"""Descriptive pilot diagnostics; no model-effectiveness claims."""
from collections import defaultdict
from statistics import mean,median
import datetime as dt

def quantile(values,p):
    values=sorted(v for v in values if isinstance(v,(int,float)))
    if not values:return None
    index=(len(values)-1)*p;lo=int(index);hi=min(lo+1,len(values)-1)
    return round(values[lo]+(values[hi]-values[lo])*(index-lo),1)

def timing_projection(initial_s=4,final_s=7,wait_s=2.5,rating_s=6,break_s=20,instructions_s=90,stimulus_s=5,fixation_s=.6,rating_every=2,collect_ratings=True):
    checks=8*(13//max(1,rating_every)) if collect_ratings else 0
    total=105*(initial_s+final_s+wait_s+stimulus_s+fixation_s)+checks*rating_s+7*break_s+instructions_s
    return dict(minutes=round(total/60,1),assumption_only=True,checkins=checks,formula=f'105 trial cycles + {checks} check-ins + 7 breaks + instructions',
                inputs=dict(initial_s=initial_s,final_s=final_s,wait_s=wait_s,rating_s=rating_s,break_s=break_s,instructions_s=instructions_s,stimulus_s=stimulus_s,fixation_s=fixation_s))

def build_report(records,people):
    grouped=defaultdict(list)
    model_groups=defaultdict(list)
    for row in records:
        if not row.get('practice'):
            grouped[row['condition_id']].append(row)
            model_groups[(row['condition_id'],row.get('provider','unknown'),row.get('model','unknown'),
                          row.get('reasoning','unknown'),row.get('adviser_mode','unknown'),row.get('prompt_version') or 'unknown')].append(row)
    model_conditions=[]
    for (cid,provider,model,reasoning,mode,prompt_version),rows in sorted(model_groups.items()):
        timed=[r for r in rows if r.get('timing_complete')]
        live=[r for r in rows if r.get('live_model')]
        model_conditions.append(dict(condition=cid,provider=provider,model=model,reasoning=reasoning,mode=mode,prompt_version=prompt_version,
            trials=len(rows),live_messages=len(live),fallbacks=sum(bool(r.get('fallback')) for r in rows),
            history_reactions=sum(r.get('history_check')=='history_wording_screen_passed' for r in live),
            trust_reactions=sum(r.get('adaptation_check')=='trust_reference_screen_passed' for r in live),
            feeling_reactions=sum(r.get('adaptation_check')=='feeling_reference_screen_passed' for r in live),
            repeated_notes=sum(r.get('repetition_check') in {'exact_repeat','similar_to_previous'} for r in live),
            generation_p50_ms=quantile([r.get('generation_ms') for r in live],.5),
            generation_p90_ms=quantile([r.get('generation_ms') for r in live],.9),
            wait_p50_ms=quantile([r.get('advice_wait_ms') for r in timed],.5),
            wait_p90_ms=quantile([r.get('advice_wait_ms') for r in timed],.9)))
    conditions=[]
    for cid,rows in sorted(grouped.items()):
        valid=[r for r in rows if r.get('timing_complete')]
        conditions.append(dict(condition=cid,trials=len(rows),timed_trials=len(valid),live_trials=sum(r.get('live_model',False) for r in rows),
            fallback_trials=sum(r.get('fallback',False) for r in rows),
            history_mismatches=sum(r.get('history_rows')!=r.get('expected_history_rows') for r in rows),
            generation_p50_ms=quantile([r.get('generation_ms') for r in rows],.5),
            generation_p90_ms=quantile([r.get('generation_ms') for r in rows],.9),
            wait_p50_ms=quantile([r.get('advice_wait_ms') for r in valid],.5),
            wait_p90_ms=quantile([r.get('advice_wait_ms') for r in valid],.9),
            trial_p50_ms=quantile([r.get('total_wall_ms',0)-r.get('break_ms',0) for r in valid],.5),
            trial_p90_ms=quantile([r.get('total_wall_ms',0)-r.get('break_ms',0) for r in valid],.9),
            late_advice=sum(r.get('advice_wait_ms',0)>r.get('target_wait_ms',2500)+500 for r in valid),
            interrupted=sum(r.get('visibility_interruptions',0)>0 or r.get('resumed',0)>0 for r in rows)))
    sessions=[]
    for p in people:
        rs=[r for r in records if r['pid']==p['pid']]
        start=p.get('started_at');end=p.get('finished_at')
        if isinstance(start,str):start=dt.datetime.fromisoformat(start)
        if isinstance(end,str):end=dt.datetime.fromisoformat(end)
        sessions.append(dict(pid=p['pid'],is_test=str(p.get('notes') or '').startswith('TEST'),completed=bool(end),trials=sum(not r.get('practice') for r in rs),
            wall_minutes=round((end-start).total_seconds()/60,2) if end and start else None,
            instrumented_minutes=round(sum(r.get('total_wall_ms',0) for r in rs)/60000,2),
            break_seconds=round(sum(r.get('break_ms',0) for r in rs)/1000,1),
            hidden_seconds=round(sum(r.get('hidden_ms',0) for r in rs)/1000,1)))
    return dict(conditions=conditions,model_conditions=model_conditions,sessions=sessions,total_trials=sum(not r.get('practice') for r in records),
        complete_sessions=sum(s['completed'] for s in sessions),timed_trials=sum(r.get('timing_complete',False) for r in records),
        live_trials=sum(r.get('live_model',False) for r in records),fallbacks=sum(r.get('fallback',False) for r in records),
        history_mismatches=sum(r.get('history_rows')!=r.get('expected_history_rows') for r in records),
        timing_projection=timing_projection(),limits=['Offline and test sessions are labelled; summaries may include both modes.',
        'A populated history proves data routing, not that the live model used it well.',
        'Compare messages under contrasting histories and conduct human pilots before estimating the condition effect.',
        'The minimum delay is not a guarantee of equal waiting time across conditions.'])
