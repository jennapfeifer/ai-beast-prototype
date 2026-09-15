# Updating the existing Render prototype to v6

Replace the repository files with this v6 folder and let Render redeploy.

For the supervisor/researcher service, check **Render → your web service → Environment**:

```text
RESEARCHER_MODE=1
ADVISER_PROVIDER=gemini
GEMINI_MODEL=gemini-3.7-flash
ADVISER_THINKING_LEVEL=low
ADVISER_MIN_WORDS=6
ADVISER_MAX_WORDS=12
ADVISER_VALIDATION_ATTEMPTS=3
ADVISER_MIN_DELAY_MS=700
SHOW_END_SCORE=1
```

Keep `GEMINI_API_KEY` as a Render secret. Do not commit API keys to GitHub.

The CSS and JavaScript URLs are version-busted to `v=6.0`, so browsers should load the new interface after redeployment rather than a cached v5 asset.
