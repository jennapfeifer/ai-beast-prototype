## v2.29 — shared voice with matched cadence

Voice timing is now explicitly matched across neutral and persuasive conditions. Persuasion is carried by warmth/engagement/confidence rather than faster rhythm, dramatic pauses, stretched words, or a punched ending. See `SHARED_VOICE_MATCHED_CADENCE_v2.29.md`.

# v2.28 — shared speaker, prosody-only voice contrast

All conditions now use the same OpenAI TTS speaker at the same synthesis and playback rate (`1.0`). Neutral versus persuasive delivery differs only through acting/prosody instructions. Persuasive speech is warmer, more assertive, more expressive, and more emphatic, but is explicitly told not to speak faster than neutral. Browser speech fallback also uses rate `1.0` in every condition. The Safari bottom-scrollbar fix from v2.27 is retained.

# v2.27 — shared OpenAI voice + deterministic delivery contrast + Safari scrollbar fix

No Hume account or extra API key is required. Voice + text uses the existing OpenAI TTS configuration with **one shared speaker identity** for every agent. Neutral and persuasive conditions still receive different acting instructions, but the browser now also applies a deterministic, pitch-preserving delivery-rate contrast (**0.88 neutral vs 1.12 persuasive**) so the manipulation remains clearly audible even when the TTS model renders the acting instructions subtly. The actual playback rate is logged as `voice_delivery_rate`.

The white strip visible at the bottom of the consent page was identified from the screenshot as a Safari-style **horizontal scrollbar track**. Participant pages now suppress root horizontal overflow and explicitly hide the horizontal WebKit scrollbar while preserving vertical scrolling. See `OPENAI_VOICE_SCROLLBAR_FIX_v2.27.md`.

## v2.26 — Hume expressive voice + Safari root-strip fix

Voice + text now prefers **Hume Octave 1** with one shared speaker identity and a deliberately large neutral-versus-persuasive acting contrast. OpenAI TTS remains a fallback. The persistent white bottom strip shown on the consent page was traced to the HTML/root scrolling canvas: only `/task` previously received the dark `task-root` class. Consent, instructions, and debrief now receive the same dark root and horizontal-overflow clipping. See `HUME_VOICE_AND_ROOT_FIX_v2.26.md`.

## v2.25 — one speaker, deliberately dramatic delivery contrast

All eight named agents now use the **same TTS speaker identity**. Neutral C1/C2/C3/C6 use a calm, cool, matter-of-fact delivery; persuasive C4/C5/C7/C8 use the same speaker but a deliberately strong warm/assertive/expressive performance. Static and adaptive persuasive conditions share the exact same voice-performance profile, so any additional difference between them comes from the generated language/history rather than a second vocal manipulation. The browser fallback also keeps one speaker and exaggerates rate/pitch only as a backup. See `SHARED_SPEAKER_DRAMATIC_DELIVERY_v2.25.md`.

# Latest: v2.23 free-form persuasion

C4/C7 and C5/C8 are no longer forced into researcher-authored persuasion tactics. Static persuasive agents may use any conversational or persuasive approach they choose. Adaptive persuasive agents receive recent completed history and may use it however they think is useful; no deterministic `recommended_strategy_family` is supplied to the model. C3/C6 remain neutral. All generated messages are asked for one short sentence of roughly 12–20 words and to include the recommendation number. The first successful model response is displayed as-is: there is no semantic repair and no length-only retry. Recent same-agent messages are supplied only to discourage copying. Current first estimates remain hidden during generation. See `FREE_PERSUASION_UPDATE_v2.23.md`.

# Latest: v2.21 social encouragement + 16–18-word matching + simulation prefetch parity

Persuasive C4/C5/C7/C8 agents now include brief human social encouragement (for example, “Good job”, “You’re doing great”, or “Nice work”) without tying praise to objective accuracy. All eight conditions target 16–18 spoken words. C1/C2 use a rewritten fixed bank; C3–C8 get at most one mechanical length-only retry, with the untouched first draft retained in the audit. The live-review simulator now calls the same prefetch endpoint as the real task before supplying the synthetic participant’s current estimate, so C3–C8 audits should show `initial_context_available=false`. See `SOCIAL_PRAISE_LENGTH_SIMULATION_UPDATE_v2.21.md`.

# Latest: v2.20 prefetched advice + stronger voice contrast + dark-root fix

Generated C3-C8 agent text no longer receives the participant's current first estimate. That lets text generation begin before the dot display and lets natural TTS prepare while the participant is viewing/estimating, greatly reducing visible wait. Adaptive agents still receive completed earlier-trial behaviour and ratings. The same speaker identity is held constant across neutral and persuasive conditions, but the TTS instructions now deliberately make the neutral delivery restrained/low-affect and the persuasive delivery forceful, emotionally engaged, high-conviction, and dynamically stressed. The task root is also dark so Safari/browser overscroll no longer reveals a white bar at the bottom. See `PREFETCH_VOICE_UI_UPDATE_v2.20.md`.

# Latest: v2.19 grounded + length-matched + genuinely adaptive agents

