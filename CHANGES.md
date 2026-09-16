# Fieldwork 2.1 · v6.1 integration

Retains the repository's number-line first estimates, final slider, short-note Gemini configuration, prefetch, and end-only scoring. Adds the field-map presentation and protected pilot workspace from the prepared build.

- Prefetch is cached server-side by trial token; repeated requests do not generate again.
- C5/C8 receive exact completed within-block history; static/neutral receive no previous trials. The current estimate is consistently withheld from model generation, including synchronous recovery.
- Backend cursor, pending advice and prefetched notes move out of the browser cookie into transactional database state.
- Duplicate initial/final submissions are safe; stale tokens cannot advance a different trial.
- Adds separate task/researcher access, CSRF checks, opaque stimulus URLs and protected exports.
- Records model generation, prefetch and visible wait separately, plus response/rating/break/exposure and interruption timing.
- One Gemini SDK attempt with explicit timeout. Fallbacks remain labelled and do not claim to have used earlier history.
- Generates PNGs privately at startup using the existing public stimulus code and stops template overwrite during setup.
- Includes a contrastive history probe, complete-session tests and number-line browser validation.

Mechanical and browser tests establish routing/functionality, not a human adaptive-versus-static effect. Live latency/fallback and text quality are separate pilot checks. Legacy v6 deployment/migration documents are historical; README describes the current build.
