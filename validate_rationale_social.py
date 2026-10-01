"""Dependency-light structural checks for the rationale/social comparison build."""
import design
import social_design
import adviser_flexible

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

for p in range(6):
    rows=social_design.build_schedule(p)
    assert len(rows)==18 and len({r['scenario_id'] for r in rows})==18
    for cid in design.CONDITIONS:
        block=[r for r in rows if r['condition_id']==cid]
        assert len(block)==6
        assert sum(r['direction']=='UP' for r in block)==3
        assert sum(r['direction']=='DOWN' for r in block)==3

rationale='They were online but did not reply.'
scenario={'text':'A friend has not replied but posted in a group chat.','question':'How likely is deliberate avoidance?'}
for style in ('neutral','static'):
    system,user=adviser_flexible.build_prompt(style,None,30,[],task_type='social',current_rationale=rationale,scenario=scenario)
    assert rationale not in user
system,user=adviser_flexible.build_prompt('adaptive',None,30,[],task_type='social',current_rationale=rationale,scenario=scenario)
assert rationale in user
assert 'MUST make the message visibly responsive' in system

for p in range(6):
    tasks=['numerosity','social'] if p%2==0 else ['social','numerosity']
    blocks=[]
    for task in tasks:
        order=design.balanced_condition_order(p) if task=='numerosity' else social_design.condition_order(p)
        blocks.extend(f'{task}:{cid}' for cid in order)
    names=design.adviser_name_mapping_for_blocks(p,blocks)
    assert len(set(names.values()))==6

print('PASS: rationale isolation, social counterbalancing, shortened dot matching, block names')
