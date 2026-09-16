/* DOM interaction checks; no browser/network or claims about painted layout. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const {parseHTML}=require('linkedom');
const source=fs.readFileSync(path.join(__dirname,'../static/estimate.js'),'utf8');

function setup(options={}){
  const {window,document}=parseHTML('<html><body><div id="stage"></div></body></html>');
  let focused=null,disconnected=false;
  const width=options.width||640;
  window.HTMLElement.prototype.focus=function(){focused=this;};
  window.HTMLElement.prototype.getBoundingClientRect=function(){
    return {left:40,width:this.id==='previous-copy'?Math.min(310,width):this.id==='advice-copy'?Math.min(620,width):width};
  };
  class Observer{observe(){}disconnect(){disconnected=true;}}
  const context={window,ResizeObserver:Observer,setTimeout,clearTimeout};
  vm.runInNewContext(source,context);
  const stage=document.getElementById('stage');
  const result=window.BEASTEstimate.render({stage,max:400,clock:()=>0,elapsed:()=>({wall:25,active:25}),...options});
  const key=(key,props={})=>{let prevented=false;focused.onkeydown({key,preventDefault(){prevented=true;},...props});return prevented;};
  return {api:window.BEASTEstimate,stage,result,key,get focused(){return focused;},get disconnected(){return disconnected;}};
}

test('initial estimate is blank, cannot submit, then typing creates one grey value',async()=>{
  const ui=setup();let resolved=false;ui.result.then(()=>{resolved=true;});
  assert.equal(ui.stage.querySelector('#initial-pin').hidden,true);
  assert.equal(ui.stage.querySelector('#go').disabled,true);
  ui.key('Enter');await Promise.resolve();assert.equal(resolved,false);
  for(const digit of '151')ui.key(digit);
  assert.equal(ui.stage.querySelector('#initial-pin-value').textContent,'151');
  assert.equal(ui.stage.querySelector('#initial-pin').hidden,false);
  assert.equal(ui.focused.getAttribute('aria-valuenow'),'151');
  assert.equal(ui.stage.querySelectorAll('.value-square').length,1);
  ui.key('Enter');assert.equal((await ui.result).estimate,151);
});

test('final starts at the initial answer, supports keyboard adjustment, and submits once',async()=>{
  const ui=setup({initial:151,advice:{advice_number:160,advice_text:'I would use that estimate for the display.'}});
  assert.equal(ui.stage.querySelector('#est').value,'151');
  ui.key('ArrowRight');assert.equal(ui.stage.querySelector('#revised-value').textContent,'152');
  for(const digit of '119')ui.key(digit);
  assert.equal(ui.stage.querySelector('#revised-value').textContent,'119');
  assert.equal(ui.focused.getAttribute('aria-valuetext'),'119 dots');
  ui.key('Enter');ui.key('Enter');
  assert.equal((await ui.result).estimate,119);
  assert.equal(ui.disconnected,true);
});

test('pointer mapping uses the shared rail and clamps outside its endpoints',async()=>{
  const ui=setup({initial:151,advice:{advice_number:160,advice_text:'Move toward my estimate.'},width:399});
  const axis=ui.stage.querySelector('#final-line');
  const event=x=>({clientX:x,button:0,pointerId:1,preventDefault(){}});
  axis.onpointerdown(event(40+118));
  assert.equal(ui.stage.querySelector('#revised-value').textContent,'119');
  axis.onpointermove(event(-100));assert.equal(ui.stage.querySelector('#est').value,'1');
  axis.onpointermove(event(999));assert.equal(ui.stage.querySelector('#est').value,'400');
  axis.onpointercancel();axis.onpointermove(event(40));
  assert.equal(ui.stage.querySelector('#est').value,'400');
  ui.stage.querySelector('#go').onclick();assert.equal((await ui.result).estimate,400);
});

test('native range input changes are reflected in the visible box and recorded value',async()=>{
  const ui=setup({initial:151,advice:{advice_number:160,advice_text:'Move toward my estimate.'}});
  const slider=ui.stage.querySelector('#est');slider.value='287';slider.oninput();
  assert.equal(ui.stage.querySelector('#revised-value').textContent,'287');
  ui.key('Enter');assert.equal((await ui.result).estimate,287);
});

test('nearby or identical references retain separate labels and markers without a legend',async()=>{
  for(const [first,ai] of [[151,160],[151,151],[1,1],[400,400]]){
    const ui=setup({initial:first,advice:{advice_number:ai,advice_text:'Move toward my estimate.'},width:224});
    assert.equal(ui.stage.querySelectorAll('.reference-lane').length,2);
    assert.equal(ui.stage.querySelectorAll('.previous-marker,.advice-marker,.value-marker').length,3);
    assert.equal(ui.stage.querySelectorAll('.estimate-pair,.line-legend,.revision-readout').length,0);
    assert.equal(ui.stage.querySelectorAll('.scale-end').length,2);
    for(const id of ['previous-copy','advice-copy']){
      const label=ui.stage.querySelector('#'+id);
      const left=parseFloat(label.style.left);
      assert(left>=0&&left+label.getBoundingClientRect().width<=224);
    }
    ui.key('Enter');await ui.result;
  }
});

test('advice is escaped and does not create injected elements or handlers',async()=>{
  const malicious='<img src=x onerror=alert(1)> "&"';
  const ui=setup({initial:151,advice:{advice_number:160,advice_text:malicious}});
  assert.equal(ui.stage.querySelectorAll('img,script').length,0);
  assert(ui.stage.querySelector('#advice-copy').textContent.includes(malicious));
  ui.key('Enter');await ui.result;
});

test('keyboard endpoints preserve the numerical range without a midpoint default',async()=>{
  const ui=setup();ui.key('ArrowRight');assert.equal(ui.stage.querySelector('#go').disabled,true);
  ui.key('End');assert.equal(ui.stage.querySelector('#initial-pin-value').textContent,'400');
  ui.key('ArrowUp');assert.equal(ui.stage.querySelector('#initial-pin-value').textContent,'400');
  ui.key('Home');ui.key('ArrowDown');assert.equal(ui.stage.querySelector('#initial-pin-value').textContent,'1');
  ui.key('Enter');assert.equal((await ui.result).estimate,1);
});

test('erasing an initial typed answer restores the blank state',async()=>{
  const ui=setup();for(const digit of '151')ui.key(digit);
  for(let i=0;i<3;i++)ui.key('Backspace');
  assert.equal(ui.stage.querySelector('#initial-pin').hidden,true);
  assert.equal(ui.stage.querySelector('#go').disabled,true);
  assert.equal(ui.focused.hasAttribute('aria-valuenow'),false);
  ui.key('Home');ui.key('Enter');await ui.result;
});
