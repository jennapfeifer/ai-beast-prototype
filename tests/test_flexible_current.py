import adviser,adviser_flexible as flex,store
from conftest import start,post

def test_current_prompts_isolate_history():
    h=[dict(trial_position=1,initial_estimate=100,advice_number=120,final_estimate=110,trust_rating=2)]
    static=flex.build_prompt('static',151,160,h)
    adaptive=flex.build_prompt('adaptive',151,160,h)
    assert '151' in static[1] and '160' in static[1]
    assert 'completed_trials' not in static[1] and 'completed_trials' in adaptive[1]
    assert 'REQUIRED MESSAGE FOCUS' not in str(adaptive)
    assert 'Do not invent' not in str(adaptive)

def test_implicit_and_paraphrased_history_accepted_without_retry(monkeypatch):
    for sentence in ['Give this estimate another look before settling on your final answer.', 'Your last choice was close to my estimate; give mine more weight.']:
        monkeypatch.setattr(adviser,'_model_text',lambda *args:sentence)
        result=flex.generate_message('adaptive',151,160,history=[])
        assert result['live_model'] and result['attempts']==1
        assert result['review_required']

def test_wrong_direction_repaired_but_numbers_and_claims_flagged(monkeypatch):
    assert not flex.screen('Move left toward my estimate for your final answer.', 'static',100,150,[],[])[0]
    ok,_,flags=flex.screen('My estimate is verified, so move toward 150 for your final answer.','static',100,150,[],[])
    assert ok
    calls=iter(['Move left toward my estimate for your final answer.','Move right toward my estimate for your final answer.'])
    monkeypatch.setattr(adviser,'_model_text',lambda *args:next(calls))
    result=flex.generate_message('static',100,150)
    assert result['attempts']==2 and result['live_model']

def test_new_server_flow_waits_for_current_estimate(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','mock-only')
    seen=[]
    def mock(system,user):
        seen.append(user)
        return 'Give this estimate another look before settling on your final answer.'
    monkeypatch.setattr(adviser,'_model_text',mock)
    st=start(client,['C4','C5'],trials=1,skip=True,mode='live')
    assert post(client,'/api/prefetch',json={'trial_token':st['trial_token']}).get_json()['reason']=='requires_current_estimate'
    assert not seen
    assert '"prefetch_enabled": false' in client.get('/task').get_data(as_text=True)
    msg=post(client,'/api/initial',json={'trial_token':st['trial_token'],'estimate':151}).get_json()
    assert '"current_first_estimate": 151' in seen[0]
    assert msg['researcher']['initial_context_available']
    assert msg['researcher']['prompt_version']==flex.PROMPT_VERSION
    post(client,'/api/initial',json={'trial_token':st['trial_token'],'estimate':151})
    assert len(seen)==1

def test_legacy_sessions_keep_prefetch(client):
    st=start(client,['C4'],trials=1,skip=True)
    with client.session_transaction() as cookie:pid=cookie['pid']
    with store.session_transaction(pid) as (con,data):data['config'].pop('adviser_protocol')
    assert post(client,'/api/prefetch',json={'trial_token':st['trial_token']}).get_json()['prefetched']
