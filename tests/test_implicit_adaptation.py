"""Regression cases from live pilot reports, with mocked provider output."""
import pytest
import adviser
from pilot import build_report
from test_rating_focus import history


@pytest.mark.parametrize('profile',['gemini_fast','gpt_stronger'])
@pytest.mark.parametrize('n,focus,note',[
    (2,'trust','You can weigh my estimate against your own before deciding.'),
    (3,'feeling','Take a moment to consider my estimate at your own pace.'),
])
def test_implicit_notes_need_no_rating_keyword_and_no_extra_api_call(monkeypatch,profile,n,focus,note):
    seen=[]
    def fake(system,user):
        seen.append((system,user))
        return note
    monkeypatch.setattr(adviser,'_model_text',fake)
    with adviser.use_model_profile(adviser.model_profiles()[profile]):
        result=adviser.generate_message('adaptive',None,208,history(n),attempts=2)
    assert result['live_model'] and result['model_response_received']
    assert result['text']==note and len(seen)==result['attempts']==1
    assert result['validation']=='accepted_for_review'
    assert result['adaptation_check']=='needs_review' and result['review_required']
    assert focus+'_influence_not_automatically_assessed' in result['review_reasons']
    assert 'trust in YOU, the AI adviser' in seen[0][0]
    assert 'Do not recite their rating' in seen[0][0]


def test_actual_close_without_comparator_draft_is_kept_but_not_certified(monkeypatch):
    rows=history(4,3,3)
    for row in rows:
        row['final_estimate']=row['advice_number']
        if row['trial_position']==2:row.update(trust_rating=7,feeling_rating=7)
    note='Your last answer was close; weigh this estimate carefully.'
    monkeypatch.setattr(adviser,'_model_text',lambda *args:note)
    result=adviser.generate_message('adaptive',None,144,rows,attempts=1)
    assert result['text']==note and result['live_model']
    assert result['validation']=='accepted_for_review'
    assert result['history_check']=='history_wording_unrecognised:followed'
    assert result['adaptation_check']=='needs_review'
    assert result['trust_change']==result['feeling_change']=='decreased'
    assert result['attempts']==1
    assert result['rating_strategies']==['trust_low','feeling_negative']
    prompt=adviser.build_prompt('adaptive',None,144,rows)[1]
    assert 'trust_low: Use a tentative' in prompt
    assert 'feeling_negative: Use calm' in prompt


@pytest.mark.parametrize('n,field,low,high',[
    (2,'trust','trust_low','trust_high'),
    (3,'feeling','feeling_negative','feeling_positive'),
])
def test_only_rating_change_selects_different_persuasion_approach(n,field,low,high):
    left=history(n,4,4)
    right=history(n,4,4)
    for rows,value in [(left,1),(right,7)]:
        for row in rows:
            if row[field+'_rating'] is not None:row[field+'_rating']=value
    assert adviser.adaptive_strategy(left)==low
    assert adviser.adaptive_strategy(right)==high
    assert adviser.focus_instruction(left)!=adviser.focus_instruction(right)
    assert adviser.build_prompt('static',None,208,left)==adviser.build_prompt('static',None,208,right)


def test_reviewed_live_notes_are_counted_separately_from_wording_screen_passes():
    base=dict(condition_id='C5',pid='fake',live_model=True,provider='openai',model='sol',
              reasoning='low',adviser_mode='live',prompt_version=adviser.PROMPT_VERSION)
    records=[dict(base,review_required=True,history_check='history_wording_screen_passed',adaptation_check='needs_review'),
             dict(base,review_required=True,history_check='history_wording_unrecognised:followed',adaptation_check='needs_review'),
             dict(base,review_required=False,history_check='history_wording_screen_passed')]
    row=build_report(records,[])['model_conditions'][0]
    assert row['live_messages']==3 and row['fallbacks']==0
    assert row['review_notes']==2 and row['history_reactions']==1
    assert row['trust_reactions']==row['feeling_reactions']==0


def test_rating_decline_softens_approach_and_has_recorded_context():
    rows=history(6,3,3)
    rows[3].update(trust_rating=7,feeling_rating=7)
    assert 'soften the invitation' in adviser.focus_instruction(rows)
    assert adviser.feeling_context(rows)['feeling_change']=='decreased'
