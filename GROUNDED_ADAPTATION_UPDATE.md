# BEAST v2.6 — ground adaptive wording in the participant's history

App: `fieldwork-2.6-grounded-adaptation`  
Prompt: `adaptive-reaction-v6-grounded`

## Why this change is needed

“Please gently consider blending this number into your final choice” is a generic
invitation. It could fit almost any participant. The v2.5 code allowed such wording
on trust/feeling turns because it stopped requiring explicit rating mentions. That
removed an overly literal constraint but left an observable gap in the manipulation.

A successful API call, a correctly copied rating, or the word “gently” does not
establish meaningful adaptation. This update changes both the generation request
and the acceptance criteria. It does not claim that a stronger validator alone
makes Gemini or GPT more persuasive.

## Generation and checks

Every adaptive note after usable history must include a short concrete reference
to the latest completed decision, followed by an invitation. Trust and feeling
remain implicit influences on the invitation. They do not have to be named.
The behaviour/trust/feeling cycle still selects emphasis; it no longer exempts
rating-focused turns from the history requirement. The first trial cannot reference
history that does not exist. Unusable history also permits no invented recap.

Illustrative wording for a participant who moved partway toward the advice:
“You moved closer earlier; give my estimate more weight.” This is an example of
a grounded sentence, not an observed model result or validated rating effect.

In the same API request, the model returns a structured object containing:

- Latest completed trial and recorded response category.
- Latest trust/feeling ratings and the trials where they were collected, or null.
- The participant-facing message.
- A verbatim excerpt of its history reference from that message.

The server checks this against its own record. Wrong ratings, stale trial positions,
missing fields, invented annotations and malformed responses fail. Accurate metadata
cannot rescue generic prose: the displayed sentence and its quoted reference also
undergo the history wording screen. Known contradictory behaviour/rating claims fail.
Unfamiliar past-response wording remains explicitly uncertain and goes to review;
it is not automatically certified as truthful. The lexical screen still has limits.

Only the message is shown to participants. Internal fields go to protected researcher
diagnostics and exports. There is no separate model-judge request. The existing
attempt count remains in force (normally one); if it is set higher, repair feedback
includes the actual completed-response fact. Exhausted failures still produce a
clearly labelled generic fallback, never a claimed successful adaptive note.

Adaptive requests now use structured output for both Gemini and GPT. The output-token
ceiling is 384 for Gemini and no-reasoning GPT, to accommodate the internal record;
low-reasoning GPT retains its existing 2048-token ceiling. Participant notes remain
6–12 words. Extra output can affect latency, so live timings must be measured again.

## Clear persuasion across rating states

The further example “If you wish, weigh the displayed estimate against your own”
is too noncommittal for a persuasive condition. The earlier low-trust and negative-
feeling instructions were too tentative. They now call for direct recommendations
throughout: ratings change the framing and delivery, not the objective of moving
toward the AI estimate. Low trust prompts concrete reconsideration without appeals
to blind trust; negative feeling prompts composed delivery with a clear recommendation.
Higher trust permits firmer continuity when supported by recorded behaviour; positive
feeling permits warmer, more energetic delivery. No invented accuracy claims or guilt.

Both static and adaptive persuasive conditions reject explicit optional filler such
as “if you wish,” “feel free,” and “no pressure.” This is a narrow language screen,
not a measure of persuasiveness: absence of those phrases does not establish strong
or effective persuasion. `persuasion_check` records the result. The supplied example
also fails when embedded in an otherwise grounded history sentence. Neutral/control
conditions do not acquire a persuasion requirement. No additional retries are enabled.

## What the researcher sees

A concise status separates generation from content review, for example:
“Live response received · 646 ms. History reference screened. Ratings supplied;
their influence is not yet assessed.” This is an illustrative status, not a measured
v2.6 latency.

Diagnostics now include the actual `displayed_message`, so a copied diagnostic
contains the sentence being assessed, and:

- `generation_status`: live response or fallback outcome.
- `grounding_record_check`: whether the internal record matches supplied facts.
- `model_basis`: the model's record and quoted history phrase.
- `rating_influence_status`: not assessed / no recorded ratings / not applicable.
- Existing history checks, raw drafts, repetition flags and review reasons.

All notes with available ratings retain review reasons for unassessed rating influence,
including behaviour-focused notes. The workspace separately counts history wording
references and matched internal records. Neither count demonstrates that trust or
feeling changed the sentence. Comparisons remain separated by prompt version.

The contrastive probe now also displays each model record. Run repeated matched
low/high-trust and negative/positive-feeling comparisons, holding behaviour fixed,
and assess changes in tone and invitation rather than looking for rating keywords.
If outputs remain interchangeable, the manipulation is still weak even when the
record and history checks pass. Human pilot data are needed to assess advice-taking.

## Validation

140 automated tests passed with mocked provider responses and offline sessions:

- Optional filler fails in both persuasive styles, including when a valid history reference is present.
- Low trust and negative feeling retain an explicit persuasive objective.
- The exact supplied generic sentence fails across both provider profiles and all
  behaviour/trust/feeling emphases with usable history, despite correct metadata.
- A configured repair can return a grounded sentence without rating keywords.
- Incorrect ratings, incorrect timestamps, fabricated excerpts and malformed JSON fail.
- Both installed SDK request paths receive the structured schema only for adaptive
  conditions; the schema context is cleared before the next request.
- Internal records and displayed messages survive prefetch and diagnostic export.
- Existing condition schedules, 105-trial completion, privacy, sparse ratings,
  within-block history, idempotency and recovery tests continue to pass.

Python compilation, JavaScript syntax, all template compilation, and consent,
instructions, task and researcher page rendering also pass.

No live provider calls were made for this revision. Semantic effectiveness, actual
latency and live-provider schema acceptance remain to be checked in the deployed
pilot. Interactive browser inspection remains unavailable because the preview browser
was blocked earlier. No claim of live or visual validation is made.

## Install

This archive updates the existing repository; it is not a standalone full application.
It includes the relevant templates/styles to prevent a partial interface upload.

1. Export any pilot results you want to keep and update between sessions.
2. Unzip and upload the CONTENTS into the existing repository root, preserving the
   `templates`, `static` and `tests` folders. Replace existing files. Do not upload
   just the ZIP or create an extra parent directory.
3. Let the existing Render automatic deployment complete, then start a NEW pilot.
4. Confirm `fieldwork-2.6-grounded-adaptation` in the researcher workspace and
   `adaptive-reaction-v6-grounded` in diagnostics. Try at least four trials to reach
   behaviour, trust and feeling emphasis with the default check-in schedule.

No keys, environment settings, dependencies or database migrations need changing.
The private access and researcher gates remain. Model selection, numerical advice,
dot stimuli, rating questions, word limits, prefetch and timing measurements remain.

GitHub's connected integration previously denied writes with HTTP 403. The update
has been prepared locally for upload through your existing access; it is not deployed.

For optional server-side live comparisons (24 messages and API usage per command):

```bash
python verify_adaptation.py --live --model-profile gemini_fast --contrast trust --repetitions 3 --out probe-gemini-trust
python verify_adaptation.py --live --model-profile gemini_fast --contrast feeling --repetitions 3 --out probe-gemini-feeling
```

Use `--model-profile gpt_stronger` for the same contrasts with Sol. Offline probes
check routing only. Do not mix previous prompt versions into estimates of this
revision's adaptive effect.
