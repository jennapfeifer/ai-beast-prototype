"""Real rejected Sol wording, trust isolation, and saved prefetch diagnostics."""
from conftest import provider_reply
from copy import deepcopy
import csv
import io

import pytest

import adviser
import store
import verify_adaptation as probe
from conftest import finish_trial, post, start
from test_adaptive_grounding import rows


SOL_NOTE = 'Last time you followed closely; please consider this estimate too.'


@pytest.mark.parametrize('initial,advice', [(100,120),(100,80)])
def test_actual_sol_rejection_is_fixed_for_both_directions(monkeypatch,initial,advice):
    history=rows(advice,initial,advice)
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=(SOL_NOTE)))
    with adviser.use_model_profile(adviser.model_profiles()['gpt_stronger']):
        result=adviser.generate_message('adaptive',None,74,history,attempts=1)
    assert result['text']==SOL_NOTE and result['live_model']
    assert result['model_response_received']
    assert result['source']=='openai:gpt-5.6-sol'
    assert result['history_check']=='history_wording_screen_passed'
    assert result['attempts']==1
    assert result['trust_check']=='no_trust_rating_available'


@pytest.mark.parametrize('final', [90,100,110,140])
def test_followed_closely_is_still_rejected_for_wrong_history(final):
    assert not adviser.adaptive_history_check(SOL_NOTE,rows(final))[0]


@pytest.mark.parametrize('note', [
    'Last time you took my advice; consider this estimate too.',
    'Previously you went with my estimate; consider this suggestion too.',
    'Earlier you stayed close to mine; consider this estimate too.',
    'Previously you followed it closely; consider this suggestion too.',
])
def test_common_following_paraphrases(note):
    assert adviser.message_is_valid(note)[0]
    assert adviser.adaptive_history_check(note,rows(120))[0]
    assert not adviser.adaptive_history_check(note,rows(100))[0]


def test_unknown_wording_is_not_mislabeled_a_known_contradiction():
    ok,reason=adviser.adaptive_history_check('Earlier you did something unusual; consider this estimate too.',rows(120))
    assert ok and reason=='history_wording_unrecognised:followed'
    assert not adviser.adaptive_history_check('Last time you never followed closely; consider this estimate too.',rows(120))[0]
    assert not adviser.adaptive_history_check('Previously you followed closely and moved away; consider mine.',rows(120))[0]


@pytest.mark.parametrize('rating', [None,True,0,8,2.5,'bad',float('nan'),float('inf')])
def test_invalid_or_missing_trust_is_not_a_neutral_rating(rating):
    history=rows(120);history[0]['trust_rating']=rating
    context=adviser.trust_context(history)
    assert context['trust_rating_available'] is False
    assert context['trust_latest_rating'] is None
    assert 'No trust check-in' in adviser.trust_prompt_summary(context)


def test_latest_trust_survives_unrated_trial_and_uses_only_real_comparisons():
    history=[dict(rows(120)[0],trial_position=i,trust_rating={2:6,4:2}.get(i)) for i in range(1,6)]
    context=adviser.trust_context(history)
    assert context==dict(trust_rating_available=True,trust_latest_rating=2,trust_latest_trial=4,
                        trust_previous_rating=6,trust_change='decreased',trust_age_trials=1)
    assert adviser.recent_response(history)=='followed'  # Behaviour is not self-reported trust.
    assert adviser.trust_context(history[:3])['trust_change']=='not_available'


@pytest.mark.parametrize('direction', ['UP','DOWN'])
def test_trust_probe_changes_only_trust_and_only_adaptive_prompts(direction):
    scenarios=probe.histories(direction,'trust')
    low,high=scenarios['low_trust'],scenarios['high_trust']
    low_copy,high_copy=deepcopy(low),deepcopy(high)
    for row in low_copy+high_copy:row.pop('trust_rating')
    assert low_copy==high_copy
    for style in ['neutral','static']:
        assert adviser.build_prompt(style,None,74,low)==adviser.build_prompt(style,None,74,high)
    low_prompt=adviser.build_prompt('adaptive',None,74,low)
    high_prompt=adviser.build_prompt('adaptive',None,74,high)
    assert low_prompt!=high_prompt
    assert 'Latest trust check-in=1' in low_prompt[1]
    assert 'Latest trust check-in=7' in high_prompt[1]
    assert '1=not at all; 7=completely' in low_prompt[1]


@pytest.mark.parametrize('rating,note,expected', [
    (1,'You reported low trust; consider this estimate.','trust_wording_consistent'),
    (7,'Your reported trust was high; consider this estimate.','trust_wording_consistent'),
    (1,'Your trust was high; consider this estimate.','trust_claim_conflicts_with_rating'),
    (7,'You reported low trust; consider this estimate.','trust_claim_conflicts_with_rating'),
    (4,'You reported high trust; consider this estimate.','trust_claim_conflicts_with_rating'),
    (None,'You reported high trust; consider this estimate.','trust_claim_without_rating'),
    (2,'Your trust increased; consider this estimate.','trust_trend_without_comparison'),
    (2,'You did not trust my advice; consider this estimate.','trust_reference_needs_review'),
    (2,SOL_NOTE,'trust_not_mentioned'),
])
def test_trust_wording_audit(rating,note,expected):
    history=rows(120);history[0]['trust_rating']=rating
    assert adviser.trust_wording_check(note,adviser.trust_context(history))==expected


