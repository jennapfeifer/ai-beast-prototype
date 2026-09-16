"""Ratings shape the prompt; implicit influence is retained for human review."""
from conftest import provider_reply
from copy import deepcopy
import pytest
import adviser
import store
import verify_adaptation as probe
from conftest import post,start
from pilot import build_report


NOTES={
    'behaviour':'Last time you moved away; please consider my estimate now.',
    'trust':'You moved away earlier; could you give mine another look?',
    'feeling':'You moved away earlier; take another look at my estimate.',
}


def history(n=6,trust=1,feeling=1):
    return [dict(trial_position=i,initial_estimate=100,advice_number=120,final_estimate=90,
                 advice_text=NOTES['behaviour'],trust_rating=trust if i%2==0 else None,
                 feeling_rating=feeling if i%2==0 else None) for i in range(1,n+1)]


def test_focus_gives_both_ratings_a_turn_and_retains_behaviour():
    assert [adviser.adaptive_focus(history(i)) for i in range(7)]==[
        'behaviour','behaviour','trust','feeling','behaviour','trust','feeling']
    assert adviser.adaptive_focus(history(6,trust=None,feeling=None))=='behaviour'


@pytest.mark.parametrize('n,focus',[(2,'trust'),(3,'feeling'),(4,'behaviour'),(6,'feeling')])
def test_focus_is_supplied_and_review_status_saved(n,focus,monkeypatch):
    seen=[]
    def fake(system,user):seen.append(user);return provider_reply(system,user,(NOTES[focus]))
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,208,history(n),attempts=1)
    assert result['live_model'] and result['adaptive_focus']==focus
    assert result['trust_context_in_prompt'] and result['feeling_context_in_prompt']
    assert 'REQUIRED MESSAGE FOCUS:\n'+focus in seen[0]
    assert result['adaptation_check']=='needs_review'
    assert result['review_required']
    assert result['history_check']=='history_wording_screen_passed'
    assert result['grounding_record_check']=='matched_input_record'


def test_user_duplicate_is_not_a_failure_when_it_matches_current_focus(monkeypatch):
    seen=[]
    def fake(system,user):seen.append(user);return provider_reply(system,user,(NOTES['behaviour']))
    monkeypatch.setattr(adviser,'_model_text',fake)
    # Same six completed decisions, no collected ratings: the behaviour focus applies.
    result=adviser.generate_message('adaptive',None,208,history(6,None,None),
                                    previous_messages=[NOTES['behaviour']],attempts=1)
    assert result['live_model'] and result['model_response_received']
    assert result['repetition_check']=='exact_repeat' and result['repetition_similarity']==1
    assert result['attempts']==1
    assert 'Avoid copying these recent adviser notes' in seen[0]


def test_repetition_and_unverified_rating_influence_are_separate_flags(monkeypatch):
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=(NOTES['behaviour'])))
    result=adviser.generate_message('adaptive',None,208,history(6),
                                    previous_messages=[NOTES['behaviour']],attempts=1)
    assert result['live_model'] and result['adaptive_focus']=='feeling'
    assert result['attempt_log'][0]['result']=='accepted_for_review'
    assert 'feeling_influence_not_automatically_assessed' in result['review_reasons']
    assert result['attempt_log'][0]['repetition_check']=='exact_repeat'


@pytest.mark.parametrize('n,rating,note',[
    (2,7,'You reported low trust; weigh this estimate carefully before deciding.'),
    (3,7,'You rated the advice negatively; consider this estimate on merit.'),
])
def test_explicit_opposite_rating_is_rejected(n,rating,note,monkeypatch):
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=(note)))
    result=adviser.generate_message('adaptive',None,208,history(n,rating,rating),attempts=1)
    assert not result['live_model']
    assert 'conflicts_with_rating' in result['attempt_log'][0]['result']


def test_rating_focus_repair_receives_the_actual_rating_fact(monkeypatch):
    seen=[]
    def fake(system,user):seen.append(user);return provider_reply(system,user,('You rated the advice positively; consider this estimate on merit.' if len(seen)==1 else NOTES['feeling']))
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,208,history(),attempts=2)
    assert result['live_model'] and result['attempts']==2
    assert 'internal approach=feeling_negative' in seen[1]


