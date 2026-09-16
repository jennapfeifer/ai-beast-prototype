# Fieldwork 2.1 integration validation

Integrated against GitHub commit `e97fdcaea053cd2bd433fad82d6c29d0e781d4a5` (v6.1). Preserves number-line responses, short notes, Gemini preference, advice prefetch and end-only scores.

- 22 API-free automated tests passed, including a full 105-trial session, fixed schedules, sparse ratings, adaptive history 0–12, static history isolation, production allocation, privacy/CSRF and exports.
- Prefetch-specific checks: cached once, duplicate requests reuse it, current estimate withheld consistently, stale requests rejected, previous completed answers available to the next adaptive prefetch.
- Browser pilot: seven trials (warm-up plus C4/C5 × three), normal five-second image exposure, no artificial delay. Number-line keyboard entry, final slider, ratings, checkpoint, reload recovery, debrief and export passed.
- Desktop 1440 px and mobile 390 px inspected, including the number-line decision screen. No overflow or uncaught JavaScript errors in that run.
- Offline visible wait medians: C4 13 ms; C5 14.5 ms. These are local deterministic templates, not live model latency. Trial medians were approximately six seconds with automated responses. No human duration estimate follows from these numbers.
- One deliberate advice-screen reload was flagged resumed and excluded from complete timing summaries.
- The existing public generator recreates all 105 original PNGs byte for byte; PNG files are not committed.

Live model semantics, live latency, concurrent production load and human effects are separate checks. Different wording alone does not establish meaningful adaptation. Pre-answer reload can repeat exposure; browser timing is approximate. The illustrative R analysis is not a preregistered specification.
