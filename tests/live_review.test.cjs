const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),{parseHTML}=require('linkedom');
function setup(fail=false){
 const {document}=parseHTML('<html><body>'+['review-model','review-start','review-stop','review-status','review-csv','review-json'].map(id=>`<button id="${id}"></button>`).join('')+'</body></html>');document.getElementById('review-model').value='gemini_fast';
 const c={document,window:{},REVIEW_CONFIG:{csrf:'test'},URLSearchParams,URL,Blob,setTimeout};vm.createContext(c);vm.runInContext(fs.readFileSync('static/live_review.js','utf8'),c);
 let session=0,trial=0,saved=0,failed=false,prefetches=0;const starts=[];
 const trueCounts=[64,72,80,88,96,104,112,120,128,136,152,160];
 c.reviewRequest=async(path,body)=>{
  if(path==='/start'){session++;trial=0;starts.push(body);return;}
  if(path==='/api/state'){
   if(trial===36)return {done:true};
   const block=Math.floor(trial/12)+1,pos=trial%12+1;
   const cond=['N','P','A'][block-1];
   return {trial_token:`${session}:${trial}`,trial_in_block:pos,block,practice:false,ratings_due:pos%2===0,adviser_name:['Jamie','Alex','Sam'][block-1],researcher:{mode:'live',pid:String(session),true_count:trueCounts[pos-1],participant_index:session-1,condition:cond}};
  }
  if(path==='/api/prefetch'){prefetches++;return {ok:true,prefetched:true};}
  if(path==='/api/initial')return {advice_number:208,advice_text:'Actual mock model message',researcher:{live_model:true,initial_context_available:false}};
  if(path==='/api/final'){
   if(body.trial_token===`${session}:${trial}`){trial++;saved++;}
   if(fail&&!failed){failed=true;throw Error('Connection lost after commit');}
   return {ok:true};
  }
 };
 return {c,starts,count:()=>saved,prefetches:()=>prefetches,rows:()=>vm.runInContext('reviewRows',c)};
}
test('three condition-blind synthetic participants export 108 messages',async()=>{
 const t=setup();await t.c.generateReview();assert.equal(t.count(),108);assert.equal(t.rows().length,108);
 assert.equal(t.starts.length,3);for(let i=0;i<t.starts.length;i++){const s=t.starts[i];assert.equal(s.get('researcher_test'),'1');assert.equal(s.get('adviser_mode'),'live');assert.equal(s.get('test_index'),String(i));}
 assert.equal(new Set(t.rows().map(r=>r.simulation_id)).size,3);assert.equal(t.prefetches(),108);
 assert.ok(t.rows().every(r=>r.response_generator==='condition_blind_matched_by_numerosity_v1'));
});
test('same participant and numerosity has same simulated weight across conditions',async()=>{
 const t=setup();await t.c.generateReview();
 const rows=t.rows().filter(r=>r.simulation_id==='sim-1'&&r.true_count===64);
 assert.equal(rows.length,3);assert.equal(new Set(rows.map(r=>r.simulated_weight)).size,1);
});
test('lost save acknowledgement is retried without duplicate or missing exported row',async()=>{
 const t=setup(true);await t.c.generateReview();assert.equal(t.count(),1);assert.equal(t.rows().length,0);
 await t.c.generateReview();assert.equal(t.count(),108);assert.equal(t.rows().length,108);
});
