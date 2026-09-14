# v3 change

- Reduced practice from three trials to **one warm-up trial** (88 dots, outside the experimental count set). The full session is now 1 warm-up + 104 experimental trials = 105 trials shown.

# Changes in this revision

This revision keeps the NEW25 numerical design and historical GPT-5 persuasion policy, and adds the requested prototype refinements.

- Trust + feeling check-ins now appear only after every second experimental trial (2, 4, 6, 8, 10, 12 within each 13-trial block). Odd trials and trial 13 store blank rating fields.
- Production condition order still rotates over 8 counterbalancing rows. Researcher TEST sessions no longer consume that production sequence.
- In `RESEARCHER_MODE=1`, the start page now has a condition selector, trials-per-condition control, skip-practice checkbox, and counterbalancing-row selector.
- GPT-5 validation attempts increased from 3 to 6.
- Added anti-repetition validation: near-duplicate wording within a block is regenerated.
- Replaced the single repeated fallback sentence with varied style-specific fallback banks.
- Updated the OpenAI Python SDK requirement so the Responses API used by GPT-5 is actually available (`openai>=1.68,<2`). The older pinned SDK could cause every GPT-5 call to fail and therefore trigger the fallback repeatedly.
- Added `/admin?token=YOUR_ADMIN_TOKEN`, with buttons to download trials, participants, blind message ratings, or one ZIP containing all three.
- Added `/admin/export/all.zip?token=YOUR_ADMIN_TOKEN`.
- Researcher overlay now reports how many earlier messages were checked for repetition as well as adaptive history length.
## v4 — one visible number + grounded adaptive history

- GPT-5 drafts now use a literal `[ESTIMATE]` placeholder; the server inserts the fixed NEW25 advice number only after validation.
- Visible adviser messages therefore contain the current recommendation as the only numerical value; previous estimates/ratings are used internally but may only be referenced qualitatively.
- Adaptive prompts now explicitly require claims about the participant's prior behaviour to match the actual supplied history.
- Added a server-derived qualitative movement summary (mostly resistant / mixed / often moved toward) to help ground adaptive wording while retaining the full exact history.
- Adaptive fallbacks no longer make stock claims that the participant has previously revised toward or followed the adviser.
- Retry feedback no longer accumulates across attempts, reducing prompt clutter after a format failure.
- Repetition similarity now normalises recommendation numbers so the same wording with a different target is still detected as repetition.

