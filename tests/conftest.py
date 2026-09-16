import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
DB_DIR=tempfile.TemporaryDirectory(prefix='beast-tests-')
os.environ.update(DATABASE_URL='sqlite:///'+DB_DIR.name+'/tests.db',SECRET_KEY='automated-test-only',ADMIN_TOKEN='researcher-test',
                  ACCESS_CODE='',RENDER='false',ADVISER_MODE='offline',STUDY_MODE='pilot')
os.environ.pop('OPENAI_API_KEY',None)
os.environ.pop('GEMINI_API_KEY',None)
import pytest
import app as A
@pytest.fixture(autouse=True)
def clean_db():
    with A.store.engine.begin() as con:
        for table in reversed(A.store.meta.sorted_tables):con.execute(table.delete())
    yield
@pytest.fixture
def client():
    A.app.config['TESTING']=True
    return A.app.test_client()
def csrf(client):
    client.get('/')
    with client.session_transaction() as s:return s['csrf']
def post(client,url,json=None,data=None):
    token=csrf(client)
    if json is not None:return client.post(url,json=json,headers={'X-CSRF-Token':token})
    return client.post(url,data={'csrf_token':token,**(data or {})})
def start(client,conditions=None,trials=13,skip=False,mode='offline'):
    if conditions is not None:
        assert post(client,'/researcher',data={'token':'researcher-test'}).status_code==200
    payload={'consent':'yes'}
    if conditions is not None:payload.update(researcher_test='1',conditions=conditions,trials=str(trials),test_index='0',adviser_mode=mode,skip_practice='1' if skip else '')
    assert post(client,'/start',data=payload).status_code==302
    return client.get('/api/state').get_json()
def finish_trial(client,state,initial=100,final=110):
    body={'trial_token':state['trial_token'],'estimate':initial,'rt_ms':3000}
    advice=post(client,'/api/initial',json=body)
    assert advice.status_code==200,advice.get_json()
    payload={'trial_token':state['trial_token'],'estimate':final,'rt_ms':5000,'trust':4 if state['ratings_due'] else None,
             'feeling':5 if state['ratings_due'] else None,'telemetry':{'stimulus_visible_ms':5000,'advice_wait_ms':2500,
             'total_wall_ms':16000,'total_active_ms':16000,'rating_ms':6000 if state['ratings_due'] else 0,'break_ms':0}}
    response=post(client,'/api/final',json=payload)
    assert response.status_code==200,response.get_json()
    return advice.get_json(),payload

def provider_reply(system,user,note):
    """Mock the new provider envelope while leaving the test's wording unchanged."""
    import json
    marker='SUPPLIED RECORD JSON:\n'
    if marker not in user:return note
    record=json.loads(user.split(marker,1)[1].splitlines()[0])
    phrase='' if record['history_route'] in {'no_history','unusable'} else note.split(';',1)[0]
    return json.dumps(dict(record,history_phrase=phrase,message=note))
