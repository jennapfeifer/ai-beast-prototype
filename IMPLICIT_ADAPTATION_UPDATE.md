# BEAST v2.5 — implicit adaptation and a simpler interface

App: `fieldwork-2.5-implicit-adaptation`  
Prompt: `adaptive-reaction-v5-implicit`  
Prepared: 16 September 2026

## Install the update

This package is implemented and tested locally. It has not been committed or deployed:
the connected GitHub integration previously returned HTTP 403 for repository writes.

Export any pilot results you want to retain, then unzip this package and upload its
contents into the existing `jennapfeifer/ai-beast-prototype` repository root. Preserve
`templates/`, `static/`, and `tests/`. Replace the existing files; do not upload the ZIP
itself or place the update inside an extra parent folder. In particular, replace BOTH
`static/style.css` and `templates/task.html`. The checked GitHub task template still
contained the old footer, so updating Python alone would leave that text visible.

Render's existing automatic deployment follows your commit. Start a NEW pilot after
the deployment finishes: in-progress sessions can contain cached advice from an older
prompt. Check the app version in the researcher workspace and the prompt version in
trial diagnostics. Styles and task scripts now have versioned asset URLs.

No environment variables, keys, dependencies, schema, or access codes need changing.
The access gate and researcher gate remain in place. The update archive contains
source and synthetic tests, not participant data, credentials, or dot-image assets.

## What caused the examples

“Since your reported trust is low, please review this figure.” followed the previous
prompt's explicit instruction to acknowledge a rating. That was too literal for the
intended manipulation. It restated the input without demonstrating a useful response.

“Your last answer was close; weigh this estimate carefully.” returned successfully
from Sol, but the local phrase matcher rejected it. “Close” has no comparator here:
it might refer to advice or truth. This is ambiguous, not a proven valid history claim.
The new prompt asks the model to specify “close to my estimate” when describing that
relationship. If an unfamiliar past-response phrase still appears, the app retains the
live draft with a review flag instead of replacing it with a generic fallback.

## Revised manipulation

Trust is **trust in the AI adviser**, not self-confidence or a proxy for compliance.
Feeling is **the reaction to the advice**, not general mood or a named emotion.

Both available ratings supply internal approaches on adaptive turns, including turns
whose main focus is behaviour. The existing deterministic focus cycle selects emphasis
(behaviour → trust → feeling when both ratings exist); it is not a model-chosen policy.
The model still receives the exact completed within-block decisions, check-ins, rating
age/change, and recent notes. Static/neutral conditions receive no participant history.

| Recorded input | Internal instruction to the adviser |
| --- | --- |
| Trust 1–3 | Tentative invitation to compare estimates; preserve choice. |
| Trust 4 | Balanced invitation to weigh the AI estimate. |
| Trust 5–7 | Concise, confident invitation without claims of proven accuracy. |
| Feeling 1–3 | Calm, less insistent wording and a fresh invitation. |
| Feeling 4 | Straightforward, matter-of-fact wording. |
| Feeling 5–7 | Warmer encouragement without praising compliance. |
| Decreased rating | Soften the invitation rather than increasing pressure. |

These are declared prototype manipulation rules, not validated psychological cutoffs.
The model writes its own sentence; these are not participant-facing stock messages.
The prompt discourages rating recitals, labels such as “your trust is low,” and explaining
the persuasion objective. It does not require the words “trust” or “feeling.” It also
prohibits fabricated image evidence, accuracy claims, inferred named emotions, and guilt.
Missing ratings remain missing. Check-ins are retrospective, not certainty about the
participant's current state. Recommendations remain the experiment's fixed numbers.

## Interpreting diagnostics

- `model_response_received`: an API response arrived.
- `live_model`: the displayed message came from the live model.
- `adaptive_focus`: the programmed emphasis for this turn.
- `adaptive_strategy`: the approach for that emphasis.
- `rating_strategies`: available trust/feeling approaches supplied in the prompt.
- `trust_context_in_prompt` / `feeling_context_in_prompt`: input-routing evidence.
- `validation: accepted_for_review`, `adaptation_check: needs_review`: the live message
  was kept, but the app has not established that its adaptation is meaningful.
- `review_reasons`: why review is required, including implicit rating influence or an
  unrecognised past-response phrase.
- `trust_not_mentioned` / `feeling_not_mentioned`: lexical observations, not failures.
- `repetition_check`: an independent quality flag; repetition alone does not cause fallback.

All rating-focused messages require review even if they happen to name a rating. Known
contradictions, fabricated explicit rating claims, format violations, missing required
behaviour reactions, and API failures still follow the configured attempts/fallback path.
An unrecognised phrase is not certified as truthful. The screen cannot catch every error.

The workspace now separates retained live notes needing review from fallbacks. Review
notes are excluded from passed wording-screen counts. Those counts are only lexical
checks, not evidence that persuasion worked. Behaviour-focused turns can pass their
history screen without establishing a rating effect. Inspect rating influence with
matched comparisons and human review. Model comparisons remain grouped by prompt
version; the older condition-only summary still pools versions and modes.

No extra API call was added to assess implicit wording, so this change adds no second
model-judge request. It does not promise faster or more effective generated messages.

## Interface

The stylesheet has been replaced: white background, dark text/buttons, flatter layout,
less decoration, larger rating choices, and equal You/AI estimate cards. The green hero
illustration, old task footer, and round map are removed. Researcher diagnostics start
collapsed. The first estimate remains blank; the final slider starts at that estimate.

Stimulus content/exposure, numerical schedules, source-marker geometry, condition
allocation, question wording/anchors, prefetch, timing capture, and private gates are
preserved. Consent and debrief remain; the debrief describes implicit rating use.

## Validation and the next pilot

106 automated tests passed, using mocked API responses and offline sessions. These cover
the supplied Sol draft, keyword-free Gemini/Sol paths, explicit contradictions, one-call
acceptance, both rating inputs, routing across blocks, export/report flags, a complete
105-trial session, and the existing privacy/idempotency checks. Python compilation,
JavaScript syntax and template rendering were checked separately.

Live Gemini/Sol output quality and human completion time have NOT been validated for
this prompt. Interactive visual QA remains unverified because the preview browser was
blocked. The source-level styling changes should be inspected after your deployment.

For a short interactive check, run at least four trials per condition: with check-ins
at trial 2, trial 3 emphasises trust and trial 4 feeling. To check implicit use more
carefully, run controlled probes in an environment with your configured server keys:

```bash
python verify_adaptation.py --live --model-profile gemini_fast --contrast trust --repetitions 3 --out probe-gemini-trust
python verify_adaptation.py --live --model-profile gpt_stronger --contrast feeling --repetitions 3 --out probe-sol-feeling
```

Each command requests 24 messages; charges apply. Repeat both rating contrasts for each
model you are comparing. Only the selected rating changes within matched histories;
static prompts stay identical. Review the messages blind first, then inspect the input
histories and tone/invitation with the key. Compare repeated samples, not one different
sentence. The generated HTML/JSON and review CSV support this check. Offline mode checks
routing only and does not simulate live implicit adaptation. A participant effect needs
human pilot responses; neither a prompt hash nor a keyword check establishes it.
