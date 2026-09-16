"""Regression checks for generic successful API output and wrong-history reactions."""
import pytest
import adviser


GENERIC = 'Consider blending your own perspective with this thoughtful suggestion.'


def rows(final, initial=100, advice=120):
    return [dict(trial_position=1, initial_estimate=initial, advice_number=advice,
                 final_estimate=final, advice_text='Consider giving my estimate some weight before deciding.')]


@pytest.mark.parametrize('final,route,note', [
    (100, 'stayed', 'You kept your estimate earlier; consider giving mine more weight.'),
    (90, 'away', 'You moved away previously; consider giving my estimate more weight.'),
    (110, 'partway', 'You moved partway earlier; consider moving closer to my estimate.'),
    (120, 'followed', 'You followed my estimate earlier; consider this suggestion too.'),
    (140, 'beyond', 'You went beyond my estimate previously; consider staying nearer mine.'),
])
def test_reaction_matches_completed_response(final, route, note):
    assert adviser.recent_response(rows(final)) == route
    assert adviser.message_is_valid(note)[0]
    assert adviser.adaptive_history_check(note, rows(final))[0]
    assert not adviser.adaptive_history_check(GENERIC, rows(final))[0]


def test_successful_api_with_generic_note_is_not_accepted_as_adaptation(monkeypatch):
    monkeypatch.setattr(adviser, '_model_text', lambda *args: GENERIC)
    adaptive = adviser.generate_message('adaptive', None, 125, rows(100), attempts=1)
    static = adviser.generate_message('static', None, 125, rows(100), attempts=1)
    assert adaptive['source'].startswith('fallback:') and not adaptive['live_model']
    assert adaptive['history_check'] == 'fallback_not_adaptive'
    assert adaptive['attempt_log'][0]['result'] == 'missing_history_reaction'
    assert adaptive['attempt_log'][0]['draft'] == GENERIC
    assert static['live_model'] and static['text'] == GENERIC


def test_repair_receives_observed_response_and_logs_rejected_draft(monkeypatch):
    seen = []
    def fake(system, user):
        seen.append(user)
        return GENERIC if len(seen) == 1 else 'You kept your estimate earlier; consider giving mine more weight.'
    monkeypatch.setattr(adviser, '_model_text', fake)
    result = adviser.generate_message('adaptive', None, 125, rows(100), attempts=2)
    assert result['live_model'] and result['attempts'] == 2
    assert result['history_route'] == 'stayed'
    assert result['history_check'] == 'history_wording_screen_passed'
    assert result['attempt_log'][0]['result'] == 'missing_history_reaction'
    assert adviser.REACTION_FACTS['stayed'] in seen[1]
    assert len(result['prompt_sha256']) == 64


def test_wrong_or_negated_history_claims_fail():
    assert not adviser.adaptive_history_check('You followed my estimate earlier; consider this suggestion too.', rows(100))[0]
    assert not adviser.adaptive_history_check("You never followed my estimate earlier; consider it now.", rows(120))[0]
    assert not adviser.adaptive_history_check('You kept your estimate earlier; consider mine now.', rows(120))[0]


def test_latest_response_takes_priority_after_behaviour_changes():
    history = rows(100) * 3 + rows(120)
    history[-1]['trial_position'] = 4
    assert adviser.recent_response(history) == 'followed'
    _, prompt = adviser.build_prompt('adaptive', None, 125, history)
    assert adviser.REACTION_FACTS['followed'] in prompt
    assert not adviser.adaptive_history_check('You kept your estimate earlier; consider mine now.', history)[0]


def test_direction_symmetry_and_equal_estimates():
    assert adviser.recent_response(rows(120, 100, 80)) == 'away'
    assert adviser.recent_response(rows(90, 100, 80)) == 'partway'
    assert adviser.recent_response(rows(80, 100, 80)) == 'followed'
    assert adviser.recent_response(rows(60, 100, 80)) == 'beyond'
    aligned = rows(105, 100, 100)
    assert adviser.recent_response(aligned) == 'aligned'
    assert adviser.adaptive_history_check('Our estimates matched previously; consider this suggestion on its merits.', aligned)[0]
    assert not adviser.adaptive_history_check('You followed my estimate earlier; consider this suggestion too.', aligned)[0]


def test_first_trial_cannot_claim_previous_response():
    assert adviser.recent_response([]) == 'no_history'
    assert adviser.adaptive_history_check(GENERIC, [])[0]
    assert not adviser.adaptive_history_check('You kept your estimate earlier; consider mine now.', [])[0]
    assert adviser.recent_response(rows(float('nan'))) == 'unusable'


def test_repeated_live_note_is_retained_and_flagged(monkeypatch):
    note = 'You kept your estimate earlier; consider giving mine more weight.'
    monkeypatch.setattr(adviser, '_model_text', lambda *args: note)
    result = adviser.generate_message('adaptive', None, 125, rows(100), previous_messages=[note], attempts=1)
    assert result['live_model'] and result['text']==note
    assert result['repetition_check']=='exact_repeat'
    assert result['repetition_similarity']==1.0
    assert result['attempt_log'][0]['result']=='passed'
