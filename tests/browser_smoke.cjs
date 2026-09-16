const {chromium}=require('playwright'),{spawn}=require('child_process'),fs=require('fs'),assert=require('assert/strict'),path=require('path');
const root=path.resolve(__dirname,'..');const tmp=fs.mkdtempSync(path.join(require('os').tmpdir(),'beast-browser-'));
const env={...process.env,DATABASE_URL:'sqlite:///'+tmp+'/pilot.db',SECRET_KEY:'browser-test-secret',ADMIN_TOKEN:'browser-researcher',ACCESS_CODE:'',STUDY_MODE:'pilot',ADVISER_MODE:'offline',STIMULUS_MS:'5000',FIXATION_MS:'450',ADVISER_MIN_DELAY_MS:'0',COLLECT_RATINGS:'1',RATING_EVERY:'2',PREFILL_FINAL:'0',PORT:'5187',HOST:'127.0.0.1',PYTHONUNBUFFERED:'1',RENDER:'false'};delete env.OPENAI_API_KEY;delete env.GEMINI_API_KEY;
const server=spawn(process.env.BEAST_TEST_PYTHON||'python',['app.py'],{cwd:root,env,stdio:['ignore','pipe','pipe']});let logs='';server.stderr.on('data',b=>logs+=b);const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{let browser;try{
for(let i=0;i<80;i++){try{if((await fetch('http://127.0.0.1:5187/healthz')).ok)break;}catch{}await sleep(100);}
browser=await chromium.launch({...(process.env.BEAST_TEST_CHROMIUM?{executablePath:process.env.BEAST_TEST_CHROMIUM}:{}),args:['--no-sandbox','--disable-dev-shm-usage','--no-zygote','--disable-gpu'],headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:5187');await page.screenshot({path:root+'/validation/welcome-desktop.png',fullPage:true});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),1440);
await page.goto('http://127.0.0.1:5187/researcher');await page.locator('[name=token]').fill('browser-researcher');await page.locator('button').click();await page.waitForSelector('form[action="/start"] button');await page.screenshot({path:root+'/validation/researcher-desktop.png',fullPage:true});
await page.locator('[name=trials]').fill('3');await page.locator('form[action="/start"] button').click();await page.waitForURL('**/instructions');await page.locator('a[href="/task"]').click();let seen=0;
while(seen<7){
 const state=await (await page.request.get('http://127.0.0.1:5187/api/state')).json();if(state.done)break;
 await page.waitForSelector('#continue-round, #initial-line',{timeout:20000});if(await page.locator('#continue-round').count())await page.locator('#continue-round').click();
 await page.waitForSelector('#initial-line',{timeout:20000});assert(await page.locator('#initial-pin').isHidden());await page.locator('#initial-line').pressSequentially('100');await page.locator('#go').click();
 await page.waitForFunction(()=>document.getElementById('phase-name')?.textContent==='YOUR FINAL DECISION',{timeout:90000});
 assert.equal(await page.locator('.previous-marker,.advice-marker,.value-marker').count(),3);assert.equal(await page.locator('.line-legend,.estimate-pair').count(),0);
 if(seen===2)await page.screenshot({path:root+'/validation/advice-desktop.png',fullPage:true});
 if(seen===3){await page.setViewportSize({width:390,height:844});await page.screenshot({path:root+'/validation/numberline-mobile.png',fullPage:true});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);await page.setViewportSize({width:1440,height:1050});}if(seen===5){await page.reload();await page.waitForSelector('#resume-advice');await page.locator('#resume-advice').click();await page.waitForFunction(()=>document.getElementById('phase-name')?.textContent==='YOUR FINAL DECISION');}
 const saved=page.waitForResponse(r=>r.url().endsWith('/api/final')&&r.request().method()==='POST');await page.locator('#est').fill('110');await page.locator('#go').click();
 if(state.ratings_due){await page.locator('[name=trust][value="4"]').check();await page.locator('[name=feeling][value="5"]').check();await page.locator('#rating-form button').click();}
 assert.equal((await saved).status(),200);seen++;console.log('Browser trial completed',seen);
 await page.waitForFunction(()=>!document.getElementById('phase-name')||document.getElementById('phase-name').textContent!=='RECORDING YOUR RESPONSE');
}
await page.waitForURL('**/debrief');assert((await page.locator('body').innerText()).includes('6 experimental trials'));const response=await page.request.get('http://127.0.0.1:5187/api/researcher/report');const report=await response.json();assert.equal(report.total_trials,6);assert.equal(report.history_mismatches,0);assert.equal(report.live_trials,0);assert.equal(report.complete_sessions,1);
const diag=await(await page.request.get('http://127.0.0.1:5187/admin/export/diagnostics.csv')).text();fs.writeFileSync(root+'/validation/browser-diagnostics.csv',diag);fs.writeFileSync(root+'/validation/browser-report.json',JSON.stringify(report,null,2));
for(const c of report.conditions){assert(c.wait_p50_ms>=0);assert(c.trial_p50_ms>=5400);}
await page.setViewportSize({width:390,height:844});await page.goto('http://127.0.0.1:5187');await page.screenshot({path:root+'/validation/welcome-mobile.png',fullPage:true});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
assert.deepEqual(errors,[]);console.log(JSON.stringify({result:'PASS',browser_trials:seen,recorded_trials:report.total_trials,session_minutes:report.sessions[0].wall_minutes,conditions:report.conditions,errors}));
}finally{if(browser)await browser.close();server.kill();fs.writeFileSync(tmp+'/server.log',logs);}})().catch(e=>{console.error(e);console.error(logs.slice(-2500));process.exitCode=1;server.kill();});
