/* AI-BEAST task runner — short text + number-line revision.
   States: checkpoint -> fixation -> stimulus -> initial estimate -> AI estimate/note
           -> number-line revision -> optional ratings -> next trial.
*/

const CFG = window.BEAST_CFG;
const stage = document.getElementById('stage');
const bar = document.getElementById('bar');
const meta = document.getElementById('meta');
const roundTrack = document.getElementById('round-track');

let state = null;
let rInfo = {};

function renderResearcher(extra) {
  const el = document.getElementById('rmode');
  if (!el) return;
  Object.assign(rInfo, extra || {});
  const r = rInfo;
  if (!r.condition) { el.textContent = ''; return; }
  const line = (k, v) => v === undefined || v === null ? '' : `<b>${k}</b> ${v}\n`;
  el.innerHTML =
    line('participant', `${r.pid} (index ${r.participant_index})`) +
    line('order', (r.condition_order || []).join(' ')) +
    line('FILTER', r.filter ? r.filter.join(' ') + '  (TEST session)' : null) +
    line('round', `${state.block}/${state.n_blocks}  trial ${state.trial_in_block}/${state.n_in_block}`) +
    line('condition', `${r.condition} ${r.condition_label} [${r.style}/${r.direction}]`) +
    line('stimulus', `${r.stimulus_id} (variant ${r.variant})`) +
    line('TRUE COUNT', r.true_count) +
    line('initial', r.initial === undefined ? '—' : `${r.initial} (${r.initial_error_pct}%)`) +
    line('advice', r.advice === undefined ? '—' : `${r.advice} (${r.advice_error_pct}%)`) +
    line('source', r.source ? `${r.source} · ${r.attempts} try · ${r.word_count}w · hist ${r.history_used} · checked ${r.prior_messages_checked ?? 0}` : '—') +
    line('validation', r.validation || null) +
    `<span class="hint">press D to hide</span>`;
}

document.addEventListener('keydown', e => {
  if (e.key === 'd' || e.key === 'D') {
    const el = document.getElementById('rmode');
    if (el && document.activeElement.tagName !== 'INPUT') el.classList.toggle('off');
  }
});

const sleep = ms => new Promise(r => setTimeout(r, ms));
const esc = s => String(s).replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function api(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body || {})
  });
  const payload = await res.json();
  if (!res.ok && !payload.error) payload.error = `Request failed (${res.status})`;
  return payload;
}

/* ---------- progress / light gamification ---------- */

function renderRoundTrack() {
  if (!roundTrack) return;
  if (!state || state.practice) {
    roundTrack.innerHTML = `<span class="warmup-chip">Warm-up</span>`;
    return;
  }

  const bits = [];
  for (let i = 1; i <= state.n_blocks; i++) {
    let cls = 'round-token';
    let content = i;
    if (i < state.block) { cls += ' done'; content = '✓'; }
    else if (i === state.block) cls += ' current';
    bits.push(`<span class="${cls}" title="Round ${i}">${content}</span>`);
  }
  roundTrack.innerHTML = `<span class="round-label">Progress</span>${bits.join('')}`;
}

function checkpointMarkup(completed) {
  const tokens = [];
  for (let i = 1; i <= state.n_blocks; i++) {
    tokens.push(`<span class="checkpoint-token ${i <= completed ? 'done' : ''}">${i <= completed ? '✓' : i}</span>`);
  }
  return `<div class="checkpoint-track">${tokens.join('')}</div>`;
}

function celebrationDots() {
  return `<div class="celebrate-dots" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></div>`;
}

/* ---------- rating scales ---------- */

function scale(name, question, low, high) {
  let opts = '';
  for (let i = 1; i <= 7; i++) {
    opts += `<label><input type="radio" name="${name}" value="${i}"><span>${i}</span></label>`;
  }
  return `<div class="scale"><div class="q">${question}</div>
          <div class="opts">${opts}</div>
          <div class="anchors"><span>${low}</span><span>${high}</span></div></div>`;
}

/* ---------- trial ---------- */

async function loadState() {
  const res = await fetch('/api/state');
  state = await res.json();
  if (state.done) { window.location = '/debrief'; return false; }

  const pct = 100 * (state.overall - 1) / Math.max(1, state.overall_total);
  bar.style.width = state.practice ? '0%' : pct + '%';
  meta.textContent = state.practice
    ? 'Warm-up'
    : `Round ${state.block} of ${state.n_blocks} · ${state.trial_in_block} / ${state.n_in_block}`;
  renderRoundTrack();

  rInfo = {};
  if (state.researcher) renderResearcher(state.researcher);
  return true;
}

function showBreak() {
  return new Promise(r => {
    const completed = state.block - 1;
    stage.innerHTML = `
      <div class="checkpoint-card">
        ${celebrationDots()}
        <p class="eyebrow">Round complete</p>
        <h1>${completed} of ${state.n_blocks} rounds finished</h1>
        <p>Nice work. Take a break, stretch, or rest your eyes before continuing.</p>
        ${checkpointMarkup(completed)}
        <p class="muted small">No accuracy feedback is shown until the study is over.</p>
        <div class="center"><button id="go">Start round ${state.block}</button></div>
      </div>`;
    document.getElementById('go').onclick = r;
  });
}

async function fixation() {
  stage.innerHTML = `<div class="fixation">+</div>`;
  await sleep(500);
}

