/* Shared continuous judgment UI for numerosity (1–400) and social judgments (0–100). */
'use strict';
window.BEASTEstimate = (() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const percent = (value, min, max) => 100 * (clamp(value,min,max)-min) / Math.max(1,max-min);
  const pointerValue = (x,left,width,min,max) => Math.round(min+clamp((x-left)/Math.max(1,width),0,1)*(max-min));
  const labelLeft = (value,railWidth,labelWidth,min,max) =>
    clamp(percent(value,min,max)*railWidth/100-labelWidth/2,0,Math.max(0,railWidth-labelWidth));

  function markup({initial=null,advice=null,min=1,max=400,title=null,lowLabel=null,highLabel=null,unit=''}={}) {
    const final=advice!==null, first=Number(initial), ai=Number(advice?.advice_number);
    const agentName=final?String(advice?.adviser_name||'Adviser'):'';
    const agentLabel=`${agentName}’s advice`;
    const heading=title || `Enter your ${final?'final ':'first '}estimate`;
    const low=lowLabel??String(min), high=highLabel??String(max);
    return `<div class="estimate-card ${final?'decision-card':'initial-card'}">
      <h1 class="estimate-question ${final?'final-colour':'previous-colour'}" id="estimate-title">${escape(heading)}</h1>
      <div class="estimate-scale">
        ${final?`<div class="reference-lane previous-lane"><p class="reference-copy previous-colour" id="previous-copy">YOUR FIRST JUDGMENT: <strong>${first}</strong></p></div>`:''}
        <div class="estimate-axis" id="${final?'final-line':'initial-line'}" ${final?'':'tabindex="0" role="group" aria-labelledby="estimate-title"'}>
          <div class="estimate-rail" aria-hidden="true"></div>
          ${final?`<span class="previous-marker" style="left:${percent(first,min,max)}%" aria-hidden="true"></span>
          <span class="advice-marker" style="left:${percent(ai,min,max)}%" aria-hidden="true"></span>
          <span class="advice-marker-label" id="advice-marker-label" style="left:${percent(ai,min,max)}%"><span class="advice-label-glyph" aria-hidden="true">▲</span>${escape(agentLabel)}</span>
          <input class="estimate-range" id="est" type="range" min="${min}" max="${max}" step="1" value="${first}" aria-labelledby="estimate-title" aria-describedby="previous-copy advice-marker-label" aria-valuetext="${first}${unit?' '+escape(unit):''}">`:''}
          <div class="value-marker ${final?'final-marker':'initial-marker'}" id="${final?'final-pin':'initial-pin'}" ${final?`style="left:${percent(first,min,max)}%"`:'hidden'} aria-hidden="true"><span class="value-stem"></span><span class="value-square" id="${final?'revised-value':'initial-pin-value'}">${final?first:''}</span></div>
          <span class="scale-end scale-start" aria-hidden="true">${escape(low)}</span><span class="scale-end scale-finish" aria-hidden="true">${escape(high)}</span>
        </div>
      </div>
      <div class="center"><button class="button estimate-confirm ${final?'confirm-final':'confirm-initial'}" id="go" ${final?'':'disabled'}>${final?'Confirm':'Continue'}</button></div>
    </div>`;
  }

  function render({stage,initial=null,advice=null,min=1,max=400,title=null,lowLabel=null,highLabel=null,unit='',clock,elapsed}) {
    const final=advice!==null;
    stage.innerHTML=markup({initial,advice,min,max,title,lowLabel,highLabel,unit});
    const axis=stage.querySelector(final?'#final-line':'#initial-line'), rail=axis.querySelector('.estimate-rail');
    const pin=stage.querySelector(final?'#final-pin':'#initial-pin'), readout=stage.querySelector(final?'#revised-value':'#initial-pin-value');
    const slider=final?stage.querySelector('#est'):null, keyboard=slider||axis, button=stage.querySelector('#go'), started=clock();
    let selected=final?Number(initial):null,dragging=false,typed='',typedTimer=null,submitted=false,observer=null;
    function update(value){
      if(!Number.isFinite(value))return;selected=clamp(Math.round(value),min,max);pin.hidden=false;
      pin.style.left=`${percent(selected,min,max)}%`;readout.textContent=selected;button.disabled=false;if(slider)slider.value=selected;
      else keyboard.setAttribute('role','slider');keyboard.setAttribute('aria-valuemin',String(min));keyboard.setAttribute('aria-valuemax',String(max));
      keyboard.setAttribute('aria-valuenow',String(selected));keyboard.setAttribute('aria-valuetext',`${selected}${unit?' '+unit:''}`);
    }
    function resetTyping(){typed='';clearTimeout(typedTimer);}
    function locateLabels(){if(!final)return;const width=rail.getBoundingClientRect().width,previous=stage.querySelector('#previous-copy');
      previous.style.left=`${labelLeft(Number(initial),width,previous.getBoundingClientRect().width,min,max)}px`;
      const agent=stage.querySelector('#advice-marker-label');agent.style.left=`${labelLeft(Number(advice.advice_number),width,agent.getBoundingClientRect().width,min,max)}px`;}
    function fromPointer(event){const b=rail.getBoundingClientRect();update(pointerValue(event.clientX,b.left,b.width,min,max));}
    axis.onpointerdown=e=>{if(e.button!==undefined&&e.button!==0)return;e.preventDefault();resetTyping();dragging=true;keyboard.focus({preventScroll:true});axis.setPointerCapture?.(e.pointerId);fromPointer(e);};
    axis.onpointermove=e=>{if(dragging)fromPointer(e);};axis.onpointerup=e=>{dragging=false;if(axis.hasPointerCapture?.(e.pointerId))axis.releasePointerCapture(e.pointerId);};axis.onpointercancel=axis.onlostpointercapture=()=>{dragging=false;};
    if(slider)slider.oninput=()=>update(Number(slider.value));
    if(final){locateLabels();if(typeof ResizeObserver!=='undefined'){observer=new ResizeObserver(locateLabels);observer.observe(axis);observer.observe(stage.querySelector('#previous-copy'));observer.observe(stage.querySelector('#advice-marker-label'));}update(selected);}
    return new Promise(resolve=>{
      const submit=()=>{if(selected===null||submitted)return;submitted=true;button.disabled=true;clearTimeout(typedTimer);observer?.disconnect();resolve({estimate:selected,...elapsed(started)});};
      button.onclick=submit;keyboard.onkeydown=e=>{if(e.ctrlKey||e.metaKey||e.altKey)return;if(/^\d$/.test(e.key)){e.preventDefault();typed=(typed+e.key).slice(-String(max).length);const v=Number(typed);if(v>=min&&v<=max)update(v);clearTimeout(typedTimer);typedTimer=setTimeout(()=>typed='',900);return;}
        if(e.key==='Backspace'){e.preventDefault();typed=typed.slice(0,-1);if(typed&&Number(typed)>=min)update(Number(typed));else if(!final){selected=null;pin.hidden=true;readout.textContent='';button.disabled=true;keyboard.setAttribute('role','group');for(const a of ['aria-valuemin','aria-valuemax','aria-valuenow','aria-valuetext'])keyboard.removeAttribute(a);}return;}
        const d={ArrowLeft:-1,ArrowDown:-1,ArrowRight:1,ArrowUp:1,PageDown:-10,PageUp:10}[e.key];if(d!==undefined){e.preventDefault();resetTyping();if(selected!==null)update(selected+d);return;}
        if(e.key==='Home'||e.key==='End'){e.preventDefault();resetTyping();update(e.key==='Home'?min:max);return;}if(e.key==='Enter'){e.preventDefault();submit();}};
    });
  }
  return {render,markup,percent,pointerValue,labelLeft};
})();
