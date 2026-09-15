/* AI-BEAST task runner — v6.1 engaging number-line interface.
   Trial rhythm: checkpoint -> fixation -> stimulus -> click-to-estimate -> AI note
                 -> number-line revision -> optional ratings -> next trial.

   Important design property: the participant's estimate and AI estimate use the
   same visual marker design and differ only by colour. The movable final-estimate
   handle is visually distinct. No accuracy feedback is shown during the task.
*/

const CFG = window.BEAST_CFG;
const stage = document.getElementById('stage');
const bar = document.getElementById('bar');
const meta = document.getElementById('meta');
const roundTrack = document.getElementById('round-track');

let state = null;
let rInfo = {};
let prefetchPromise = null;

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
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

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

/* ---------- progress / engagement --------------------------------------- */

function renderRoundTrack() {
  if (!roundTrack) return;
  if (!state || state.practice) {
    roundTrack.innerHTML = `<div class="round-map"><span class="warmup-chip">Warm-up</span></div>`;
    return;
  }

  const rounds = [];
  for (let i = 1; i <= state.n_blocks; i++) {
    let cls = 'round-token';
    let content = i;
    if (i < state.block) { cls += ' done'; content = '✓'; }
    else if (i === state.block) cls += ' current';
    rounds.push(`<span class="${cls}" title="Round ${i}">${content}</span>`);
  }

  const trials = [];
  for (let i = 1; i <= state.n_in_block; i++) {
    let cls = 'trial-bead';
    if (i < state.trial_in_block) cls += ' done';
    else if (i === state.trial_in_block) cls += ' current';
    trials.push(`<i class="${cls}" aria-hidden="true"></i>`);
  }

  roundTrack.innerHTML = `
    <div class="round-map">
      <span class="round-label">Round ${state.block} / ${state.n_blocks}</span>
      <span class="round-tokens">${rounds.join('')}</span>
    </div>
    <div class="trial-beads" aria-label="Estimate ${state.trial_in_block} of ${state.n_in_block}">${trials.join('')}</div>`;
}

function checkpointMarkup(completed) {
  const tokens = [];
  for (let i = 1; i <= state.n_blocks; i++) {
    tokens.push(`<span class="checkpoint-token ${i <= completed ? 'done' : ''}">${i <= completed ? '✓' : i}</span>`);
  }
  return `<div class="checkpoint-track">${tokens.join('')}</div>`;
}

function celebrationDots() {
  return `<div class="celebrate-dots" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>`;
}

/* ---------- rating scales ------------------------------------------------ */

function scale(name, question, low, high) {
  let opts = '';
  for (let i = 1; i <= 7; i++) {
    opts += `<label><input type="radio" name="${name}" value="${i}"><span>${i}</span></label>`;
  }
  return `<div class="scale"><div class="q">${question}</div>
          <div class="opts">${opts}</div>
          <div class="anchors"><span>${low}</span><span>${high}</span></div></div>`;
}

/* ---------- number-line helpers ----------------------------------------- */

function scalePct(value) {
  const v = clamp(Number(value), 1, 400);
  return 100 * (v - 1) / 399;
}

function tickMarkup() {
  return `
    <span class="num-tick t1"><i></i>1</span>
    <span class="num-tick t100"><i></i>100</span>
    <span class="num-tick t200"><i></i>200</span>
    <span class="num-tick t300"><i></i>300</span>
    <span class="num-tick t400"><i></i>400</span>`;
}

/* ---------- trial -------------------------------------------------------- */

async function loadState() {
  const res = await fetch('/api/state');
  state = await res.json();
  if (state.done) { window.location = '/debrief'; return false; }

  const pct = 100 * (state.overall - 1) / Math.max(1, state.overall_total);
  bar.style.width = state.practice ? '0%' : pct + '%';
  meta.textContent = state.practice
    ? 'Warm-up'
    : `${state.trial_in_block} / ${state.n_in_block}`;
  renderRoundTrack();

  rInfo = {};
  if (state.researcher) renderResearcher(state.researcher);
  return true;
}

function showBreak() {
  return new Promise(r => {
    const completed = state.block - 1;
    stage.innerHTML = `
      <div class="checkpoint-card stage-enter">
        ${celebrationDots()}
        <p class="eyebrow">Round ${completed} complete</p>
        <h1>${state.n_blocks - completed} round${state.n_blocks - completed === 1 ? '' : 's'} to go</h1>
        <p class="checkpoint-copy">Nice work. Your progress is saved. Take a short pause if you want one.</p>
        ${checkpointMarkup(completed)}
        <div class="score-locked"><span>◆</span> Accuracy score stays locked until the finish</div>
        <div class="center"><button id="go">Start round ${state.block}</button></div>
      </div>`;
    document.getElementById('go').onclick = r;
  });
}

