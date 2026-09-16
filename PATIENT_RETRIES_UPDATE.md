# BEAST v2.7 — patient retries and small length overruns

App: `fieldwork-2.7-patient-retries`  
Prompt: `adaptive-reaction-v7-repair`  
Retry policy: `patient-v1`

## What changes

Previously the normal one-attempt setting turned the first rejected draft into a
generic fallback. All model profiles now default to three total attempts (the
initial request plus two retries) with a 60-second generation allowance. A valid
first response returns immediately. Static, adaptive and neutral model requests
use the same retry policy; fixed control notes remain preprogrammed.

Rejected content is sent back with the specific failure, the rejected output and
repair instructions. History failures receive the actual recorded response fact;
optional filler receives a direct-recommendation instruction. Structured-record,
rating, length and direction failures receive corresponding corrections. The
model, supplied history and numerical recommendation stay the same. A temporary
API failure between drafts does not erase the earlier repair instructions.

Timeouts, connection failures, rate limiting and temporary server errors can retry
with brief backoff. Numeric `Retry-After` is respected; if it cannot fit within the
remaining allowance, generation stops rather than retrying early. Authentication,
invalid-request and other non-recoverable errors stop immediately. Both SDKs have
automatic retries disabled so the application records each attempt.

The remaining allowance limits each request timeout. Gemini Fast and GPT Fast use
15 seconds per request; GPT Sol with low reasoning uses 25 seconds. The server-default
profile respects `ADVISER_REQUEST_TIMEOUT` (15 seconds when unset). Browser requests
allow 90 seconds and the Gunicorn worker timeout is 120 seconds. These are limits,
not deliberate delays. SDK timeouts are not a strict wall-clock deadline; a valid
late response is kept and marked `budget_overrun`, rather than discarded.

## The reported 13-word rejection

“You moved away last time, so please shift right toward my estimate now.” was
rejected by v2.6 solely for exceeding 12 words. Its internal history record matched.
The history reference is appropriate for an `away` response. V2.7 keeps otherwise
valid 13–15-word messages and marks them `word_count_slightly_over_target` for
review. All model-generated conditions share this tolerance; the requested target
remains 6–12 words. This is a study-setting change, recorded in diagnostics and exports.

That example also contains an unsupported current direction: prefetch does not
know the participant's current first estimate, so it cannot know whether “right”
moves toward the AI recommendation. V2.7 screens explicit current direction
instructions and requests “toward my estimate” instead. The same example now
gets a direction repair, rather than a length rejection and immediate fallback.
A supported replacement is “You moved away last time; now move toward my estimate.”
The wording screen is limited; it does not establish full semantic correctness.

Slight length overruns, repetition and unassessed rating influence are review flags,
not reasons for another call. Generic adaptive notes, known false history/rating
claims, incorrect fact records and other substantive failures still need repair.
Exhausting the attempts or available time still produces an explicitly labelled
fallback. More attempts do not establish that trust or feeling caused different
wording, or that the manipulation changes participant behaviour.

## Diagnostics

Each trial records `max_attempts`, `total_budget_s`, `retry_policy_version`,
`retry_count`, `recovered_after_retry`, `stop_reason` and `budget_overrun`.
Each attempt includes its actual timeout, duration, request hash, failure category
and, for content failures, the rejected draft. API exception text and keys are not
exported. The existing base prompt hash stays separate from repair-request hashes.

`target_word_range`, `word_tolerance`, `word_count_check` and `direction_check` show
how wording was assessed. Retry results survive prefetch and subsequent initial-
answer requests without generating the same advice again. The researcher workspace
shows retried and recovered trial counts and separates retry policies/settings in
model comparisons. Generation duration includes retries; visible advice wait remains
separate. Inspect both when comparing conditions and total experiment duration.

## Settings and installation

This ZIP updates the existing repository; it is not a standalone application.

1. Export pilot data to retain, and upload between sessions.
2. Unzip and upload the contents to the existing GitHub repository root, preserving
   `templates`, `static` and `tests`. Replace the corresponding files. Include
   `gunicorn.conf.py`; do not upload only the ZIP or an extra containing directory.
3. Let the existing Render automatic deployment complete. Start a **new pilot**:
   existing sessions keep their saved model-profile settings.
4. Confirm app `fieldwork-2.7-patient-retries` and prompt
   `adaptive-reaction-v7-repair`. New live-trial diagnostics should show
   `max_attempts: 3`, `total_budget_s: 60`, `retry_policy_version: patient-v1`.

The new defaults work without editing existing Render environment values:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ADVISER_MAX_ATTEMPTS` | `3` | Total application attempts, capped at 5 |
| `ADVISER_TOTAL_BUDGET_SECONDS` | `60` | Generation allowance, capped at 60 seconds |
| `ADVISER_REQUEST_TIMEOUT` | `15` | Per-request seconds for the server-default profile |
| `ADVISER_WORD_TOLERANCE` | `3` | Extra words above the target maximum, capped at 4; 0 restores strict length |

The older `ADVISER_VALIDATION_ATTEMPTS` and `ADVISER_BUDGET_SECONDS` variables are
deprecated and ignored. This is intentional: their old one-attempt/12-second values
must not silently disable the new behavior. They may be removed later. An existing
`ADVISER_REQUEST_TIMEOUT=10` still gives the server-default profile 10 seconds per
attempt, with the new three-attempt policy. Set it to 15 to match the new default;
the named model presets use their own request timeouts. Existing min/max word
settings still define the target; tolerance is added above that maximum.

Keep `ACCESS_CODE`, `ADMIN_TOKEN`, `SECRET_KEY`, provider keys, adviser mode and
database settings. No new key or service is needed. Access gates remain in place.
Editing `render.yaml` alone does not change an existing manually configured Render
service; these new policy defaults are also implemented in the Python code.

## Validation and limits

185 automated tests passed using mocked provider responses and offline sessions.
Coverage includes third-attempt content recovery, timeouts/rate limits/server errors,
permanent failures, remaining-time limits reaching both SDKs, saved repair feedback,
attempt exhaustion, prefetch reuse, policy snapshots and export/report integration.
The exact reported sentence is tested for direction repair, and otherwise valid
13–15-word notes are retained on their first attempt in all generated styles.
Existing 105-trial routing, privacy, ratings and persistence checks also pass.

Python compilation, JavaScript syntax, template compilation and key Flask page
rendering were checked. No live Gemini/OpenAI requests were made for this update;
actual recovery rates, cost, latency and semantic quality still need live pilot
measurement. The previously blocked preview browser was not used for visual claims.

The package contains no provider keys, access secrets, participant records, database,
or stimulus PNGs. It is prepared for manual upload because the GitHub integration
previously rejected write access to this repository. This package is not a claim
that v2.7 is already deployed.
