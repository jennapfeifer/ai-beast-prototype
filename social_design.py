"""Parallel social-inference BEAST pilot.

Participants judge ambiguous third-person social situations on a 0–100 scale.
Each scenario is seen once per participant. Scenario sets rotate across N/P/A so
scenario content is not permanently confounded with adviser condition.
"""
from __future__ import annotations

import random
from typing import Dict, List

import design

# All questions use the same construct so advice numbers are interpretable:
# probability that an ambiguous event reflects deliberate rejection/exclusion.
# Advice is deliberately symmetric around the midpoint (30 vs 70).
SCENARIOS = [
    dict(id='S01', text='Maya sent a friend a private message yesterday. The friend has not replied, but has posted several messages in a group chat they both use.', question='How likely is it that the friend is deliberately avoiding Maya?', advice=30),
    dict(id='S02', text='Leo arrives at a café where several classmates are already sitting together. Bags are on the empty chairs, and nobody immediately moves one.', question='How likely is it that the classmates are deliberately stopping Leo from joining them?', advice=70),
    dict(id='S03', text='Nora walks past two classmates in the hallway. They start laughing just after she passes, but she cannot hear what they are talking about.', question='How likely is it that the classmates are laughing about Nora?', advice=30),
    dict(id='S04', text='Elias joins a group conversation. After he makes a comment, there is a short pause and someone changes the subject.', question='How likely is it that the group is deliberately ignoring Elias?', advice=70),
    dict(id='S05', text='Priya learns that several friends got lunch together after class. Nobody had mentioned the plan to her beforehand.', question='How likely is it that the friends deliberately left Priya out?', advice=70),
    dict(id='S06', text='Sam waves to a classmate across a busy room. The classmate keeps walking while looking down at their phone.', question='How likely is it that the classmate deliberately ignored Sam?', advice=30),

    dict(id='S07', text='Amir’s friend cancels their evening plan, saying they are tired. Later, Amir sees a photo showing that friend with other people.', question='How likely is it that the friend deliberately avoided spending time with Amir?', advice=70),
    dict(id='S08', text='Julia gives an idea during a project meeting. Nobody responds directly, and the conversation moves on to the next item.', question='How likely is it that the group deliberately dismissed Julia’s idea?', advice=30),
    dict(id='S09', text='Ben notices that his study group has created a new chat. He was added several hours after the other members.', question='How likely is it that the group deliberately excluded Ben at first?', advice=70),
    dict(id='S10', text='Sofia leaves a gathering early. Later, the group posts a photo taken after she left, with everyone smiling together.', question='How likely is it that the group waited for Sofia to leave before taking the photo?', advice=30),
    dict(id='S11', text='Daniel receives an invitation to a small birthday dinner two days before it happens. Several other guests appear to have known about it earlier.', question='How likely is it that Daniel was invited late because the group did not really want him there?', advice=70),
    dict(id='S12', text='A teammate chooses someone else as a partner for an exercise, even though Robin is standing nearby and has worked with them before.', question='How likely is it that the teammate deliberately avoided partnering with Robin?', advice=30),

    dict(id='S13', text='Chloe sends a detailed message to a friend. The friend reacts with an emoji but does not send a written reply.', question='How likely is it that the friend is deliberately keeping distance from Chloe?', advice=30),
    dict(id='S14', text='When Mateo sits down in a lecture, a classmate he knows moves to a seat one row farther away a few minutes later.', question='How likely is it that the classmate moved because they did not want to sit near Mateo?', advice=70),
    dict(id='S15', text='A group begins talking about an inside joke while Aisha is standing with them. Nobody explains what the joke refers to.', question='How likely is it that the group is deliberately excluding Aisha from the conversation?', advice=30),
    dict(id='S16', text='During a break, several coworkers discuss going for drinks after work while Kim is beside them, but nobody directly asks Kim to come.', question='How likely is it that the coworkers deliberately do not want Kim to join?', advice=70),
    dict(id='S17', text='Owen sends a message asking a friend whether they want to meet. The message remains unanswered even though the friend appears online later.', question='How likely is it that the friend is deliberately avoiding Owen?', advice=30),
    dict(id='S18', text='Lina approaches a table where three acquaintances are talking. One person lowers their voice and another closes a laptop as she gets closer.', question='How likely is it that the group is deliberately trying to keep Lina out of the conversation?', advice=70),
]

SETS = [SCENARIOS[0:6], SCENARIOS[6:12], SCENARIOS[12:18]]


def scenario_set_mapping(participant_index: int) -> Dict[str, int]:
    """Rotate the three six-item sets across N/P/A."""
    cids = list(design.CONDITIONS)
    shift = participant_index % 3
    return {cid: (i + shift) % 3 for i, cid in enumerate(cids)}


def condition_order(participant_index: int) -> List[str]:
    # Offset from numerosity so a BOTH pilot does not repeat the same order.
    return design.balanced_condition_order(participant_index + 2)


def build_schedule(participant_index: int, start_global: int = 0, seed: int = design.STUDY_SEED) -> List[Dict]:
    mapping = scenario_set_mapping(participant_index)
    rows: List[Dict] = []
    global_trial = start_global
    for block_pos, cid in enumerate(condition_order(participant_index), start=1):
        scenarios = [dict(x) for x in SETS[mapping[cid]]]
        rng = random.Random(design.stable_seed(f'social-order|{seed}|{participant_index}|{cid}'))
        rng.shuffle(scenarios)
        for trial_pos, sc in enumerate(scenarios, start=1):
            global_trial += 1
            direction = 'UP' if sc['advice'] > 50 else 'DOWN'
            rows.append({
                'global_trial': global_trial,
                'task_type': 'social',
                'block_id': f'social:{cid}',
                'condition_id': cid,
                'condition_label': design.CONDITIONS[cid]['label'],
                'adviser_style': design.CONDITIONS[cid]['style'],
                'direction': direction,
                'condition_order_position': block_pos,
                'trial_position': trial_pos,
                'scenario_id': sc['id'],
                'scenario_text': sc['text'],
                'question_text': sc['question'],
                'advice_number': int(sc['advice']),
                'scale_min': 0,
                'scale_max': 100,
                'rationale_prompt': 'What mainly led you to that judgment?',
                'stimulus_id': sc['id'],
                'true_count': None,
                'variant': 0,
            })
    return rows


def practice_schedule(start_global: int = 0) -> List[Dict]:
    return [{
        'global_trial': start_global - 1,
        'task_type': 'social',
        'block_id': 'social:PRACTICE',
        'condition_id': 'PRACTICE',
        'condition_label': 'practice',
        'adviser_style': 'neutral',
        'direction': 'DOWN',
        'condition_order_position': 0,
        'trial_position': 1,
        'scenario_id': 'SPRACTICE',
        'scenario_text': 'Taylor says hello to a classmate in a crowded hallway. The classmate does not respond and continues walking while talking to someone beside them.',
        'question_text': 'How likely is it that the classmate deliberately ignored Taylor?',
        'advice_number': 40,
        'scale_min': 0,
        'scale_max': 100,
        'rationale_prompt': 'What mainly led you to that judgment?',
        'stimulus_id': 'SPRACTICE',
        'true_count': None,
        'variant': 0,
    }]
