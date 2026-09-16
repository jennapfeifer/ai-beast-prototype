/* Shared estimate UI. Positions map to the same rail for every source.
   No participant numbers or trial state are stored outside the caller. */
'use strict';
window.BEASTEstimate = (() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const percent = (value, max) => 100 * (clamp(value, 1, max) - 1) / (max - 1);
  const pointerValue = (x, left, width, max) => Math.round(1 + clamp((x-left)/Math.max(1,width),0,1)*(max-1));
  const labelLeft = (value, railWidth, labelWidth, max) =>
    clamp(percent(value,max)*railWidth/100-labelWidth/2,0,Math.max(0,railWidth-labelWidth));

  function markup({initial = null, advice = null, max = 400}) {
    const final = advice !== null;
    const first = Number(initial);
    const ai = Number(advice?.advice_number);
    return `<div class="estimate-card ${final?'decision-card':'initial-card'}">
      <h1 class="estimate-question ${final?'final-colour':'previous-colour'}" id="estimate-title">Enter your ${final?'final ':''}estimate</h1>
      ${final?'':'<p class="estimate-instruction" id="estimate-help">Click the line or type a number.</p>'}
      <div class="estimate-scale">
        ${final?`<div class="reference-lane previous-lane"><p class="reference-copy previous-colour" id="previous-copy">YOUR PREVIOUS ESTIMATE: <strong>${first}</strong></p></div>
        <div class="reference-lane advice-lane"><p class="reference-copy ai-colour" id="advice-copy"><span class="advice-intro">AI ADVICE: <strong>${ai}</strong></span><span class="advice-words"> — ${escape(advice.advice_text)}</span></p></div>`:''}
        <div class="estimate-axis" id="${final?'final-line':'initial-line'}" ${final?'':'tabindex="0" role="group" aria-labelledby="estimate-title" aria-describedby="estimate-help"'}>
          <div class="estimate-rail" aria-hidden="true"></div>
          ${final?`<span class="previous-marker" style="left:${percent(first,max)}%" aria-hidden="true"></span>
          <span class="advice-marker" style="left:${percent(ai,max)}%" aria-hidden="true"></span>
          <input class="estimate-range" id="est" type="range" min="1" max="${max}" step="1" value="${first}" aria-labelledby="estimate-title" aria-describedby="previous-copy advice-copy" aria-valuetext="${first} dots">`:''}
          <div class="value-marker ${final?'final-marker':'initial-marker'}" id="${final?'final-pin':'initial-pin'}" ${final?`style="left:${percent(first,max)}%"`:'hidden'} aria-hidden="true"><span class="value-stem"></span><span class="value-square" id="${final?'revised-value':'initial-pin-value'}">${final?first:''}</span></div>
          <span class="scale-end scale-start" aria-hidden="true">1</span><span class="scale-end scale-finish" aria-hidden="true">${max}</span>
        </div>
      </div>
      <div class="center"><button class="button estimate-confirm ${final?'confirm-final':'confirm-initial'}" id="go" ${final?'':'disabled'}>${final?'Confirm':'Continue'}</button></div>
    </div>`;
  }

  function render({stage, initial = null, advice = null, max = 400, clock, elapsed}) {
    const final = advice !== null;
    stage.innerHTML = markup({initial,advice,max});
    const axis = stage.querySelector(final?'#final-line':'#initial-line');
    const rail = axis.querySelector('.estimate-rail');
    const pin = stage.querySelector(final?'#final-pin':'#initial-pin');
    const readout = stage.querySelector(final?'#revised-value':'#initial-pin-value');
    const slider = final ? stage.querySelector('#est') : null;
    const keyboard = slider || axis;
    const button = stage.querySelector('#go');
    const started = clock();
    let selected = final ? Number(initial) : null, dragging = false, typed = '', typedTimer = null;
    let submitted = false, observer = null;

    function update(value) {
      if (!Number.isFinite(value)) return;
      selected = clamp(Math.round(value),1,max);
      pin.hidden = false;
      pin.style.left = `${percent(selected,max)}%`;
      readout.textContent = selected;
      button.disabled = false;
      if (slider) slider.value = selected;
      else keyboard.setAttribute('role','slider');
      keyboard.setAttribute('aria-valuemin','1');
      keyboard.setAttribute('aria-valuemax',String(max));
      keyboard.setAttribute('aria-valuenow',String(selected));
      keyboard.setAttribute('aria-valuetext',`${selected} dots`);
    }
    function resetTyping() {typed='';clearTimeout(typedTimer);}
    function locateLabels() {
      if (!final) return;
      const width = rail.getBoundingClientRect().width;
      for (const [id,value] of [['previous-copy',initial],['advice-copy',advice.advice_number]]) {
        const label = stage.querySelector('#'+id);
        label.style.left = `${labelLeft(Number(value),width,label.getBoundingClientRect().width,max)}px`;
      }
    }
    function fromPointer(event) {
      const bounds = rail.getBoundingClientRect();
      update(pointerValue(event.clientX,bounds.left,bounds.width,max));
    }
    axis.onpointerdown = event => {
      if (event.button !== undefined && event.button !== 0) return;
      event.preventDefault();resetTyping();dragging=true;
      keyboard.focus({preventScroll:true});axis.setPointerCapture?.(event.pointerId);fromPointer(event);
    };
    axis.onpointermove = event => {if(dragging)fromPointer(event);};
    axis.onpointerup = event => {dragging=false;if(axis.hasPointerCapture?.(event.pointerId))axis.releasePointerCapture(event.pointerId);};
    axis.onpointercancel = axis.onlostpointercapture = () => {dragging=false;};
    if (slider) slider.oninput = () => update(Number(slider.value));
    if (final) {
      locateLabels();
      if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(locateLabels);
        observer.observe(axis);
        observer.observe(stage.querySelector('#advice-copy'));
        observer.observe(stage.querySelector('#previous-copy'));
      }
      update(selected);
    }
    return new Promise(resolve => {
      const submit = () => {
        if (selected === null || submitted) return;
        submitted = true;button.disabled = true;clearTimeout(typedTimer);observer?.disconnect();
        resolve({estimate:selected,...elapsed(started)});
      };
      button.onclick = submit;
      keyboard.onkeydown = event => {
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        if (/^\d$/.test(event.key)) {
          event.preventDefault();typed=(typed+event.key).slice(-String(max).length);
          const value=Number(typed);if(value>=1&&value<=max)update(value);
          clearTimeout(typedTimer);typedTimer=setTimeout(()=>{typed='';},900);return;
        }
        if (event.key==='Backspace') {
          event.preventDefault();typed=typed.slice(0,-1);
          if (typed && Number(typed)>0) update(Number(typed));
          else if (!final) {
            selected=null;pin.hidden=true;readout.textContent='';button.disabled=true;
            keyboard.setAttribute('role','group');
            for (const attr of ['aria-valuemin','aria-valuemax','aria-valuenow','aria-valuetext']) keyboard.removeAttribute(attr);
          }
          return;
        }
        const delta={ArrowLeft:-1,ArrowDown:-1,ArrowRight:1,ArrowUp:1,PageDown:-10,PageUp:10}[event.key];
        if (delta!==undefined) {event.preventDefault();resetTyping();if(selected!==null)update(selected+delta);return;}
        if (event.key==='Home' || event.key==='End') {event.preventDefault();resetTyping();update(event.key==='Home'?1:max);return;}
        if (event.key==='Enter') {event.preventDefault();submit();}
      };
      keyboard.focus({preventScroll:true});
    });
  }
  return {render,markup,percent,pointerValue,labelLeft};
})();
