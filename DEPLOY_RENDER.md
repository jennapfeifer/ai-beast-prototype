# Existing Render deployment

This project updates the existing `ai-beast-prototype` service linked to GitHub `jennapfeifer/ai-beast-prototype` on `main`. Pushing a commit triggers deployment automatically; do not trigger a duplicate deployment after the push.

Build: `pip install -r requirements.txt`. Start: `gunicorn app:app`. The repository's `gunicorn.conf.py` supplies port binding, threads and timeout. Versioned antialiased stimuli are generated on the protected server at startup using the existing deterministic placement algorithm. Include static/estimate.js and the updated assets.py/stimuli.py when uploading v2.9. Templates are committed directly.

Required Render secrets: `SECRET_KEY`, `ACCESS_CODE`, `ADMIN_TOKEN`, and `GEMINI_API_KEY` for live Gemini. Keep existing provider keys and database settings when adding variables. `STUDY_MODE=pilot`; `ADVISER_MODE=live`; provider `gemini`; model `gemini-3.5-flash-lite`; thinking `minimal`; notes target 6–12 words with a three-word tolerance; up to three attempts in a 60-second generation allowance; zero artificial delay. See [PATIENT_RETRIES_UPDATE.md](PATIENT_RETRIES_UPDATE.md) for the new retry variables and migration from the old one-attempt settings. The blueprint documents the configuration; editing YAML alone does not update settings on an existing manually configured service.

`ACCESS_CODE` protects entry; `ADMIN_TOKEN` protects researcher controls/exports. The running task is private even though the authorised source repository remains public. Open a fresh browser session to verify the gate. `/healthz` is public and returns OK plus a version; `/api/researcher/status` is protected and reports configuration without keys.

Data should use persistent Postgres. Local SQLite is useful for tests; on an ephemeral free web service it is not retained across restarts. Export/back up before replacing a deployment. Runtime sessions from the original prototype cannot be resumed after this upgrade.

Official references: [Render Flask deployment](https://render.com/docs/deploy-flask), [Blueprint fields](https://render.com/docs/blueprint-spec).
