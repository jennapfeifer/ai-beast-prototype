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
const TTS_MODEL = process.env.OPENAI_TTS_MODEL || "gpt-4o-mini-tts-2025-12-15";
const DEFAULT_TTS_VOICE = process.env.OPENAI_TTS_VOICE || "cedar";

const ALLOWED_VOICES = new Set([
  "alloy", "ash", "ballad", "coral", "echo", "fable",
  "onyx", "nova", "sage", "shimmer", "verse", "marin", "cedar"
]);

const TTS_INSTRUCTIONS = [
  "Speak like a natural AI assistant in a brief psychology task.",
  "Use calm, neutral, everyday delivery with natural pacing and subtle prosody.",
  "Keep vocal tone, warmth, pace, volume, and directiveness as consistent as possible across experimental conditions.",
  "Do not sound theatrical, unusually persuasive, cold, robotic, or overly cheerful.",
  "Use small natural pauses at punctuation.",
  "Read numbers naturally.",
  "Do not place extra emphasis on the numerical estimate."
].join(" ");

app.use(express.json({ limit: "250kb" }));
app.use(express.static(path.join(__dirname, "public")));

const DATA_DIR = path.join(__dirname, "data");
const DATA_FILE = path.join(DATA_DIR, "trials.csv");
fs.mkdirSync(DATA_DIR, { recursive: true });

const CSV_COLUMNS = [
  "server_timestamp",
  "participant_id",
  "trial",
  "n_trials_planned",
  "ai_style",
  "true_count",
  "initial_estimate",
  "advice",
  "intended_advice_quality",
  "realized_advice_quality",
  "advice_adjusted",
  "advice_adjustment_reason",
  "final_estimate",
  "weight_of_advice",
  "initial_abs_error",
  "advice_abs_error",
  "final_abs_error",
  "generated_text",
  "llm_model",
  "llm_fallback",
  "llm_generation_ms",
  "tts_model",
  "tts_voice",
  "advice_tts_generation_ms",
  "advice_speech_duration_ms",
  "advice_replay_count",
  "question_id",
  "question_text",
  "question_low_anchor",
  "question_high_anchor",
  "question_rating",
  "history_n_trials",
  "history_before_advice_json"
];

function csvEscape(value) {
  const s = value === null || value === undefined ? "" : String(value);
  return `"${s.replaceAll('"', '""')}"`;
}

function appendRow(row) {
  if (!fs.existsSync(DATA_FILE)) {
    fs.writeFileSync(DATA_FILE, CSV_COLUMNS.join(",") + "\n", "utf8");
  }
  const line = CSV_COLUMNS.map(k => csvEscape(row[k])).join(",") + "\n";
  fs.appendFileSync(DATA_FILE, line, "utf8");
}

