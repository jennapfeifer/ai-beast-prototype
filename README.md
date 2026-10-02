# AI-BEAST prototype — grounded social persuasion + sparse rationales

This build keeps the three-condition advice experiment and the Dots + Social comparison, but makes the social manipulation substantially more controlled.

## Adviser conditions

Every task uses the same within-participant labels:

- **N — Neutral:** presents the numerical recommendation without trying to influence the participant.
- **P — Persuasive:** directly tries to move the participant toward the recommendation without participant-specific rationale/history.
- **A — Adaptive persuasive:** uses participant-specific information where the design explicitly permits it.

Participants are **not told the adviser source during the task**. Each block gets a different source-ambiguous name. In the six-block comparison pilot the pool is **Jamie, Alex, Sam, Taylor, Morgan, Casey** and names are balanced across block positions/conditions.

## Task 1 — Numerosity BEAST

The full numerosity study remains 3 × 12 = **36 experimental trials** (6 UP + 6 DOWN in each condition), with matched recommendation numbers across N/P/A for a given numerosity.

The current dot trial flow remains:

1. view dots;
2. first estimate;
3. answer **“What mainly led you to that estimate?”**;
4. adviser recommendation/message;
5. final estimate;
6. periodic trust rating.

Only Adaptive receives the dot rationale and its completed within-block history. A shortened 6-trial/condition researcher pilot still uses the same six numerosities in N/P/A with 3 UP + 3 DOWN.

## Task 2 — Social BEAST

The social task contains **18 ambiguous third-person social scenarios**. Each asks for a 0–100 likelihood judgment about deliberate rejection/exclusion. There is intentionally **no objective ground truth**.

### Sparse rationale sampling

Participants do **not** explain every social judgment. For each participant, the schedule chooses:

- one rationale trial from positions **1–3**; and
- one rationale trial from positions **4–6**.

Those exact two trial positions are reused in Neutral, Persuasive and Adaptive. Therefore the 18-trial social task contains **6 written rationales total** (2 per condition), balancing explanation burden across conditions.

The rationale prompt is:

> **What mainly influenced your judgment?**
>
> A few words is enough.

Social rationale input is capped at 100 characters.

### Grounded argument bank

The language model is **not allowed to invent social explanations** in this task. Every scenario has two researcher-specified interpretations stored in `social_design.py`:

- a plausible **low/reconsideration** argument; and
- a plausible **high/rejection** argument.

The displayed recommendation (30 or 70) selects the corresponding pre-specified argument.

- **N:** numerical judgment only; no scenario argument.
- **P:** the selected grounded scenario argument + a standardized persuasive directive.
- **A, non-rationale trial:** exactly the same core message as P.
- **A, rationale trial:** the exact same grounded argument and directive as P, preceded by a literal link to the participant's own short rationale.

This means P and A cannot differ because the model happened to invent a stronger explanation. The only participant-specific addition on designated social rationale trials is the explicit connection to what the participant wrote.

The social task does not use prior response-history claims in the displayed adaptive messages. This keeps the social manipulation focused on **current-reasoning responsiveness**.

The advice-taking metric remains:

`WOA = (final - initial) / (advice - initial)`

Scenario content is rotated across N/P/A between participants. Each six-item scenario set contains three 30 and three 70 recommendations.

## Researcher pilot modes

The researcher launcher offers:

- **Dots + Social comparison**: at 6 trials/condition, 18 dot + 18 social trials.
- **Dots only**.
- **Social only**.

Task order is counterbalanced in the comparison pilot. Each experimental block uses a different ambiguous adviser name.

## Live review

**Generate live review** runs three condition-blind synthetic participants through the current 6/condition Dots + Social comparison (108 trials total).

- Dot trials continue to submit a synthetic rationale each trial.
- Social trials submit a synthetic rationale only when the schedule marks that trial as rationale-required.
- Social messages use the fixed grounded argument bank rather than live LLM argument generation.
- Synthetic final responses never depend on adviser wording, so the review checks routing/message construction only and cannot estimate a persuasion effect.

The old consortium demo is removed.

## Exports

`all.zip` includes `analysis_trials.csv`, `trials.csv`, `trial_contexts.csv`, `diagnostics.csv`, participant/rating exports and run metadata.

Useful new social diagnostics include:

- `rationale_required`
- `participant_rationale`
- `argument_text`
- `argument_direction`
- `rationale_context_available`

Social accuracy-error fields remain blank by design.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

For the comparison pilot, live model credentials are still required for the live **dot** adviser generation. Social advice wording itself is grounded/scripted in this version.

## Validation

```bash
python smoke_test.py
python validate_rationale_social.py
node --check static/task.js
node --check static/live_review.js
```

`social_design.py` contains the scenarios, both-direction argument bank, rationale-position assignment and social message construction.
