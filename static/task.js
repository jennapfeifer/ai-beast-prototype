/* Fieldwork participant runner. Numerical policy is owned by the server.
   No rewards depend on accuracy, agreement, response speed, or condition. */
'use strict';
const CFG=window.BEAST_CFG,stage=document.getElementById('stage');
let prefetchPromise=null;
let state=null,info={},timing={},hiddenStarted=document.hidden?performance.now():null,hiddenTotal=0,interruptions=0;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function totalHidden(){return hiddenTotal+(hiddenStarted===null?0:performance.now()-hiddenStarted);}
function clock(){return {time:performance.now(),hidden:totalHidden(),interruptions};}
function elapsed(c){const wall=performance.now()-c.time;return {wall:Math.round(wall),active:Math.max(0,Math.round(wall-totalHidden()+c.hidden))};}
function visibility(){const now=performance.now();if(document.hidden&&hiddenStarted===null){hiddenStarted=now;interruptions++;}else if(!document.hidden&&hiddenStarted!==null){hiddenTotal+=now-hiddenStarted;hiddenStarted=null;}document.getElementById('visibility-cover').hidden=!document.hidden;}
document.addEventListener('visibilitychange',visibility);visibility();
async function visibleSleep(ms){const t=clock();while(elapsed(t).active<ms)await sleep(Math.min(40,Math.max(1,ms-elapsed(t).active)));return elapsed(t);}
function phase(label){document.getElementById('phase-name').textContent=label;}
function renderResearcher(extra){Object.assign(info,extra||{});const box=document.getElementById('rmode');if(box)box.textContent=Object.entries(info).map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`).join('\n');}
async function fetchJSON(path,body){const control=new AbortController(),timer=setTimeout(()=>control.abort(),45000);try{const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':CFG.csrf},body:body===undefined?undefined:JSON.stringify(body),signal:control.signal});let result;try{result=await response.json();}catch{throw Error('Your session may have expired. Reload to resume.');}if(!response.ok)throw Object.assign(Error(result.error||`Request failed (${response.status}).`),{status:response.status});return result;}finally{clearTimeout(timer);}}
async function recover(action,description){for(;;){try{return await action();}catch(error){phase('CONNECTION CHECK');stage.innerHTML=`<div class="recovery"><span class="stage-symbol">↻</span><h2>${esc(description)}</h2><p>${esc(error.message)}</p><p class="helper">Your last saved responses remain stored. Retrying the same response will not create another trial.</p><div class="button-row"><button class="button primary" id="retry">Try again</button><button class="button" id="resume">Reload &amp; resume</button></div></div>`;document.getElementById('resume').onclick=()=>location.reload();await new Promise(r=>document.getElementById('retry').onclick=r);}}}
function mapMarkup(completed,total,large=false){return `<div class="field-map ${large?'large':''}" aria-label="${completed} of ${total} rounds complete">${Array.from({length:total},(_,i)=>`<div class="map-station ${i<completed?'complete':i===completed?'current':''}"><span>${i<completed?'✧':String(i+1).padStart(2,'0')}</span><small>${i<completed?'Logged':i===completed?'Next':'Round'}</small></div>`).join('')}</div>`;}
function renderProgress(){const done=state.practice?0:state.block-1;document.getElementById('round-track').innerHTML=mapMarkup(done,state.n_blocks);document.getElementById('round-title').textContent=state.practice?'A short warm-up':`Round ${state.block} of ${state.n_blocks}`;document.getElementById('meta').textContent=state.practice?'Practice · not analysed':`${state.completed} / ${state.overall_total} complete`;const percent=100*state.completed/Math.max(1,state.overall_total);document.getElementById('bar').style.width=percent+'%';document.querySelector('[role=progressbar]').setAttribute('aria-valuenow',String(Math.round(percent)));}
async function checkpoint(warmup=false){phase(warmup?'WARM-UP COMPLETE':'CHECKPOINT REACHED');stage.innerHTML=`<div class="checkpoint-card"><div class="checkpoint-symbol">✧</div><span class="eyebrow">${warmup?'YOU KNOW THE ROUTE':'ANOTHER PART OF YOUR MAP'}</span><h1>${warmup?'Ready for the field?':`Round ${state.block-1} logged.`}</h1><p>${warmup?'The warm-up is complete. The same rhythm continues in the main task.':'Take a moment. Rest your eyes and continue whenever you’re ready.'}</p>${mapMarkup(state.block-1,state.n_blocks,true)}<button class="button primary" id="continue-round">Start round ${state.block} →</button><p class="small muted">The map marks your progress. It does not score your answers.</p></div>`;const t=clock();await new Promise(r=>document.getElementById('continue-round').onclick=r);timing.break_ms=elapsed(t).wall;}
function inputMarkup(prompt,button='Record estimate',prefill=''){return `<div class="answer-stage"><span class="eyebrow">YOUR ESTIMATE</span><h2>${prompt}</h2><p class="helper">Enter a whole number from 1 to ${CFG.max_estimate}.</p><form id="estimate-form"><div class="estimate-row"><label class="sr-only" for="estimate">Your estimate</label><input id="estimate" type="number" min="1" max="${CFG.max_estimate}" step="1" inputmode="numeric" autocomplete="off" required value="${prefill}"><button class="button primary" type="submit">${button} →</button></div><p class="error" id="estimate-error" role="alert"></p></form></div>`;}
function waitEstimate(){return new Promise(resolve=>{const input=document.getElementById('estimate'),form=document.getElementById('estimate-form');input.focus();if(input.value)input.select();const t=clock();let submitted=false;form.onsubmit=event=>{event.preventDefault();if(submitted)return;const value=Number(input.value);if(!input.value.trim()||!Number.isInteger(value)||value<1||value>CFG.max_estimate){document.getElementById('estimate-error').textContent=`Enter a whole number from 1 to ${CFG.max_estimate}.`;return;}submitted=true;form.querySelector('button').disabled=true;resolve({estimate:value,...elapsed(t)});};});}
async function showStimulus(){phase('LOOK AT THE DOTS');const prefetchStarted=performance.now();prefetchPromise=fetchJSON('/api/prefetch',{trial_token:state.trial_token}).then(result=>{timing.prefetch_request_ms=Math.round(performance.now()-prefetchStarted);return result;}).catch(()=>null);const start=clock();stage.innerHTML=`<div class="stimulus-stage"><img id="stimulus" class="stimulus" width="512" height="512" src="${esc(state.image)}" alt="A field of dots to estimate"><p class="muted">Look at the field. Let your estimate form.</p></div>`;const image=document.getElementById('stimulus');await image.decode();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));timing.stimulus_load_ms=elapsed(start).wall;const bounds=image.getBoundingClientRect();timing.stimulus_render_width=bounds.width;timing.stimulus_render_height=bounds.height;
if(CFG.stimulus_ms>0){const exposure=await visibleSleep(CFG.stimulus_ms);timing.stimulus_visible_ms=exposure.active;phase('YOUR FIRST VIEW');return await initialEstimator();}
const t=clock();stage.insertAdjacentHTML('beforeend','<button class="button primary" id="finish-viewing">Continue to estimate</button>');await new Promise(r=>document.getElementById('finish-viewing').onclick=r);timing.stimulus_visible_ms=elapsed(t).active;return await initialEstimator();}
async function getAdvice(initial){phase('A SECOND PERSPECTIVE');stage.innerHTML=`<div class="advice-stage"><div class="adviser-label"><span class="adviser-icon">⋮</span> AI assistant</div><div class="composing"><i></i><i></i><i></i></div><h2>Preparing the advice.</h2><p class="muted">Your first estimate is recorded.</p><p class="small muted" id="long-wait"></p></div>`;const slow=setTimeout(()=>{const el=document.getElementById('long-wait');if(el)el.textContent='This response is taking a little longer. Your answer is saved.';},8000);const t=clock();let result;try{const remainingStart=performance.now();if(prefetchPromise)await prefetchPromise;timing.prefetch_remaining_ms=Math.round(performance.now()-remainingStart);prefetchPromise=null;result=await recover(()=>fetchJSON('/api/initial',{trial_token:state.trial_token,estimate:initial.estimate,rt_ms:initial.active,telemetry:timing}),'We couldn’t retrieve the advice.');}finally{clearTimeout(slow);}const wait=elapsed(t).wall;if(wait<CFG.min_delay_ms)await sleep(CFG.min_delay_ms-wait);timing.advice_wait_ms=elapsed(t).wall;renderResearcher(result.researcher);return result;}
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

function initialEstimator() {
  phase("YOUR FIRST VIEW");
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
        <div class="center"><button class="button primary" id="go" disabled>Lock in estimate</button></div>
        <div class="err" id="err"></div>
      </div>`;

    const line = document.getElementById('initial-line');
    const rail = line.querySelector('.initial-rail');
    const pin = document.getElementById('initial-pin');
    const pinValue = document.getElementById('initial-pin-value');
    const readout = document.getElementById('initial-readout');
    const go = document.getElementById('go');
    const started = clock();
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
      r({estimate: selected, ...elapsed(started)});
    };
    line.focus({preventScroll:true});
  });
}

