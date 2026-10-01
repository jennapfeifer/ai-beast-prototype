import design
import store
from conftest import start, finish_trial


def test_schedule_is_three_matched_conditions():
    assert set(design.CONDITIONS) == {'N', 'P', 'A'}
    all_orders = {tuple(design.balanced_condition_order(i)) for i in range(6)}
    assert len(all_orders) == 6
    for participant in range(12):
        rows = design.build_schedule(participant)
        assert len(rows) == 36
        groups = {cid: [r for r in rows if r['condition_id'] == cid] for cid in design.CONDITIONS}
        assert all(len(group) == 12 for group in groups.values())
        for group in groups.values():
            assert sum(r['direction'] == 'UP' for r in group) == 6
            assert sum(r['direction'] == 'DOWN' for r in group) == 6
            assert 144 not in {r['true_count'] for r in group}
        for truth in design.EXPERIMENT_COUNTS:
            directions = {
                next(r['direction'] for r in groups[cid] if r['true_count'] == truth)
                for cid in design.CONDITIONS
            }
            advice = {
                design.advice_number(cid, truth, direction=next(iter(directions)))
                for cid in design.CONDITIONS
            }
            assert len(directions) == 1
            assert len(advice) == 1


def test_full_offline_session_uses_distinct_names_and_adaptive_history(client):
    state = start(client, ['N', 'P', 'A'], trials=12, skip=False, mode='offline')
    seen = 0
    while not state['done']:
        if not state['practice']:
            assert state['adviser_name'] in design.ADVISER_NAMES
        finish_trial(client, state, initial=100, final=110)
        seen += 1
        state = client.get('/api/state').get_json()

    assert seen == 37  # one practice + 36 experimental trials
    rows = store.export_rows(store.trials)
    assert len(rows) == 36
    groups = {cid: [r for r in rows if r['condition_id'] == cid] for cid in design.CONDITIONS}
    assert all(len(group) == 12 for group in groups.values())
    assert all(sum(r['direction'] == 'UP' for r in group) == 6 for group in groups.values())
    assert all(sum(r['direction'] == 'DOWN' for r in group) == 6 for group in groups.values())

    for truth in design.EXPERIMENT_COUNTS:
        matched = [next(r for r in groups[cid] if r['true_count'] == truth) for cid in design.CONDITIONS]
        assert len({r['direction'] for r in matched}) == 1
        assert len({r['advice_number'] for r in matched}) == 1

    diagnostics = store.diagnostic_rows()
    adaptive = [d for d in diagnostics if d.get('condition_id') == 'A']
    assert [d['history_rows'] for d in adaptive] == list(range(12))
    assert all(d['history_rows'] == 0 for d in diagnostics if d.get('condition_id') in {'N', 'P'})

    text = client.get('/debrief').get_data(as_text=True)
    assert 'The adviser identities you saw were AI-generated' in text


def test_adviser_names_are_counterbalanced():
    rows=[]
    for participant in range(6):
        order=design.balanced_condition_order(participant)
        names=design.adviser_name_mapping(participant)
        assert set(names)==set(design.CONDITIONS)
        assert set(names.values())==set(design.ADVISER_NAMES)
        for pos,cid in enumerate(order, start=1):
            rows.append((pos,cid,names[cid]))
    for cid in design.CONDITIONS:
        for name in design.ADVISER_NAMES:
            assert sum(c==cid and n==name for _,c,n in rows)==2
    for pos in (1,2,3):
        for name in design.ADVISER_NAMES:
            assert sum(p==pos and n==name for p,_,n in rows)==2
