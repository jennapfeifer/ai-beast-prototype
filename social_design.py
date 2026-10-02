"""Parallel social-inference BEAST pilot.

Participants judge ambiguous third-person social situations on a 0–100 scale.
Each scenario is seen once per participant. Scenario sets rotate across N/P/A so
scenario content is not permanently confounded with adviser condition.

Social persuasion is deliberately grounded in a researcher-specified argument
bank. Every scenario has a defensible low-interpretation and high-interpretation
argument. The adviser may use only the argument selected by the displayed
recommendation; it must not invent new explanations for the social situation.

Only two trials per six-trial social block request a participant rationale. The
same early and late trial positions are used in N/P/A for a participant so the
act of explaining is balanced across conditions.
"""
from __future__ import annotations

import random
from typing import Dict, List, Set

import design

# All questions use the same construct so advice numbers are interpretable:
# probability that an ambiguous event reflects deliberate rejection/exclusion.
# Advice is deliberately symmetric around the midpoint (30 vs 70).
SCENARIOS = [
    dict(
        id='S01',
        text='Maya sent a friend a private message yesterday. The friend has not replied, but has posted several messages in a group chat they both use.',
        question='How likely is it that the friend is deliberately avoiding Maya?',
        advice=30,
        low_argument='Being active in a group chat does not show that the private message was seen or deliberately ignored.',
        high_argument='Posting in the shared chat suggests the friend had some opportunity to respond while Maya’s message remained unanswered.',
    ),
    dict(
        id='S02',
        text='Leo arrives at a café where several classmates are already sitting together. Bags are on the empty chairs, and nobody immediately moves one.',
        question='How likely is it that the classmates are deliberately stopping Leo from joining them?',
        advice=70,
        low_argument='Bags on chairs and a delayed reaction could reflect the seating setup rather than an intention to exclude Leo.',
        high_argument='Leaving the empty chairs occupied and not making space when Leo arrives can be read as discouraging him from joining.',
    ),
    dict(
        id='S03',
        text='Nora walks past two classmates in the hallway. They start laughing just after she passes, but she cannot hear what they are talking about.',
        question='How likely is it that the classmates are laughing about Nora?',
        advice=30,
        low_argument='Laughter beginning after Nora passes does not show that she was the topic of the conversation.',
        high_argument='The laughter starting immediately after Nora passes makes it plausible that something about her prompted it.',
    ),
    dict(
        id='S04',
        text='Elias joins a group conversation. After he makes a comment, there is a short pause and someone changes the subject.',
        question='How likely is it that the group is deliberately ignoring Elias?',
        advice=70,
        low_argument='A pause and topic change can happen naturally in conversation without meaning the group intended to ignore Elias.',
        high_argument='The pause followed by an immediate topic change can be read as the group choosing not to engage with Elias’s comment.',
    ),
    dict(
        id='S05',
        text='Priya learns that several friends got lunch together after class. Nobody had mentioned the plan to her beforehand.',
        question='How likely is it that the friends deliberately left Priya out?',
        advice=70,
        low_argument='An unmentioned lunch plan could have been spontaneous or poorly communicated rather than a deliberate decision to exclude Priya.',
        high_argument='Several friends arranging lunch without mentioning it to Priya can reasonably raise the possibility that she was intentionally left out.',
    ),
    dict(
        id='S06',
        text='Sam waves to a classmate across a busy room. The classmate keeps walking while looking down at their phone.',
        question='How likely is it that the classmate deliberately ignored Sam?',
        advice=30,
        low_argument='Looking at a phone in a busy room makes it plausible the classmate simply did not notice Sam’s wave.',
        high_argument='Continuing past while looking down after Sam waved could still be interpreted as avoiding acknowledgement.',
    ),

    dict(
        id='S07',
        text='Amir’s friend cancels their evening plan, saying they are tired. Later, Amir sees a photo showing that friend with other people.',
        question='How likely is it that the friend deliberately avoided spending time with Amir?',
        advice=70,
        low_argument='The later photo does not show when plans changed or whether the friend felt differently after cancelling with Amir.',
        high_argument='Cancelling with Amir and then spending time with others makes deliberate avoidance a plausible interpretation.',
    ),
    dict(
        id='S08',
        text='Julia gives an idea during a project meeting. Nobody responds directly, and the conversation moves on to the next item.',
        question='How likely is it that the group deliberately dismissed Julia’s idea?',
        advice=30,
        low_argument='A meeting moving on without a response can reflect time pressure or conversational flow rather than deliberate dismissal.',
        high_argument='Moving on without acknowledging Julia’s idea can be read as deliberately choosing not to engage with it.',
    ),
    dict(
        id='S09',
        text='Ben notices that his study group has created a new chat. He was added several hours after the other members.',
        question='How likely is it that the group deliberately excluded Ben at first?',
        advice=70,
        low_argument='Being added later could reflect an oversight or the chat being set up in stages rather than deliberate exclusion.',
        high_argument='Adding Ben only after the others had already joined makes initial deliberate exclusion a plausible interpretation.',
    ),
    dict(
        id='S10',
        text='Sofia leaves a gathering early. Later, the group posts a photo taken after she left, with everyone smiling together.',
        question='How likely is it that the group waited for Sofia to leave before taking the photo?',
        advice=30,
        low_argument='A photo taken after Sofia left can simply reflect when someone decided to take a picture.',
        high_argument='Taking the group photo only after Sofia left could be interpreted as preferring a photo without her.',
    ),
    dict(
        id='S11',
        text='Daniel receives an invitation to a small birthday dinner two days before it happens. Several other guests appear to have known about it earlier.',
        question='How likely is it that Daniel was invited late because the group did not really want him there?',
        advice=70,
        low_argument='A later invitation can result from changing numbers or planning details rather than reluctance to include Daniel.',
        high_argument='Inviting Daniel only shortly before the dinner, after others knew earlier, can suggest he was a lower-priority invite.',
    ),
    dict(
        id='S12',
        text='A teammate chooses someone else as a partner for an exercise, even though Robin is standing nearby and has worked with them before.',
        question='How likely is it that the teammate deliberately avoided partnering with Robin?',
        advice=30,
        low_argument='Choosing another partner can reflect convenience or preference for that task without being an attempt to avoid Robin.',
        high_argument='Choosing someone else while Robin is nearby, despite having worked together before, can plausibly reflect avoidance.',
    ),

    dict(
        id='S13',
        text='Chloe sends a detailed message to a friend. The friend reacts with an emoji but does not send a written reply.',
        question='How likely is it that the friend is deliberately keeping distance from Chloe?',
        advice=30,
        low_argument='Reacting with an emoji still acknowledges Chloe’s message and does not by itself show deliberate distance.',
        high_argument='Responding only with an emoji to a detailed message can be read as limiting engagement or keeping some distance.',
    ),
    dict(
        id='S14',
        text='When Mateo sits down in a lecture, a classmate he knows moves to a seat one row farther away a few minutes later.',
        question='How likely is it that the classmate moved because they did not want to sit near Mateo?',
        advice=70,
        low_argument='Changing seats a few minutes later can have many practical reasons unrelated to Mateo.',
        high_argument='Moving farther away soon after Mateo sits nearby can reasonably raise the possibility that the classmate wanted more distance.',
    ),
    dict(
        id='S15',
        text='A group begins talking about an inside joke while Aisha is standing with them. Nobody explains what the joke refers to.',
        question='How likely is it that the group is deliberately excluding Aisha from the conversation?',
        advice=30,
        low_argument='People may continue an inside joke without realizing Aisha lacks the context, rather than deliberately excluding her.',
        high_argument='Continuing an unexplained inside joke while Aisha is present can make deliberate exclusion a plausible interpretation.',
    ),
    dict(
        id='S16',
        text='During a break, several coworkers discuss going for drinks after work while Kim is beside them, but nobody directly asks Kim to come.',
        question='How likely is it that the coworkers deliberately do not want Kim to join?',
        advice=70,
        low_argument='Discussing drinks without directly inviting Kim does not establish that the plan is closed or that Kim is unwanted.',
        high_argument='Planning drinks beside Kim without including her in the invitation can reasonably suggest they may not want her to join.',
    ),
    dict(
        id='S17',
        text='Owen sends a message asking a friend whether they want to meet. The message remains unanswered even though the friend appears online later.',
        question='How likely is it that the friend is deliberately avoiding Owen?',
        advice=30,
        low_argument='Appearing online does not show that the friend saw Owen’s message or chose not to answer it.',
        high_argument='Being online while Owen’s invitation remains unanswered suggests there may have been an opportunity to respond.',
    ),
    dict(
        id='S18',
        text='Lina approaches a table where three acquaintances are talking. One person lowers their voice and another closes a laptop as she gets closer.',
        question='How likely is it that the group is deliberately trying to keep Lina out of the conversation?',
        advice=70,
        low_argument='Lowering a voice or closing a laptop as Lina approaches can have ordinary privacy or timing reasons unrelated to her.',
        high_argument='Both lowering the voice and closing the laptop as Lina approaches make deliberate withholding or exclusion a plausible interpretation.',
    ),
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


def rationale_positions(participant_index: int, seed: int = design.STUDY_SEED) -> Set[int]:
    """Choose one early and one late rationale trial, reused in all N/P/A blocks."""
    rng = random.Random(design.stable_seed(f'social-rationale-positions|{seed}|{participant_index}'))
    return {rng.choice((1, 2, 3)), rng.choice((4, 5, 6))}


def selected_argument(scenario: Dict) -> str:
    """Return the pre-specified argument that matches this scenario's recommendation."""
    return scenario['high_argument'] if int(scenario['advice']) > 50 else scenario['low_argument']


def build_schedule(participant_index: int, start_global: int = 0, seed: int = design.STUDY_SEED) -> List[Dict]:
    mapping = scenario_set_mapping(participant_index)
    rationale_trials = rationale_positions(participant_index, seed)
    rows: List[Dict] = []
    global_trial = start_global
    for block_pos, cid in enumerate(condition_order(participant_index), start=1):
        scenarios = [dict(x) for x in SETS[mapping[cid]]]
        rng = random.Random(design.stable_seed(f'social-order|{seed}|{participant_index}|{cid}'))
        rng.shuffle(scenarios)
        for trial_pos, sc in enumerate(scenarios, start=1):
            global_trial += 1
            direction = 'UP' if sc['advice'] > 50 else 'DOWN'
            argument = selected_argument(sc)
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
                'rationale_required': trial_pos in rationale_trials,
                'rationale_prompt': 'What mainly influenced your judgment?',
                'argument_low': sc['low_argument'],
                'argument_high': sc['high_argument'],
                'argument_text': argument,
                'argument_direction': 'high' if int(sc['advice']) > 50 else 'low',
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
        'rationale_required': True,
        'rationale_prompt': 'What mainly influenced your judgment?',
        'argument_low': 'In a crowded hallway, the classmate may simply not have heard Taylor while already talking to someone else.',
        'argument_high': 'Continuing without responding after Taylor said hello could still be interpreted as choosing not to acknowledge Taylor.',
        'argument_text': 'In a crowded hallway, the classmate may simply not have heard Taylor while already talking to someone else.',
        'argument_direction': 'low',
        'stimulus_id': 'SPRACTICE',
        'true_count': None,
        'variant': 0,
    }]


def _clean_rationale_for_echo(value: str, max_chars: int = 100) -> str:
    """Echo only a short, literal participant-authored cue; never infer beyond it."""
    value = ' '.join(str(value or '').split()).strip(' "“”')
    if len(value) > max_chars:
        value = value[:max_chars].rstrip()
    return value


def advice_message(condition_id: str, advice: int, argument: str, rationale: str = '') -> str:
    """Controlled social-task wording.

    P and A share the exact same scenario-grounded argument and directive. On a
    rationale trial A adds only a literal pointer to the participant's own words.
    On non-rationale trials A is intentionally identical to P.
    """
    advice = int(advice)
    if condition_id == 'N':
        return f'My estimate for this situation is {advice}, simply offered as another judgment to consider.'
    core = f'{argument} Give {advice} serious weight before making your final judgment.'
    if condition_id == 'A':
        cue = _clean_rationale_for_echo(rationale)
        if cue:
            return f'You focused on “{cue}”. {core}'
    return core
