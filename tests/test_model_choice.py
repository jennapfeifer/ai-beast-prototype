from conftest import provider_reply
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
import re
import pytest
import adviser
import store
from conftest import post, finish_trial
from pilot import build_report


def test_provider_settings_are_isolated_between_concurrent_pilots():
    profiles=adviser.model_profiles()
    before=(adviser.resolved_provider(),adviser.resolved_model())
    barrier=Barrier(2)
    def read(key):
        with adviser.use_model_profile(profiles[key]):
            barrier.wait(timeout=3)
            return adviser.resolved_provider(),adviser.resolved_model(),adviser.generation_settings()['reasoning']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(read,['gemini_fast','gpt_stronger']))
    assert results==[('gemini',adviser.GEMINI_MODEL,'minimal'),('openai','gpt-5.6-sol','low')]
    assert (adviser.resolved_provider(),adviser.resolved_model())==before
    with pytest.raises(RuntimeError):
        with adviser.use_model_profile(profiles['gpt_stronger']):raise RuntimeError('test')
    assert (adviser.resolved_provider(),adviser.resolved_model())==before


def test_selected_provider_needs_its_own_key(client,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','mock-only-never-used')
    post(client,'/researcher',data={'token':'researcher-test'})
    result=post(client,'/start',data=dict(consent='yes',researcher_test='1',adviser_mode='live',model_profile='gpt_stronger'))
    assert result.status_code==400 and b'OPENAI_API_KEY' in result.data
    assert not store.export_rows(store.participants)


def test_unknown_model_is_rejected(client):
    post(client,'/researcher',data={'token':'researcher-test'})
    result=post(client,'/start',data=dict(consent='yes',researcher_test='1',adviser_mode='offline',model_profile='arbitrary-model'))
    assert result.status_code==400


def test_researcher_defaults_live_when_key_exists(client,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','mock-only-never-used')
    html=post(client,'/researcher',data={'token':'researcher-test'}).get_data(as_text=True)
    mode=re.search(r'<select name="adviser_mode".*?</select>',html).group()
    assert '<option value="live" selected>' in mode
    assert 'GPT-5.6 Sol' in html and 'key missing' in html


def test_model_is_pinned_and_exported_through_prefetch(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','mock-only-never-used')
    captured=[]
    def fake(system,user):
        captured.append((adviser.resolved_provider(),adviser.resolved_model()))
        return provider_reply(system,user,('Consider giving my estimate some weight before deciding.'))
    monkeypatch.setattr(adviser,'_model_text',fake)
    post(client,'/researcher',data={'token':'researcher-test'})
    assert post(client,'/start',data=dict(consent='yes',researcher_test='1',adviser_mode='live',
        model_profile='gpt_stronger',conditions=['C5'],trials='1',skip_practice='1')).status_code==302
    state=client.get('/api/state').get_json()
    with client.session_transaction() as sess:pid=sess['pid']
    config=store.session_data(pid)['config']
    assert config['model_profile']['model']=='gpt-5.6-sol'
    # An environment default change must not change an already launched pilot.
    monkeypatch.setattr(adviser,'OPENAI_MODEL','different-model')
    assert post(client,'/api/prefetch',json={'trial_token':state['trial_token']}).status_code==200
    finish_trial(client,state)
    row=store.diagnostic_rows(pid)[0]
    assert captured==[('openai','gpt-5.6-sol')]
    assert row['model']=='gpt-5.6-sol' and row['reasoning']=='low' and row['prefetched']
    assert row['request_timeout_s']==25 and row['prompt_version']==adviser.PROMPT_VERSION
    assert client.get('/admin/export/model_comparison.csv').status_code==200


def test_participant_form_cannot_select_researcher_model(client):
    assert post(client,'/start',data=dict(consent='yes',adviser_mode='offline',model_profile='gpt_stronger')).status_code==302
    with client.session_transaction() as sess:pid=sess['pid']
    assert store.session_data(pid)['config']['model_profile_id']=='server'


def test_openai_low_reasoning_has_room_for_reasoning_tokens(monkeypatch):
    seen={}
    class FakeClient:
        def with_options(self,**kwargs):seen['options']=kwargs;return self
        @property
        def responses(self):return self
        def create(self,**kwargs):seen['request']=kwargs;return SimpleNamespace(output_text='A short test note.')
    monkeypatch.setattr(adviser,'get_openai_client',lambda:FakeClient())
    with adviser.use_model_profile(adviser.model_profiles()['gpt_stronger']):
        assert adviser._openai_text('system','user')=='A short test note.'
    assert seen['request']['model']=='gpt-5.6-sol'
    assert seen['request']['reasoning']=={'effort':'low'}
    assert seen['request']['max_output_tokens']==2048 and seen['request']['store'] is False
    assert seen['options']==dict(timeout=25,max_retries=0)


def test_report_does_not_pool_providers_or_offline_mode():
    base=dict(condition_id='C5',pid='synthetic',history_rows=1,expected_history_rows=1,practice=False,
              timing_complete=True,advice_wait_ms=200,generation_ms=1000,live_model=True,adviser_mode='live',
              history_check='history_wording_screen_passed')
    rows=[dict(base,provider='gemini',model='gemini-model',reasoning='minimal'),
          dict(base,provider='openai',model='gpt-5.6-sol',reasoning='low'),
          dict(base,provider='openai',model='gpt-5.6-sol',reasoning='low',adviser_mode='offline',live_model=False)]
    groups=build_report(rows,[])['model_conditions']
    assert len(groups)==3 and sum(g['live_messages'] for g in groups)==2
    offline=next(g for g in groups if g['mode']=='offline')
    assert offline['generation_p50_ms'] is None and offline['history_reactions']==0
