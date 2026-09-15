# AI-BEAST human study prototype — v6

A Flask web app for the NEW25 AI-advice dot-estimation study. This version keeps the experimental numerical architecture intact while making the participant interaction quicker and more game-like.

## Participant flow

1. Consent
2. Short instructions
3. One warm-up trial (unless skipped in researcher mode)
4. Eight rounds of 13 experimental trials
5. End-only estimation summary and debrief

Each trial is:

**dot image → click first estimate on a 1–400 line → AI estimate + very short note → revise/confirm on the same scale → occasional check-in**

The participant never sees the true count or correctness feedback during the task.

## Interface / gamification

- First estimates are made by clicking the number line; there is no visible default marker before the first click.
- **You** and **AI** use matched circular markers and matched information cards; only colour differs.
- The final-estimate handle is visually distinct.
- The top display shows the current round plus an 8-round map and within-round estimate beads.
- Round-complete screens provide completion feedback only.
- Accuracy score remains locked until the task is finished.
- There are no points for agreeing with AI, no streaks, no leaderboards, no speed reward, and no interim correctness feedback.

The debrief can show:
- first-estimate score,
- final-estimate score,
- closest final estimate,
- number of trials where the final estimate improved on the first.

Scores are 100 minus mean absolute percentage error, clipped to 0–100. These are motivational end feedback, not analysis variables.

## Adviser generation

The numerical advice comes from `design.py`; the language model generates only the short note beneath the displayed AI estimate.

Default visible-note length: **6–12 words**.

`ADVISER_PROVIDER=auto` prefers Gemini when `GEMINI_API_KEY` exists and otherwise uses OpenAI. The Render blueprint is configured for Gemini Flash.

The adviser validator rejects:
- additional visible numerical values,
- image-specific evidence such as invented claims about clusters or overlap,
- jargon such as anchoring/calibration,
- claims of verified/proven correctness,
- highly repetitive wording.

Adaptive conditions still receive the complete earlier history from the current block.

## Core design retained

- Study seed: `20260909`
- 8 conditions × 13 experimental trials = 104 trials
- 104 distinct experimental stimulus images per participant
- C1 mean advice error: exactly 0%
- C3/C4/C5 mean advice error: exactly +25%
- C6/C7/C8 mean advice error: exactly -25%
- C3=C4=C5 numerically for a given truth
- C6=C7=C8 numerically for a given truth
- 144-dot special case remains 144 in C1 and both fixed ±25 schedules
- Ratings after trials 2, 4, 6, 8, 10, 12

## Environment variables

| Variable | Default | Purpose |
|---|---:|---|
| `ADVISER_PROVIDER` | `auto` | `gemini`, `openai`, or automatic key-based choice |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini adviser model |
| `OPENAI_MODEL` | `gpt-5.6-luna` | OpenAI fallback model |
| `ADVISER_THINKING_LEVEL` | `low` | Gemini thinking level |
| `ADVISER_REASONING_EFFORT` | `none` | OpenAI reasoning effort |
| `ADVISER_MIN_WORDS` / `ADVISER_MAX_WORDS` | `6` / `12` | visible note length |
| `ADVISER_VALIDATION_ATTEMPTS` | `3` | retries before fallback |
| `ADVISER_MIN_DELAY_MS` | `700` | common minimum wait floor |
| `STIMULUS_MS` | `5000` | dot-image display time; `0` = untimed debug mode |
| `COLLECT_RATINGS` | `1` | collect trust/feeling check-ins |
| `RATING_EVERY` | `2` | check-in cadence |
| `SHOW_END_SCORE` | `1` | show performance summary only after task completion |
| `RESEARCHER_MODE` | `0` | researcher controls and diagnostic overlay |

### Gemini / Render

Set the following in Render Environment:

```text
GEMINI_API_KEY = your key
ADVISER_PROVIDER = gemini
GEMINI_MODEL = gemini-3.5-flash-lite
ADVISER_THINKING_LEVEL = minimal
ADVISER_MIN_WORDS = 6
ADVISER_MAX_WORDS = 12
ADVISER_MIN_DELAY_MS = 0
```

For the supervisor/researcher deployment also set:

```text
RESEARCHER_MODE = 1
```

## Run locally

```bash
pip install -r requirements.txt
python setup_files.py
python stimuli.py --size 512 --force
python app.py
```

Researcher mode:

```bash
RESEARCHER_MODE=1 ADMIN_TOKEN=test123 python app.py
```

## Data

The built-in admin page can export participants, trials, ratings, or all data as a ZIP. Keep the admin token private.
