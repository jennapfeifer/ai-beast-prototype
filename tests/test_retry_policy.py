"""Patient recovery, bounded cost/wait, SDK deadlines, and saved retry diagnostics."""
import io
import json
import zipfile
from types import SimpleNamespace

import pytest
import adviser
import store
from conftest import provider_reply, post, start, finish_trial
from pilot import build_report
from test_grounded_contract import GENERIC, PARTWAY, OPTIONAL, partway_history


class Clock:
    def __init__(self):self.now=0.;self.sleeps=[]
    def perf_counter(self):return self.now
    def sleep(self,seconds):self.sleeps.append(seconds);self.now+=seconds


@pytest.fixture
def clock(monkeypatch):
    clock=Clock()
    monkeypatch.setattr(adviser,'time',clock)
    return clock


def api_error(status,attribute='status_code',retry_after=None):
    error=RuntimeError('provider detail must not appear in logs or exports')
    setattr(error,attribute,status)
    error.response=SimpleNamespace(headers={} if retry_after is None else {'retry-after':str(retry_after)})
    return error


@pytest.mark.parametrize('profile',['server','gemini_fast','gpt_fast','gpt_stronger'])
def test_three_attempt_default_repairs_specific_failures_then_accepts(monkeypatch,profile,clock):
    seen=[]
    def fake(system,user):
        seen.append((system,user,adviser.resolved_model()))
        return provider_reply(system,user,[GENERIC,OPTIONAL,PARTWAY][len(seen)-1])
    monkeypatch.setattr(adviser,'_model_text',fake)
    with adviser.use_model_profile(adviser.model_profiles()[profile]):
        result=adviser.generate_message('adaptive',None,320,partway_history())
    assert result['text']==PARTWAY and result['live_model']
    assert result['attempts']==result['max_attempts']==3 and result['retry_count']==2
    assert result['recovered_after_retry'] and result['stop_reason']=='accepted'
    assert result['total_budget_s']==60 and result['retry_policy_version']=='patient-v1'
    assert GENERIC in seen[1][1] and 'missing_history_reaction' in seen[1][1]
    assert OPTIONAL in seen[2][1] and 'Remove optional filler' in seen[2][1]
    assert len({s[0] for s in seen})==len({s[2] for s in seen})==1
    assert all('Fixed displayed recommendation (internal only): 320' in s[1] for s in seen)
    assert len({a['request_sha256'] for a in result['attempt_log']})==3
    assert clock.sleeps==[]


def test_valid_review_flagged_note_returns_immediately(monkeypatch,clock):
    seen=[]
    def fake(system,user):seen.append(1);return provider_reply(system,user,PARTWAY)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,partway_history(),previous_messages=[PARTWAY])
    assert result['live_model'] and result['review_required'] and result['repetition_check']=='exact_repeat'
    assert result['attempts']==1 and result['retry_count']==0 and not result['recovered_after_retry']
    assert len(seen)==1 and clock.sleeps==[]


@pytest.mark.parametrize('error',[
    TimeoutError(),ConnectionError(),api_error(408),api_error(429,retry_after=2),
    api_error(503),api_error(429,'code'),api_error(500,'code'),
])
def test_transient_api_failure_is_retried(monkeypatch,clock,error):
    seen=[]
    def fake(system,user):
        seen.append(user)
        if len(seen)==1:raise error
        return provider_reply(system,user,PARTWAY)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,partway_history())
    assert result['live_model'] and result['recovered_after_retry'] and result['attempts']==2
    assert seen[0]==seen[1] and len(clock.sleeps)==1
    assert result['attempt_log'][0]['failure_kind']=='transient_api'
    if getattr(error,'response',None) and error.response.headers:assert clock.sleeps==[2.]
    assert adviser._request_timeout.get() is adviser._response_schema.get() is None


@pytest.mark.parametrize('error',[
    api_error(400),api_error(401),api_error(403),api_error(404),api_error(400,'code'),
    api_error(401,'code'),RuntimeError('API key missing'),ValueError('invalid config'),
])
def test_permanent_api_failure_stops_without_repeating(monkeypatch,clock,error):
    seen=[]
    def fake(*args):seen.append(1);raise error
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,partway_history())
    assert result['attempts']==len(seen)==1 and not result['live_model']
    assert result['stop_reason']=='permanent_api_error' and clock.sleeps==[]
    assert not result['attempt_log'][0]['retryable']
    assert 'provider detail' not in json.dumps(result) and 'API key missing' not in json.dumps(result)
    assert adviser._request_timeout.get() is adviser._response_schema.get() is None


def test_repair_feedback_survives_intervening_timeout(monkeypatch,clock):
    seen=[]
    def fake(system,user):
        seen.append(user)
        if len(seen)==2:raise TimeoutError()
        return provider_reply(system,user,GENERIC if len(seen)==1 else PARTWAY)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,partway_history())
    assert result['live_model'] and result['attempts']==3
    assert seen[1]==seen[2] and 'missing_history_reaction' in seen[2]