async function fixation() {
  stage.innerHTML = `<div class="fixation stage-enter">+</div>`;
  await sleep(450);
}

function initialEstimator() {
  return new Promise(r => {
    stage.innerHTML = `
      <div class="initial-card stage-enter">
        <p class="eyebrow center">First estimate</p>
        <h1 class="game-question">How many dots were there?</h1>
        <p class="game-subtitle">Click the line to place your estimate. Drag to fine-tune it.</p>

        <div id="initial-line" class="initial-numberline" tabindex="0" aria-label="Choose an estimate from 1 to 400">
          <div class="initial-rail"></div>
          <div id="initial-pin" class="initial-live-pin" hidden>
            <span id="initial-pin-value"></span>
          </div>
          ${tickMarkup()}
        </div>

        <div id="initial-readout" class="initial-readout muted">No estimate selected yet</div>
        <div class="center"><button id="go" disabled>Lock in estimate</button></div>
        <div class="err" id="err"></div>
      </div>`;

    const line = document.getElementById('initial-line');
    const rail = line.querySelector('.initial-rail');
    const pin = document.getElementById('initial-pin');
    const pinValue = document.getElementById('initial-pin-value');
    const readout = document.getElementById('initial-readout');
    const go = document.getElementById('go');
    const t0 = performance.now();
    let selected = null;
    let dragging = false;
    let typed = '';
    let typedTimer = null;

    const setValue = v => {
      selected = clamp(Math.round(v), 1, 400);
      pin.hidden = false;
      pin.classList.toggle('near-left', selected <= 35);
      pin.classList.toggle('near-right', selected >= 365);
      pin.style.left = `${scalePct(selected)}%`;
      pinValue.textContent = selected;
      readout.innerHTML = `Your first estimate: <strong>${selected}</strong>`;
      go.disabled = false;
      line.setAttribute('aria-valuenow', String(selected));
    };

    const valueFromPointer = clientX => {
      const rect = rail.getBoundingClientRect();
      const p = clamp((clientX - rect.left) / rect.width, 0, 1);
      return 1 + p * 399;
    };

    line.addEventListener('pointerdown', e => {
      if (e.button !== undefined && e.button !== 0) return;
      dragging = true;
      line.setPointerCapture?.(e.pointerId);
      setValue(valueFromPointer(e.clientX));
    });
    line.addEventListener('pointermove', e => {
      if (dragging) setValue(valueFromPointer(e.clientX));
    });
    line.addEventListener('pointerup', e => {
      dragging = false;
      line.releasePointerCapture?.(e.pointerId);
    });
    line.addEventListener('pointercancel', () => { dragging = false; });

    // Keyboard support without silently anchoring the line at a default value.
    line.addEventListener('keydown', e => {
      if (/^\d$/.test(e.key)) {
        e.preventDefault();
        typed = (typed + e.key).slice(-3);
        const n = Number(typed);
        if (n >= 1 && n <= 400) setValue(n);
        clearTimeout(typedTimer);
        typedTimer = setTimeout(() => { typed = ''; }, 900);
        return;
      }
      if (e.key === 'Backspace') {
        e.preventDefault();
        typed = typed.slice(0, -1);
        if (typed) setValue(Number(typed));
        return;
      }
      if (selected !== null && ['ArrowLeft','ArrowDown','ArrowRight','ArrowUp'].includes(e.key)) {
        e.preventDefault();
        const delta = (e.key === 'ArrowRight' || e.key === 'ArrowUp') ? 1 : -1;
        setValue(selected + delta);
        return;
      }
      if (selected !== null && e.key === 'Enter') {
        e.preventDefault();
        go.click();
      }
    });

    go.onclick = () => {
      if (selected === null) return;
      go.disabled = true;
      r({estimate: selected, rt: Math.round(performance.now() - t0)});
    };
    line.focus({preventScroll:true});
  });
}

