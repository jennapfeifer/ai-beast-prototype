# v6 — engaging number-line prototype

This revision keeps the NEW25 experimental architecture unchanged and redesigns the interaction around speed, clarity, and completion-based gamification.

## Interaction
- First estimate is now made directly on a 1–400 number line.
- No default marker is shown before the participant makes a choice, reducing visual anchoring from a pre-positioned handle.
- Mouse/touch click places the estimate; dragging fine-tunes it. Keyboard number entry and arrow-key adjustment are also supported.
- The final-estimate screen gives **You** and **AI** the same marker shape, size, layout, and typography; they differ only in colour.
- The movable final-estimate handle has a third, distinct visual treatment.
- The numerical recommendation is separated from the verbal persuasion note.

## Advice
- Default generated note length reduced from 8–16 to **6–12 words**.
- Gemini Flash remains the default Render adviser for faster generation.
- Existing safeguards remain: no image-specific hallucinated evidence, no displayed extra numbers, no unsupported claims of verified accuracy, and adaptive behavioural claims must be grounded in the block history.

## Engagement
- 8-round map remains visible throughout the task.
- A 13-dot micro-progress strip fills within each round.
- Round-complete screens use small completion animations and a “score locked until the finish” cue.
- No trial-by-trial or round-by-round accuracy feedback is given.
- No rewards for following the AI, moving toward advice, speed, or agreement are used.
- End-only summary now shows first-estimate score, final-estimate score, closest final estimate, and the number of trials on which the final estimate was closer to truth.

## Study screens
- Instructions frame the task as an estimation game with a simple accuracy goal.
- Consent text is shorter and describes 8 rounds rather than foregrounding “104 images.”
- Researcher controls and diagnostic overlay are unchanged.

## Not changed
- 8 conditions × 13 experimental trials.
- NEW25 numerical advice schedules and exact +25% / -25% means.
- Counterbalancing and stimulus assignment.
- Adaptive adviser receives complete earlier within-block history.
- Trust/feeling ratings remain after trials 2, 4, 6, 8, 10, and 12.
- No correctness feedback occurs before the experiment is complete.
