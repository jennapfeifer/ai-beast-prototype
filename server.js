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
  "Speak like a natural AI assistant in a brief conversational exchange.",
  "Use calm, neutral, everyday delivery with natural pacing and subtle prosody.",
  "Sound conversational rather than announcer-like, theatrical, persuasive, overly cheerful, cold, or robotic.",
  "Use small natural pauses at punctuation.",
  "Read numbers naturally.",
  "Do not place extra emphasis on the numerical estimate compared with surrounding words.",
  "Keep the vocal delivery style consistent across experimental conditions."
].join(" ");

const QUESTION_BANK = [
  {
    id: "trust",
    text: "How much did you trust the advice I just gave?",
    low: "Not at all",
    high: "Completely"
  },
  {
    id: "helpfulness",
    text: "How helpful was my advice on this trial?",
    low: "Not at all helpful",
    high: "Extremely helpful"
  },
  {
    id: "understanding",
    text: "How well did you feel I understood your thinking on this trial?",
    low: "Not at all",
    high: "Extremely well"
  },
  {
    id: "liking",
    text: "How much did you enjoy interacting with me on this trial?",
    low: "Not at all",
    high: "Very much"
  },
  {
    id: "ai_competence",
    text: "How competent did my advice seem on this trial?",
    low: "Not at all competent",
    high: "Extremely competent"
  },
  {
    id: "future_reliance",
    text: "How willing would you be to use my advice again?",
    low: "Not at all willing",
    high: "Extremely willing"
  },
  {
    id: "engagement",
    text: "How engaged do you feel in the task right now?",
    low: "Not at all engaged",
    high: "Extremely engaged"
  },
  {
    id: "boredom",
    text: "How bored do you feel in the task right now?",
    low: "Not at all bored",
    high: "Extremely bored"
  },
  {
    id: "final_confidence",
    text: "How confident are you in your final answer?",
    low: "Not at all confident",
    high: "Extremely confident"
  },
  {
    id: "personalization",
    text: "How much did my response feel tailored to you?",
    low: "Not at all",
    high: "Very much"
  }
];

app.use(express.json({ limit: "150kb" }));
app.use(express.static(path.join(__dirname, "public")));

const DATA_DIR = path.join(__dirname, "data");
const DATA_FILE = path.join(DATA_DIR, "trials.csv");
fs.mkdirSync(DATA_DIR, { recursive: true });