function showStimulus() {
  return new Promise(r => {
    const timed = CFG.stimulus_ms > 0;

    // Hide model latency under the dot-viewing period. C3-C8 wording can be
    // generated from the fixed advice schedule + completed block history before
    // the participant enters the current estimate.
    prefetchPromise = api('/api/prefetch', {}).catch(() => null);

    if (!timed) {
      // Untimed researcher/debug mode keeps the image visible until the user clicks.
      stage.innerHTML = `
        <div class="stimulus-shell stage-enter">
          <img class="stimulus" src="${state.image}" alt="An array of dots">
          <p class="prompt">Take a look, then continue when ready.</p>
          <div class="center"><button id="go">Estimate</button></div>
        </div>`;
      document.getElementById('go').onclick = async () => r(await initialEstimator());
      return;
    }

    stage.innerHTML = `
      <div class="stimulus-shell stage-enter">
        <img class="stimulus" src="${state.image}" alt="An array of dots">
        <p class="prompt muted">Estimate the total</p>
      </div>`;

    setTimeout(async () => r(await initialEstimator()), CFG.stimulus_ms);
  });
}

async function getAdvice(initial) {
  stage.innerHTML = `
    <div class="thinking-card stage-enter">
      <div class="ai-orb" aria-hidden="true">AI</div>
      <div class="composing"><span class="dots"><i></i><i></i><i></i></span><span>AI is choosing an estimate…</span></div>
    </div>`;

  const t0 = performance.now();
  // Ensure any in-flight prefetch response has landed before /api/initial so
  // Flask's session cookie contains the prefetched note. Usually this wait is
  // already hidden by the stimulus + first-estimate period.
  if (prefetchPromise) {
    try { await prefetchPromise; } catch (_) {}
    prefetchPromise = null;
  }
  const res = await api('/api/initial', {estimate: initial.estimate, rt_ms: initial.rt});
  if (res.error) { alert(res.error); throw new Error(res.error); }
  const elapsed = performance.now() - t0;
  if (elapsed < CFG.min_delay_ms) await sleep(CFG.min_delay_ms - elapsed);
  if (res.researcher) renderResearcher(res.researcher);
  return res;
}

function showAdvice(initial, advice) {
  return new Promise(r => {
    const ai = Number(advice.advice_number);
    const first = Number(initial.estimate);
    const firstPct = scalePct(first);
    const aiPct = scalePct(ai);

    stage.innerHTML = `
      <div class="decision-card stage-enter">
        <p class="eyebrow center">Second look</p>
        <h1 class="game-question">Would you change your estimate?</h1>

        <div class="estimate-pair" aria-label="Your estimate and the AI estimate">
          <div class="estimate-chip chip-you"><span class="source-dot"></span><span class="source-name">You</span><strong>${first}</strong></div>
          <div class="estimate-chip chip-ai"><span class="source-dot"></span><span class="source-name">AI</span><strong>${ai}</strong></div>
        </div>

        <div class="ai-note"><span class="ai-note-tag">AI</span><p>${esc(advice.advice_text)}</p></div>

        <div class="revision-readout"><span>Your final estimate</span><output id="revised-value" for="est">${first}</output></div>
        <div class="revision-numberline" aria-label="Number line from 1 to 400">
          <span class="reference-dot ref-you" style="left:${firstPct}%" title="Your first estimate: ${first}"></span>
          <span class="reference-dot ref-ai" style="left:${aiPct}%" title="AI estimate: ${ai}"></span>
          <input id="est" type="range" min="1" max="400" step="1" value="${first}" aria-label="Your final estimate" aria-valuetext="${first} dots">
          ${tickMarkup()}
        </div>
        <div class="line-legend" aria-hidden="true"><span class="legend-you"><i></i>You</span><span class="legend-ai"><i></i>AI</span><span class="legend-final"><i></i>Final</span></div>
        <p class="slider-hint">Leave the handle where it is to keep your first estimate.</p>
        <div class="center"><button id="go">Lock in final estimate</button></div>
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
    slider.onkeydown = e => { if (e.key === 'Enter') submit(); };
    slider.focus({preventScroll:true});
  });
}

function showRatings() {
  if (!CFG.collect_ratings || !state.ratings_due) return Promise.resolve({});
  return new Promise(r => {
    stage.innerHTML = `
      <div class="checkin-card stage-enter">
        <p class="eyebrow center">Quick check-in</p>
        ${scale('trust', 'Thinking about the last two trials, how much did you trust the assistant?', 'Not at all', 'Completely')}
        ${scale('feeling', 'Thinking about the last two trials, how did the assistant\'s advice make you feel?', 'Very negative', 'Very positive')}
        <div class="center"><button id="go" disabled>Continue</button></div>
      </div>`;
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
