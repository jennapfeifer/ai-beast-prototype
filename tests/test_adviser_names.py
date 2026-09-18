import app as A
import store
from conftest import start,post,finish_trial

def test_names_unique_stable_and_exported(client):
    state=start(client,['C4','C5'],trials=1,skip=True)
    name=state['adviser_name']
    assert name in A.ADVISER_NAMES
    with client.session_transaction() as cookie:pid=cookie['pid']
    names=store.session_data(pid)['config']['adviser_names']
    assert len(names)==len(set(names.values()))==8
    assert client.get('/api/state').get_json()['adviser_name']==name
    msg,payload=finish_trial(client,state)
    assert msg['adviser_name']==name
    assert store.diagnostic_rows(pid)[0]['adviser_name']==name
    assert client.get('/api/state').get_json()['adviser_name']!=name

def test_practice_and_old_sessions(client):
    state=start(client)
    assert state['adviser_name']=='Practice Agent'
    with client.session_transaction() as cookie:pid=cookie['pid']
    with store.session_transaction(pid) as (con,data):
        data['config'].pop('adviser_names')
    assert A.adviser_name(store.session_data(pid),'C5')=='Agent'

def test_agent_voice_is_constant_across_conditions_and_exposed(client):
    state=start(client,['C3','C4'],trials=1,skip=True)
    with client.session_transaction() as cookie:pid=cookie['pid']
    data=store.session_data(pid)
    voices=data['config']['adviser_voices']
    assert len(voices)==8
    assert set(voices.values())=={A.TTS_VOICE}
    assert state['voice_slot']==0

def test_voice_delivery_contrast_is_deliberate():
    assert A._voice_speed('C4') > A._voice_speed('C3')
    assert 'immediately and unmistakably audible' in A._voice_instructions('C4')
    assert 'matter-of-fact' in A._voice_instructions('C3')
    assert A._voice_profile('C4') == A._voice_profile('C5') == 'dramatic_persuasive'
