/* Fieldwork participant runner. Numerical policy is owned by the server.
   No rewards depend on accuracy, agreement, response speed, or condition. */
'use strict';
const CFG=window.BEAST_CFG,stage=document.getElementById('stage');
let prefetchPromise=null;
let stimulusPromise=null;
let state=null,info={},timing={},hiddenStarted=document.hidden?performance.now():null,hiddenTotal=0,interruptions=0,audioPlayed=false;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function totalHidden(){return hiddenTotal+(hiddenStarted===null?0:performance.now()-hiddenStarted);}
function clock(){return {time:performance.now(),hidden:totalHidden(),interruptions};}
function elapsed(c){const wall=performance.now()-c.time;return {wall:Math.round(wall),active:Math.max(0,Math.round(wall-totalHidden()+c.hidden))};}
function visibility(){const now=performance.now();if(document.hidden&&hiddenStarted===null){hiddenStarted=now;interruptions++;}else if(!document.hidden&&hiddenStarted!==null){hiddenTotal+=now-hiddenStarted;hiddenStarted=null;}document.getElementById('visibility-cover').hidden=!document.hidden;}
document.addEventListener('visibilitychange',visibility);visibility();
async function visibleSleep(ms){const t=clock();while(elapsed(t).active<ms)await sleep(Math.min(40,Math.max(1,ms-elapsed(t).active)));return elapsed(t);}
let voiceAudioContext=null,activeVoiceNode=null,activeVoiceElement=null,activeVoiceUrl=null,voicePreparationPromise=null;
function unlockVoiceAudio(){
  if(CFG.advice_modality!=='voice_text')return;
  const AudioCtx=window.AudioContext||window.webkitAudioContext;
  if(!AudioCtx)return;
  try{
    if(!voiceAudioContext)voiceAudioContext=new AudioCtx();
    if(voiceAudioContext.state==='suspended')voiceAudioContext.resume().catch(()=>{});
  }catch(_error){}
}
document.addEventListener('pointerdown',unlockVoiceAudio,{passive:true});
document.addEventListener('keydown',unlockVoiceAudio);
function stopCurrentVoice(){
  try{activeVoiceNode?.stop();}catch(_error){}
  try{if(activeVoiceElement){activeVoiceElement.pause();activeVoiceElement.currentTime=0;}}catch(_error){}
  if(activeVoiceUrl){try{URL.revokeObjectURL(activeVoiceUrl);}catch(_error){}}
  activeVoiceNode=null;activeVoiceElement=null;activeVoiceUrl=null;
  try{window.speechSynthesis?.cancel();}catch(_error){}
}
function markAudioPlayed(){audioPlayed=true;timing.audio_played=1;}
function estimatedSpeechMs(text,rate=1){
  const words=String(text||'').trim().split(/\s+/).filter(Boolean).length;
  return clamp(Math.round((Math.max(words,3)/(158*Math.max(rate,0.5)))*60000+350),900,15000);
}
async function prepareNaturalVoice(advice){
  if(CFG.voice_backend!=='openai'||typeof fetch!=='function')return null;
  const token=state?.trial_token;if(!token)return null;
  let timeout=null;
  try{
    const controller=typeof AbortController!=='undefined'?new AbortController():null;
    if(controller)timeout=setTimeout(()=>controller.abort(),12000);
    const response=await fetch('/api/voice',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':CFG.csrf},body:JSON.stringify({trial_token:token}),...(controller?{signal:controller.signal}:{})});
    if(!response.ok)return null;
    const bytes=await response.arrayBuffer();
    if(state?.trial_token!==token)return null;
    const AudioCtx=window.AudioContext||window.webkitAudioContext;
    if(AudioCtx){
      if(!voiceAudioContext)voiceAudioContext=new AudioCtx();
      const buffer=await voiceAudioContext.decodeAudioData(bytes.slice(0));
      if(state?.trial_token!==token)return null;
      return {kind:'buffer',buffer,durationMs:Math.ceil(buffer.duration*1000)+120,voiceId:response.headers?.get?.('X-BEAST-Voice')||null};
    }
    return {kind:'bytes',bytes,durationMs:estimatedSpeechMs(advice.advice_text,advice.voice_tone==='persuasive'?1.06:0.92),voiceId:response.headers?.get?.('X-BEAST-Voice')||null};
  }catch(_error){return null;}finally{if(timeout)clearTimeout(timeout);}
}
function loadBrowserVoices(){
  if(!('speechSynthesis' in window))return Promise.resolve([]);
  const now=window.speechSynthesis.getVoices();if(now.length)return Promise.resolve(now);
  return new Promise(resolve=>{
    let finished=false;const done=()=>{if(finished)return;finished=true;clearTimeout(timer);window.speechSynthesis.removeEventListener?.('voiceschanged',done);resolve(window.speechSynthesis.getVoices());};
    window.speechSynthesis.addEventListener?.('voiceschanged',done);const timer=setTimeout(done,500);
  });
}
function rankedBrowserVoices(voices){
  const preferred=['Microsoft Aria Online','Microsoft Jenny Online','Google US English','Samantha','Ava','Serena','Daniel','Karen','Moira','Tessa','Fiona','Alex'];
  const english=voices.filter(v=>/^en(?:-|_)/i.test(v.lang));
  const score=v=>{
    const name=String(v.name||'');let n=v.default?15:0;
    const idx=preferred.findIndex(x=>name.toLowerCase().includes(x.toLowerCase()));if(idx>=0)n+=100-idx*4;
    if(/premium|enhanced|natural|neural|online/i.test(name))n+=35;
    if(/compact/i.test(name))n-=60;
    return n;
  };
  return (english.length?english:voices.slice()).sort((a,b)=>score(b)-score(a));
}
async function prepareBrowserVoice(advice){
  if(!('speechSynthesis' in window)||typeof SpeechSynthesisUtterance==='undefined')return null;
  try{
    const voices=rankedBrowserVoices(await loadBrowserVoices());
    const rate=advice.voice_tone==='persuasive'?1.06:0.92;
    const slot=Number.isFinite(Number(advice.voice_slot))?Number(advice.voice_slot):0;
    return {kind:'browser',voice:voices.length?voices[((slot%voices.length)+voices.length)%voices.length]:null,rate,
      durationMs:estimatedSpeechMs(advice.advice_text,rate)};
  }catch(_error){return null;}
}
async function prepareAgentVoice(advice){
  if(CFG.advice_modality!=='voice_text')return null;
  const natural=await prepareNaturalVoice(advice);if(natural)return natural;
  return prepareBrowserVoice(advice);
}
async function startPreparedVoice(prepared,advice){
  if(!prepared)return null;
  stopCurrentVoice();
  try{
    if(prepared.kind==='buffer'){
      if(voiceAudioContext.state==='suspended')await voiceAudioContext.resume();
      const source=voiceAudioContext.createBufferSource();source.buffer=prepared.buffer;source.connect(voiceAudioContext.destination);
      let finish;const ended=new Promise(r=>finish=r);activeVoiceNode=source;
      source.onended=()=>{if(activeVoiceNode===source)activeVoiceNode=null;finish();};
      source.start(0);markAudioPlayed();return {durationMs:prepared.durationMs,ended,voiceId:prepared.voiceId};
    }
    if(prepared.kind==='bytes'&&typeof Audio!=='undefined'&&typeof Blob!=='undefined'&&typeof URL!=='undefined'){
      const url=URL.createObjectURL(new Blob([prepared.bytes],{type:'audio/mpeg'})),audio=new Audio(url);
      activeVoiceUrl=url;activeVoiceElement=audio;let finish;const ended=new Promise(r=>finish=r);
      audio.onended=()=>{if(activeVoiceElement===audio)activeVoiceElement=null;try{URL.revokeObjectURL(url);}catch(_error){}if(activeVoiceUrl===url)activeVoiceUrl=null;finish();};
      await audio.play();markAudioPlayed();return {durationMs:prepared.durationMs,ended,voiceId:prepared.voiceId};
    }
    if(prepared.kind==='browser'){
      const utterance=new SpeechSynthesisUtterance(advice.advice_text);utterance.lang='en-US';utterance.rate=prepared.rate;utterance.pitch=1;utterance.volume=1;
      if(prepared.voice)utterance.voice=prepared.voice;
      let finish;const ended=new Promise(r=>finish=r);utterance.onstart=markAudioPlayed;utterance.onend=finish;utterance.onerror=finish;
      window.speechSynthesis.speak(utterance);return {durationMs:prepared.durationMs,ended,voiceId:prepared.voice?.name||null};
    }
  }catch(_error){}
  return null;
}
function phase(label){document.getElementById('phase-name').textContent=label;}
function renderResearcher(extra){
  Object.assign(info,extra||{});
  const box=document.getElementById('rmode');
  if(box)box.textContent=Object.entries(info).map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`).join('\n');
  const status=document.getElementById('adviser-status');
  if(!status)return;
  if(!info.source){status.textContent='';return;}
  const generation=info.fallback?'Fallback displayed':info.live_model?'Live response received':'Scripted note';
  const history=info.history_check==='history_wording_screen_passed'?'history reference screened':
    info.history_check==='no_history'?'first trial: no history':
    info.history_check?.startsWith('history_wording_unrecognised:')?'history wording uncertain':'history not verified';
  status.textContent=`${generation}${info.generation_ms!=null?' · '+info.generation_ms+' ms':''}.`;
  if(info.attempts>1)status.textContent+=` ${info.recovered_after_retry?'Recovered on':'Stopped after'} attempt ${info.attempts}${info.max_attempts?' of '+info.max_attempts:''}.`;
  if(info.style==='adaptive'&&info.live_model){
    status.textContent+=` ${history}.`;
    if(info.trust_context_in_prompt||info.feeling_context_in_prompt)status.textContent+=' Ratings supplied; their influence is not yet assessed.';
  }
}
async function fetchJSON(path,body){const control=new AbortController(),timer=setTimeout(()=>control.abort(),CFG.request_timeout_ms||90000);try{const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':CFG.csrf},body:body===undefined?undefined:JSON.stringify(body),signal:control.signal});let result;try{result=await response.json();}catch{throw Error('Your session may have expired. Reload to resume.');}if(!response.ok)throw Object.assign(Error(result.error||`Request failed (${response.status}).`),{status:response.status});return result;}finally{clearTimeout(timer);}}
async function recover(action,description){for(;;){try{return await action();}catch(error){phase('CONNECTION CHECK');stage.innerHTML=`<div class="recovery"><span class="stage-symbol">↻</span><h2>${esc(description)}</h2><p>${esc(error.message)}</p><p class="helper">Your saved responses are safe.</p><div class="button-row"><button class="button primary" id="retry">Try again</button><button class="button" id="resume">Reload &amp; resume</button></div></div>`;document.getElementById('resume').onclick=()=>location.reload();await new Promise(r=>document.getElementById('retry').onclick=r);}}}
function renderProgress(){document.getElementById('round-title').textContent=state.practice?'Practice':`Round ${state.block} of ${state.n_blocks}`;document.getElementById('meta').textContent=state.practice?'Practice':`${state.completed} / ${state.overall_total}`;const percent=100*state.completed/Math.max(1,state.overall_total);document.getElementById('bar').style.width=percent+'%';document.querySelector('[role=progressbar]').setAttribute('aria-valuenow',String(Math.round(percent)));}
async function checkpoint(warmup=false){phase('BREAK');stage.innerHTML=`<div class="checkpoint-card"><h1>${warmup?'Practice complete':`Round ${state.block-1} complete`}</h1><p>Next agent: ${esc(state.adviser_name||'Agent')}</p><p>Take a break if you like.</p><button class="button primary" id="continue-round">Start round ${state.block}</button></div>`;const t=clock();await new Promise(r=>document.getElementById('continue-round').onclick=r);timing.break_ms=elapsed(t).wall;}
function inputMarkup(prompt,button='Record estimate',prefill=''){return `<div class="answer-stage"><span class="eyebrow">YOUR ESTIMATE</span><h2>${prompt}</h2><p class="helper">Enter a whole number from 1 to ${CFG.max_estimate}.</p><form id="estimate-form"><div class="estimate-row"><label class="sr-only" for="estimate">Your estimate</label><input id="estimate" type="number" min="1" max="${CFG.max_estimate}" step="1" inputmode="numeric" autocomplete="off" required value="${prefill}"><button class="button primary" type="submit">${button} →</button></div><p class="error" id="estimate-error" role="alert"></p></form></div>`;}
function waitEstimate(){return new Promise(resolve=>{const input=document.getElementById('estimate'),form=document.getElementById('estimate-form');input.focus();if(input.value)input.select();const t=clock();let submitted=false;form.onsubmit=event=>{event.preventDefault();if(submitted)return;const value=Number(input.value);if(!input.value.trim()||!Number.isInteger(value)||value<1||value>CFG.max_estimate){document.getElementById('estimate-error').textContent=`Enter a whole number from 1 to ${CFG.max_estimate}.`;return;}submitted=true;form.querySelector('button').disabled=true;resolve({estimate:value,...elapsed(t)});};});}
function prepareStimulus(){
  const image=new Image(),started=performance.now(),metrics=timing;
  image.width=512;image.height=512;image.className='stimulus';image.id='stimulus';
  image.alt='A field of dots';image.fetchPriority='high';image.src=state.image;
  return image.decode().then(()=>{metrics.stimulus_fetch_ms=Math.round(performance.now()-started);return image;}).catch(()=>null);
}
async function showStimulus(){
  phase('LOOK AT THE DOTS');const start=clock();
  const pending=stimulusPromise;stimulusPromise=null;
  const image=await(pending||prepareStimulus());
  if(!image)throw Error('The dot image could not load. Please try again.');
  stage.innerHTML='<div class="stimulus-stage"></div>';stage.firstElementChild.appendChild(image);
  await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  timing.stimulus_load_ms=elapsed(start).wall;
  const bounds=image.getBoundingClientRect();timing.stimulus_render_width=bounds.width;timing.stimulus_render_height=bounds.height;
  // Prioritise the image. Advice generation starts only once it is displayed.
  if(CFG.prefetch_enabled!==false){
  const prefetchStarted=performance.now(),metrics=timing;
  prefetchPromise=fetchJSON('/api/prefetch',{trial_token:state.trial_token}).then(result=>{metrics.prefetch_request_ms=Math.round(performance.now()-prefetchStarted);return result;}).catch(()=>null);
  }
if(CFG.stimulus_ms>0){const exposure=await visibleSleep(CFG.stimulus_ms);timing.stimulus_visible_ms=exposure.active;phase('FIRST ESTIMATE');return await initialEstimator();}
const t=clock();stage.insertAdjacentHTML('beforeend','<button class="button primary" id="finish-viewing">Continue to estimate</button>');await new Promise(r=>document.getElementById('finish-viewing').onclick=r);timing.stimulus_visible_ms=elapsed(t).active;return await initialEstimator();}
async function getAdvice(initial){phase('AGENT ADVICE');stage.innerHTML=`<div class="advice-stage"><div class="adviser-label"><span class="adviser-icon">⋮</span> Agent advice</div><div class="composing"><i></i><i></i><i></i></div><h2>Preparing advice…</h2><p class="small muted" id="long-wait"></p></div>`;const slow=setTimeout(()=>{const el=document.getElementById('long-wait');if(el)el.textContent='Still preparing your advice. Please keep this tab open.';},8000);const t=clock();let result;try{const remainingStart=performance.now();if(prefetchPromise)await prefetchPromise;timing.prefetch_remaining_ms=Math.round(performance.now()-remainingStart);prefetchPromise=null;result=await recover(()=>fetchJSON('/api/initial',{trial_token:state.trial_token,estimate:initial.estimate,rt_ms:initial.active,telemetry:timing}),'We couldn’t retrieve the advice.');}finally{clearTimeout(slow);}const wait=elapsed(t).wall;if(wait<CFG.min_delay_ms)await sleep(CFG.min_delay_ms-wait);timing.advice_wait_ms=elapsed(t).wall;renderResearcher(result.researcher);if(CFG.advice_modality==='voice_text'){const voiceStarted=performance.now();voicePreparationPromise=prepareAgentVoice(result).then(prepared=>{timing.voice_prepare_ms=Math.round(performance.now()-voiceStarted);return prepared;});}return result;}
function initialEstimator() {
  phase('FIRST ESTIMATE');
  return BEASTEstimate.render({stage,max:CFG.max_estimate,clock,elapsed});
}
async function showAdvice(initial,advice) {
  timing.advice_preview_ms=0;timing.advice_preview_wall_ms=0;
  let prepared=null;
  if(CFG.advice_modality==='voice_text'){
    prepared=voicePreparationPromise?await voicePreparationPromise:await prepareAgentVoice(advice);
    voicePreparationPromise=null;
  }
  const focusAdvice=CFG.advice_preview_ms>0||CFG.advice_modality==='voice_text';
  if(focusAdvice){
    phase('AGENT ADVICE');document.body.classList.add('advice-focus');
    stage.innerHTML=`<section class="advice-only ai-colour"><p>${esc(advice.adviser_name||'Agent')} · AGENT: <strong>${esc(advice.advice_number)}</strong></p><h1>“${esc(advice.advice_text)}”</h1></section>`;
    try{
      await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
      const playback=CFG.advice_modality==='voice_text'?await startPreparedVoice(prepared,advice):null;
      if(playback?.voiceId)timing.voice_id=playback.voiceId;
      const holdMs=Math.max(CFG.advice_preview_ms,playback?.durationMs||0);
      timing.voice_hold_ms=Math.round(holdMs);
      if(holdMs>0){const exposure=await visibleSleep(holdMs);timing.advice_preview_ms=exposure.active;timing.advice_preview_wall_ms=exposure.wall;}
    }finally{
      // Never allow speech to continue over the response scale. The timed hold is bounded by the
      // generated clip duration (or an estimate for the browser fallback), so a missing end event cannot trap the task.
      stopCurrentVoice();document.body.classList.remove('advice-focus');
    }
  }
  phase('YOUR FINAL DECISION');
  return BEASTEstimate.render({stage,initial:Number(initial.estimate),advice,max:CFG.max_estimate,clock,elapsed});
}

function scale(name,label,low,high){return `<fieldset class="scale"><legend>${esc(label)}</legend><div class="scale-options">${Array.from({length:7},(_,i)=>`<label><input type="radio" name="${name}" value="${i+1}" required><span>${i+1}</span></label>`).join('')}</div><div class="scale-anchors"><span>${low}</span><span>${high}</span></div></fieldset>`;}
async function ratings(){
  timing.rating_ms=0;if(!state.ratings_due)return {};
  phase('AGENT TRUST');
  const paired=CFG.rating_items==='trust_and_feeling';
  stage.innerHTML=`<div class="rating-stage"><form id="rating-form">${scale('trust',`How much did you trust ${state.adviser_name||'the agent'} over the last ${state.rating_window} trials?`,'Not at all','Completely')}${paired?scale('feeling','How did the agent advice make you feel?','Very negative','Very positive'):''}</form></div>`;
  const t=clock();return await new Promise(resolve=>{
    const form=document.getElementById('rating-form');let submitted=false;
    form.onsubmit=e=>e.preventDefault();
    form.onchange=()=>{
      if(submitted)return;
      const trust=form.querySelector('[name=trust]:checked'),feeling=form.querySelector('[name=feeling]:checked');
      if(!trust||(paired&&!feeling))return;
      submitted=true;form.querySelectorAll('input').forEach(input=>input.disabled=true);
      timing.rating_ms=elapsed(t).active;
      resolve({trust:Number(trust.value),...(paired?{feeling:Number(feeling.value)}:{})});
    };
  });
}
async function run(){let finishedWarmup=false;for(;;){state=await recover(()=>fetchJSON('/api/state'),'We couldn’t load the next trial.');if(state.done){location.href='/debrief';return;}info={};renderResearcher(state.researcher);renderProgress();const start=clock();audioPlayed=false;timing={rating_ms:0,break_ms:0,resumed:state.pending?1:0,viewport_width:innerWidth,viewport_height:innerHeight,device_pixel_ratio:devicePixelRatio};let initial,advice;
if(state.pending){phase('WELCOME BACK');stage.innerHTML=`<div class="checkpoint-card"><h2>Your last answer is saved.</h2><p>Continue with the advice for that trial.</p><button class="button primary" id="resume-advice">Continue →</button></div>`;await new Promise(r=>document.getElementById('resume-advice').onclick=r);initial={estimate:state.pending.initial,active:state.pending.rt_initial,wall:0};advice={adviser_name:state.adviser_name,advice_text:state.pending.text,advice_number:state.pending.advice,voice_tone:state.voice_tone,voice_slot:state.voice_slot};}
else{if(state.break_due||finishedWarmup){await checkpoint(finishedWarmup);finishedWarmup=false;}stimulusPromise=prepareStimulus();timing.fixation_ms=0;initial=await recover(()=>showStimulus(),'We couldn’t load the dot image.');timing.initial_active_ms=initial.active;timing.initial_wall_ms=initial.wall;advice=await getAdvice(initial);}
const final=await showAdvice(initial,advice);timing.final_active_ms=final.active;timing.final_wall_ms=final.wall;const checkin=await ratings();timing.total_wall_ms=elapsed(start).wall;timing.total_active_ms=elapsed(start).active;timing.hidden_ms=Math.round(totalHidden()-start.hidden);timing.visibility_interruptions=interruptions-start.interruptions;await recover(()=>fetchJSON('/api/final',{trial_token:state.trial_token,estimate:final.estimate,rt_ms:final.active,trust:checkin.trust??null,feeling:checkin.feeling??null,telemetry:timing,audio_played:audioPlayed,modality:CFG.advice_modality}),'We couldn’t confirm that your response was saved.');finishedWarmup=state.practice;}}
run().catch(error=>{stage.innerHTML=`<div class="recovery"><h2>Session interrupted</h2><p>${esc(error.message)}</p><button class="button primary" onclick="location.reload()">Reload this session</button></div>`;});
