# BEAST · private AI adviser pilot

The v6.1 **number line, short Gemini notes and advice prefetch** are integrated with protected pilot controls, server-side sessions, timing diagnostics and recovery. Original NEW25 numbers, counterbalancing and 105 original PNGs are preserved.


Current update: **v2.5, implicit adaptation** (`fieldwork-2.5-implicit-adaptation`).
See [IMPLICIT_ADAPTATION_UPDATE.md](IMPLICIT_ADAPTATION_UPDATE.md) for installation,
validation scope, changed prompts, and how to interpret review flags. This supersedes
the mandatory rating-acknowledgement checks described in the v2.4 update.

Trust means trust in the AI adviser. Feeling means the reported reaction to its advice.
These inputs now supply internal persuasion approaches rather than requiring the model
to repeat the ratings. Both available approaches inform adaptive tone; the existing
behaviour/trust/feeling cycle selects emphasis. Implicit influence needs comparison and
human review. A lexical mention is not evidence of adaptation.

## Participant flow

Image (5 s) → first estimate on a blank number line → AI number + 6–12-word note → final slider → occasional trust/feeling check-in. The final slider starts at the participant's first estimate, as in v6.1. You/AI use matched circular markers and cards. A plain progress bar shows completion; scores appear only after finishing.

C3–C8 notes are prefetched during image viewing. The model gets the fixed recommendation and, for C5/C8 only, every completed earlier trial in that block. **It never gets the current first estimate**, even if prefetch fails and synchronous generation is needed. This keeps the information supplied consistent. C1/C2 use fixed control notes and C2's number still depends on the current estimate.

Default live provider: `gemini`, model `gemini-3.5-flash-lite`, thinking `minimal`, one application-level attempt, no artificial minimum wait. The Gemini SDK has a 10-second request timeout and one SDK attempt. Failure produces a labelled generic fallback. Short notes and prefetch can reduce waiting; effectiveness and live latency must be checked in the pilot. Mechanical validation is not a semantic guarantee.

## Researcher workspace

Unlock `/` with `ACCESS_CODE`, then sign in at `/researcher` with the separate `ADMIN_TOKEN`. Launch a short/full pilot with selected conditions, block length and counterbalance row. Offline mode uses labelled local templates; live mode requires the selected provider key. All researcher and pilot sessions are `TEST`, excluded from production allocation.

Trial diagnostics include actual/expected history length, generation source, fallback/attempts, `prefetched`, and `initial_context_available`. Exports include estimates, errors, WOA, sparse ratings, messages, and phase timing. The display records **generation time separately from visible advice wait**, plus prefetch request and remaining wait, image exposure, response/check-in/break time, hidden-tab interruptions and resume flags.

The duration calculator is an assumption-based planning aid. Use human pilot data to estimate total duration. With the shorter notes the previous package's 42-minute estimate is not a measurement of this version. Aggregate tables can pool offline/live modes; filter `adviser_mode`, `is_test` and `source` before interpretation.

Reloading after the first answer is saved resumes advice without re-showing the image. Retries do not create duplicate trials or repeat generation. A reload before the initial answer is saved can repeat exposure; this remains a pilot limitation. Exposure pauses in hidden tabs and browser timing is not a calibrated visual trigger.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python smoke_test.py
export ADMIN_TOKEN="choose-a-long-researcher-token"
export ACCESS_CODE="choose-a-different-private-code"
python app.py
```

The local default adviser mode is offline. To run Gemini live, set `GEMINI_API_KEY`, `ADVISER_PROVIDER=gemini` and `ADVISER_MODE=live` in the environment. `.env.example` is documentation, not automatically loaded. Never commit secrets or participant exports.

Startup generates missing PNGs on the protected server using the repository’s existing deterministic `stimuli.py`; image files are not published to GitHub. `setup_files.py` validates rather than rewriting edited assets. `gunicorn.conf.py` preserves the required 1-worker/8-thread setup even when Render starts plain `gunicorn app:app`.

## Adaptation checks

`python smoke_test.py` checks the complete 105-trial session, schedules, history routing, prefetch idempotency, stale requests, privacy, ratings, fallbacks and end-only scores. The browser test in `tests/browser_smoke.cjs` covers desktop/mobile number lines, ratings, prefetch, reload and exports at normal display timings.

```bash
python verify_adaptation.py
python verify_adaptation.py --live --model-profile gemini_fast --contrast trust --repetitions 3 --out probe-trust
python verify_adaptation.py --live --model-profile gpt_stronger --contrast feeling --repetitions 3 --out probe-feeling
```

Offline is API-free. Each example `--live` command makes 24 message generations and incurs usage. It contrasts resistance/following histories while holding the current advice fixed, with the current estimate unavailable as in prefetch. Reports include raw messages, prompt hashes, latency, source/fallback and shuffled blind review sheets. Static prompts must stay identical across histories; adaptive prompts must differ. Different live text alone does not prove adaptation; inspect whether history claims are supported. Behavioural effects require human data.

## Deployment and data

GitHub: `jennapfeifer/ai-beast-prototype`; Render service: `ai-beast-prototype`, auto-deploying `main`. The source repository remains public as authorised; the task and researcher data are gated by separate private codes. Codes grant access to their holders, not named accounts. The health endpoint reveals only OK/version.

Set `SECRET_KEY`, `ACCESS_CODE` and `ADMIN_TOKEN` before deploying; on Render the app refuses to start without them. Preserve provider API keys and the existing database URL when editing environment settings. `DATABASE_URL` should point to persistent Postgres for retained data; a SQLite file on the free web service can disappear when it restarts. The build stays in pilot mode. Before recruitment, finalise participant information/contact/withdrawal terms, validate live manipulation and timings, and use durable storage.

The original table schema is retained and diagnostic/session tables are additive. Old browser sessions from v6.1 cannot migrate; update between sessions. Retain a data export before deployment. Read the protected `/api/researcher/status` for the deployed model/configuration and database dialect without exposing keys.
