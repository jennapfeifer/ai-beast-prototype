import app as A
import adviser
import store
from conftest import start,post,finish_trial

def test_default_advice_and_trust_only_are_pinned(client):
    state=start(client,['C5'],trials=3,skip=True)
    with client.session_transaction() as cookie:pid=cookie['pid']
    assert A.ADVICE_PREVIEW_MS==5000
    assert store.session_data(pid)['config']['rating_items']=='trust_only'
    finish_trial(client,state)
    state=client.get('/api/state').get_json()
    assert state['ratings_due']
    assert post(client,'/api/initial',json=dict(trial_token=state['trial_token'],estimate=100)).status_code==200
    payload=dict(trial_token=state['trial_token'],estimate=110,trust=6)
    assert post(client,'/api/final',json=payload).status_code==200
    assert post(client,'/api/final',json=payload).get_json()['already_saved']
    rows=store.export_rows(store.trials)
    assert rows[-1]['trust_rating']==6 and rows[-1]['feeling_rating'] is None
    assert store.diagnostic_rows(pid)[-1]['rating_items']=='trust_only'
    state=client.get('/api/state').get_json()
    finish_trial(client,state)
    diagnostic=store.diagnostic_rows(pid)[-1]
    history=store.export_rows(store.trials)
    assert adviser.trust_context(history)['trust_rating_available']
    assert not adviser.feeling_context(history)['feeling_rating_available']


def test_researcher_can_restore_simultaneous_advice(client):
    post(client,'/researcher',data={'token':'researcher-test'})
    assert post(client,'/start',data=dict(consent='yes',researcher_test='1',advice_preview_ms='0')).status_code==302
    assert '"advice_preview_ms": 0' in client.get('/task').get_data(as_text=True)
