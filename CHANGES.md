# v5 — number line + short advice + faster adviser

- Integrated the attached number-line concept into the actual final-estimate screen.
- AI number is displayed separately from the generated note.
- Final slider starts at the participant's initial estimate; no movement = no update.
- Shortened generated advice from 25–30 words to 8–16 words.
- Added plain-language requirement and bans on invented image-specific evidence, jargon, and verified-accuracy claims.
- Added explicit current-direction context internally so persuasion should not argue in the wrong direction.
- Added Gemini 3.7 Flash support with low thinking; OpenAI GPT-5.6 Luna remains available as a fast fallback.
- Reduced default forced response-delay floor from 2500 ms to 700 ms.
- Reduced validation attempts from 6 to 3 to avoid long retry chains.
- Shortened consent/instructions and made the skip-warm-up researcher path explicit.
- Enhanced progress-only gamification with round-complete feedback and subtle progress animation.
- Added an optional end-only estimation score and closest-estimate summary after all experimental decisions are complete.
- Kept 8×13 production design unchanged pending a power/design decision about shortening the study.
