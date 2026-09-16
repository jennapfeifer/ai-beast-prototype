"""Regression cases from the 13-word 'shift right' live pilot rejection."""
import pytest
import adviser
from conftest import provider_reply
from test_rating_focus import history

REPORTED='You moved away last time, so please shift right toward my estimate now.'
REPAIRED='You moved away last time; now move toward my estimate.'
LONGER='You moved away last time; now give my estimate a little more weight.'


def test_reported_note_gets_direction_repair_instead_of_word_count_rejection(monkeypatch):
    seen=[]
    def fake(system,user):
        seen.append(user)
        return provider_reply(system,user,REPORTED if len(seen)==1 else REPAIRED)
    monkeypatch.setattr(adviser,'_model_text',fake)
    result=adviser.generate_message('adaptive',None,320,history(3,7,7))
    assert adviser.words(REPORTED)==13 and adviser.message_is_valid(REPORTED)[0]
    assert result['text']==REPAIRED and result['live_model'] and result['attempts']==2
    rejected=result['attempt_log'][0]
    assert rejected['result']=='current_direction_unknown'
    assert rejected['word_count_check']=='slightly_over_target' and rejected['grounding_record_check']=='matched_input_record'
    assert "move toward my estimate" in seen[1] and 'Keep the supported history reference' in seen[1]
    assert result['history_check']=='history_wording_screen_passed'


@pytest.mark.parametrize('style',['adaptive','static','neutral'])
@pytest.mark.parametrize('tail',['',' before deciding'])
def test_small_length_overrun_is_kept_without_retry_and_flagged(monkeypatch,style,tail):
    # Static and neutral receive no history: use a length-matched neutral fixture.
    note=(LONGER if style=='adaptive' else 'This is my estimate for you to consider alongside your own initial answer.')
    note=note.rstrip('.')+tail+'.'
    assert 13<=adviser.words(note)<=15
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=note))
    result=adviser.generate_message(style,None,320,history(3,7,7))
    assert result['text']==note and result['live_model'] and result['attempts']==1
    assert result['word_count_check']=='slightly_over_target'
    assert 'word_count_slightly_over_target' in result['review_reasons']
    assert result['validation']=='accepted_for_review'


def test_length_tolerance_does_not_rescue_wrong_history(monkeypatch):
    note='You followed my estimate last time; now give my estimate a little more weight.'
    monkeypatch.setattr(adviser,'_model_text',lambda *args:provider_reply(*args,note=note))
    result=adviser.generate_message('adaptive',None,320,history(3,7,7),attempts=1)
    assert not result['live_model'] and 'history' in result['attempt_log'][0]['result']
    assert result['attempt_log'][0]['word_count_check']=='slightly_over_target'


def test_hard_length_bound_and_optional_strict_setting(monkeypatch):
    assert adviser.message_is_valid(LONGER)[0]
    too_long=LONGER.rstrip('.')+' before deciding again.'
    assert adviser.words(too_long)==16
    assert adviser.message_is_valid(too_long)==(False,'word_count=16')
    monkeypatch.setattr(adviser,'ADVISER_WORD_TOLERANCE',0)
    assert adviser.message_is_valid(LONGER)==(False,'word_count=13')


@pytest.mark.parametrize('phrase',['shift right','move left','adjust your estimate up','revise lower',
                                   'raise your estimate','lower your answer'])
def test_current_direction_needs_current_initial(phrase):
    assert adviser.direction_wording_check('Please '+phrase+' toward my estimate.',None,320)==(False,'current_direction_unknown')


def test_direction_check_distinguishes_current_commands_from_past_history():
    assert adviser.direction_wording_check('You moved right earlier; now move toward my estimate.',None,320)[0]
    assert adviser.direction_wording_check(REPORTED,300,320)==(True,'current_direction_consistent')
    assert adviser.direction_wording_check(REPORTED,350,320)==(False,'current_direction_conflict')
    assert adviser.direction_wording_check(REPORTED,320,320)==(False,'current_direction_conflict')
