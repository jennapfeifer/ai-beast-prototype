const {test}=require('node:test'),assert=require('node:assert/strict');
const {parseHTML}=require('linkedom'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const full=fs.readFileSync(path.join(__dirname,'../static/task.js'),'utf8');
const source=full.slice(0,full.lastIndexOf('\nrun().catch'));

function setup(preview=0,pause=false){
 const {document}=parseHTML('<html><body><div id="stage"></div><div id="phase-name"></div><div id="visibility-cover" hidden></div></body></html>');
 let now=0,hidden=false;const order=[];const images=[];
 Object.defineProperty(document,'hidden',{get:()=>hidden});
 const ctx={document,console,performance:{now:()=>now},
   BEAST_CFG:{max_estimate:400,advice_preview_ms:preview,stimulus_ms:1},
   requestAnimationFrame:cb=>queueMicrotask(()=>{order.push('paint');cb();}),
   setTimeout:(cb,ms)=>{queueMicrotask(()=>{
     now+=ms;
     if(pause){const next=now>=1000&&now<3000;if(next!==hidden){hidden=next;ctx.visibility();}}
     cb();
   });return 1;},clearTimeout:()=>{},
   BEASTEstimate:{render:async()=>{order.push('final');return {estimate:119,wall:20,active:20};}},
   Image:function(){const image=document.createElement('img');image.decode=async()=>{order.push('decode');now+=250;};image.getBoundingClientRect=()=>({width:512,height:512});images.push(image);return image;}
 };ctx.window=ctx;vm.createContext(ctx);vm.runInContext(source,ctx);
 ctx.fetchJSON=async()=>{order.push('prefetch');return {ok:true};};
 return {ctx,document,order,images,timing:()=>vm.runInContext('timing',ctx)};
}

test('advice-only exposure pauses when hidden and final UI appears afterwards',async()=>{
 const {ctx,document,order,timing}=setup(3000,true);
 const result=ctx.showAdvice({estimate:151},{advice_number:160,advice_text:'Read this advice before making your final estimate.'});
 assert(document.body.classList.contains('advice-focus'));
 assert(document.querySelector('.advice-only'));
 assert.equal(document.querySelector('.estimate-axis'),null);
 assert(!order.includes('final'));
 assert.equal((await result).estimate,119);
 assert(timing().advice_preview_ms>=3000&&timing().advice_preview_ms<3100);
 assert(timing().advice_preview_wall_ms>=5000);
 assert.equal(document.body.classList.contains('advice-focus'),false);
 assert.equal(order.at(-1),'final');
});

test('default flow does not add an advice-only delay',async()=>{
 const {ctx,document,timing}=setup();
 await ctx.showAdvice({estimate:151},{advice_number:160,advice_text:'Example'});
 assert.equal(timing().advice_preview_ms,0);
 assert.equal(document.querySelector('.advice-only'),null);
});

test('the preloaded image is reused and displayed before AI prefetch starts',async()=>{
 const {ctx,document,order,images,timing}=setup();
 vm.runInContext("state={image:'/stimulus/current-token',trial_token:'token'};stimulusPromise=prepareStimulus();",ctx);
 ctx.initialEstimator=async()=>({estimate:100,wall:10,active:10});
 await ctx.showStimulus();
 assert.equal(images.length,1);
 assert.equal(document.getElementById('stimulus'),images[0]);
 assert(order.indexOf('prefetch')>order.lastIndexOf('paint'));
 assert(order.indexOf('decode')<order.indexOf('paint'));
 assert.equal(timing().stimulus_fetch_ms,250);
 assert.equal(images[0].fetchPriority,'high');
});

test('one trust selection advances immediately, locks choices, and invents no feeling',async()=>{
 const {ctx,document}=setup();
 vm.runInContext("state={ratings_due:true,rating_window:2};",ctx);
 const pending=ctx.ratings();
 assert.equal(document.querySelectorAll('fieldset').length,1);
 assert.equal(document.querySelector('button'),null);
 assert(!document.body.textContent.includes('Check-in'));
 const input=document.querySelector('[name=trust][value="6"]');
 input.setAttribute('checked','');
 document.getElementById('rating-form').onchange();
 const result=await pending;
 assert.equal(result.trust,6);assert.equal(result.feeling,undefined);
 assert([...document.querySelectorAll('input')].every(input=>input.disabled));
});
