# BEAST v2.4: trust, feeling, and a simpler interface

Prepared 16 September 2026. App version: `fieldwork-2.4-rating-focus`.
Prompt version: `adaptive-reaction-v4-ratings`.

## Status and installation

Implemented and validated locally; not uploaded or deployed. GitHub's integration
previously denied repository writes, so upload this package through your own access.

Unzip the package and upload its contents to the existing repository root, preserving
the `templates`, `static`, and `tests` folders. Do not upload the ZIP itself or put
the whole update inside an extra folder.

Required web-app replacements:

- Root: `adviser.py`, `app.py`, `pilot.py`.
- `static/task.js`.
- `templates/base.html`, `templates/task.html`, `templates/instructions.html`,
  `templates/consent.html`, `templates/debrief.html`, `templates/researcher.html`.

The root `verify_adaptation.py` adds the optional feeling comparison probe. Tests
and this note are included for reproducibility. No environment, API-key, dependency,
database-schema, or access-control changes are required.

Render's existing automatic deployment follows the GitHub commit. Start a fresh
pilot afterward to avoid mixing prompt policies or retaining cached old advice.
Check `prompt_version: adaptive-reaction-v4-ratings` in researcher diagnostics.

## What the supplied failure means

The Sol API returned the draft in about one second. Its rejection reason was
`repetition_similarity=1.000`: it exactly repeated a previous note. The app then
displayed a generic fallback. `trust_not_mentioned` was an audit result, not that
rejection's cause. The pasted excerpt contains no actual trust or feeling values,
so it cannot establish which ratings the model saw or whether tone was affected.

The preceding prompt forced every adaptive note to recap the latest decision.
Trust was secondary, and feeling had no explicit instruction despite appearing
in the raw history. This revision changes that policy.

## Adaptive message focus

Each short note has one required focus. The app deterministically cycles through
behaviour, trust, and feeling once those ratings exist. The LLM receives the focus
and recorded values, then writes its own brief acknowledgement and invitation to
consider the numerical advice. It does not choose the focus itself.

With the default check-in every two trials:

| Trial | Required focus |
| --- | --- |
| 1 | Brief invitation; no earlier response exists. |
| 2 | Previous decision. |
| 3 | Trust recorded after trial 2. |
| 4 | Feeling recorded after trial 2. |
| 5 | Previous decision. |
| 6 | Latest available trust. |
| 7 | Latest available feeling. |

The cycle continues. Missing ratings are excluded from the available focus types;
they are never invented or replaced with neutral scores. History resets by block.
All available within-block decisions and ratings remain in the adaptive prompt,
even though the visible note concentrates on one input. Static and neutral
conditions do not receive participant history or ratings.

The trust scale is 1=not at all to 7=completely. Feeling is 1=very negative to
7=very positive **about the advice**, not a measure of general mood. For short
wording, the prompt uses descriptive bands: 1–3 low/negative, 4 midpoint/neutral,
5–7 high/positive. These are prototype wording rules, not validated cutoffs.
Exact ratings and changes remain available internally. The prompt prohibits
inferring named emotions, motives, or trust from advice uptake.

This is a substantive change to the adaptive condition. Pilot it separately from
v2.3. The researcher model comparison now groups by prompt version as well as
condition, provider, model, reasoning, and mode; earlier versions are not pooled
into the same row. The older condition-only summary still pools pilot versions.

## Checks and repetition

On behaviour-focused turns, the existing history wording screen applies. On
rating-focused turns, the app checks for a reference to the relevant self-report
instead of requiring a simultaneous behavioural recap. A behaviour-only note on
a feeling-focused turn gets `missing_feeling_reaction`, not a repetition error.
Recognisable opposite rating claims are rejected on those focused turns;
uncertain paraphrases are flagged for review. These are lexical checks, not a
semantic judge. They can miss subtle errors or reject unfamiliar valid wording.

Recent adviser messages are explicitly included as examples to avoid copying.
Repetition alone no longer discards an otherwise valid live note. Such notes stay
labelled live and record `repetition_check: exact_repeat` or `similar_to_previous`.
They are not silently described as varied. Other failures still follow the
configured validation attempt count and then return labelled fallbacks. No extra
API call has been added solely to obtain a different phrase.

Diagnostics and CSV exports include:

- `adaptive_focus` and `adaptation_check`.
- `trust_context_in_prompt`, latest/previous trust values, trial, age, and change.
- Equivalent `feeling_context_in_prompt`, latest/previous feeling values, trial,
  age, and change fields, plus `feeling_check`.
- `repetition_check`, `repetition_similarity`, and the existing rejected drafts.
- `model_response_received` independently of whether the displayed note is live.

The researcher comparison reports behaviour/trust/feeling reference checks and
repeated-note counts. Passing a reference check does not establish meaningful
adaptation or a behavioural effect. Inspect actual messages with their inputs.

## Participant interface

Removed the “Own estimate → AI advice → Final decision” footer, “Progress celebrates
completion”, the global footer, and the round map. The trial screen retains a
simple round/trial count and progress bar. Instructions, waiting screens, breaks,
button labels, and the finish heading are shorter. Researcher diagnostics are
collapsed initially and remain available in researcher pilots.

The first estimate remains blank until selected; the final slider still starts
at that estimate. Matched You/AI markers, stimulus exposure, recommendation
schedules, trial allocation, phase timing, prefetching, and rating frequency are
preserved. The trust/feeling questions and their anchors are unchanged. Consent
and debrief information remain, with the debrief describing the new policy.

## Controlled probes

The probe can separately manipulate behaviour, trust, or feeling while holding
the other inputs constant. Rating probes use a history length that makes the
next message focus on that rating.

Offline routing check (no API calls):

```bash
python verify_adaptation.py --contrast feeling --out probe-results/feeling-offline
```

Optional live comparison where OPENAI_API_KEY is already configured:

```bash
python verify_adaptation.py --contrast feeling --model-profile gpt_stronger --repetitions 3 --live --out probe-results/feeling-sol
python verify_adaptation.py --contrast trust --model-profile gpt_stronger --repetitions 3 --live --out probe-results/trust-sol
```

Each command requests 24 messages; configured retries can add calls. Inspect
repeated paired outputs, not just one different phrase. The reports include
messages, focus, checks, and exact synthetic histories. No live comparison was
run in this update, and no API keys were read. Keep reports outside the public repo.

## Validation

99 automated tests passed. Coverage includes live-path mocked generation for
both advice directions, both ratings, missing values, block resets, prefetch
caching, exports, repeated valid notes, absent required rating reactions,
contradictory ratings, invented specific emotions, and separation of prompt
versions. The existing complete 105-trial API rehearsal and privacy checks pass.
The feeling-only offline probe passes its routing checks. JavaScript syntax and
Flask template/API rendering checks pass.

Visual browser validation was blocked by `ERR_BLOCKED_BY_CLIENT` when opening
the local preview. No desktop/mobile visual pass or live deployed check is claimed.
