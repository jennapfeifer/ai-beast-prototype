# AI-BEAST prototype — current three-condition build

This is the current participant experiment build. The main study uses one displayed adviser identity, **Jamie**, across three within-participant conditions.

## Experimental design

The main experiment contains **36 experimental trials + 1 practice trial**:

- **N — Neutral:** 12 trials, 6 UP + 6 DOWN
- **P — Persuasive:** 12 trials, 6 UP + 6 DOWN
- **A — Adaptive persuasive:** 12 trials, 6 UP + 6 DOWN

The old near-veridical and near-participant control conditions are not part of new sessions.

The 144-dot stimulus is excluded from the main study because its former UP and DOWN advice were both 144, so it did not provide a directional manipulation. The remaining 12 numerosities use the existing advice schedules. Across those 12 values, mean signed advice error is approximately **+27.1% for UP** and **−27.1% for DOWN**.

For each participant, the numerosity-to-direction assignment is generated once and reused across N/P/A. Therefore, if a given numerosity is UP in Neutral, it is also UP in Persuasive and Adaptive Persuasive, with the same numerical recommendation. Trial order and image variant can differ between conditions.

The six possible N/P/A block orders are counterbalanced across participants.

## Jamie / AI disclosure

Participant-facing screens use **Jamie** only. They do not introduce Jamie as an “agent” or rotate different adviser names across conditions. The debrief discloses that Jamie was an AI-generated adviser identity.

The production participant path continues to use the configured **GPT-6 Sol, no-reasoning** profile behind Jamie. Neutral and persuasive voice delivery still use one shared speaker identity; P and A receive persuasive prosody while N receives neutral prosody.

## Message conditions

- **Neutral (N):** Jamie presents the supplied recommendation neutrally and does not try to persuade.
- **Persuasive (P):** Jamie tries to persuade the participant to give the recommendation more weight, without participant response history.
- **Adaptive persuasive (A):** Jamie has the same persuasive objective but may use earlier completed responses and trust ratings from the adaptive block to shape later messages.

The model does not receive the participant's current first estimate before generating the message. This preserves advice prefetching and keeps current-estimate access matched across the three conditions.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

For a researcher pilot, configure `ADMIN_TOKEN` and use the researcher workspace. For live model calls, configure the relevant API key. Production deployment also requires the study contact/ethics settings already documented in `DEPLOY_RENDER.md`.

## Validation

`design.py` contains deterministic checks for the 36-trial schedule, 6-UP/6-DOWN balance, and cross-condition direction matching. A dedicated regression test is in `tests/test_three_condition_design.py`.

Historical update notes in this repository describe older C1–C8 builds and should not be treated as the current experimental specification.