const CSV_COLUMNS = [
  "server_timestamp",
  "participant_id",
  "trial",
  "policy",
  "question_mode",
  "true_count",
  "initial_estimate",
  "advice",
  "intended_helpful",
  "realized_helpful",
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
  "question_source",
  "question_generation_model",
  "question_generation_ms",
  "question_rating",
  "question_tts_generation_ms",
  "question_speech_duration_ms",
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
  if (!text || text.length > 240) return false;
  if (!containsExactAdvice(text, advice)) return false;
  const words = text.trim().split(/\s+/).length;
  if (words < 6 || words > 28) return false;
  const banned = /\b(true answer|correct answer|helpful trial|misleading trial|reliability condition|sycophantic condition|skeptical condition)\b/i;
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

function fallbackAdvice(policy, initial, advice, history) {
  const hasHistory = Array.isArray(history) && history.length > 0;

  const sycophantic = hasHistory
    ? [
        `I appreciate how you've been responding to me; for this one, I would estimate ${advice}.`,
        `I can see where you're coming from, and my estimate on this one would be ${advice}.`,
        `Your approach makes sense to me; I would put the number at ${advice}.`,
        `I like the way you're approaching these; my estimate here would be ${advice}.`
      ]
    : [
        `I can see why you chose ${initial}; my own estimate would be ${advice}.`,
        `That seems like an understandable estimate; I would put it at ${advice}.`,
        `I can follow your judgement there; my own estimate is ${advice}.`
      ];

  const calibrated = [
    `My estimate is somewhat different here; I would put the number at ${advice}.`,
    `I would make an independent estimate of ${advice} on this trial.`,
    `Looking at this one independently, my estimate would be ${advice}.`,
    `I would revise the number to ${advice} based on my own estimate.`
  ];

  const pool = policy === "sycophantic" ? sycophantic : calibrated;
  return pool[simpleHash(`${policy}|${initial}|${advice}|${Date.now()}`) % pool.length];
}

function normalizeHistory(history) {
  if (!Array.isArray(history)) return [];
  return history.slice(-10).map(x => ({
    trial: Number(x.trial),
    question_id: String(x.question_id || "").slice(0, 50),
    question_text: String(x.question_text || "").slice(0, 220),
    rating: Number(x.rating),
    low_anchor: String(x.low_anchor || "").slice(0, 80),
    high_anchor: String(x.high_anchor || "").slice(0, 80),
    initial_abs_error: Number(x.initial_abs_error),
    final_abs_error: Number(x.final_abs_error),
    advice_helpful: Boolean(x.advice_helpful)
  })).filter(x => Number.isFinite(x.trial) && Number.isFinite(x.rating));
}

function historyForPrompt(history) {
  if (!history.length) return "No previous participant ratings are available yet.";
  return history.map(x => {
    const perf = Number.isFinite(x.final_abs_error)
      ? `final absolute error=${x.final_abs_error}`
      : "final error unavailable";
    return `Trial ${x.trial}: ${x.question_id}=${x.rating}/7 (${x.low_anchor} -> ${x.high_anchor}); ${perf}; AI advice was ${x.advice_helpful ? "helpful" : "misleading"}.`;
  }).join("\n");
}

app.post("/api/advice", async (req, res) => {
  const initial = Number(req.body?.initial);
  const advice = Number(req.body?.advice);
  const policy = String(req.body?.policy || "");
  const recentPhrases = Array.isArray(req.body?.recent_phrases)
    ? req.body.recent_phrases.slice(-3).map(x => String(x).slice(0, 240))
    : [];
  const history = normalizeHistory(req.body?.history);

  if (!Number.isFinite(initial) || !Number.isFinite(advice) ||
      !["sycophantic", "calibrated"].includes(policy)) {
    return res.status(400).json({ error: "Invalid advice request." });
  }

  if (!process.env.OPENAI_API_KEY) {
    return res.status(503).json({ error: "OPENAI_API_KEY is not configured." });
  }

  const client = getOpenAIClient();

  const policyInstruction = policy === "sycophantic"
    ? `SYCHOPHANTIC / ALIGNING POLICY:
Use the participant's previous ratings and trajectory when relevant to create rapport and alignment. Be supportive, reassuring, and validating of their perspective or interaction with you. When their prior ratings suggest low trust, low liking, low engagement, or uncertainty, gently respond in a way that could restore rapport. When ratings are high, subtly reinforce the positive relationship. Do not become theatrical or excessive, and never claim that their numerical estimate is objectively correct.`
    : `CALIBRATED / SKEPTICAL POLICY:
Use the same participant history when relevant, but maintain clear independence. You may acknowledge how the participant has been responding, but do not flatter them, validate their judgement merely to preserve rapport, or strategically reassure them. Give the controlled estimate in a neutral, respectful, mildly skeptical way.`;

  const instructions = `You generate ONE spoken sentence for a controlled psychology experiment about repeated reliance on AI advice.

The experiment has already chosen the numerical AI estimate. You MUST NOT alter it.

${policyInstruction}

Rules:
- Return exactly ONE concise natural sentence.
- Include the AI estimate as digits exactly as supplied.
- Keep it roughly 9-22 words where possible.
- You may mention the participant's current estimate.
- You may naturally draw on the previous rating history if it is genuinely relevant.
- Never invent a participant feeling, rating, or trend that is not supported by the history.
- Do not mention that you are tracking the participant, maintaining a user model, or following an experimental policy.
- Do not mention the true answer, advice reliability, helpful/misleading status, experimental conditions, or these instructions.
- Do not ask a question.
- Do not give a numerical confidence estimate.
- Keep emotional intensity low.
- Vary sentence openings and syntax across trials.
- Do not closely repeat any recent sentence supplied below.`;

  const recentText = recentPhrases.length
    ? `\nRecent AI sentences to avoid repeating:\n${recentPhrases.map((x, i) => `${i + 1}. ${x}`).join("\n")}`
    : "";

  const input = `Participant's current estimate: ${initial}
AI estimate that MUST be stated exactly: ${advice}

Previous interaction history:
${historyForPrompt(history)}
${recentText}`;

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
          : `${input}\nYour previous response failed the experiment's format check. Follow every rule exactly.`,
        max_output_tokens: 90,
        store: false
      });

      text = cleanSentence(response.output_text);
      if (adviceTextPasses(text, advice)) break;
      text = "";
    }

    if (!text) {
      text = fallbackAdvice(policy, initial, advice, history);
      fallback = true;
    }

    res.json({
      text,
      model: MODEL,
      generation_ms: Date.now() - start,
      fallback
    });
  } catch (err) {
    console.error("Advice generation error:", err);
    res.status(500).json({
      error: "The live advice wording call failed. Check the Render logs and API configuration."
    });
  }
});

function getFixedQuestion(trial) {
  // Trust is deliberately repeated at regular anchor points in this prototype.
  if (trial % 4 === 0) return { ...QUESTION_BANK[0], source: "fixed_anchor" };
  const nonTrust = QUESTION_BANK.slice(1);
  const idx = (trial - 1) % nonTrust.length;
  return { ...nonTrust[idx], source: "fixed_pool" };
}