def test_trust_change_claims_use_two_checkins():
    history=[dict(rows(120)[0],trial_position=i,trust_rating=value) for i,value in [(2,6),(4,2)]]
    context=adviser.trust_context(history)
    assert adviser.trust_wording_check('Your reported trust decreased; consider this estimate.',context)=='trust_wording_consistent'
    assert adviser.trust_wording_check('Your trust increased; consider this estimate.',context)=='trust_trend_conflicts_with_ratings'


def test_explicit_trust_contradiction_is_rejected_even_on_behaviour_focus(monkeypatch):
    history=rows(120);history[0]['trust_rating']=1
    note='Earlier you followed closely; your reported trust was high.'
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=(note)))
    result=adviser.generate_message('adaptive',None,74,history,attempts=1)
    assert not result['live_model'] and result['trust_context_in_prompt']
    assert result['trust_check']=='fallback_not_trust_adaptive'
    assert result['attempt_log'][0]['trust_check']=='trust_claim_conflicts_with_rating'


def test_static_audit_does_not_claim_to_receive_trust(monkeypatch):
    history=rows(120);history[0]['trust_rating']=1
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=('Consider giving my estimate some weight before deciding.')))
    result=adviser.generate_message('static',None,74,history,attempts=1)
    assert result['trust_context_in_prompt'] is False
    assert result['trust_latest_rating'] is None and result['trust_check']=='not_applicable'


def test_received_but_rejected_is_distinct_from_api_failure(monkeypatch):
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=('Consider blending your own perspective with this thoughtful suggestion.')))
    result=adviser.generate_message('adaptive',None,74,rows(120),attempts=1)
    assert result['model_response_received'] and not result['live_model']
    assert result['trust_check']=='fallback_not_trust_adaptive'
    def fail(*args):raise TimeoutError('synthetic')
    monkeypatch.setattr(adviser,'_model_text',fail)
    result=adviser.generate_message('adaptive',None,74,rows(120),attempts=1)
    assert not result['model_response_received'] and not result['live_model']


def test_trust_rating_reaches_next_prefetch_and_resets_between_blocks(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','mock-only-never-used')
    captured=[]
    def fake(system,user):
        captured.append(user)
        if 'REQUIRED MESSAGE FOCUS:\ntrust' in user:return provider_reply(system,user,('You followed my estimate earlier; weigh this suggestion on its merits.'))
        return provider_reply(system,user,(SOL_NOTE if 'LATEST COMPLETED RESPONSE' in user else 'Consider giving my estimate some weight before deciding.'))
    monkeypatch.setattr(adviser,'_model_text',fake)
    state=start(client,['C5','C8'],trials=3,skip=True,mode='live')
    with client.session_transaction() as sess:pid=sess['pid']
    while not state['done']:
        assert post(client,'/api/prefetch',json={'trial_token':state['trial_token']}).status_code==200
        payload=post(client,'/api/initial',json={'trial_token':state['trial_token'],'estimate':100}).get_json()
        diagnostic=payload['researcher']
        position=state['trial_in_block']
        assert diagnostic['trust_context_in_prompt']==(position==3)
        assert diagnostic['trust_latest_rating']==(4 if position==3 else None)
        assert diagnostic['trust_latest_trial']==(2 if position==3 else None)
        assert diagnostic['model_response_received'] and diagnostic['prefetched']
        assert diagnostic['live_model'],diagnostic
        # Follow the fixed recommendation so the next generated history claim is true.
        result=post(client,'/api/final',json=dict(trial_token=state['trial_token'],estimate=payload['advice_number'],
                    trust=4 if state['ratings_due'] else None,feeling=5 if state['ratings_due'] else None))
        assert result.status_code==200
        state=client.get('/api/state').get_json()
    records=store.diagnostic_rows(pid)
    assert len(captured)==len(records)==6  # Prefetch cache avoids a second model call.
    assert all('Latest trust check-in=4' in captured[i] for i in [2,5])
    assert all('No trust check-in' in captured[i] for i in [0,1,3,4])
    exported=list(csv.DictReader(io.StringIO(client.get('/admin/export/diagnostics.csv').get_data(as_text=True))))
    assert exported[2]['trust_latest_rating']=='4' and exported[2]['trust_context_in_prompt']=='True'


def test_trust_probe_offline_never_claims_live_trust_use(tmp_path,monkeypatch):
    def unexpected(*args,**kwargs):raise AssertionError('No API calls permitted')
    monkeypatch.setattr(adviser,'generate_message',unexpected)
    report=probe.run_probe(contrast='trust',repetitions=2)
    probe.write_report(report,tmp_path)
    assert report['summary']['routing_passed'] and report['summary']['live_messages']==0
    assert report['summary']['trust_effect']=='NOT AUTOMATICALLY ASSESSED'
    assert len(report['results'])==16
    assert 'low vs high reported trust' in (tmp_path/'adaptation-probe.html').read_text()
