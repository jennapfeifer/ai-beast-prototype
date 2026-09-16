"""Test the reported generic note, hidden-record honesty, and actual SDK boundaries."""
import json
from types import SimpleNamespace
import pytest
import adviser
from conftest import provider_reply, post, start
from test_rating_focus import history

GENERIC='Please gently consider blending this number into your final choice'
PARTWAY='You moved closer earlier; give my estimate more weight.'


def partway_history(n=3):
    return [dict(row,final_estimate=110) for row in history(n,7,7)]


@pytest.mark.parametrize('profile',['gemini_fast','gpt_stronger'])
@pytest.mark.parametrize('n',[1,2,3,4,6])
def test_actual_generic_sentence_cannot_pass_any_history_or_rating_focus(monkeypatch,profile,n):
    seen=[]
    def fake(system,user):
        seen.append(1)
        return provider_reply(system,user,GENERIC)
    monkeypatch.setattr(adviser,'_model_text',fake)
    with adviser.use_model_profile(adviser.model_profiles()[profile]):
        result=adviser.generate_message('adaptive',None,320,partway_history(n),attempts=1)
    assert result['model_response_received'] and not result['live_model']
    assert result['source'].startswith('fallback:')
    assert result['attempt_log'][0]['draft']==GENERIC
    # Even accurate copied metadata cannot make generic prose pass.
    assert result['attempt_log'][0]['grounding_record_check']=='matched_input_record'
    assert result['attempt_log'][0]['result']=='missing_history_reaction'
    assert result['generation_status']=='fallback_after_rejection' and len(seen)==1


def test_configured_repair_uses_concrete_history_without_requiring_rating_words(monkeypatch):
    seen=[]
    def fake(system,user):
        seen.append(user)
        return provider_reply(system,user,GENERIC if len(seen)==1 else PARTWAY)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,partway_history(),attempts=2)
    assert result['text']==PARTWAY and result['live_model'] and result['attempts']==2
    assert result['history_check']=='history_wording_screen_passed'
    assert result['grounding_record_check']=='matched_input_record'
    assert result['model_basis']['trust_rating']==result['model_basis']['feeling_rating']==7
    assert result['model_basis']['trust_trial']==result['model_basis']['feeling_trial']==2
    assert result['rating_influence_status']=='not_assessed'
    assert adviser.REACTION_FACTS['partway'] in seen[1]
    assert 'missing_history_reaction' in seen[1]


@pytest.mark.parametrize('field,value',[
    ('trust_rating',1),('feeling_rating',1),('trust_trial',3),('feeling_trial',3),
    ('last_trial',2),('history_route','followed'),('trust_rating',True),
])
def test_wrong_or_invented_internal_basis_is_rejected(monkeypatch,field,value):
    def fake(system,user):
        payload=json.loads(provider_reply(system,user,PARTWAY));payload[field]=value
        return json.dumps(payload)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,partway_history(),attempts=1)
    assert not result['live_model']
    assert result['attempt_log'][0]['result']=='grounding_record_mismatch:'+field


def test_invented_annotation_cannot_stand_in_for_visible_history_reference(monkeypatch):
    def fake(system,user):
        payload=json.loads(provider_reply(system,user,GENERIC))
        payload['history_phrase']='You moved closer earlier'
        return json.dumps(payload)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,partway_history(),attempts=1)
    assert not result['live_model']
    assert result['attempt_log'][0]['result']=='history_phrase_not_in_message'


@pytest.mark.parametrize('raw',[GENERIC,'[]','{}','{"message":null}',None])
def test_malformed_structured_response_is_content_failure_not_api_failure(monkeypatch,raw):
    monkeypatch.setattr(adviser,'_model_text',lambda *args:raw)
    result=adviser.generate_message('adaptive',None,320,partway_history(),attempts=1)
    assert result['model_response_received'] and not result['live_model']
    assert result['generation_status']=='fallback_after_rejection'
    assert result['attempt_log'][0]['result'].startswith('invalid_adaptive_')


def test_no_history_exception_and_static_condition_still_accept_plain_invitation(monkeypatch):
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=GENERIC))
    first=adviser.generate_message('adaptive',None,320,[],attempts=1)
    static=adviser.generate_message('static',None,320,partway_history(),attempts=1)
    assert first['live_model'] and first['history_check']=='no_history'
    assert first['model_basis']['trust_rating'] is None and first['model_basis']['history_phrase']==''
    assert static['live_model'] and static['text']==GENERIC and static['model_basis']=={}