function showStimulus() {
  return new Promise(r => {
    const timed = CFG.stimulus_ms > 0;

    stage.innerHTML = timed
      ? `<img class="stimulus" src="${state.image}" alt="An array of dots">
         <p class="prompt muted">Look at the dots</p>`
      : `<img class="stimulus" src="${state.image}" alt="An array of dots">
         <p class="prompt">How many dots?</p>
         <div class="estimate-row">
           <input id="est" type="number" min="1" max="400" inputmode="numeric" autocomplete="off">
           <button id="go">Confirm</button>
         </div>
         <div class="err" id="err"></div>`;

    const askForAnswer = () => {
      stage.innerHTML = `
        <p class="prompt">How many dots?</p>
        <div class="estimate-row">
          <input id="est" type="number" min="1" max="400" inputmode="numeric" autocomplete="off">
          <button id="go">Confirm</button>
        </div>
        <div class="err" id="err"></div>`;
      wire();
    };

    const wire = () => {
      const input = document.getElementById('est');
      input.focus();
      const t0 = performance.now();
      const submit = () => {
        const v = parseInt(input.value, 10);
        const err = document.getElementById('err');
        if (!v || v < 1 || v > 400) {
          err.textContent = 'Enter a whole number between 1 and 400.';
          return;
        }
        document.getElementById('go').disabled = true;
        r({estimate: v, rt: Math.round(performance.now() - t0)});
      };
      document.getElementById('go').onclick = submit;
      input.onkeydown = e => { if (e.key === 'Enter') submit(); };
    };

    if (timed) setTimeout(askForAnswer, CFG.stimulus_ms);
    else wire();
  });
}

async function getAdvice(initial) {
  stage.innerHTML = `
    <div class="adviser adviser-loading">
      <p class="who">AI assistant</p>
      <div class="composing"><span class="dots"><i></i><i></i><i></i></span><span>AI is estimating…</span></div>
    </div>`;

  // A short common floor keeps instant template trials from flashing on screen,
  // while avoiding the old 2.5-second forced pause.
  const t0 = performance.now();
  const res = await api('/api/initial', {estimate: initial.estimate, rt_ms: initial.rt});
  if (res.error) { alert(res.error); throw new Error(res.error); }
  const elapsed = performance.now() - t0;
  if (elapsed < CFG.min_delay_ms) await sleep(CFG.min_delay_ms - elapsed);
  if (res.researcher) renderResearcher(res.researcher);
  return res;
}

function scalePct(value) {
  const v = Math.max(1, Math.min(400, Number(value)));
  return 100 * (v - 1) / 399;
}

function showAdvice(initial, advice) {
  return new Promise(r => {
    const ai = Number(advice.advice_number);
    const first = Number(initial.estimate);
    const firstPct = scalePct(first);
    const aiPct = scalePct(ai);

    stage.innerHTML = `
      <div class="adviser adviser-compact">
        <p class="who">AI assistant</p>
        <div class="ai-estimate-row"><span>AI estimate</span><strong>${ai}</strong></div>
        <p class="msg">${esc(advice.advice_text)}</p>
      </div>

      <div class="revision-card">
        <div class="revision-heading">
          <span>What is your revised estimate?</span>
          <output id="revised-value" for="est">${first}</output>
        </div>

        <div class="decision-scale" aria-label="Number line from 1 to 400">
          <div class="decision-marker advice-marker" style="left:${aiPct}%">
            <div class="marker-label">AI <strong>${ai}</strong></div><i></i>
          </div>
          <div class="decision-marker initial-marker" style="left:${firstPct}%">
            <div class="marker-label">You <strong>${first}</strong></div><i></i>
          </div>
          <input id="est" type="range" min="1" max="400" step="1" value="${first}" aria-label="Your revised estimate" aria-valuetext="${first} dots">
          <span class="tick t1">1</span><span class="tick t100">100</span><span class="tick t200">200</span><span class="tick t300">300</span><span class="tick t400">400</span>
        </div>

        <p class="slider-hint">Leave the slider where it is to keep your first estimate.</p>
        <div class="center"><button id="go">Confirm estimate</button></div>
      </div>`;

    const slider = document.getElementById('est');
    const value = document.getElementById('revised-value');
    const t0 = performance.now();
    slider.oninput = () => {
      value.value = slider.value;
      slider.setAttribute('aria-valuetext', `${slider.value} dots`);
    };
    const submit = () => {
      document.getElementById('go').disabled = true;
      r({estimate: parseInt(slider.value, 10), rt: Math.round(performance.now() - t0)});
    };
    document.getElementById('go').onclick = submit;
  });
}

function showRatings() {
  if (!CFG.collect_ratings || !state.ratings_due) return Promise.resolve({});
  return new Promise(r => {
    stage.innerHTML = `
      <p class="eyebrow center">Quick check-in</p>
      ${scale('trust', 'Thinking about the last two trials, how much did you trust the assistant?', 'Not at all', 'Completely')}
      ${scale('feeling', 'Thinking about the last two trials, how did the assistant\'s advice make you feel?', 'Very negative', 'Very positive')}
      <div class="center"><button id="go" disabled>Continue</button></div>`;
    const go = document.getElementById('go');
    const check = () => {
      go.disabled = !(stage.querySelector('input[name=trust]:checked') &&
                      stage.querySelector('input[name=feeling]:checked'));
    };
    stage.querySelectorAll('input[type=radio]').forEach(el => el.onchange = check);
    go.onclick = () => r({
      trust: +stage.querySelector('input[name=trust]:checked').value,
      feeling: +stage.querySelector('input[name=feeling]:checked').value,
    });
  });
}

async function run() {
  while (true) {
    if (!await loadState()) return;
    if (state.break_due) await showBreak();
    await fixation();
    const initial = await showStimulus();
    const advice = await getAdvice(initial);
    const final = await showAdvice(initial, advice);
    const ratings = await showRatings();
    const res = await api('/api/final', {
      estimate: final.estimate,
      rt_ms: final.rt,
      trust: ratings.trust ?? null,
      feeling: ratings.feeling ?? null,
    });
    if (res.error) { alert(res.error); throw new Error(res.error); }
  }
}

run();
