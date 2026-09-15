# Updating the existing Render/GitHub prototype from v4 to v5

Replace the v4 project files with the files in this folder and push to the same GitHub repository. Render can redeploy from the same service.

## Render environment changes

For Gemini 3.7 Flash:

```text
ADVISER_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
ADVISER_THINKING_LEVEL=minimal
ADVISER_VALIDATION_ATTEMPTS=1
ADVISER_MIN_WORDS=8
ADVISER_MAX_WORDS=16
ADVISER_MIN_DELAY_MS=0
SHOW_END_SCORE=1
GEMINI_API_KEY=<secret>
```

The old `ADVISER_MODEL=gpt-5` variable is no longer used by v5, so it can be removed.

If you do not want to add a Gemini key yet, use:

```text
ADVISER_PROVIDER=openai
OPENAI_MODEL=gpt-5.6-luna
OPENAI_API_KEY=<your existing secret>
```

Keep `RESEARCHER_MODE=1` on the supervisor-testing service and `0` on the eventual participant service.

## Files changed from v4

Top level: `adviser.py`, `app.py`, `store.py`, `setup_files.py`, `requirements.txt`, `render.yaml`, `smoke_test.py`, `README.md`, `CHANGES.md`.

Inside `static/`: `task.js`, `style.css`.

Inside `templates/`: `consent.html`, `instructions.html`, `debrief.html`, `rate.html`.

The locked `design.py`, `stimuli.py`, generated dot images, database schema for existing trial fields, and condition schedules are unchanged. The database is extended only by computing the end score from already-stored trial rows; no migration is required.