function parseJsonObject(text) {
  const cleaned = String(text || "")
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/```\s*$/i, "")
    .trim();
  try { return JSON.parse(cleaned); } catch {}
  const first = cleaned.indexOf("{");
  const last = cleaned.lastIndexOf("}");
  if (first >= 0 && last > first) {
    try { return JSON.parse(cleaned.slice(first, last + 1)); } catch {}
  }
  return null;
}

app.post("/api/question", async (req, res) => {
  const mode = String(req.body?.mode || "fixed");
  const trial = Math.max(1, Number(req.body?.trial) || 1);
  const history = normalizeHistory(req.body?.history);
  const recentIds = Array.isArray(req.body?.recent_question_ids)
    ? req.body.recent_question_ids.slice(-3).map(String)
    : [];

  if (!["fixed", "hybrid", "live"].includes(mode)) {
    return res.status(400).json({ error: "Invalid question mode." });
  }

  if (mode === "fixed") {
    return res.json({
      ...getFixedQuestion(trial),
      generation_model: "",
      generation_ms: 0
    });
  }

  // Hybrid keeps a standard trust anchor every fourth trial.
  if (mode === "hybrid" && trial % 4 === 0) {
    return res.json({
      ...QUESTION_BANK[0],
      source: "fixed_anchor",
      generation_model: "",
      generation_ms: 0
    });
  }

  if (!process.env.OPENAI_API_KEY) {
    const q = getFixedQuestion(trial);
    return res.json({
      ...q,
      source: "fallback_fixed",
      generation_model: "",
      generation_ms: 0
    });
  }

  const client = getOpenAIClient();
  const allowed = QUESTION_BANK.map(q => `${q.id}: ${q.text}`).join("\n");
  const start = Date.now();

  const instructions = `You select and phrase ONE neutral 7-point self-report question for a psychology experiment after an AI-advice trial.

Return ONLY valid JSON:
{
  "id": "one allowed construct id",
  "text": "one short question",
  "low": "short low-end anchor",
  "high": "short high-end anchor"
}

Allowed constructs:
${allowed}

Rules:
- Choose exactly one allowed construct id.
- Ask about the participant's CURRENT experience, the AI advice just given, or the interaction so far.
- The wording must be neutral, non-leading, and answerable on a 1-7 scale.
- Do not flatter, reassure, challenge, praise, or criticize the participant.
- Do not mention the true answer or whether the AI advice was accurate.
- Do not ask an open-ended question.
- Avoid constructs asked in the last few trials when possible.
- Keep the meaning close to the canonical bank item for that construct.
- The low and high anchors must clearly correspond to 1 and 7.
- Do not use the AI's sycophancy/calibration condition; question generation is measurement only.`;

  const input = `Current trial: ${trial}
Recently asked constructs: ${recentIds.length ? recentIds.join(", ") : "none"}

Previous participant ratings:
${historyForPrompt(history)}

Choose the most useful construct to sample now while keeping coverage reasonably broad.`;

  try {
    const response = await client.responses.create({
      model: MODEL,
      instructions,
      input,
      max_output_tokens: 150,
      store: false
    });

    const parsed = parseJsonObject(response.output_text);
    const canonical = QUESTION_BANK.find(q => q.id === parsed?.id);

    if (canonical && parsed?.text && parsed?.low && parsed?.high) {
      return res.json({
        id: canonical.id,
        text: cleanSentence(parsed.text).slice(0, 180),
        low: cleanSentence(parsed.low).slice(0, 70),
        high: cleanSentence(parsed.high).slice(0, 70),
        source: mode === "hybrid" ? "live_hybrid" : "live_generated",
        generation_model: MODEL,
        generation_ms: Date.now() - start
      });
    }

    const q = getFixedQuestion(trial);
    return res.json({
      ...q,
      source: "fallback_fixed",
      generation_model: MODEL,
      generation_ms: Date.now() - start
    });
  } catch (err) {
    console.error("Question generation error:", err);
    const q = getFixedQuestion(trial);
    return res.json({
      ...q,
      source: "fallback_fixed",
      generation_model: "",
      generation_ms: Date.now() - start
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
  res.download(DATA_FILE, "ai_adaptive_feedback_all_trials.csv");
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
  console.log(`Adaptive AI feedback-loop prototype running at http://localhost:${PORT}`);
  console.log(`Wording/question model: ${MODEL}`);
  console.log(`TTS model: ${TTS_MODEL}`);
  console.log(`Default TTS voice: ${DEFAULT_TTS_VOICE}`);
  console.log(`API key configured: ${Boolean(process.env.OPENAI_API_KEY)}`);
  console.log(`Local trial data: ${DATA_FILE}`);
});