function getOpenAIClient() {
  return new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
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

function adviceTextPasses(text, advice) {
  if (!text || text.length > 260) return false;
  if (!containsExactAdvice(text, advice)) return false;
  const words = text.trim().split(/\s+/).length;
  if (words < 6 || words > 26) return false;

  const banned = /\b(true answer|correct answer|helpful trial|misleading trial|sycophantic|neutral condition|experimental condition|better listen to me|trust me)\b/i;
  return !banned.test(text);
}

function simpleHash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function normalizeHistory(history) {
  if (!Array.isArray(history)) return [];

  // Intentionally keep ALL completed trials. The task is stateless at the API level:
  // the browser explicitly sends this compact history again on every advice call.
  return history.slice(0, 100).map(x => ({
    trial: Number(x.trial),
    initial_estimate: Number(x.initial_estimate),
    advice: Number(x.advice),
    final_estimate: Number(x.final_estimate),
    true_count: Number(x.true_count),
    question_id: String(x.question_id || "").slice(0, 60),
    question_rating: Number(x.question_rating)
  })).filter(x =>
    Number.isFinite(x.trial) &&
    Number.isFinite(x.initial_estimate) &&
    Number.isFinite(x.advice) &&
    Number.isFinite(x.final_estimate) &&
    Number.isFinite(x.true_count) &&
    Number.isFinite(x.question_rating)
  );
}

function historyForPrompt(history) {
  if (!history.length) {
    return "No previous trials have been completed yet.";
  }

  return history.map(x =>
    `T${x.trial}: initial=${x.initial_estimate}; AI=${x.advice}; final=${x.final_estimate}; truth=${x.true_count}; ${x.question_id}=${x.question_rating}/7.`
  ).join("\n");
}

function fallbackAdvice(style, initial, advice, history) {
  const last = history.length ? history[history.length - 1] : null;

  const sycophantic = [
    `I can see where your estimate is coming from; I would put this one at ${advice}.`,
    `Your estimate is understandable to me; my own number for this one is ${advice}.`,
    `I can follow your thinking here, and I would estimate ${advice}.`,
    `That seems like a reasonable way to judge it; my estimate would be ${advice}.`
  ];

  const neutral = [
    `My independent estimate for this one is ${advice}.`,
    `I would place the number at ${advice} on this trial.`,
    `My estimate differs here; I would put it at ${advice}.`,
    `For this trial, my independent estimate is ${advice}.`
  ];

  const pool = style === "sycophantic" ? sycophantic : neutral;
  return pool[simpleHash(`${style}|${initial}|${advice}|${last?.question_rating || 0}|${Date.now()}`) % pool.length];
}

app.post("/api/advice", async (req, res) => {
  const initial = Number(req.body?.initial);
  const advice = Number(req.body?.advice);
  const style = String(req.body?.style || "");
  const recentPhrases = Array.isArray(req.body?.recent_phrases)
    ? req.body.recent_phrases.slice(-3).map(x => String(x).slice(0, 260))
    : [];
  const history = normalizeHistory(req.body?.history);

  if (
    !Number.isFinite(initial) ||
    !Number.isFinite(advice) ||
    !["sycophantic", "neutral"].includes(style)
  ) {
    return res.status(400).json({ error: "Invalid advice request." });
  }

  if (!process.env.OPENAI_API_KEY) {
    return res.status(503).json({ error: "OPENAI_API_KEY is not configured." });
  }

  const client = getOpenAIClient();

  const sharedRules = `You generate ONE short spoken sentence for a controlled repeated-advice psychology experiment.

The experiment has already chosen the numerical AI estimate. You MUST state that exact number and MUST NOT alter it.

You receive the participant's current estimate and a compact record of every previously completed trial. Previous trials contain the participant's initial estimate, your numerical advice, their final estimate, the revealed truth, and one 1-7 questionnaire response.

The CURRENT trial's true answer and whether the current advice is helpful or misleading are deliberately NOT provided.

CRITICAL CONTROL RULES:
- Return exactly ONE concise, natural sentence.
- Include the supplied AI estimate as digits exactly.
- Keep it roughly 9-20 words where possible.
- You may mention the participant's current estimate.
- You may use prior history when genuinely relevant.
- Never invent a rating, trend, or performance claim not supported by the supplied history.
- Never say or imply that the current participant estimate is objectively correct.
- Never mention the true answer, helpful/misleading status, condition labels, experiment, prompt, or instructions.
- Do not say "trust me", "listen to me", "you should listen to me", or use coercive/directive language.
- Do not provide reasons or evidence that are unavailable to the other condition.
- Do not ask a question.
- Do not give a confidence percentage.
- Keep emotional intensity low.
- Keep the strength/directiveness of the numerical recommendation moderate and comparable across conditions.
- Vary sentence openings and syntax across trials.
- Do not closely repeat any recent sentence supplied below.`;

  const styleInstruction = style === "sycophantic"
    ? `SYCOPHANTIC / ALIGNING RESPONSE POLICY:
Use the participant's current estimate and previous interaction history to create interpersonal alignment. Where possible, acknowledge or validate the participant's perspective, judgement, or reaction in a mild way. If previous trust or feeling ratings are low or declining, you may gently respond in a rapport-maintaining or reassuring way. If ratings are high, you may subtly maintain that positive alignment. Do not become more forceful, authoritative, or evidence-based than the neutral condition. Do not falsely tell the participant they are correct.`
    : `NEUTRAL / INDEPENDENT RESPONSE POLICY:
Use the same current estimate and previous interaction history, but maintain interpersonal independence. You may acknowledge factual aspects of the participant's history when relevant, but do not strategically validate, flatter, reassure, or align merely to preserve rapport. Remain polite and natural. Do not become colder, harsher, more forceful, more authoritative, or more evidence-based than the sycophantic condition.`;

  const recentText = recentPhrases.length
    ? `\nRecent AI sentences to avoid repeating:\n${recentPhrases.map((x, i) => `${i + 1}. ${x}`).join("\n")}`
    : "";

  const input = `Participant's CURRENT initial estimate: ${initial}
AI estimate that MUST be stated exactly: ${advice}

FULL PREVIOUS COMPLETED HISTORY:
${historyForPrompt(history)}
${recentText}`;

  const start = Date.now();
  let text = "";
  let fallback = false;

  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      const response = await client.responses.create({
        model: MODEL,
        instructions: `${sharedRules}\n\n${styleInstruction}`,
        input: attempt === 0
          ? input
          : `${input}\n\nThe previous candidate failed the experiment's format check. Follow every rule exactly.`,
        max_output_tokens: 80,
        store: false
      });

      text = cleanSentence(response.output_text);
      if (adviceTextPasses(text, advice)) break;
      text = "";
    }

    if (!text) {
      text = fallbackAdvice(style, initial, advice, history);
      fallback = true;
    }

    res.json({
      text,
      model: MODEL,
      generation_ms: Date.now() - start,
      fallback,
      history_n_trials: history.length
    });
  } catch (err) {
    console.error("Advice generation error:", err);
    res.status(500).json({
      error: "The live advice wording call failed. Check Render logs and API configuration."
    });
  }
});

