# AI-BEAST prototype — rationale + social-comparison pilot

This build keeps the three-condition advice experiment and adds two exploratory ways to make adviser responsiveness more meaningful.

## Adviser conditions

Every task uses the same within-participant conditions:

- **N — Neutral:** presents the numerical recommendation without trying to influence the participant.
- **P — Persuasive:** directly tries to move the participant toward the recommendation, but receives no participant-specific rationale or response history.
- **A — Adaptive persuasive:** has the same persuasive objective and receives the participant's current short rationale plus completed responses/trust ratings from that adviser block.

Participants are **not told that the advisers are AI during the task**. Each block gets a different source-ambiguous name. In the six-block comparison pilot the pool is **Jamie, Alex, Sam, Taylor, Morgan, Casey**; names are rotated across block positions. The debrief discloses that the adviser identities were AI-generated.

## Task 1 — Numerosity BEAST

The full numerosity study remains 3 × 12 = **36 experimental trials** (6 UP + 6 DOWN in each condition), with the same recommendation matched across N/P/A for a given numerosity.

Each trial is now:

1. view dots;
2. first estimate;
3. answer **“What mainly led you to that estimate?”** in one short sentence;
4. receive adviser recommendation/message;
5. final estimate;
6. periodic trust rating.

All three conditions collect the rationale. **Only A receives it.** N and P can still prefetch while the participant is estimating. A waits for the rationale before generating.

When a shortened researcher pilot is run (for example 6 trials per condition), the selected numerosities are shared across N/P/A and balanced by UP/DOWN direction, preserving matched numerical advice.

## Task 2 — Social BEAST

The parallel social task contains **18 ambiguous third-person social scenarios**. Each asks for a 0–100 likelihood judgment about deliberate rejection/exclusion. There is intentionally **no objective ground truth**.

Each trial is:

1. read the social situation;
2. initial 0–100 judgment;
3. answer **“What mainly led you to that judgment?”**;
4. receive adviser recommendation/message;
5. final 0–100 judgment;
6. periodic trust rating.

The same advice-taking metric applies:

`WOA = (final - initial) / (advice - initial)`

Scenario content is not permanently tied to condition. The 18 scenarios are split into three balanced six-item sets and rotated across N/P/A between participants. Each six-item set contains three lower (30) and three higher (70) adviser judgments.

In P and A, the model receives the social scenario so it can give a grounded argument. Only A additionally receives the participant's rationale and block history. The prompt explicitly treats scenarios as ambiguous and prohibits stating hidden social intentions as fact.

## Researcher pilot modes

The researcher launcher now offers:

- **Comparison pilot — dots + social** (default): with 6 trials/condition this is 18 dot + 18 social trials.
- **Dots only**.
- **Social only**.

Task order is counterbalanced in the comparison pilot. Each experimental block uses a different ambiguous adviser name.

## Live review

The researcher **Generate live review** tool runs the current 6/condition Dots + Social comparison with three condition-blind synthetic participants (108 trials total). It now submits a short rationale on every trial, allowing the Adaptive prompt to be audited against participant reasoning. Synthetic final responses never depend on adviser wording, so the tool is for generation/routing checks only, not persuasion-effect estimation.

The old standalone consortium demo has been removed.

## Exports

`all.zip` now includes:

- `analysis_trials.csv` — recommended analysis file; trial outcomes merged with task/scenario/rationale context.
- `trials.csv` — legacy outcome table.
- `trial_contexts.csv` — task type, scenario text/question, participant rationale and rationale RT.
- `diagnostics.csv` — generation/timing/manipulation diagnostics.
- the existing participant/rating/report exports.

Social trials have blank accuracy-error fields by design. End-of-task accuracy summaries, when enabled, use numerosity trials only.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

For live model calls configure the relevant API key. Production remains conservative by default: unless explicitly changed, the non-researcher path starts in numerosity mode.

## Validation

```bash
python smoke_test.py
python validate_rationale_social.py
node --test tests/live_review.test.cjs
```

The build also includes `social_design.py`, which defines the social scenarios and their counterbalancing.
