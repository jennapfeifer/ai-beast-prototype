# BEAST · private AI adviser pilot

The v6.1 **number line, short Gemini notes and advice prefetch** are integrated with protected pilot controls, server-side sessions, timing diagnostics and recovery. Original NEW25 numerical advice, counterbalancing and deterministic dot positions/counts are retained; visual and delivery versions are recorded.


Current update: **v2.9, advice layout and image loading** (`fieldwork-2.9-advice-layout`).
See [ADVICE_LAYOUT_UPDATE.md](ADVICE_LAYOUT_UPDATE.md) for the grey/blue/red layout,
lossless image compression, simpler introduction, optional three-second advice
screen and installation. The v2.7 adviser repair/retry policy remains in place.

Trust means trust in the AI adviser. Feeling means the reported reaction to its advice.
These inputs now supply internal persuasion approaches rather than requiring the model
to repeat the ratings. Both available approaches inform adaptive tone; the existing
behaviour/trust/feeling cycle selects emphasis. Implicit influence needs comparison and
human review. Every adaptive note with usable history must now reference the previous decision, including trust/feeling turns. The model returns a structured internal fact record and a short participant-facing message in the same request. Matching that record checks extraction, not whether ratings meaningfully changed the wording. Both persuasive conditions request clear recommendations; optional filler such as “if you wish” is rejected. Low trust and negative feeling change the framing without switching to neutral advice.

## Participant flow

Image (5 s) → first estimate on a blank number line → AI number + short note (target 6–12 words, tolerance up to 15) → final slider → occasional trust/feeling check-in. The final slider starts at the participant's first estimate, as in v6.1. The first estimate uses a grey square, AI advice a bright-blue pointer below the white line, and the final choice a red square. Direct labels replace the cards and legend. A plain progress bar shows completion; scores appear only after finishing.

C3–C8 notes are prefetched after the image is displayed. Images preload during fixation. An optional researcher setting shows the advice alone for three visible seconds before the final-estimate line; it applies to all selected conditions and does not prove reading. The model gets the fixed recommendation and, for C5/C8 only, every completed earlier trial in that block. **It never gets the current first estimate**, even if prefetch fails and synchronous generation is needed. This keeps the information supplied consistent. C1/C2 use fixed control notes and C2's number still depends on the current estimate.

Default live provider: `gemini`, model `gemini-3.5-flash-lite`, thinking `minimal`, up to three application-level attempts, no artificial minimum wait. All model profiles default to a 60-second total generation allowance, with per-request timeouts clipped to the remaining time. Gemini Fast uses 15 seconds per request; the server-default profile respects `ADVISER_REQUEST_TIMEOUT`. SDK retries are disabled. Recoverable failures retry; permanent API errors stop immediately. Exhausted failures produce a labelled generic fallback. Live recovery, latency and cost must be measured in the pilot.

Otherwise valid notes up to three words above the target maximum are kept and flagged for review. During prefetch, explicit instructions to move right/left/up/down need repair because the current initial estimate is unavailable. “Move toward my estimate” avoids that unsupported assumption. The same settings apply across generated conditions. Mechanical validation is not a semantic guarantee.

## Researcher workspace

Unlock `/` with `ACCESS_CODE`, then sign in at `/researcher` with the separate `ADMIN_TOKEN`. Launch a short/full pilot with selected conditions, block length and counterbalance row. Offline mode uses labelled local templates; live mode requires the selected provider key. All researcher and pilot sessions are `TEST`, excluded from production allocation.

Trial diagnostics include actual/expected history length, generation source, fallback/attempts, `prefetched`, and `initial_context_available`. Exports include estimates, errors, WOA, sparse ratings, messages, and phase timing. The display records **generation time separately from visible advice wait**, plus prefetch request and remaining wait, image exposure, response/check-in/break time, hidden-tab interruptions and resume flags.

The duration calculator is an assumption-based planning aid. Use human pilot data to estimate total duration. With the shorter notes the previous package's 42-minute estimate is not a measurement of this version. Aggregate tables can pool offline/live modes and interface versions; filter `adviser_mode`, `is_test`, `source`, `ui_version`, `stimulus_render_version` and `advice_preview_target_ms` before interpretation.

Reloading after the first answer is saved resumes advice without re-showing the image. Repeated browser submissions reuse saved advice without creating duplicate trials or starting a new generation cycle. A reload before the initial answer is saved can repeat exposure; this remains a pilot limitation. Exposure pauses in hidden tabs and browser timing is not a calibrated visual trigger.

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

Startup generates versioned, antialiased stimuli on the protected server and serves pixel-identical lossless WebP files. The files are 1024 pixels wide and display at up to 512 CSS pixels; legacy generator output remains available. Image files are not published to GitHub. `setup_files.py` validates rather than rewriting edited assets. `gunicorn.conf.py` preserves the required 1-worker/8-thread setup even when Render starts plain `gunicorn app:app`.

## Adaptation checks

`python smoke_test.py` checks the complete 105-trial session, schedules, history routing, prefetch idempotency, stale requests, privacy, ratings, fallbacks and end-only scores. DOM interaction tests run with `npm run test:ui`. The browser test in `tests/browser_smoke.cjs` is provided to check desktop/mobile number lines, ratings, prefetch, reload and exports at normal display timings.

```bash
python verify_adaptation.py
python verify_adaptation.py --live --model-profile gemini_fast --contrast trust --repetitions 3 --out probe-trust
python verify_adaptation.py --live --model-profile gpt_stronger --contrast feeling --repetitions 3 --out probe-feeling
```

Offline is API-free. Each example `--live` command makes 24 message generations, each with up to three API attempts by default, and incurs usage. It contrasts resistance/following histories while holding the current advice fixed, with the current estimate unavailable as in prefetch. Reports include raw messages, prompt hashes, latency, source/fallback and shuffled blind review sheets. Static prompts must stay identical across histories; adaptive prompts must differ. Different live text alone does not prove adaptation; inspect whether history claims are supported. Behavioural effects require human data.

## Deployment and data

GitHub: `jennapfeifer/ai-beast-prototype`; Render service: `ai-beast-prototype`, auto-deploying `main`. The source repository remains public as authorised; the task and researcher data are gated by separate private codes. Codes grant access to their holders, not named accounts. The health endpoint reveals only OK/version.

Set `SECRET_KEY`, `ACCESS_CODE` and `ADMIN_TOKEN` before deploying; on Render the app refuses to start without them. Preserve provider API keys and the existing database URL when editing environment settings. `DATABASE_URL` should point to persistent Postgres for retained data; a SQLite file on the free web service can disappear when it restarts. The build stays in pilot mode. Before recruitment, finalise participant information/contact/withdrawal terms, validate live manipulation and timings, and use durable storage.

The original table schema is retained and diagnostic/session tables are additive. Old browser sessions from v6.1 cannot migrate; update between sessions. Retain a data export before deployment. Read the protected `/api/researcher/status` for the deployed model/configuration and database dialect without exposing keys.