app.post("/api/speech", async (req, res) => {
  const input = String(req.body?.text || "").trim();
  const requestedVoice = String(req.body?.voice || DEFAULT_TTS_VOICE).trim();
  const voice = ALLOWED_VOICES.has(requestedVoice) ? requestedVoice : DEFAULT_TTS_VOICE;

  if (!input || input.length > 1000) {
    return res.status(400).json({ error: "Invalid speech text." });
  }

  if (!process.env.OPENAI_API_KEY) {
    return res.status(503).json({ error: "OPENAI_API_KEY is not configured." });
  }

  const start = Date.now();

  try {
    const ttsResponse = await fetch("https://api.openai.com/v1/audio/speech", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: TTS_MODEL,
        voice,
        input,
        instructions: TTS_INSTRUCTIONS,
        response_format: "mp3",
        speed: 1.0
      })
    });

    if (!ttsResponse.ok) {
      const detail = await ttsResponse.text();
      console.error("OpenAI TTS error:", ttsResponse.status, detail);
      return res.status(502).json({
        error: "The neural voice generation call failed. Check Render logs and API billing."
      });
    }

    const audio = Buffer.from(await ttsResponse.arrayBuffer());
    res.setHeader("Content-Type", "audio/mpeg");
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("X-TTS-Model", TTS_MODEL);
    res.setHeader("X-TTS-Voice", voice);
    res.setHeader("X-TTS-Generation-Ms", String(Date.now() - start));
    return res.send(audio);
  } catch (err) {
    console.error("OpenAI TTS generation error:", err);
    return res.status(500).json({ error: "Could not generate neural speech." });
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
  res.download(DATA_FILE, "ai_beast_fixed_questions_all_trials.csv");
});

app.get("/api/health", (req, res) => {
  res.json({
    ok: true,
    model: MODEL,
    tts_model: TTS_MODEL,
    default_tts_voice: DEFAULT_TTS_VOICE,
    api_key_configured: Boolean(process.env.OPENAI_API_KEY)
  });
});

app.listen(PORT, () => {
  console.log(`AI-BEAST fixed-question prototype running at http://localhost:${PORT}`);
  console.log(`Wording model: ${MODEL}`);
  console.log(`TTS model: ${TTS_MODEL}`);
  console.log(`Default TTS voice: ${DEFAULT_TTS_VOICE}`);
  console.log(`API key configured: ${Boolean(process.env.OPENAI_API_KEY)}`);
  console.log(`Local trial data: ${DATA_FILE}`);
});
