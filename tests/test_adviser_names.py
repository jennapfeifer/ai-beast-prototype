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
    assert state['adviser_name']=='Practice AI'
    with client.session_transaction() as cookie:pid=cookie['pid']
    with store.session_transaction(pid) as (con,data):
        data['config'].pop('adviser_names')
    assert A.adviser_name(store.session_data(pid),'C5')=='AI'