def test_feeling_does_not_inherit_trust_or_treat_missing_as_neutral():
    rows=history(5,trust=7,feeling=1)
    rows[3]['feeling_rating']=None
    context=adviser.feeling_context(rows)
    assert context['feeling_latest_rating']==1 and context['feeling_latest_trial']==2
    assert context['feeling_age_trials']==3 and context['feeling_previous_rating'] is None
    assert not adviser.feeling_context(history(6,trust=7,feeling=None))['feeling_rating_available']


def test_invented_specific_emotion_still_fails(monkeypatch):
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=('You felt anxious earlier; consider giving my estimate some weight.')))
    result=adviser.generate_message('adaptive',None,208,history(3),attempts=1)
    assert not result['live_model']
    assert result['attempt_log'][0]['result']=='feeling_claim_over_specific'


@pytest.mark.parametrize('contrast,field',[('trust','trust_rating'),('feeling','feeling_rating')])
@pytest.mark.parametrize('direction',['UP','DOWN'])
def test_rating_probes_hold_every_other_input_constant(contrast,field,direction):
    low,high=probe.histories(direction,contrast).values()
    assert adviser.adaptive_focus(low)==adviser.adaptive_focus(high)==contrast
    a,b=deepcopy(low),deepcopy(high)
    for row in a+b:row.pop(field)
    assert a==b
    assert adviser.build_prompt('static',None,208,low)==adviser.build_prompt('static',None,208,high)
    assert adviser.build_prompt('adaptive',None,208,low)!=adviser.build_prompt('adaptive',None,208,high)


def test_report_separates_policy_versions_and_counts_rating_reactions():
    base=dict(condition_id='C5',pid='fake',live_model=True,provider='openai',model='sol',reasoning='low',adviser_mode='live')
    rows=[dict(base,prompt_version='v3',history_check='history_wording_screen_passed'),
          dict(base,prompt_version='v4',adaptation_check='trust_reference_screen_passed',repetition_check='exact_repeat'),
          dict(base,prompt_version='v4',adaptation_check='feeling_reference_screen_passed')]
    report=build_report(rows,[])['model_conditions']
    assert len(report)==2
    latest=next(r for r in report if r['prompt_version']=='v4')
    assert latest['trust_reactions']==latest['feeling_reactions']==latest['repeated_notes']==1


def test_live_prefetch_routes_and_exports_both_ratings_across_two_blocks(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','mock-only-never-used')
    calls=[]
    def fake(system,user):
        calls.append(user)
        if 'REQUIRED MESSAGE FOCUS:\ntrust' in user:return provider_reply(system,user,(NOTES['trust']))
        if 'REQUIRED MESSAGE FOCUS:\nfeeling' in user:return provider_reply(system,user,(NOTES['feeling']))
        return provider_reply(system,user,(NOTES['behaviour'] if 'LATEST COMPLETED RESPONSE' in user else 'Consider giving my estimate some weight before deciding.'))
    monkeypatch.setattr(adviser,'_model_text',fake)
    state=start(client,['C5','C8'],trials=4,skip=True,mode='live')
    with client.session_transaction() as sess:pid=sess['pid']
    while not state['done']:
        post(client,'/api/prefetch',json={'trial_token':state['trial_token']})
        advice=post(client,'/api/initial',json={'trial_token':state['trial_token'],'estimate':100}).get_json()
        d=advice['researcher'];position=state['trial_in_block']
        assert d['live_model'],d
        assert d['adaptive_focus']=={1:'behaviour',2:'behaviour',3:'trust',4:'feeling'}[position]
        assert d['feeling_context_in_prompt']==(position>=3)
        assert d['feeling_latest_rating']==(1 if position>=3 else None)
        # Move away in either recommendation direction.
        final=90 if advice['advice_number']>100 else 110
        assert post(client,'/api/final',json=dict(trial_token=state['trial_token'],estimate=final,
                    trust=1 if state['ratings_due'] else None,feeling=1 if state['ratings_due'] else None)).status_code==200
        state=client.get('/api/state').get_json()
    records=store.diagnostic_rows(pid)
    assert len(calls)==len(records)==8
    assert sum(r['adaptive_focus']=='feeling' and r['review_required'] for r in records)==2
    assert all(r['adaptive_strategy'].startswith(r['adaptive_focus']+'_') for r in records)
    exported=client.get('/admin/export/diagnostics.csv').get_data(as_text=True)
    assert 'feeling_latest_rating' in exported and 'adaptive_focus' in exported
    assert 'review_required' in exported and 'adaptive_strategy' in exported
    html=client.get('/researcher').get_data(as_text=True)
    assert 'Live notes to review' in html