def test_deadline_clamps_each_request_and_prevents_an_extra_request(monkeypatch,clock):
    timeouts=[]
    def fake(system,user):
        timeouts.append(adviser.generation_settings()['timeout'])
        clock.now+=adviser.generation_settings()['timeout']
        return provider_reply(system,user,GENERIC)
    monkeypatch.setattr(adviser,'_model_text',fake)
    with adviser.use_model_profile(dict(adviser.model_profiles()['gpt_stronger'],budget=30)):
        result=adviser.generate_message('adaptive',None,320,partway_history())
    assert timeouts==[25,5] and result['attempts']==2
    assert result['stop_reason']=='time_budget' and 'time_budget_exceeded' in result['validation']
    assert [a['request_timeout_s'] for a in result['attempt_log']]==[25,5]
    assert adviser._request_timeout.get() is None


def test_retry_after_beyond_remaining_budget_does_not_retry_early(monkeypatch,clock):
    def fake(*args):raise api_error(429,retry_after=61)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('static',None,320)
    assert result['attempts']==1 and result['stop_reason']=='time_budget'
    assert result['validation']=='fallback_after:retry_wait_exceeds_budget' and clock.sleeps==[]


def test_exhausted_attempts_stay_a_labelled_fallback(monkeypatch,clock):
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=GENERIC))
    result=adviser.generate_message('adaptive',None,320,partway_history())
    assert not result['live_model'] and result['source'].startswith('fallback:')
    assert result['attempts']==3 and result['stop_reason']=='attempt_limit'
    assert not result['recovered_after_retry'] and result['history_check']=='fallback_not_adaptive'


def test_late_valid_response_is_kept_and_overrun_reported(monkeypatch,clock):
    def fake(system,user):clock.now+=61;return provider_reply(system,user,PARTWAY)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,partway_history())
    assert result['live_model'] and result['budget_overrun'] and result['attempts']==1


@pytest.mark.parametrize('provider',['gemini','openai'])
def test_remaining_timeout_reaches_sdk_with_no_hidden_sdk_retries(monkeypatch,clock,provider):
    timeouts=[]
    class FakeOpenAI:
        def with_options(self,**kw):
            timeouts.append(kw['timeout']);assert kw['max_retries']==0;return self
        @property
        def responses(self):return self
        def create(self,**kw):return SimpleNamespace(output_text=provider_reply('',kw['input'][1]['content'],PARTWAY))
    class FakeGemini:
        @property
        def models(self):return self
        def generate_content(self,**kw):
            timeouts.append(kw['config'].http_options.timeout/1000)
            assert kw['config'].http_options.retry_options.attempts==1
            return SimpleNamespace(text=provider_reply('',kw['contents'],PARTWAY))
    monkeypatch.setattr(adviser,'get_openai_client',lambda:FakeOpenAI())
    monkeypatch.setattr(adviser,'get_gemini_client',lambda:FakeGemini())
    with adviser.use_model_profile(dict(adviser.model_profiles()['gemini_fast' if provider=='gemini' else 'gpt_stronger'],budget=2)):
        result=adviser.generate_message('adaptive',None,320,partway_history())
    assert result['live_model'] and timeouts==[2]


def test_prefetch_saves_recovery_and_reuses_result_without_regeneration(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','mock-only-never-used')
    calls=[]
    def fake(system,user):
        calls.append(user)
        return provider_reply(system,user,OPTIONAL if len(calls)==1 else GENERIC)
    monkeypatch.setattr(adviser,'_model_text',fake)
    state=start(client,['C5'],trials=1,skip=True,mode='live')
    with client.session_transaction() as session:pid=session['pid']
    # This regression exercises a session started under the legacy prefetch protocol.
    with store.session_transaction(pid) as (con,data):data['config'].pop('adviser_protocol',None)
    profile=store.session_data(pid)['config']['model_profile']
    assert profile['attempts']==3 and profile['budget']==60
    # New defaults cannot change this already launched session's retry policy.
    monkeypatch.setattr(adviser,'ADVISER_MAX_ATTEMPTS',1)
    for _ in range(2):assert post(client,'/api/prefetch',json={'trial_token':state['trial_token']}).status_code==200
    finish_trial(client,state)
    assert len(calls)==2
    row=store.diagnostic_rows(pid)[0]
    assert row['prefetched'] and row['max_attempts']==3 and row['retry_count']==1 and row['recovered_after_retry']
    assert row['stop_reason']=='accepted' and row['retry_policy_version']=='patient-v1'
    report=client.get('/api/researcher/report').get_json()['model_conditions'][0]
    assert report['retried_trials']==report['recovered_trials']==1 and report['recorded_api_attempts']==2
    assert client.get('/researcher').status_code==200
    with zipfile.ZipFile(io.BytesIO(client.get('/admin/export/all.zip').data)) as archive:
        assert b'recovered_after_retry' in archive.read('diagnostics.csv')
        assert b'recovered_trials' in archive.read('model_comparison.csv')
        assert json.loads(archive.read('run_metadata.json'))['retry_policy_version']=='patient-v1'


def test_model_comparison_separates_retry_settings():
    base=dict(condition_id='C5',pid='synthetic',history_rows=1,expected_history_rows=1,
              adviser_mode='live',retry_policy_version='patient-v1',total_budget_s=60,attempts=2,retry_count=1,
              live_model=True,recovered_after_retry=True)
    rows=[dict(base,max_attempts=2),dict(base,max_attempts=3),
          dict(base,max_attempts=3,recovered_after_retry=False,live_model=False,fallback=True)]
    groups=build_report(rows,[])['model_conditions']
    assert len(groups)==2
    three=next(r for r in groups if r['max_attempts']==3)
    assert three['retried_trials']==2 and three['recovered_trials']==1 and three['fallbacks']==1
