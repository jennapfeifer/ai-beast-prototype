import app as A
import design
import store
from conftest import start, finish_trial


def test_names_unique_stable_and_exported(client):
    state=start(client,['N','P','A'],trials=1,skip=True)
    with client.session_transaction() as cookie:
        pid=cookie['pid']
    data=store.session_data(pid)
    names=data['config']['adviser_names']
    assert set(names)==set(design.CONDITIONS)
    assert set(names.values())==set(design.ADVISER_NAMES)
    first=state['adviser_name']
    assert first in design.ADVISER_NAMES
    finish_trial(client,state)
    next_state=client.get('/api/state').get_json()
    assert next_state['adviser_name'] != first


def test_practice_uses_generic_label(client):
    state=start(client)
    assert state['adviser_name']=='Practice adviser'


def test_agent_voice_is_constant_across_conditions_and_exposed(client):
    state=start(client,['N','P','A'],trials=1,skip=True)
    with client.session_transaction() as cookie:
        pid=cookie['pid']
    data=store.session_data(pid)
    voices=data['config']['adviser_voices']
    assert set(voices)==set(design.CONDITIONS)
    assert set(voices.values())=={A.shared_voice_identity()}
    assert state['voice_slot']==0
