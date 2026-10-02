"""Dependency-light structural checks for the grounded social comparison build."""
import design
import social_design

# Shortened dot comparison stays matched across N/P/A.
for p in range(12):
    full=design.build_schedule(p)
    assert len(full)==36
    subset=set(design.balanced_trial_subset(p,6))
    dm=design.direction_map(p)
    assert len(subset)==6
    assert sum(dm[x]=='UP' for x in subset)==3
    assert sum(dm[x]=='DOWN' for x in subset)==3
    for cid in design.CONDITIONS:
        rows=[r for r in full if r['condition_id']==cid and r['true_count'] in subset]
        assert {r['true_count'] for r in rows}==subset
        assert sum(r['direction']=='UP' for r in rows)==3
        assert sum(r['direction']=='DOWN' for r in rows)==3

# Social task: 18 unique items, balanced direction, exactly two rationale trials
# per block, with the same early + late positions in N/P/A.
for p in range(24):
    rows=social_design.build_schedule(p)
    assert len(rows)==18 and len({r['scenario_id'] for r in rows})==18
    rationale_positions=None
    for cid in design.CONDITIONS:
        block=[r for r in rows if r['condition_id']==cid]
        assert len(block)==6
        assert sum(r['direction']=='UP' for r in block)==3
        assert sum(r['direction']=='DOWN' for r in block)==3
        positions={r['trial_position'] for r in block if r['rationale_required']}
        assert len(positions)==2
        assert len(positions & {1,2,3})==1
        assert len(positions & {4,5,6})==1
        rationale_positions = positions if rationale_positions is None else rationale_positions
        assert positions==rationale_positions
        for r in block:
            assert r['argument_low'] and r['argument_high']
            expected=r['argument_high'] if r['advice_number']>50 else r['argument_low']
            assert r['argument_text']==expected
            assert r['argument_direction']==('high' if r['advice_number']>50 else 'low')

# Controlled social messages: P and non-rationale A are identical; rationale A
# adds only the participant-authored cue before the same grounded core argument.
example=social_design.SCENARIOS[0]
argument=social_design.selected_argument(example)
p_text=social_design.advice_message('P',example['advice'],argument,'')
a_plain=social_design.advice_message('A',example['advice'],argument,'')
a_rationale=social_design.advice_message('A',example['advice'],argument,'they were online but did not reply')
n_text=social_design.advice_message('N',example['advice'],argument,'they were online but did not reply')
assert p_text==a_plain
assert argument in p_text and argument in a_rationale
assert 'they were online but did not reply' not in p_text
assert 'they were online but did not reply' in a_rationale
assert argument not in n_text

# Scenario rotation still moves each six-item set through all three conditions.
for scenario in social_design.SCENARIOS:
    seen=[]
    for p in range(3):
        row=next(r for r in social_design.build_schedule(p) if r['scenario_id']==scenario['id'])
        seen.append(row['condition_id'])
    assert set(seen)==set(design.CONDITIONS)

# Adviser names remain unique across the six combined blocks.
for p in range(6):
    tasks=['numerosity','social'] if p%2==0 else ['social','numerosity']
    blocks=[]
    for task in tasks:
        order=design.balanced_condition_order(p) if task=='numerosity' else social_design.condition_order(p)
        blocks.extend(f'{task}:{cid}' for cid in order)
    names=design.adviser_name_mapping_for_blocks(p,blocks)
    assert len(set(names.values()))==6

print('PASS: grounded social arguments, sparse matched rationales, counterbalancing, shortened dot matching, block names')
