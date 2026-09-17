import io,json,zipfile,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
import app as A
import adviser,design,store
from pilot import timing_projection
from conftest import post,start,finish_trial,csrf,provider_reply

def test_complete_105_trial_session_preserves_design_and_history(client):
    start(client);count=0;images=set()
    while True:
        state=client.get('/api/state').get_json()
        if state['done']:break
        assert state['researcher'] is None
        assert 'N144' not in state['image'] and 'true_count' not in state
        assert client.get(state['image']).status_code==200
        images.add(state['image']);assert post(client,'/api/prefetch',json={'trial_token':state['trial_token']}).status_code==200
        finish_trial(client,state);count+=1
    rows=store.export_rows(store.trials);diagnostics=store.diagnostic_rows()
    assert count==105 and len(rows)==104 and len(images)==105
    assert len({r['stimulus_id'] for r in rows})==104
    groups={cid:[r for r in rows if r['condition_id']==cid] for cid in design.CONDITIONS}
    assert all(len(rs)==13 for rs in groups.values())
    for triplet in [('C3','C4','C5'),('C6','C7','C8')]:
        schedules=[{r['true_count']:r['advice_number'] for r in groups[c]} for c in triplet]
        assert schedules[0]==schedules[1]==schedules[2]
    for cid,target in [('C1',0),('C3',25),('C6',-25)]:assert sum(r['advice_error_pct'] for r in groups[cid])/13==pytest.approx(target)
    for cid in ['C5','C8']:
        ds=[d for d in diagnostics if d['condition_id']==cid]
        assert [d['history_rows'] for d in ds]==list(range(13))
        assert all(d['history_rows']==d['expected_history_rows'] for d in ds)
    assert all(d['history_rows']==0 for d in diagnostics if d['condition_id'] not in ['C5','C8'])
    assert all([r['trial_position'] for r in rs if r['trust_rating'] is not None]==[2,4,6,8,10,12] for rs in groups.values())
    participant=store.export_rows(store.participants)[0]
    assert participant['finished_at'] and participant['notes']=='TEST'
    assert client.get('/debrief').status_code==200

def test_counterbalance_and_probe_positions():
    orders=[design.balanced_condition_order(i) for i in range(8)]
    for position in range(8):assert {o[position] for o in orders}==set(design.CONDITIONS)
    for cid in design.CONDITIONS:assert {design.trial_order(i,cid).index(144) for i in range(13)}==set(range(13))
    for p in range(8):assert len({r['stimulus_id'] for r in design.build_schedule(p)})==104

def test_control_two_remains_under_four_percent():
    for truth in design.TRUE_COUNTS:
        for initial in range(1,401):assert abs(design.c2_advice_from_initial(truth,initial)-initial)/initial<.04

def test_duplicate_initial_and_final_are_idempotent(client,monkeypatch):
    state=start(client,['C5'],trials=2,skip=True)
    calls=[];original=adviser.generate_offline_message
    def track(**kwargs):calls.append(kwargs);return original(**kwargs)
    monkeypatch.setattr(adviser,'generate_offline_message',track)
    body={'trial_token':state['trial_token'],'estimate':100,'rt_ms':2000}
    a=post(client,'/api/initial',json=body).get_json();b=post(client,'/api/initial',json=body).get_json()
    assert a==b and len(calls)==1
    assert client.get(state['image']).status_code==404
    resumed=client.get('/api/state').get_json();assert resumed['pending']['initial']==100
    final={'trial_token':state['trial_token'],'estimate':110,'rt_ms':3000}
    assert post(client,'/api/final',json=final).get_json()['ok']
    assert post(client,'/api/final',json=final).get_json()['already_saved']
    assert len(store.export_rows(store.trials))==1
    assert post(client,'/api/final',json={**final,'estimate':111}).status_code==409
    assert post(client,'/api/initial',json=body).status_code==409

def test_cookie_contains_no_pending_advice_or_truth(client):
    state=start(client,['C5'],skip=True,trials=1)
    post(client,'/api/initial',json={'trial_token':state['trial_token'],'estimate':100})
    with client.session_transaction() as cookie:
        assert 'pending' not in cookie and 'cursor' not in cookie and 'participant_index' not in cookie

def test_server_validates_consent_ratings_and_nonfinite_numbers(client):
    assert post(client,'/start',data={}).status_code==400
    state=start(client,['C5'],trials=2,skip=True)
    for value in [None,'NaN','Infinity',4.4,True,0,401]:
        assert post(client,'/api/initial',json={'trial_token':state['trial_token'],'estimate':value}).status_code==400
    finish_trial(client,state)
    st=client.get('/api/state').get_json();assert st['ratings_due']
    post(client,'/api/initial',json={'trial_token':st['trial_token'],'estimate':100})
    for rating in [None,0,8,2.2]:assert post(client,'/api/final',json={'trial_token':st['trial_token'],'estimate':110,'trust':rating,'feeling':4}).status_code==400

