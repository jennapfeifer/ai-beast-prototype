# AI-BEAST human study web app

Text-only browser version of the final **NEW25** 8-condition dot-estimation advice-taking task.
The numerical design is aligned to `simulate_beast_final_old25_vs_new25_imagefirst.py`, while
static/adaptive adviser wording uses the **historical broad-persuasion architecture** from the
final simulation. Generated adviser messages are mechanically validated before display.

## Locked experimental structure

- 8 rounds × 13 trials = 104 experimental trials, plus 1 warm-up trial.
- 13 true counts: 32, 40, 48, 64, 80, 96, 112, 128, 144, 160, 192, 224, 256.
- 8 deterministic visual arrangements per count = 104 experimental images.
- Each participant sees every count/variant image exactly once.
- Condition order is counterbalanced and the 144-dot item rotates across within-round positions.
- Study seed: `20260909`.
- Image is shown once, then removed before the participant enters the initial estimate.
- The image is **not** shown again after AI advice.
- Final response range: 1–400 in the human interface.

### Conditions

| Condition | Number policy | Wording policy |
|---|---|---|
| C1 | near-veridical fixed schedule, mean signed error 0% | fixed non-persuasive control bank |
| C2 | near participant's initial estimate, <4% movement | fixed non-persuasive control bank |
| C3 | NEW25 fixed truth-relative UP schedule, mean +25% | GPT-5 neutral |
| C4 | same numbers as C3 | GPT-5 historical static persuasion |
| C5 | same numbers as C3 | GPT-5 historical adaptive persuasion |
| C6 | NEW25 fixed truth-relative DOWN schedule, mean -25% | GPT-5 neutral |
| C7 | same numbers as C6 | GPT-5 historical static persuasion |
| C8 | same numbers as C6 | GPT-5 historical adaptive persuasion |

The 144-dot trial is 144 in C1 and both fixed NEW25 steering schedules.

## Historical persuasion + validation

`adviser.py` deliberately restores the broad historical persuasion policy used in the final
simulation. Static/adaptive messages may make persuasive claims about the participant's counts;
there is no content checker that suppresses those strategies.

Adaptive C5/C8 receives **all completed earlier trials in that same block**, including:

- initial estimate,
- fixed recommendation,
- final estimate,
- trust rating,
- feeling rating,
- exact previous AI message.

The human app deliberately retains **mechanical validation**, even though the final simulation
used one-shot messages. GPT-5 now writes the literal token `[ESTIMATE]` rather than printing
the recommendation itself. A draft is accepted only if:

1. it is 25–30 words;
2. it contains `[ESTIMATE]` exactly once;
3. it contains no digits or other numerical values; and
4. it is not a near-duplicate of an earlier visible message in that block.

After validation, the server replaces `[ESTIMATE]` with the fixed NEW25 recommendation. This
guarantees that the current recommendation is the **only visible number**, while adaptive GPT-5
can still reason over the complete exact numerical history internally. Earlier estimates, advice,
final answers and ratings may be referred to qualitatively but are not quoted numerically.

For adaptive trials, claims about what the participant actually did (e.g. followed, resisted,
revised, or moved toward the adviser) must be consistent with the supplied history. A server-derived
qualitative summary of the movement pattern is included alongside the exact history to help ground
those claims. Broad historical persuasion remains allowed; this grounding rule applies specifically
to claims about the participant's own prior behaviour.

Failed drafts are retried with format-only feedback, with the retry note replaced rather than
accumulated on every attempt. If all attempts fail, the app uses a varied fallback bank. Adaptive
fallbacks deliberately avoid unsupported claims such as saying the participant has previously
followed the adviser.

The adviser default is intentionally pinned to `gpt-5` to match the final simulation rather than
a newer model family. Changing `ADVISER_MODEL` changes the experimental manipulation and should
be treated as a protocol change.

## Progress-only gamification

Participants see the task as **8 rounds** with a small round tracker. Between rounds they reach a
checkpoint screen showing how many rounds are complete. This is deliberately not performance
gamification: there are no points, accuracy scores, streaks, leaderboards, or rewards for agreeing
with the AI. Checkpoints only mark completion/progress.

## Text only

Voice/TTS and microphone input have been removed. Every participant receives written adviser
messages. The legacy `modality` and `audio_played` database columns are retained only so an
existing database/export schema does not need to be migrated; new sessions record `text` and
`False` respectively.

## Files

```text
app.py          Flask routes + trial API
adviser.py      GPT-5 historical persuasion + mechanical validation
design.py       NEW25 schedules + counterbalancing
store.py        SQLite/Postgres storage; adaptive full-history retrieval
stimuli.py      exact dot-array generator aligned to the simulation
setup_files.py  writes templates/ and checks local files
style.css       participant UI + checkpoint/round styling
task.js         text-only trial state machine + progress gamification
task.html       task template (also written by setup_files.py)
smoke_test.py   API-free end-to-end design/history checks
render.yaml     Render blueprint
requirements.txt
```