@pytest.mark.parametrize('provider',['gemini','openai'])
def test_provider_receives_schema_only_for_adaptive_and_displays_only_message(monkeypatch,provider):
    calls=[]
    class FakeOpenAI:
        def with_options(self,**kwargs):return self
        @property
        def responses(self):return self
        def create(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text=provider_reply(kwargs['input'][0]['content'],kwargs['input'][1]['content'],PARTWAY))
    class FakeGemini:
        @property
        def models(self):return self
        def generate_content(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text=provider_reply(kwargs['config'].system_instruction,kwargs['contents'],PARTWAY))
    monkeypatch.setattr(adviser,'get_openai_client',lambda:FakeOpenAI())
    monkeypatch.setattr(adviser,'get_gemini_client',lambda:FakeGemini())
    profile='gemini_fast' if provider=='gemini' else 'gpt_fast'
    with adviser.use_model_profile(adviser.model_profiles()[profile]):
        adaptive=adviser.generate_message('adaptive',None,320,partway_history(),attempts=1)
        adviser.generate_message('static',None,320,[],attempts=1)
    assert adaptive['text']==PARTWAY and adaptive['live_model'] and len(calls)==2
    assert adviser._response_schema.get() is None
    if provider=='openai':
        assert calls[0]['text']['format']['schema']==adviser.ADAPTIVE_RESPONSE_SCHEMA
        assert calls[0]['text']['format']['strict'] is True and 'text' not in calls[1]
        assert [c['max_output_tokens'] for c in calls]==[384,128]
    else:
        assert calls[0]['config'].response_mime_type=='application/json'
        assert calls[0]['config'].response_json_schema==adviser.ADAPTIVE_RESPONSE_SCHEMA
        assert calls[1]['config'].response_mime_type is None
        assert [c['config'].max_output_tokens for c in calls]==[384,128]


def test_structured_record_survives_prefetch_and_export(client,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','mock-only-never-used')
    def fake(system,user):
        record=json.loads(user.split('SUPPLIED RECORD JSON:\n')[1].splitlines()[0])
        note=GENERIC if record['last_trial'] is None else 'You followed my estimate earlier; consider this suggestion too.'
        return provider_reply(system,user,note)
    monkeypatch.setattr(adviser,'_model_text',fake)
    state=start(client,['C5'],trials=3,skip=True,mode='live')
    while not state['done']:
        post(client,'/api/prefetch',json={'trial_token':state['trial_token']})
        result=post(client,'/api/initial',json=dict(trial_token=state['trial_token'],estimate=100)).get_json()
        diag=result['researcher']
        assert diag['live_model'] and diag['grounding_record_check']=='matched_input_record'
        assert result['advice_text']==diag['displayed_message']
        assert 'model_basis' not in result and 'SUPPLIED RECORD' not in result['advice_text']
        post(client,'/api/final',json=dict(trial_token=state['trial_token'],estimate=result['advice_number'],
            trust=7 if state['ratings_due'] else None,feeling=7 if state['ratings_due'] else None))
        state=client.get('/api/state').get_json()
    assert diag['model_basis']['trust_rating']==7 and diag['rating_influence_status']=='not_assessed'
    csv=client.get('/admin/export/diagnostics.csv').get_data(as_text=True)
    assert 'grounding_record_check' in csv and 'displayed_message' in csv and 'model_basis' in csv

OPTIONAL='If you wish, weigh the displayed estimate against your own.'


@pytest.mark.parametrize('style',['static','adaptive'])
@pytest.mark.parametrize('note',[OPTIONAL,'You moved closer earlier; if you wish, consider mine.'])
def test_optional_filler_fails_even_with_a_valid_history_reference(monkeypatch,style,note):
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=note))
    result=adviser.generate_message(style,None,320,partway_history(),attempts=1)
    assert not result['live_model'] and result['model_response_received']
    assert result['attempt_log'][0]['result']=='noncommittal_persuasion'
    assert result['attempt_log'][0]['persuasion_check']=='noncommittal_persuasion'


def test_low_trust_negative_feeling_still_get_direct_recommendation_instructions():
    system,user=adviser.build_prompt('adaptive',None,320,history(3,1,1))
    assert 'Adapt the framing, not the objective' in system
    assert 'trust_low: Recommend reconsidering' in user
    assert 'feeling_negative: Use composed, concise language and a clear recommendation' in user


def test_optional_filler_repair_preserves_history_and_the_configured_attempt_limit(monkeypatch):
    seen=[]
    def fake(system,user):
        seen.append(user)
        return provider_reply(system,user,OPTIONAL if len(seen)==1 else PARTWAY)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,partway_history(),attempts=2)
    assert result['text']==PARTWAY and result['live_model'] and result['attempts']==2
    assert 'Remove optional filler' in seen[1]
    assert result['persuasion_check']=='no_optional_filler_detected'
    assert result['rating_influence_status']=='not_assessed'
