# AI-BEAST live LLM + audio prototype

This prototype implements the design discussed for the screening task:

- The **experiment**, not the LLM, determines whether advice is helpful/misleading.
- The experiment calculates the **numerical advice** from the participant's estimate and the true count.
- A real OpenAI model is called **only to generate the wording** in either an affirming or challenging style.
- The advice is delivered aloud using the computer/browser's **built-in text-to-speech**.
- The same voice is used for both assistants.
- The generated sentence, generation latency, trial condition, estimates, WOA, replay count, and other trial-level variables are logged.
- Participant-facing adviser labels are **AI Assistant 1** and **AI Assistant 2**.
- Which assistant is higher reliability is counterbalanced deterministically from participant ID.

## What this prototype is for

This is an 8-trial proof of concept for piloting the interaction, wording, latency, and audio delivery.

It is **not yet the final N=200–250 research implementation**. The final version should use a longer fully counterbalanced schedule, formal practice trials, fixed preregistered scoring/exclusion rules, and a production data backend or research platform.

## 1. Requirements

Install:

- Node.js 20 or later
- An OpenAI API key
- A modern browser such as Chrome, Edge, Safari, or Firefox

## 2. Setup

Open Terminal in this folder and run:

    npm install

Copy `.env.example` to `.env`:

macOS/Linux:

    cp .env.example .env

Windows PowerShell:

    Copy-Item .env.example .env

Open `.env` in a text editor and replace:

    OPENAI_API_KEY=your_api_key_here

with your real API key.

Do **not** put the API key into `public/index.html` or commit `.env` to GitHub.

## 3. Start the prototype

Run:

    npm start

Then open:

    http://localhost:3000

The start screen should say **Live model ready**.

## 4. What happens on each trial

1. Dot stimulus appears briefly.
2. Participant enters an initial estimate.
3. Participant reports confidence.
4. The experiment calculates a controlled numerical advice value.
5. The server sends only:
   - participant estimate,
   - experiment-controlled AI estimate,
   - required wording style
   to the OpenAI model.
6. The LLM returns one short sentence.
7. The browser reads the sentence aloud.
8. Participant enters a final estimate.
9. True count is shown.
10. Trial data are saved locally.

The LLM is never shown the true dot count or told whether the trial is intended to be helpful/misleading. This prevents the model from changing the experimental manipulation.

## 5. Local data

Each completed trial is appended to:

    data/trials.csv

The end screen also lets you:

- download the current participant's CSV;
- download the combined local `trials.csv`.

Use anonymous study IDs, not participant names or emails.

## 6. Audio

The prototype uses the operating system/browser speech-synthesis voices. On the start screen:

- choose one English voice;
- use **Test selected voice**;
- keep exactly the same voice, rate, and pitch across experimental conditions.

The generated sentence is hidden from participants by default. Tick **Show generated wording on screen (debug only)** when you want to inspect what the model produced during development.

## 7. LLM controls

The server:

- requires the model to state the experiment-controlled advice number exactly;
- constrains the response to one short sentence;
- prevents references to correctness, accuracy, reliability, or previous trials;
- retries once if the result fails basic format checks;
- uses a fixed fallback sentence only if both generated outputs fail validation.

Whether a fallback was used is stored in `llm_fallback`.

For a formal experiment, review generated pilot outputs and decide whether fallback trials should be excluded or rerun.

## 8. Important limitation for online deployment

The `data/trials.csv` approach is useful for **local piloting on one lab computer**.

Do not rely on this file for a deployed multi-participant study on a serverless platform such as Vercel: local server storage may be ephemeral and concurrent writes are not a robust research database.

For the full screening study, connect the task to a persistent database/research platform (for example JATOS/jsPsych infrastructure, a university server, or another approved backend).

## 9. Files

- `server.js` — server-side OpenAI call + local data logging
- `public/index.html` — experiment interface and task logic
- `.env.example` — environment-variable template
- `package.json` — Node dependencies
- `data/` — local pilot data are written here

## 10. API privacy design

The OpenAI request does **not** include the participant ID. It sends only the numeric initial estimate, the controlled advice number, and the requested communication style. The prototype also sets `store: false` on the model response request.

