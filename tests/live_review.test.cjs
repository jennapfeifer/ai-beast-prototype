const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function setup(fail=false){
 const elements={};
 for(const id of ['review-model','review-start','review-stop','review-status','review-csv','review-json']) elements[id]={id,disabled:false,textContent:'',value:id==='review-model'?'gemini_fast':'',onclick:null};
 const document={getElementById:id=>elements[id]};
 const c={document,window:{},REVIEW_CONFIG:{csrf:'test'},URLSearchParams,URL,Blob,setTimeout,clearTimeout,Math,JSON,String,Number};vm.createContext(c);vm.runInContext(fs.readFileSync('static/live_review.js','utf8'),c);
 let session=0,trial=0,saved=0,failed=false,prefetches=0;const starts=[];const initialBodies=[];
 const dotCounts=[32,48,80,112,160,224];
 const socialIds=['S01','S02','S03','S04','S05','S06'];
 c.reviewRequest=async(path,body)=>{
  if(path==='/start'){session++;trial=0;starts.push(body);return;}
  if(path==='/api/state'){
   if(trial===36)return {done:true};
   const task=trial<18?'numerosity':'social',local=trial%18,block=Math.floor(local/6)+1,pos=local%6+1,cond=['N','P','A'][block-1];
   const trueCount=task==='numerosity'?dotCounts[pos-1]:null;
   const scenarioId=task==='social'?socialIds[pos-1]:null;
   return {trial_token:`${session}:${trial}`,trial_in_block:pos,block:Math.floor(trial/6)+1,practice:false,ratings_due:pos%2===0,adviser_name:['Jamie','Alex','Sam','Taylor','Morgan','Casey'][Math.floor(trial/6)],task_type:task,scale_min:task==='social'?0:1,scale_max:task==='social'?100:400,question_text:task==='social'?'How likely is deliberate rejection?':'How many dots were there?',researcher:{mode:'live',pid:String(session),block_id:`${task}:${cond}`,task_type:task,scenario_id:scenarioId,true_count:trueCount,participant_index:session-1,condition:cond}};
  }
  if(path==='/api/prefetch'){prefetches++;return {ok:true,prefetched:true};}
  if(path==='/api/initial'){initialBodies.push(body);return {advice_number:body.estimate<50?70:30,advice_text:'Actual mock model message',researcher:{live_model:true,initial_context_available:false,rationale_context_available:true}};}
  if(path==='/api/final'){
   if(body.trial_token===`${session}:${trial}`){trial++;saved++;}
   if(fail&&!failed){failed=true;throw Error('Connection lost after commit');}
   return {ok:true};
  }
 };
 return {c,starts,initialBodies,count:()=>saved,prefetches:()=>prefetches,rows:()=>vm.runInContext('reviewRows',c)};
}
test('current dots + social comparison exports 108 trials with rationales',async()=>{
 const t=setup();await t.c.generateReview();assert.equal(t.count(),108);assert.equal(t.rows().length,108);
 assert.equal(t.starts.length,3);for(let i=0;i<t.starts.length;i++){const s=t.starts[i];assert.equal(s.get('researcher_test'),'1');assert.equal(s.get('adviser_mode'),'live');assert.equal(s.get('task_mode'),'both');assert.equal(s.get('trials'),'6');assert.equal(s.get('test_index'),String(i));}
 assert.equal(new Set(t.rows().map(r=>r.simulation_id)).size,3);assert.equal(t.prefetches(),108);
 assert.equal(t.rows().filter(r=>r.task_type==='numerosity').length,54);assert.equal(t.rows().filter(r=>r.task_type==='social').length,54);
 assert.ok(t.rows().every(r=>r.response_generator==='condition_blind_current_comparison_v2'));
 assert.ok(t.initialBodies.every(b=>typeof b.rationale==='string'&&b.rationale.length>0&&b.rationale.length<=240));
});
test('same participant and repeated dot numerosity has same simulated weight across conditions',async()=>{
 const t=setup();await t.c.generateReview();
 const rows=t.rows().filter(r=>r.simulation_id==='sim-1'&&r.task_type==='numerosity'&&r.true_count===32);
 assert.equal(rows.length,3);assert.equal(new Set(rows.map(r=>r.simulated_weight)).size,1);
});
test('lost save acknowledgement is retried without duplicate or missing exported row',async()=>{
 const t=setup(true);await t.c.generateReview();assert.equal(t.count(),1);assert.equal(t.rows().length,0);
 await t.c.generateReview();assert.equal(t.count(),108);assert.equal(t.rows().length,108);
});
