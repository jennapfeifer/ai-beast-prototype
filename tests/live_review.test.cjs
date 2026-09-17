const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),{parseHTML}=require('linkedom');
function setup(fail=false){
 const {document}=parseHTML('<html><body>'+['review-model','review-start','review-stop','review-status','review-csv','review-json'].map(id=>`<button id="${id}"></button>`).join('')+'</body></html>');document.getElementById('review-model').value='gemini_fast';
 const c={document,window:{},REVIEW_CONFIG:{csrf:'test'},URLSearchParams,URL,Blob,setTimeout};vm.createContext(c);vm.runInContext(fs.readFileSync('static/live_review.js','utf8'),c);
 let session=0,trial=0,saved=0,failed=false;const starts=[];
 c.reviewRequest=async(path,body)=>{
  if(path==='/start'){session++;trial=0;starts.push(body);return;}
  if(path==='/api/state')return trial===105?{done:true}:{trial_token:`${session}:${trial}`,trial_in_block:trial%13+1,block:1,practice:trial===0,ratings_due:trial%2===0,researcher:{mode:'live',pid:String(session),true_count:160,participant_index:0,condition:'C5'}};
  if(path==='/api/initial')return {advice_number:208,advice_text:'Actual mock model message',researcher:{live_model:true}};
  if(path==='/api/final'){
   if(body.trial_token===`${session}:${trial}`){trial++;saved++;}
   if(fail&&!failed){failed=true;throw Error('Connection lost after commit');}
   return {ok:true};
  }
 };
 return {c,starts,count:()=>saved,rows:()=>vm.runInContext('reviewRows',c)};
}
test('three full TEST profiles export 315 messages and use live mode',async()=>{
 const t=setup();await t.c.generateReview();assert.equal(t.count(),315);assert.equal(t.rows().length,315);
 assert.equal(t.starts.length,3);for(const s of t.starts){assert.equal(s.get('researcher_test'),'1');assert.equal(s.get('adviser_mode'),'live');assert.equal(s.get('test_index'),'0');}
 assert.equal(new Set(t.rows().map(r=>r.profile)).size,3);
 assert.equal(t.c.profileResponse('resistant',2,100,200).final,110);
 assert.equal(t.c.profileResponse('changing',12,100,200).trust,2);
});
test('lost save acknowledgement is retried without duplicate or missing exported row',async()=>{
 const t=setup(true);await t.c.generateReview();assert.equal(t.count(),1);assert.equal(t.rows().length,0);
 await t.c.generateReview();assert.equal(t.count(),315);assert.equal(t.rows().length,315);
});