## Run locally

```bash
pip install -r requirements.txt
python stimuli.py --size 512 --force
python setup_files.py
python smoke_test.py
python app.py
```

Open <http://127.0.0.1:5000>.

`setup_files.py` moves loose `task.js` and `style.css` into `static/` and writes the HTML templates.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ADVISER_MODEL` | `gpt-5` | model used for C3–C8 wording |
| `ADVISER_REASONING_EFFORT` | `low` | GPT-5 reasoning effort |
| `ADVISER_VALIDATION_ATTEMPTS` | `6` | format/numeric/anti-repetition generation attempts |
| `ADVISER_MIN_WORDS` / `ADVISER_MAX_WORDS` | `25` / `30` | visible generated message length |
| `ADVISER_MIN_DELAY_MS` | `2500` | minimum preparing-response delay in every condition |
| `STIMULUS_MS` | `5000` | image viewing time before it disappears; `0` = untimed |
| `PREFILL_FINAL` | `0` | whether final answer box begins with initial estimate |
| `COLLECT_RATINGS` | `1` | enable trust + feeling check-ins |
| `RATING_EVERY` | `2` | show the two rating items after every second trial |
| `RESEARCHER_MODE` | `0` | test overlay; never enable for real participants |
| `DATABASE_URL` | `sqlite:///beast.db` | production should use Postgres |

## Researcher mode

Run locally with:

```bash
RESEARCHER_MODE=1 ADMIN_TOKEN=test123 python app.py
```

The start page then shows **researcher test controls**. You can choose one condition (C1-C8), choose how many trials to run, skip practice, and choose counterbalancing row 1-8. This is easier than editing URLs. URL parameters still work if preferred.

Researcher test sessions are flagged `TEST` immediately and **do not consume the production counterbalancing sequence**. Production participants rotate through eight condition orders; test sessions can explicitly select which counterbalancing row to inspect. If you restart a local app with a fresh SQLite database, production participant numbering naturally starts from row 1 again.

The overlay shows the true count and therefore **RESEARCHER_MODE must be 0 for participant data collection**.

### Rating schedule

The trust and feeling items now appear only after trials 2, 4, 6, 8, 10 and 12 within each 13-trial condition. Odd-numbered trial rows (and trial 13) have blank trust/feeling fields. In adaptive conditions, GPT-5 still receives every previous trial; it receives ratings only on trials where ratings were actually collected.

## Validation before launch

Run:

```bash
python smoke_test.py
```

The smoke test verifies:

- 104 experimental trials / 104 unique stimulus IDs;
- 13 trials in every condition;
- C3=C4=C5 advice numbers and C6=C7=C8 advice numbers;
- 0 / +25 / -25 mean signed-error schedules;
- the 144 special case;
- text-only API behaviour;
- adaptive history grows from 0 through 12 earlier trials;
- production condition-order rows rotate across participants while TEST sessions can choose a row without consuming the production sequence;
- trust/feeling fields can be sparse because check-ins occur every two trials;
- adaptive history includes exact prior adviser messages;
- the numeric-token validator rejects stray numbers.

Also pilot the live app and inspect:

- `advice_source` and fallback rate;
- `advice_attempts`;
- `advice_word_count`;
- `advice_latency_ms`;
- whether C5/C8 messages actually use prior history;
- participant completion/dropout across the 8 rounds.

## Render deployment

`render.yaml` uses one Gunicorn worker with threads and a Postgres database. Set
`OPENAI_API_KEY` in Render. Do not collect real data using an ephemeral SQLite filesystem.

### Downloading results

Open:

```text
/admin?token=YOUR_ADMIN_TOKEN
```

That page has buttons for the trial-level file, participant table, blind message-rating table, and one ZIP containing all three. Direct links still work:

```text
/admin/export/all.zip?token=YOUR_ADMIN_TOKEN
/admin/export/trials.csv?token=YOUR_ADMIN_TOKEN
/admin/export/participants.csv?token=YOUR_ADMIN_TOKEN
/admin/export/ratings.csv?token=YOUR_ADMIN_TOKEN
```

On Render, find `ADMIN_TOKEN` in the service's Environment settings. `participants.csv` tells you who started/completed and which condition order they received; `trials.csv` contains the actual estimates, advice, WOA, ratings, RTs and adviser messages. Exclude rows whose participant has `notes=TEST` from the real analysis.

## Ethics / debrief

This is a deception/manipulation study: advice numbers are experimentally controlled and
persuasive conditions are explicitly optimized to shift participants. The bundled consent and
debrief text are placeholders for protocol development, not ethics approval. Replace the contact,
withdrawal, retention, and HREC/ethics wording with the version approved for the study before
launch.