def test_private_access_researcher_auth_and_csrf(client,monkeypatch):
    monkeypatch.setattr(A,'ACCESS_CODE','private-test')
    assert client.get('/').status_code==302
    assert client.get('/api/state').status_code==403
    client.get('/unlock')
    with client.session_transaction() as s:token=s['csrf']
    assert client.post('/unlock',data={'csrf_token':token,'code':'private-test'}).status_code==302
    assert client.get('/admin/export/all.zip').status_code==403
    assert client.post('/start',data={'consent':'yes'}).status_code==403
    assert post(client,'/researcher',data={'token':'researcher-test'}).status_code==200
    assert client.get('/admin/export/all.zip').status_code==200
    assert client.post('/start',data={'csrf_token':token,'consent':'yes'},headers={'Origin':'https://elsewhere.invalid'}).status_code==403

def test_direct_stimulus_names_not_public(client):
    assert client.get('/static/stimuli/N144_V1.png').status_code==404

def test_full_zip_export_and_timing(client):
    st=start(client,['C4','C5'],trials=3,skip=True)
    while not st['done']:
        finish_trial(client,st);st=client.get('/api/state').get_json()
    response=client.get('/admin/export/all.zip');assert response.status_code==200
    z=zipfile.ZipFile(io.BytesIO(response.data))
    assert {'trials.csv','participants.csv','diagnostics.csv','timing_summary.csv','run_metadata.json','pilot_report.json','ratings.csv'}<=set(z.namelist())
    report=json.loads(z.read('pilot_report.json'));assert report['live_trials']==0 and report['timed_trials']==6
    assert report['conditions'][0]['wait_p50_ms']==2500
    assert report['sessions'][0]['completed'] and report['sessions'][0]['is_test']
    assert report['history_mismatches']==0

def test_production_indices_are_unique_under_concurrent_starts():
    def create(i):return store.create_session('production-'+str(i),dict(is_test=False,conditions=[],trials_per_block=13,skip_practice=False))
    with ThreadPoolExecutor(max_workers=8) as executor:indices=list(executor.map(create,range(16)))
    assert sorted(indices)==list(range(16))
    store.create_session('pilot',dict(is_test=True,test_index=7))
    assert create(16)==16

def history(final):return [{'trial_position':1,'initial_estimate':100,'advice_number':125,'final_estimate':final,'advice_text':'previous message','trust_rating':4,'feeling_rating':3}]

def test_static_prompt_identical_and_adaptive_prompt_changes_with_history():
    resistant,following=history(100),history(125)
    assert adviser.build_prompt('static',90,120,resistant)==adviser.build_prompt('static',90,120,following)
    assert adviser.build_prompt('neutral',90,120,resistant)==adviser.build_prompt('neutral',90,120,following)
    a=adviser.build_prompt('adaptive',90,120,resistant);b=adviser.build_prompt('adaptive',90,120,following)
    assert a[1]!=b[1] and 'previous message' in a[1] and 'trust_checkin=4' in a[1]
    assert 'do not claim' in a[1]

def test_responses_boundary_gets_history_only_for_adaptive(monkeypatch):
    received=[]
    draft='Consider giving my estimate some weight before deciding.'
    def fake(system,user,timeout_seconds=None):
        received.append((system,user))
        return provider_reply(system,user,'You kept your estimate earlier; consider giving mine more weight.' if 'EXACT INTERNAL HISTORY' in user else draft)
    monkeypatch.setattr(adviser,'_model_text',fake)
    for style in ['neutral','static','adaptive']:
        msg=adviser.generate_message(style,100,125,history(100));assert msg['source']==adviser.resolved_provider()+':'+adviser.resolved_model() and msg['validation']==('accepted_for_review' if style=='adaptive' else 'passed')
    assert 'EXACT INTERNAL HISTORY' not in received[0][1] and 'EXACT INTERNAL HISTORY' not in received[1][1]
    assert 'EXACT INTERNAL HISTORY' in received[2][1]

def test_validator_rejects_extra_numbers_and_unsupported_image_claims():
    draft="Consider giving my estimate some weight before deciding."
    assert adviser.message_is_valid(draft)[0]
    for extra in [' 7',' 1.5',' 2e5']:assert not adviser.message_is_valid(draft+extra)[0]
    assert not adviser.message_is_valid("The clusters clearly support my estimate for this display.")[0]

