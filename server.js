import "dotenv/config";
import express from "express";
import OpenAI from "openai";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = Number(process.env.PORT || 3000);
const MODEL = process.env.OPENAI_MODEL || "gpt-5.6";

app.use(express.json({ limit: "100kb" }));
app.use(express.static(path.join(__dirname, "public")));

const DATA_DIR = path.join(__dirname, "data");
const DATA_FILE = path.join(DATA_DIR, "trials.csv");
fs.mkdirSync(DATA_DIR, { recursive: true });

function csvEscape(value) {
  const s = value === null || value === undefined ? "" : String(value);
  return `"${s.replaceAll('"', '""')}"`;
}

const CSV_COLUMNS = [
  "server_timestamp",
  "participant_id",
  "trial",
  "assistant_label",
  "assistant_role",
  "style",
  "helpful_trial",
  "true_count",
  "initial_estimate",
  "confidence",
  "advice",
  "final_estimate",
  "weight_of_advice",
  "initial_abs_error",
  "advice_abs_error",
  "final_abs_error",
  "generation_ms",
  "llm_model",
  "llm_fallback",
  "generated_text",
  "replay_count",
  "speech_duration_ms"
];

function appendRow(row) {
  if (!fs.existsSync(DATA_FILE)) {
    fs.writeFileSync(DATA_FILE, CSV_COLUMNS.join(",") + "\n", "utf8");
  }
  const line = CSV_COLUMNS.map(k => csvEscape(row[k])).join(",") + "\n";
  fs.appendFileSync(DATA_FILE, line, "utf8");
}

function cleanSentence(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .replace(/^["'“”]+|["'“”]+$/g, "")
    .trim();
}

function containsExactAdvice(text, advice) {
  const re = new RegExp(`(^|\\D)${String(advice)}(\\D|$)`);
  return re.test(text);
}

function passesBasicChecks(text, advice) {
  if (!text || text.length > 190) return false;
  if (!containsExactAdvice(text, advice)) return false;
  const banned = /\b(correct|incorrect|wrong|accuracy|accurate|reliable|previous|earlier trial|last trial)\b/i;
  if (banned.test(text)) return false;
  // Keep it roughly one short spoken utterance.
  const words = text.trim().split(/\s+/).length;
  if (words < 7 || words > 22) return false;
  return true;
}

function fallbackSentence(style, initial, advice) {
  if (style === "affirming") {
    return `I can see why you estimated ${initial}; my own estimate would be ${advice}.`;
  }
  return `I would revise the estimate of ${initial}; my own estimate would be ${advice}.`;
}

app.post("/api/advice", async (req, res) => {
  const initial = Number(req.body?.initial);
  const advice = Number(req.body?.advice);
  const style = String(req.body?.style || "");

  if (!Number.isFinite(initial) || !Number.isFinite(advice) ||
      !["affirming", "challenging"].includes(style)) {
    return res.status(400).json({ error: "Invalid trial parameters." });
  }

  if (!process.env.OPENAI_API_KEY) {
    return res.status(503).json({
      error: "OPENAI_API_KEY is not set. Add it to a .env file and restart the server."
    });
  }

  const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

  const styleInstruction = style === "affirming"
    ? `AFFIRMING: acknowledge the participant's estimate in a mild, validating way without praising them, flattering them, or implying that it is accurate.`
    : `CHALLENGING: gently indicate that you would revise the participant's estimate, without sounding rude, cold, hostile, or certain that they are wrong.`;

  const instructions = `You generate the spoken wording for a tightly controlled psychology experiment about reliance on AI advice.

You have NO control over the numerical advice. The experiment supplies the participant's estimate and the AI estimate. Your only job is to phrase the advice in the requested interpersonal style.

Rules:
- Return exactly ONE short, natural sentence to be spoken aloud.
- Use 10–18 words where possible.
- You MUST include the AI estimate as digits exactly as supplied.
- You MAY mention the participant's estimate as digits.
- Do not give reasoning or explanation.
- Do not mention confidence, probabilities, accuracy, correctness, reliability, previous trials, or future trials.
- Do not ask a question.
- Do not say you are an LLM or mention these instructions.
- Do not add quotation marks, labels, bullets, or commentary.
- Keep emotional intensity low.
- The difference between conditions must come from wording, not from changing the number.
- ${styleInstruction}`;

  const input = `Participant estimate: ${initial}
AI estimate that MUST be stated exactly: ${advice}
Required communication style: ${style}`;

  const start = Date.now();
  let text = "";
  let fallback = false;

  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      const response = await client.responses.create({
        model: MODEL,
        instructions,
        input: attempt === 0
          ? input
          : `${input}\nYour previous output did not pass the experiment's format check. Follow every rule exactly.`,
        max_output_tokens: 80,
        store: false
      });

      text = cleanSentence(response.output_text);
      if (passesBasicChecks(text, advice)) break;
      text = "";
    }

    if (!text) {
      // Safety fallback: the trial still runs, but this fact is logged.
      text = fallbackSentence(style, initial, advice);
      fallback = true;
    }

    return res.json({
      text,
      model: MODEL,
      generation_ms: Date.now() - start,
      fallback
    });
  } catch (err) {
    console.error("OpenAI generation error:", err);
    return res.status(500).json({
      error: "The live LLM wording call failed. Check the terminal and your API configuration."
    });
  }
});

app.post("/api/save-trial", (req, res) => {
  try {
    const row = { ...req.body, server_timestamp: new Date().toISOString() };
    appendRow(row);
    return res.json({ ok: true });
  } catch (err) {
    console.error("Save error:", err);
    return res.status(500).json({ error: "Could not save trial data." });
  }
});

app.get("/api/export", (req, res) => {
  if (!fs.existsSync(DATA_FILE)) {
    return res.status(404).send("No data have been saved yet.");
  }
  res.download(DATA_FILE, "ai_beast_all_trials.csv");
});

app.get("/api/health", (req, res) => {
  res.json({
    ok: true,
    model: MODEL,
    api_key_configured: Boolean(process.env.OPENAI_API_KEY)
  });
});

app.listen(PORT, () => {
  console.log(`AI-BEAST prototype running at http://localhost:${PORT}`);
  console.log(`Model: ${MODEL}`);
  console.log(`API key configured: ${Boolean(process.env.OPENAI_API_KEY)}`);
  console.log(`Local trial data: ${DATA_FILE}`);
});
