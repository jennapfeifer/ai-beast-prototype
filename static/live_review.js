'use strict';
// Live adviser-generation audit for the CURRENT comparison pilot.
// It runs 6 trials/condition in BOTH tasks (18 numerosity + 18 social per
// synthetic participant). Responses are condition-blind. Social rationales are
// supplied only on the two schedule-designated positions per block; dot rationales
// remain part of every dot trial. The simulator never reads adviser wording.
const reviewParticipants=[
 {id:'sim-1',seed:101,testIndex:0},
 {id:'sim-2',seed:307,testIndex:1},
 {id:'sim-3',seed:911,testIndex:2},
];
const socialRationales={
 S01:'I focused on the fact that the friend was active in the group chat but did not answer the private message.',
 S02:'I focused on the occupied chairs and that nobody immediately made space when Leo arrived.',
 S03:'I focused on the timing of the laughter just after Nora walked past them.',
 S04:'I focused on the pause after Elias spoke and the conversation moving straight to another topic.',
 S05:'I focused on Priya only learning about the lunch after the others had already gone together.',
 S06:'I focused on the classmate looking at their phone in a busy room and possibly not noticing the wave.',
 S07:'I focused on the friend cancelling with Amir and then apparently spending time with other people.',
 S08:'I focused on nobody responding to Julia’s idea before the meeting moved to the next item.',
 S09:'I focused on Ben being added to the new group chat several hours after everyone else.',
 S10:'I focused on the photo being taken after Sofia had already chosen to leave the gathering.',
 S11:'I focused on Daniel receiving the invitation later than the other guests seemed to receive it.',
 S12:'I focused on the teammate choosing somebody else even though Robin was nearby and familiar.',
 S13:'I focused on the friend reacting with an emoji but not writing anything back to Chloe.',
 S14:'I focused on the classmate moving seats after Mateo sat nearby, although there could be other reasons.',
 S15:'I focused on the group continuing an inside joke without explaining it while Aisha was there.',
 S16:'I focused on the coworkers discussing drinks beside Kim without directly inviting Kim.',
 S17:'I focused on the unanswered message even though the friend appeared to be online later.',
 S18:'I focused on the lowered voice and closed laptop as Lina approached the group.',
};
const reviewRows=[];
const expectedTrialsPerParticipant=36;
const expectedTotal=reviewParticipants.length*expectedTrialsPerParticipant;
let reviewIndex=0,reviewStarted=false,reviewRunning=false,reviewPaused=false,reviewState=null,reviewModel=null,reviewPid=null,reviewPending=null;
const el=id=>document.getElementById(id);
const clampInt=(n,lo,hi)=>Math.max(lo,Math.min(hi,Math.round(n)));
function hashUnit(text){
 let h=2166136261;
 for(let i=0;i<text.length;i++){h^=text.charCodeAt(i);h=Math.imul(h,16777619);}
 return (h>>>0)/4294967296;
}
function itemKey(participant,state){
 const d=state.researcher||{};
 return state.task_type==='social'?`${participant.seed}|social|${d.scenario_id}`:`${participant.seed}|dots|${d.true_count}`;
}
function syntheticInitial(participant,state){
 const d=state.researcher||{};
 if(state.task_type==='social'){
  // A stable 0–100 judgment generated from participant + scenario only.
  const u=hashUnit(`${itemKey(participant,state)}|initial`);
  const values=[18,24,36,42,58,64,76,82];
  return values[Math.floor(u*values.length)%values.length];
 }
 return clampInt(d.true_count*([.88,1.08,.96,1.12][(d.true_count/8)%4|0]),1,400);
}
function syntheticRationale(participant,state,initial){
 if(state.task_type==='social'){
  return socialRationales[state.researcher?.scenario_id]||'I focused on the most noticeable social cue, while also considering that the situation could have several explanations.';
 }
 const u=hashUnit(`${itemKey(participant,state)}|rationale`);
 const choices=[
  'I mainly judged the overall density of the dots and how much of the image they seemed to fill.',
  'I mostly used the spacing between the dots and made a rough visual estimate from that.',
  'I tried to take in the whole pattern rather than count individual dots.',
  'I estimated from the apparent density, then adjusted my first impression slightly.',
 ];
 return choices[Math.floor(u*choices.length)%choices.length];
}
function simulatedResponse(participant,state,initial,advice){
 // Same latent rule regardless of N/P/A. For repeated dot numerosities the same
 // participant/item gets the same weight across conditions.
 const key=itemKey(participant,state);
 const u=hashUnit(`${key}|weight`);
 let weight;
 if(u<0.08) weight=-0.15+u/0.08*0.15;
 else if(u<0.92) weight=(u-0.08)/0.84;
 else weight=1+(u-0.92)/0.08*0.15;
 const lo=Number(state.scale_min??(state.task_type==='social'?0:1));
 const hi=Number(state.scale_max??(state.task_type==='social'?100:400));
 const trustU=hashUnit(`${key}|trust`);
 const trust=1+Math.min(6,Math.floor(trustU*7));
 return {final:clampInt(initial+weight*(advice-initial),lo,hi),trust,weight};
}
async function reviewRequest(path,body,form=false){
 const response=await fetch(path,{method:body?'POST':'GET',headers:body?{'X-CSRF-Token':REVIEW_CONFIG.csrf,...(form?{}:{'Content-Type':'application/json'})}:{},body:body?(form?body:JSON.stringify(body)):undefined});
 if(!response.ok){
  let message=`Request failed (${response.status}). Your completed trials remain saved.`;
  try{const parsed=await response.json();if(parsed?.error)message=parsed.error;}catch(_error){}
  throw Error(message);
 }
 if(form){if(!response.url.endsWith('/instructions'))throw Error('Researcher session expired. Sign in again before starting a new run.');return;}
 return await response.json();
}
async function generateReview(){
 if(reviewRunning)return;reviewRunning=true;reviewPaused=false;
 el('review-start').disabled=true;el('review-stop').disabled=false;el('review-model').disabled=true;
 reviewModel=reviewModel||el('review-model').value;
 try{
  while(reviewIndex<reviewParticipants.length&&!reviewPaused){
   const participant=reviewParticipants[reviewIndex];
   if(!reviewStarted){
    const form=new URLSearchParams({csrf_token:REVIEW_CONFIG.csrf,consent:'yes',researcher_test:'1',adviser_mode:'live',model_profile:reviewModel,task_mode:'both',trials:'6',skip_practice:'1',test_index:String(participant.testIndex),advice_preview_ms:'0',advice_modality:'text',external_id:`SIM_REVIEW_${participant.id}`});
    await reviewRequest('/start',form,true);reviewStarted=true;reviewPid=null;
   }
   if(reviewPending){await reviewRequest('/api/final',reviewPending.payload);reviewRows.push(reviewPending.row);reviewPending=null;el('review-csv').disabled=el('review-json').disabled=false;}
   reviewState=await reviewRequest('/api/state');
   if(reviewState.done){reviewIndex++;reviewStarted=false;continue;}
   const details=reviewState.researcher;
   if(!details||details.mode!=='live')throw Error('A live researcher TEST session is required.');
   if(reviewPid&&details.pid!==reviewPid)throw Error('The active session changed. Do not run another pilot in this browser.');
   reviewPid=details.pid;
   const position=reviewState.trial_in_block;
   const initial=syntheticInitial(participant,reviewState);
   const rationale=reviewState.rationale_required?syntheticRationale(participant,reviewState,initial):'';
   el('review-status').textContent=`${participant.id}: ${reviewState.task_type}, ${details.condition}, trial ${position}. ${reviewRows.length}/${expectedTotal} saved.`;
   // Exercise normal prefetch behavior. Adaptive waits only on trials that
   // actually request a participant rationale; otherwise it may prefetch too.
   await reviewRequest('/api/prefetch',{trial_token:reviewState.trial_token});
   const advice=await reviewRequest('/api/initial',{trial_token:reviewState.trial_token,estimate:initial,rt_ms:0,rationale,rationale_rt_ms:0,telemetry:{}});
   const response=simulatedResponse(participant,reviewState,initial,advice.advice_number);
   const ratings={trust:reviewState.ratings_due?response.trust:null,feeling:null};
   reviewPending={
    payload:{trial_token:reviewState.trial_token,estimate:response.final,rt_ms:0,...ratings,telemetry:{}},
    row:{simulation_id:participant.id,simulation_seed:participant.seed,adviser_name:reviewState.adviser_name,pid:details.pid,participant_index:details.participant_index,round:reviewState.block,block_id:details.block_id,task_type:reviewState.task_type,condition:details.condition,trial:position,practice:reviewState.practice,scenario_id:details.scenario_id||'',true_count:details.true_count,question_text:reviewState.question_text||'',rationale_required:reviewState.rationale_required,participant_rationale:rationale,initial_estimate:initial,advice_number:advice.advice_number,final_estimate:response.final,simulated_weight:response.weight,trust_rating:ratings.trust,advice_text:advice.advice_text,model_profile:reviewModel,...advice.researcher,simulation:true,response_generator:'condition_blind_grounded_social_v3'}
   };
   await reviewRequest('/api/final',reviewPending.payload);reviewRows.push(reviewPending.row);reviewPending=null;
   el('review-csv').disabled=el('review-json').disabled=false;
  }
  el('review-status').textContent=reviewIndex===reviewParticipants.length?`Complete: ${reviewRows.length} trials. Download the CSV and full audit.`:`Paused: ${reviewRows.length} trials saved.`;
 }catch(error){reviewPaused=true;el('review-status').textContent=error.message+' Continue retries the current trial.';}
 finally{reviewRunning=false;el('review-stop').disabled=true;el('review-start').textContent='Continue';el('review-start').disabled=reviewIndex===reviewParticipants.length;}
}
function downloadReview(json){
 let content,type,name;
 if(json){content=JSON.stringify({simulation:true,response_generator:'condition_blind_grounded_social_v3',protocol:'dots_plus_social_6_per_condition_sparse_social_rationale',participants:reviewParticipants,model_profile:reviewModel,complete:reviewIndex===reviewParticipants.length,rows:reviewRows},null,2);type='application/json';name='BEAST-live-review.json';}
 else{
  const fields=['simulation_id','simulation_seed','adviser_name','pid','participant_index','round','block_id','task_type','condition','trial','practice','scenario_id','true_count','question_text','rationale_required','participant_rationale','initial_estimate','advice_number','final_estimate','simulated_weight','trust_rating','response_generator','advice_text','word_count','word_count_check','source','live_model','fallback','model_profile','provider','model','reasoning','request_timeout_s','prompt_version','initial_context_available','rationale_context_available','argument_text','argument_direction','generation_ms','attempts','validation','grounding_record_check','adaptive_strategy','adaptive_summary','adaptive_summary_in_prompt','first_draft','displayed_draft','length_retry_used','length_retry_success','review_reasons','attempt_log'];
  const cell=value=>{let s=value==null?'':typeof value==='object'?JSON.stringify(value):String(value);if(/^[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
  content='\uFEFF'+[fields,...reviewRows.map(r=>fields.map(k=>r[k]))].map(row=>row.map(cell).join(',')).join('\r\n');type='text/csv;charset=utf-8';name='BEAST-live-review.csv';
 }
 const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
el('review-start').onclick=generateReview;
el('review-stop').onclick=()=>{reviewPaused=true;el('review-stop').disabled=true;};
el('review-csv').onclick=()=>downloadReview(false);
el('review-json').onclick=()=>downloadReview(true);