The first live-review simulation showed three issues: C1/C2/neutral messages were shorter than persuasive messages; generated agents sometimes invented visual evidence or claimed hidden accuracy; and C5/C8 adaptation was often only superficial. v2.19 gives all conditions a 14–18-word target, explicitly tells generated agents what they do and do not know, and supplies C5/C8 with a deterministic response/trust summary that must change persuasive strategy. Raw live outputs are still displayed without semantic repair. See `AGENT_GROUNDING_LENGTH_ADAPTATION_v2.19.md`.

# Latest: v2.18 faster voice + same speaker + stronger persuasion

Participant instructions no longer say ‘red’. Voice identity is now held constant across conditions, while neutral and persuasive delivery are deliberately separated much more strongly. TTS defaults to WAV for lower latency and voice preparation starts as early as possible. See `VOICE_TONE_LATENCY_UPDATE_v2.18.md`.

# Latest: v2.17 synced audio + distinct agent voices

Voice is now prepared *before* the advice appears, starts with the advice text, and finishes before the final number line is shown. Each agent also receives a different natural TTS speaker shuffled per participant, while neutral versus persuasive conditions use a deliberately stronger delivery contrast. See `VOICE_SYNC_UPDATE.md`.

# Latest: v2.16 voice reads message only

Voice + text now speaks exactly the generated advice message shown in quotation marks. The agent name, recommendation number, and interface labels are visual only. See `ADVICE_UI_VOICE_FIX.md`.

# Latest: v2.15 advice bubble + natural voice fix

Read `ADVICE_UI_VOICE_FIX.md`. Agent wording is now anchored in a box directly below the red advice triangle, voice playback cannot block progression, and Voice + text uses natural server-side TTS when `OPENAI_API_KEY` is available (with a better local-voice fallback).

# Latest: v2.14 agent / raw-generation pilot

Read AGENT_RAW_PILOT_UPDATE.md. Participant-facing framing is now AGENT, generated conditions use raw unvalidated model wording, a voice+text pilot is available, and dot layout can be switched between random/regular/jittered.

# Latest: v2.13 flexible current-trial advice

Read FLEXIBLE_ADVICE_UPDATE.md. New sessions use 10–20-word target prompts, the current first estimate, and no prefetch. Earlier sections below describe historical versions.

# Latest: v2.11

See ADVICE_READING_UPDATE.md for consistent advice typography and the five-second default (with 0/3/4/5-second options).

# BEAST · private AI adviser pilot

The v6.1 **number line, short Gemini notes and advice prefetch** are integrated with protected pilot controls, server-side sessions, timing diagnostics and recovery. Original NEW25 numerical advice, counterbalancing and deterministic dot positions/counts are retained; visual and delivery versions are recorded.


Current update: **v2.10.1, simpler participant flow and marker layering** (`fieldwork-2.10.1-marker-layer`).
See [SIMPLE_FLOW_UPDATE.md](SIMPLE_FLOW_UPDATE.md) for installation and protocol changes.

New sessions collect trust only; feeling stays null. Old sessions retain both questions.
The following adviser description also covers historical two-rating sessions and probe tools.

Trust means trust in the AI adviser. Feeling means the reported reaction to its advice.
These inputs now supply internal persuasion approaches rather than requiring the model
to repeat the ratings. Both available approaches inform adaptive tone; the existing
behaviour/trust/feeling cycle selects emphasis. Implicit influence needs comparison and
human review. Every adaptive note with usable history must now reference the previous decision, including trust/feeling turns. The model returns a structured internal fact record and a short participant-facing message in the same request. Matching that record checks extraction, not whether ratings meaningfully changed the wording. Both persuasive conditions request clear recommendations; optional filler such as “if you wish” is rejected. Low trust and negative feeling change the framing without switching to neutral advice.

## Participant flow

Image (5 s) → first estimate on a blank number line → AI number + short note (target 6–12 words, tolerance up to 15) → final slider → occasional trust rating (selection advances immediately). The final slider starts at the participant's first estimate, as in v6.1. The first estimate uses a grey square, AI advice a bright-blue pointer below the white line, and the final choice a red square. Direct labels replace the cards and legend. A plain progress bar shows completion; scores appear only after finishing.

C3–C8 notes are prefetched after the image is displayed. The fixation screen is removed. By default the task shows the advice alone for three visible seconds before the final-estimate line (the researcher can restore simultaneous display); it applies to all selected conditions and does not prove reading. The model gets the fixed recommendation and, for C5/C8 only, every completed earlier trial in that block. **It never gets the current first estimate**, even if prefetch fails and synchronous generation is needed. This keeps the information supplied consistent. C1/C2 use fixed control notes and C2's number still depends on the current estimate.

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

## v2.21 social-praise / length-matching update

C1–C8 now aim for 16–18 words. Persuasive agents may use grounded social encouragement without claiming accuracy. Live generated messages get at most one mechanical word-count retry; both the first raw draft and displayed draft are retained in the audit. The live-review simulator now uses the same prefetch-before-initial-estimate path as the participant task.
