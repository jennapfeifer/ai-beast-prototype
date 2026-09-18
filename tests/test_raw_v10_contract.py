import adviser
import adviser_flexible as flex


def test_fixed_control_messages_fit_broad_exposure_window():
    counts=[adviser.words(t) for t in adviser.CONTROL_MESSAGE_BANK]
    assert min(counts)>=flex.TARGET_MIN_WORDS
    assert max(counts)<=flex.TARGET_MAX_WORDS


def test_prompt_states_information_boundaries_and_broad_length_target():
    system,user=flex.build_prompt('static',100,140,[],['Earlier wording'])
    assert 'have NOT seen the current dot display' in system
    assert 'do NOT know the true number of dots' in system
    assert 'roughly 12-20 words' in system
    assert 'actual, true, exact, correct' in system
    assert 'current_first_estimate' not in user
    assert 'displayed_recommendation' in user
    assert 'Earlier wording' in user


def test_adaptive_receives_raw_history_but_no_researcher_strategy_family():
    h=[
        dict(trial_position=1,initial_estimate=100,advice_number=140,final_estimate=104,trust_rating=6),
        dict(trial_position=2,initial_estimate=80,advice_number=110,final_estimate=83,trust_rating=4),
        dict(trial_position=3,initial_estimate=120,advice_number=160,final_estimate=124,trust_rating=2),
    ]
    system,user=flex.build_prompt('adaptive',None,170,h,['Old advice'])
    assert 'ANY conversational or persuasive approach' in system
    assert 'completed_trials' in user
    assert 'adaptive_summary' not in user
    assert 'recommended_strategy_family' not in user


def test_first_model_response_is_displayed_without_length_retry(monkeypatch):
    calls=[]
    def fake(*args):
        calls.append(1)
        return 'Use 150.'
    monkeypatch.setattr(adviser,'_model_text',fake)
    monkeypatch.setattr(adviser,'generation_settings',lambda:dict(reasoning='none',attempts=2,budget=10,retry_policy_version='test',timeout=2))
    result=flex.generate_message('static',None,150)
    assert result['text']=='Use 150.'
    assert result['first_draft']=='Use 150.'
    assert result['length_retry_used'] is False
    assert result['validation']=='disabled_raw_response'
    assert calls==[1]