def test_timeout_fallback_not_mislabeled_live_or_adaptive_success(monkeypatch):
    calls=[]
    def fail(*args,**kwargs):calls.append(1);raise TimeoutError('test timeout')
    monkeypatch.setattr(adviser,'_model_text',fail)
    msg=adviser.generate_message('adaptive',100,125,history(125),attempts=2)
    assert len(calls)==2 and msg['source'].startswith('fallback:') and not msg['live_model']
    assert msg['attempts']==2 and len(msg['attempt_log'])==2
    assert 'earlier' not in msg['text'].lower()
    monkeypatch.setattr(adviser,'ADVISER_TOTAL_BUDGET_SECONDS',0)
    before=len(calls);msg=adviser.generate_message('static',100,125)
    assert len(calls)==before and 'time_budget_exceeded' in msg['validation']

def test_offline_adaptation_branch_changes_but_numbers_stay_fixed():
    a=adviser.generate_offline_message('adaptive',100,125,history(100));b=adviser.generate_offline_message('adaptive',100,125,history(125))
    assert a['history_route']=='resistance' and b['history_route']=='uptake'
    assert a['text']!=b['text'] and adviser.numeric_tokens(a['text'])==adviser.numeric_tokens(b['text'])==[]
    assert not a['live_model'] and a['source'].startswith('offline_demo:')

def test_setup_does_not_overwrite_interface():
    import setup_files
    p=Path(__file__).resolve().parents[1]/'templates'/'task.html';before=p.read_bytes();setup_files.main();assert p.read_bytes()==before

def test_duration_estimate_is_labelled_assumption():
    report=timing_projection();assert report['assumption_only'] and report['minutes']==38.6

def test_contrastive_probe_is_offline_and_keeps_static_prompt_constant(tmp_path,monkeypatch):
    import verify_adaptation as probe
    def unexpected(*args,**kwargs):raise AssertionError('Offline probe must not call the model')
    monkeypatch.setattr(adviser,'generate_message',unexpected)
    report=probe.run_probe();probe.write_report(report,tmp_path)
    assert report['mode']=='offline' and report['summary']['routing_passed']
    assert report['summary']['live_messages']==0 and len(report['results'])==8
    assert all(adviser.numeric_tokens(r['text'])==[] for r in report['results'])
    assert (tmp_path/'adaptation-probe.html').exists() and (tmp_path/'message-review.csv').exists()
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with pytest.raises(RuntimeError):probe.run_probe(live=True)

def test_prefetch_cached_in_database_and_does_not_reveal_advice_early(client,monkeypatch):
    st=start(client,['C5'],trials=2,skip=True)
    calls=[];original=adviser.generate_offline_message
    def capture(**kw):calls.append(kw);return original(**kw)
    monkeypatch.setattr(adviser,'generate_offline_message',capture)
    payload={'trial_token':st['trial_token']}
    for _ in range(2):
        response=post(client,'/api/prefetch',json=payload)
        assert response.status_code==200 and response.get_json()=={'ok':True,'prefetched':True}
    assert len(calls)==1 and calls[0]['initial'] is None
    with client.session_transaction() as cookie:assert 'prefetched' not in cookie
    a=post(client,'/api/initial',json={**payload,'estimate':125}).get_json()
    assert len(calls)==1 and a['researcher']['prefetched'] and not a['researcher']['initial_context_available']
    assert isinstance(a['advice_number'],int)
    assert post(client,'/api/final',json={**payload,'estimate':125}).status_code==200
    assert post(client,'/api/prefetch',json=payload).status_code==409
    st=client.get('/api/state').get_json()
    assert post(client,'/api/prefetch',json={'trial_token':st['trial_token']}).status_code==200
    assert len(calls[-1]['history'])==1
    assert calls[-1]['history'][0]['initial_estimate']==125


def test_missing_prefetch_keeps_current_estimate_out_of_model_prompt(client,monkeypatch):
    st=start(client,['C4'],trials=1,skip=True);calls=[];original=adviser.generate_offline_message
    def capture(**kw):calls.append(kw);return original(**kw)
    monkeypatch.setattr(adviser,'generate_offline_message',capture)
    finish_trial(client,st,initial=300)
    assert calls[0]['initial'] is None and calls[0]['history']==[]
    assert not store.diagnostic_rows()[0]['prefetched']


def test_end_score_only_after_completed_session(client):
    st=start(client,['C1'],trials=1,skip=True)
    assert client.get('/debrief').status_code==302
    finish_trial(client,st)
    text=client.get('/debrief').get_data(as_text=True)
    assert 'Your estimation summary' in text and 'First-estimate score' in text


def test_gemini_client_sets_timeout_and_disables_sdk_retries(monkeypatch):
    captured=[]
    import google.genai as genai
    monkeypatch.setattr(genai,'Client',lambda **kwargs:captured.append(kwargs) or object())
    monkeypatch.setattr(adviser,'_gemini_client',None)
    monkeypatch.setenv('GEMINI_API_KEY','unit-test-placeholder')
    adviser.get_gemini_client()
    assert captured[0]['http_options']['timeout']==int(adviser.ADVISER_REQUEST_TIMEOUT*1000)
    assert captured[0]['http_options']['retry_options']['attempts']==1
