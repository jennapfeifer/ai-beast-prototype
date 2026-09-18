'use strict';
const reviewProfiles=['resistant','receptive','changing'];
const reviewRows=[];let reviewIndex=0,reviewStarted=false,reviewRunning=false,reviewPaused=false,reviewState=null,reviewModel=null,reviewPid=null,reviewPending=null;
const el=id=>document.getElementById(id);
const rounded=n=>Math.max(1,Math.min(400,Math.round(n)));
function profileResponse(profile,position,initial,advice){
 const weight=profile==='resistant'?.1:profile==='receptive'?.8:position<=4?.8:position<=8?.4:.1;
 const trust=profile==='resistant'?2:profile==='receptive'?6:position<=4?6:position<=8?4:2;
 return {final:rounded(initial+weight*(advice-initial)),trust,weight};
}
async function reviewRequest(path,body,form=false){
 const response=await fetch(path,{method:body?'POST':'GET',headers:body?{'X-CSRF-Token':REVIEW_CONFIG.csrf,...(form?{}:{'Content-Type':'application/json'})}:{},body:body?(form?body:JSON.stringify(body)):undefined});
 if(!response.ok)throw Error(`Request failed (${response.status}). Your completed trials remain saved.`);
 if(form){if(!response.url.endsWith('/instructions'))throw Error('Researcher session expired. Sign in again before starting a new run.');return;}
 const result=await response.json();return result;
}
async function generateReview(){
 if(reviewRunning)return;reviewRunning=true;reviewPaused=false;
 el('review-start').disabled=true;el('review-stop').disabled=false;el('review-model').disabled=true;
 reviewModel=reviewModel||el('review-model').value;
 try{
  while(reviewIndex<reviewProfiles.length&&!reviewPaused){
   const profile=reviewProfiles[reviewIndex];
   if(!reviewStarted){
    const form=new URLSearchParams({csrf_token:REVIEW_CONFIG.csrf,consent:'yes',researcher_test:'1',adviser_mode:'live',model_profile:reviewModel,trials:'13',test_index:'0',advice_preview_ms:'0',external_id:`SIM_REVIEW_${profile}`});
    await reviewRequest('/start',form,true);reviewStarted=true;reviewPid=null;
   }
   if(reviewPending){await reviewRequest('/api/final',reviewPending.payload);reviewRows.push(reviewPending.row);reviewPending=null;el('review-csv').disabled=el('review-json').disabled=false;}
   reviewState=await reviewRequest('/api/state');
   if(reviewState.done){reviewIndex++;reviewStarted=false;continue;}
   const details=reviewState.researcher;
   if(!details||details.mode!=='live')throw Error('A live researcher TEST session is required.');
   if(reviewPid&&details.pid!==reviewPid)throw Error('The active session changed. Do not run other pilots in this browser.');
   reviewPid=details.pid;
   const position=reviewState.trial_in_block;
   const initial=rounded(details.true_count*([.88,1.08,.96,1.12][(details.true_count/8)%4|0]));
   el('review-status').textContent=`${profile}: ${details.condition}, trial ${position}. ${reviewRows.length}/315 saved.`;
   // Send the synthetic participant's current first estimate exactly as the current-trial protocol does.
   const advice=await reviewRequest('/api/initial',{trial_token:reviewState.trial_token,estimate:initial,rt_ms:0});
   const response=profileResponse(profile,position,initial,advice.advice_number);
   const ratings={trust:reviewState.ratings_due?response.trust:null,feeling:null};
   reviewPending={payload:{trial_token:reviewState.trial_token,estimate:response.final,rt_ms:0,...ratings,telemetry:{}},row:{profile,adviser_name:reviewState.adviser_name,pid:details.pid,participant_index:details.participant_index,round:reviewState.block,condition:details.condition,trial:position,practice:reviewState.practice,true_count:details.true_count,initial_estimate:initial,advice_number:advice.advice_number,final_estimate:response.final,prescribed_weight:response.weight,trust_rating:ratings.trust,advice_text:advice.advice_text,...advice.researcher,simulation:true}};
   await reviewRequest('/api/final',reviewPending.payload);reviewRows.push(reviewPending.row);reviewPending=null;
   el('review-csv').disabled=el('review-json').disabled=false;
  }
  el('review-status').textContent=reviewIndex===3?`Complete: ${reviewRows.length} trials. Download the CSV and full audit.`:`Paused: ${reviewRows.length} trials saved.`;
 }catch(error){reviewPaused=true;el('review-status').textContent=error.message+' Continue retries the current trial.';}
 finally{reviewRunning=false;el('review-stop').disabled=true;el('review-start').textContent='Continue';el('review-start').disabled=reviewIndex===3;}
}
function downloadReview(json){
 let content,type,name;
 if(json){content=JSON.stringify({simulation:true,profiles:reviewProfiles,model_profile:reviewModel,complete:reviewIndex===3,rows:reviewRows},null,2);type='application/json';name='BEAST-live-review.json';}
 else{
  const fields=['profile','adviser_name','pid','participant_index','round','condition','trial','practice','true_count','initial_estimate','advice_number','final_estimate','prescribed_weight','trust_rating','advice_text','word_count','word_count_check','source','live_model','fallback','model','prompt_version','initial_context_available','generation_ms','attempts','validation','grounding_record_check','adaptive_strategy','adaptive_summary','review_reasons','attempt_log'];
  const cell=value=>{let s=value==null?'':typeof value==='object'?JSON.stringify(value):String(value);if(/^[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
  content='\uFEFF'+[fields,...reviewRows.map(r=>fields.map(k=>r[k]))].map(row=>row.map(cell).join(',')).join('\r\n');type='text/csv;charset=utf-8';name='BEAST-live-review.csv';
 }
 const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
el('review-start').onclick=generateReview;el('review-stop').onclick=()=>{reviewPaused=true;el('review-stop').disabled=true;};el('review-csv').onclick=()=>downloadReview(false);el('review-json').onclick=()=>downloadReview(true);