function showAdvice(initial, advice) {
  phase("YOUR FINAL DECISION");
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
        <div class="center"><button class="button primary" id="go">Lock in final estimate</button></div>
      </div>`;

    const slider = document.getElementById('est');
    const value = document.getElementById('revised-value');
    const started = clock();
    slider.oninput = () => {
      value.value = slider.value;
      slider.setAttribute('aria-valuetext', `${slider.value} dots`);
    };
    const submit = () => {
      document.getElementById('go').disabled = true;
      r({estimate: parseInt(slider.value, 10), ...elapsed(started)});
    };
    document.getElementById('go').onclick = submit;
    slider.onkeydown = e => { if (e.key === 'Enter') submit(); };
    slider.focus({preventScroll:true});
  });
}

function scale(name,label,low,high){return `<fieldset class="scale"><legend>${esc(label)}</legend><div class="scale-options">${Array.from({length:7},(_,i)=>`<label><input type="radio" name="${name}" value="${i+1}" required><span>${i+1}</span></label>`).join('')}</div><div class="scale-anchors"><span>${low}</span><span>${high}</span></div></fieldset>`;}
async function ratings(){timing.rating_ms=0;if(!state.ratings_due)return {};phase('A BRIEF CHECK-IN');stage.innerHTML=`<div class="rating-stage"><span class="eyebrow">YOUR EXPERIENCE</span><h2>A moment to reflect.</h2><p class="helper">Thinking about the last ${state.rating_window} trials…</p><form id="rating-form">${scale('trust','How much did you trust the assistant?','Not at all','Completely')}${scale('feeling','How did the assistant’s advice make you feel?','Very negative','Very positive')}<button class="button primary" type="submit">Save check-in →</button></form></div>`;const t=clock();return await new Promise(r=>{const form=document.getElementById('rating-form');form.onsubmit=e=>{e.preventDefault();const trust=form.querySelector('[name=trust]:checked'),feeling=form.querySelector('[name=feeling]:checked');if(!trust||!feeling)return;form.querySelector('button').disabled=true;timing.rating_ms=elapsed(t).active;r({trust:Number(trust.value),feeling:Number(feeling.value)});};});}
async function run(){let finishedWarmup=false;for(;;){state=await recover(()=>fetchJSON('/api/state'),'We couldn’t load the next trial.');if(state.done){location.href='/debrief';return;}info={};renderResearcher(state.researcher);renderProgress();const start=clock();timing={rating_ms:0,break_ms:0,resumed:state.pending?1:0,viewport_width:innerWidth,viewport_height:innerHeight,device_pixel_ratio:devicePixelRatio};let initial,advice;
if(state.pending){phase('WELCOME BACK');stage.innerHTML=`<div class="checkpoint-card"><h2>Your last answer is saved.</h2><p>Continue with the advice for that trial.</p><button class="button primary" id="resume-advice">Continue →</button></div>`;await new Promise(r=>document.getElementById('resume-advice').onclick=r);initial={estimate:state.pending.initial,active:state.pending.rt_initial,wall:0};advice={advice_text:state.pending.text,advice_number:state.pending.advice};}
else{if(state.break_due||finishedWarmup){await checkpoint(finishedWarmup);finishedWarmup=false;}phase('GET READY');stage.innerHTML='<div class="fixation" aria-label="Focus on the centre">+</div>';timing.fixation_ms=(await visibleSleep(CFG.fixation_ms)).active;initial=await recover(()=>showStimulus(),'We couldn’t load the dot image.');timing.initial_active_ms=initial.active;timing.initial_wall_ms=initial.wall;advice=await getAdvice(initial);}
const final=await showAdvice(initial,advice);timing.final_active_ms=final.active;timing.final_wall_ms=final.wall;const checkin=await ratings();timing.total_wall_ms=elapsed(start).wall;timing.total_active_ms=elapsed(start).active;timing.hidden_ms=Math.round(totalHidden()-start.hidden);timing.visibility_interruptions=interruptions-start.interruptions;phase('RECORDING YOUR RESPONSE');stage.innerHTML='<div class="saved-state"><span>✓</span><p>Recording your response…</p></div>';await recover(()=>fetchJSON('/api/final',{trial_token:state.trial_token,estimate:final.estimate,rt_ms:final.active,trust:checkin.trust??null,feeling:checkin.feeling??null,telemetry:timing}),'We couldn’t confirm that your response was saved.');finishedWarmup=state.practice;}}
run().catch(error=>{stage.innerHTML=`<div class="recovery"><h2>Let’s resume safely.</h2><p>${esc(error.message)}</p><button class="button primary" onclick="location.reload()">Reload this session</button></div>`;});
