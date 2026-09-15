# AI-BEAST human study — v5 usability revision

This revision keeps the locked NEW25 numerical schedules, counterbalancing, 8 conditions, 13 trials per condition, one warm-up, adaptive full within-block history, and the trust/feeling schedule. It changes the participant-facing interaction to reduce reading and waiting burden.

## What changed

### 1. Advice number and language are now separate
The AI recommendation is a controlled number shown prominently as **AI estimate**. The model generates only a short note underneath it. The note contains no digits. This makes the numerical recommendation easy to see and keeps the communication manipulation separate from the number itself.

### 2. Final response uses a 1–400 number line
After the participant's first estimate, the final-answer screen shows:
- the AI estimate;
- the participant's initial estimate;
- both positions on a fixed 1–400 number line;
- a slider starting exactly at the participant's initial estimate.

Leaving the slider untouched therefore means no revision. The initial estimate is still typed rather than entered on a slider so the scale cannot anchor the initial judgment.

### 3. Shorter, simpler advice
Generated notes default to **8–16 words**, one sentence, plain language. The validator rejects:
- digits;
- image-specific claims about clusters, overlap, spacing, density, edges, etc.;
- jargon such as *anchor* or *calibrate*;
- claims of proven/verified accuracy;
- highly repetitive wording.

Adaptive messages still receive every completed earlier trial in the same block and may refer qualitatively to the participant's prior response pattern when that claim is supported by the history.

### 4. Faster adviser path
The adviser is provider-configurable:
- Gemini default: `gemini-3.7-flash`, low thinking;
- OpenAI fallback/default without a Gemini key: `gpt-5.6-luna`, reasoning effort `none`.

`ADVISER_PROVIDER=auto` prefers Gemini when `GEMINI_API_KEY` exists and otherwise uses OpenAI. The Render blueprint is set to Gemini explicitly.

The old fixed 2500 ms waiting floor is reduced to **700 ms**. Real model latency can still exceed that floor.

### 5. More motivating, but non-contaminating, progress feedback
During the task, participants get only completion feedback: an 8-round tracker, round-complete checkpoint screens, and subtle progress animation. They do **not** receive accuracy feedback, AI-agreement rewards, streaks, leaderboards, or trial-by-trial scores.

After the final experimental decision, the debrief can show an end-only estimation score and the participant's closest final estimate. The score is `100 - mean absolute percentage error`, clipped to 0–100. This is motivational feedback, not an analysis variable. Disable it with `SHOW_END_SCORE=0` if desired.

### 6. Instructions are shorter
The long instruction wording was removed. The participant now gets five concise steps and a simple 8-round roadmap.

### 7. Researcher skip-warm-up path is clearer
When the researcher selects **Skip warm-up**, the instructions page now says **Begin task** instead of **Begin warm-up**. The schedule itself continues to omit the warm-up.

## Locked experimental structure

- 8 conditions × 13 trials = 104 experimental trials.
- 1 warm-up trial (88 dots), unless skipped in researcher mode.
- True counts: `32, 40, 48, 64, 80, 96, 112, 128, 144, 160, 192, 224, 256`.
- C1 mean signed advice error 0%.
- C3/C4/C5 share the fixed NEW25 +25% mean schedule.
- C6/C7/C8 share the fixed NEW25 -25% mean schedule.
- C2 remains participant-relative and changes the current initial estimate by <4%.
- Image-to-condition mapping and condition order remain counterbalanced.
- 144 remains explicitly position-counterbalanced.
- Trust + feeling check-ins remain after trials 2, 4, 6, 8, 10 and 12 in each condition.

The production trial count is intentionally **not shortened in this revision**. Researcher mode already lets you test any condition with 1–13 trials. A production reduction should be decided from the primary contrast/power analysis rather than only from the usability pilot.

## Model configuration

| Variable | Default | Purpose |
|---|---|---|
| `ADVISER_PROVIDER` | `auto` | `gemini`, `openai`, or automatic key-based choice |
| `GEMINI_MODEL` | `gemini-3.7-flash` | Gemini adviser model |
| `OPENAI_MODEL` | `gpt-5.6-luna` | OpenAI fallback adviser model |
| `ADVISER_THINKING_LEVEL` | `low` | Gemini thinking level |
| `ADVISER_REASONING_EFFORT` | `none` | OpenAI reasoning effort |
| `ADVISER_MIN_WORDS` / `ADVISER_MAX_WORDS` | `8` / `16` | visible note length |
| `ADVISER_VALIDATION_ATTEMPTS` | `3` | retries before fallback |
| `ADVISER_MIN_DELAY_MS` | `700` | minimum wait floor in all conditions |
| `STIMULUS_MS` | `5000` | image viewing time |
| `SHOW_END_SCORE` | `1` | show score only after task completion |
| `RESEARCHER_MODE` | `0` | researcher controls/overlay |

## Render

For the default Gemini setup, add a secret environment variable:

```text
GEMINI_API_KEY = your Gemini API key
```

and set:

```text
ADVISER_PROVIDER = gemini
GEMINI_MODEL = gemini-3.7-flash
ADVISER_THINKING_LEVEL = low
ADVISER_MIN_DELAY_MS = 700
```

If you want to stay on OpenAI instead, use:

```text
ADVISER_PROVIDER = openai
OPENAI_MODEL = gpt-5.6-luna
OPENAI_API_KEY = your existing key
```

The researcher overlay reports the actual provider/model in `source`, e.g. `gemini:gemini-3.7-flash`.

## Local run

```bash
pip install -r requirements.txt
python setup_files.py
python stimuli.py --size 512 --force
python smoke_test.py
python app.py
```

Open `http://127.0.0.1:5000`.

## Important protocol note

Changing from GPT-5 to Gemini 3.7 Flash or GPT-5.6 Luna changes the language model that instantiates the communication manipulation. Treat that as a protocol change and document it. The NEW25 numbers themselves are unchanged.
