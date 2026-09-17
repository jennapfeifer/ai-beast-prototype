"""BEAST Fieldwork: the human experiment, with separate protected pilot tools."""
from __future__ import annotations
import adviser_flexible
import csv, datetime as dt, hashlib, hmac, io, json, logging, math, os, secrets, time, uuid, zipfile
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for, send_file
from sqlalchemy import update
import adviser, design, store
from pilot import build_report, timing_projection

APP_VERSION = 'fieldwork-2.13-flexible-current'
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or secrets.token_hex(32)
ON_RENDER = os.getenv('RENDER', '').lower() in {'true','1'}
ACCESS_CODE = os.getenv('ACCESS_CODE', '')
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '')
if ON_RENDER and (not ACCESS_CODE or not ADMIN_TOKEN or not os.getenv('SECRET_KEY')):
    raise RuntimeError('Private pilot requires ACCESS_CODE, ADMIN_TOKEN and SECRET_KEY in Render Environment.')
app.config.update(SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SECURE=ON_RENDER,
                  MAX_CONTENT_LENGTH=64*1024)
STUDY_MODE = os.getenv('STUDY_MODE','pilot')
ADVISER_MODE = os.getenv('ADVISER_MODE','offline')
ADVISER_MIN_DELAY_MS = int(os.getenv('ADVISER_MIN_DELAY_MS','0'))
STIMULUS_MS = int(os.getenv('STIMULUS_MS','5000'))
FIXATION_MS = 0
COLLECT_RATINGS = os.getenv('COLLECT_RATINGS','1').lower() not in {'0','false'}
RATING_EVERY = max(1,int(os.getenv('RATING_EVERY','2')))
PREFILL_FINAL = True  # The v6 final slider starts at the participant's initial estimate.
SHOW_END_SCORE = os.getenv('SHOW_END_SCORE','1').lower() not in {'0','false'}
ADVICE_PREVIEW_MS = int(os.getenv('ADVICE_PREVIEW_MS','5000'))
if ADVICE_PREVIEW_MS not in {0,3000,4000,5000}:
    raise RuntimeError('ADVICE_PREVIEW_MS must be 0, 3000, 4000 or 5000.')
STUDY_CONTACT = os.getenv('STUDY_CONTACT','')
ETHICS_DETAILS = os.getenv('ETHICS_DETAILS','')
logging.basicConfig(level=logging.INFO)
from assets import ensure_stimuli, STIMULUS_DIR, STIMULUS_RENDER_VERSION
ensure_stimuli()
store.init_db()


def csrf():
    if 'csrf' not in session: session['csrf'] = secrets.token_urlsafe(24)
    return session['csrf']


@app.context_processor
def context():
    return dict(csrf_token=csrf(), is_researcher=bool(session.get('researcher')), study_mode=STUDY_MODE,
                contact=STUDY_CONTACT, ethics_details=ETHICS_DETAILS, ui_version=APP_VERSION,end_score=SHOW_END_SCORE)


@app.before_request
def access():
    if request.path.startswith('/static/stimuli/'):
        abort(404)
    if request.path == '/healthz': return
    if ACCESS_CODE and not session.get('access') and request.endpoint not in {'unlock','static'} and not is_admin():
        if request.path.startswith('/api/'): return jsonify(error='Unlock this private pilot first.'),403
        return redirect(url_for('unlock'))
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        if origin and urlsplit(origin).netloc != request.host: abort(403)
        token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
        if not session.get('csrf') or not hmac.compare_digest(str(token),session['csrf']):
            return jsonify(error='Session expired. Reload the page and try again.'),403


@app.after_request
def headers(response):
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    return response


@app.route('/unlock',methods=['GET','POST'])
def unlock():
    error=None
    if request.method=='POST':
        if ACCESS_CODE and hmac.compare_digest(request.form.get('code',''),ACCESS_CODE):
            session['access']=True
            return redirect(url_for('consent'))
        error='That access code was not recognised.'
    return render_template('unlock.html',error=error)


def require_session():
    pid=session.get('pid')
    if not pid or not store.session_data(pid): abort(403,'No active session. Start from the beginning.')
    return pid


def is_admin():
    bearer=request.headers.get('Authorization','')
    return bool(session.get('researcher') or (ADMIN_TOKEN and hmac.compare_digest(bearer,'Bearer '+ADMIN_TOKEN)))


def require_admin():
    if not is_admin(): abort(403)


def schedule(data):
    conf=data['config']
    rows=design.build_schedule(data['participant_index'])
    if conf.get('conditions'): rows=[r for r in rows if r['condition_id'] in conf['conditions']]
    if conf.get('trials_per_block'): rows=[r for r in rows if r['trial_position']<=conf['trials_per_block']]
    return ([] if conf.get('skip_practice') else design.practice_schedule())+rows


def ratings_due(trial):
    return COLLECT_RATINGS and trial['condition_id']!='PRACTICE' and trial['trial_position']%RATING_EVERY==0


def current(data):
    sched=schedule(data)
    return (sched[data['cursor']] if data['cursor']<len(sched) else None),sched


ADVISER_NAMES = ('Alex','Casey','Drew','Jamie','Morgan','Quinn','Riley','Taylor')


def assign_adviser_names():
    names=list(ADVISER_NAMES)
    secrets.SystemRandom().shuffle(names)
    return dict(zip(design.CONDITIONS,names))


def adviser_name(data,condition):
    return data['config'].get('adviser_names',{}).get(condition,'Practice AI' if condition=='PRACTICE' else 'AI')


def ensure_token(data):
    if not data.get('token'): data['token']=secrets.token_urlsafe(24)
    return data['token']


def integer(value,minimum=1,maximum=design.MAX_ESTIMATE):
    if isinstance(value,bool): raise ValueError('Enter a whole number.')
    try: n=float(value)
    except (ValueError,TypeError): raise ValueError('Enter a whole number.')
    if not math.isfinite(n) or n!=int(n) or not minimum<=n<=maximum:
        raise ValueError(f'Enter a whole number between {minimum} and {maximum}.')
    return int(n)


def milliseconds(value):
    if value is None: return None
    return integer(value,0,86400000)


@app.route('/')
def consent():
    active=store.session_data(session['pid']) if session.get('pid') else None
    return render_template('consent.html',external_id=request.args.get('PROLIFIC_PID',''),active=bool(active and not active['complete']),
                           pilot=STUDY_MODE!='production',ratings=COLLECT_RATINGS,rating_every=RATING_EVERY)


@app.post('/start')
def start():
    if request.form.get('consent')!='yes': return 'Please confirm your consent before starting.',400
    researcher=bool(session.get('researcher') and request.form.get('researcher_test')=='1')
    mode=request.form.get('adviser_mode',ADVISER_MODE) if researcher else ADVISER_MODE
    if mode not in {'offline','live'}: return 'Invalid adviser mode.',400
    profile_id=request.form.get('model_profile','server') if researcher else 'server'
    profiles=adviser.model_profiles()
    if profile_id not in profiles:return 'Unknown model choice. Reload the researcher workspace.',400
    profile=profiles[profile_id]
    if mode=='live' and not adviser.has_api_key(profile['provider']):
        key_name='GEMINI_API_KEY' if profile['provider']=='gemini' else 'OPENAI_API_KEY'
        return f'Live adviser key is not configured for {profile["provider"]}. Set {key_name} in Render Environment or select an offline rehearsal.',400
    if STUDY_MODE=='production' and not researcher and (mode!='live' or not STUDY_CONTACT or not ETHICS_DETAILS):
        return 'Production is not configured: live adviser, approved study information and contact details are required.',503
    conditions=[]
    n=13
    if researcher:
        conditions=[x for x in request.form.getlist('conditions') if x in design.CONDITIONS]
        try: n=integer(request.form.get('trials','13'),1,13)
        except ValueError as e: return str(e),400
    try:preview_ms=integer(request.form.get('advice_preview_ms',str(ADVICE_PREVIEW_MS)),0,5000) if researcher else ADVICE_PREVIEW_MS
    except ValueError:return 'Invalid advice display setting.',400
    if preview_ms not in {0,3000,4000,5000}:return 'Invalid advice display setting.',400
    conf=dict(conditions=conditions,trials_per_block=n,skip_practice=researcher and request.form.get('skip_practice')=='1',
              adviser_protocol='flexible_v8',advice_preview_ms=preview_ms,rating_items='trust_only',adviser_names=assign_adviser_names(),
              test_index=integer(request.form.get('test_index','0'),0,7) if researcher else 0,
              adviser_mode=mode,is_test=researcher or STUDY_MODE!='production' or mode!='live',researcher=researcher,
              model_profile_id=profile_id,model_profile=profile,
              ui_version=APP_VERSION,stimulus_render_version=STIMULUS_RENDER_VERSION,
              started_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat())
    pid=uuid.uuid4().hex[:12]
    store.create_session(pid,conf,(request.form.get('external_id') or '')[:128] or None)
    session['pid']=pid
    return redirect(url_for('instructions'))


@app.route('/instructions')
def instructions():
    pid=require_session();data=store.session_data(pid);sched=schedule(data)
    return render_template('instructions.html',n_trials=sum(r['condition_id']!='PRACTICE' for r in sched),
      n_blocks=len({r['condition_id'] for r in sched if r['condition_id']!='PRACTICE'}),practice=not data['config']['skip_practice'],
      stimulus_seconds=STIMULUS_MS/1000,ratings=COLLECT_RATINGS,rating_every=RATING_EVERY,pilot=data['config']['is_test'],
      advice_preview_ms=data['config'].get('advice_preview_ms',0),rating_items=data['config'].get('rating_items','trust_and_feeling'))


@app.route('/task')
def task():
    pid=require_session();data=store.session_data(pid)
    return render_template('task.html',config=dict(csrf=csrf(),min_delay_ms=ADVISER_MIN_DELAY_MS,stimulus_ms=STIMULUS_MS,
        fixation_ms=FIXATION_MS,collect_ratings=COLLECT_RATINGS,rating_every=RATING_EVERY,prefill_final=PREFILL_FINAL,
        researcher_mode=bool(session.get('researcher') and data['config'].get('researcher')),max_estimate=design.MAX_ESTIMATE,
        pilot=data['config']['is_test'],offline=data['config']['adviser_mode']=='offline',request_timeout_ms=90000,
        advice_preview_ms=data['config'].get('advice_preview_ms',0),prefetch_enabled=data['config'].get('adviser_protocol')!='flexible_v8',rating_items=data['config'].get('rating_items','trust_and_feeling')))


@app.get('/api/state')
def api_state():
    pid=require_session()
    with store.session_transaction(pid) as (con,data):
        trial,sched=current(data)
        if trial is None: return jsonify(done=True)
        token=ensure_token(data)
        practice=trial['condition_id']=='PRACTICE'
        conditions=list(dict.fromkeys(r['condition_id'] for r in sched if r['condition_id']!='PRACTICE'))
        experimental=[r for r in sched if r['condition_id']!='PRACTICE']
        completed=sum(r['condition_id']!='PRACTICE' for r in sched[:data['cursor']])
        block=0 if practice else conditions.index(trial['condition_id'])+1
        out=dict(done=False,trial_token=token,practice=practice,block=block,n_blocks=len(conditions),
                 adviser_name=adviser_name(data,trial['condition_id']),trial_in_block=trial['trial_position'],n_in_block=sum(r['condition_id']==trial['condition_id'] for r in sched),
                 overall=completed+1,completed=completed,overall_total=len(experimental),
                 image=url_for('stimulus',token=token),break_due=not practice and trial['trial_position']==1 and block>1,
                 ratings_due=ratings_due(trial),rating_window=RATING_EVERY,pending=None,researcher=None)
        if data['pending']:
            out['pending']={k:data['pending'][k] for k in ['initial','text','rt_initial','latency_ms','advice']}
        if session.get('researcher') and data['config'].get('researcher'):
            out['researcher']=dict(condition=trial['condition_id'],style=trial['adviser_style'],direction=trial['direction'],
                true_count=trial['true_count'],pid=pid,participant_index=data['participant_index'],mode=data['config']['adviser_mode'],
                condition_order=conditions,**(data['pending'].get('diagnostic',{}) if data['pending'] else {}))
        return jsonify(out)


@app.get('/stimulus/<token>')
def stimulus(token):
    pid=require_session();data=store.session_data(pid);trial,_=current(data)
    if not trial or data.get('pending') or not data.get('token') or not hmac.compare_digest(token,data['token']):abort(404)
    return send_file(STIMULUS_DIR/f"{trial['stimulus_id']}.webp",mimetype='image/webp',max_age=0,download_name='dot-field.webp')


def advice_payload(pending,data):
    trial,_=current(data)
    result=dict(adviser_name=adviser_name(data,trial['condition_id']),advice_text=pending['text'],advice_number=pending['advice'],latency_ms=pending['latency_ms'])
    if session.get('researcher') and data['config'].get('researcher'):result['researcher']=pending['diagnostic']
    return result


def prepared_advice(con,data,trial,initial):
    practice=trial['condition_id']=='PRACTICE'
    style='fixed' if practice else trial['adviser_style']
    advice=design.clamp_int(initial*1.05) if practice else design.advice_number(trial['condition_id'],trial['true_count'],initial or 100)
    flexible=data['config'].get('adviser_protocol')=='flexible_v8'
    cached=None if flexible else data.get('prefetched')
    if style!='fixed' and cached and cached.get('token')==data.get('token') and cached['advice']==advice:
        return advice,cached['message'],dict(cached['diagnostic'],prefetched=True)
    rows=[] if practice else store.block_history(data['_pid'],trial['condition_id'],con)
    history=rows if style=='adaptive' else []
    generator=adviser.generate_offline_message if data['config']['adviser_mode']=='offline' else adviser.generate_message
    if flexible and data['config']['adviser_mode']=='live':generator=adviser_flexible.generate_message
    t=time.perf_counter()
    # Protocol is pinned at session creation; legacy v7 withholds the current estimate.
    profile=data['config'].get('model_profile') or adviser.model_profiles()['server']
    with adviser.use_model_profile(profile):
        msg=generator(style=style,initial=initial if flexible or style=='fixed' else None,advice=advice,history=history,
            previous_messages=[r['advice_text'] for r in rows if r.get('advice_text')],
            key=f"{data['participant_index']}|{trial['condition_id']}|{trial['trial_position']}")
    diagnostic=dict(history_rows=len(history),expected_history_rows=trial['trial_position']-1 if style=='adaptive' else 0,
        history_positions=[r['trial_position'] for r in history],displayed_message=msg['text'],source=msg['source'],attempts=msg['attempts'],
        validation=msg['validation'],word_count=msg['word_count'],live_model=msg.get('live_model',False),
        history_route=msg.get('history_route'),generation_ms=round((time.perf_counter()-t)*1000),
        history_check=msg.get('history_check'),prompt_version=msg.get('prompt_version'),
        prompt_sha256=msg.get('prompt_sha256'),
        attempt_log=msg.get('attempt_log',[]),fallback=msg['source'].startswith('fallback:'),
        adviser_protocol=data['config'].get('adviser_protocol','legacy_v7'),initial_context_available=flexible or style=='fixed',prefetched=False,provider=profile['provider'],
        model=profile['model'],reasoning=profile['reasoning'],request_timeout_s=profile['timeout'],advice=advice)
    diagnostic.update(model_response_received=msg.get('model_response_received',False),
        trust_context_in_prompt=msg.get('trust_context_in_prompt',False),
        feeling_context_in_prompt=msg.get('feeling_context_in_prompt',False),
        trust_check=msg.get('trust_check','not_checked_offline' if data['config']['adviser_mode']=='offline' else 'not_applicable'))
    for field in ('trust_latest_rating','trust_latest_trial','trust_previous_rating','trust_change','trust_age_trials',
                  'feeling_latest_rating','feeling_latest_trial','feeling_previous_rating','feeling_change','feeling_age_trials',
                  'adaptive_focus','adaptive_strategy','adaptation_check','feeling_check','repetition_check','repetition_similarity',
                  'review_required','review_reasons','rating_strategies','grounding_record_check','model_basis',
                  'generation_status','rating_influence_status','persuasion_check',
                  'max_attempts','total_budget_s','retry_policy_version','retry_count',
                  'recovered_after_retry','stop_reason','budget_overrun',
                  'target_word_range','word_tolerance','word_count_check','direction_check'):
        diagnostic[field]=msg.get(field)
    return advice,msg,diagnostic


@app.post('/api/prefetch')
def api_prefetch():
    pid=require_session();body=request.get_json(silent=True) or {}
    with store.session_transaction(pid) as (con,data):
        trial,_=current(data)
        if trial is None or not data.get('token') or body.get('trial_token')!=data.get('token'):
            return jsonify(error='This trial is no longer current.'),409
        if data['config'].get('adviser_protocol')=='flexible_v8':
            return jsonify(ok=True,prefetched=False,reason='requires_current_estimate')
        if data.get('pending') or trial['condition_id']=='PRACTICE' or trial['adviser_style']=='fixed':
            return jsonify(ok=True,prefetched=False)
        data['_pid']=pid
        advice,msg,diagnostic=prepared_advice(con,data,trial,None)
        data['prefetched']=dict(token=data['token'],advice=advice,message=msg,diagnostic=diagnostic)
        return jsonify(ok=True,prefetched=True)


@app.post('/api/initial')
def api_initial():
    pid=require_session();body=request.get_json(silent=True) or {}
    try:initial=integer(body.get('estimate'));rt=milliseconds(body.get('rt_ms'))
    except ValueError as e:return jsonify(error=str(e)),400
    with store.session_transaction(pid) as (con,data):
        trial,_=current(data)
        if trial is None or body.get('trial_token')!=data.get('token'):return jsonify(error='This trial is no longer current. Reload to resume.'),409
        if data['pending']:
            if data['pending']['initial']!=initial:return jsonify(error='An initial answer is already recorded for this trial.'),409
            return jsonify(advice_payload(data['pending'],data))
        data['_pid']=pid
        advice,msg,diagnostic=prepared_advice(con,data,trial,initial)
        elapsed=diagnostic['generation_ms']
        pending=dict(initial=initial,advice=advice,text=msg['text'],source=msg['source'],attempts=msg['attempts'],
            word_count=msg['word_count'],rt_initial=rt,latency_ms=elapsed,diagnostic=diagnostic,
            initial_telemetry=body.get('telemetry') if isinstance(body.get('telemetry'),dict) else {})
        data['pending']=pending
        return jsonify(advice_payload(pending,data))


TIMING_FIELDS=['fixation_ms','stimulus_load_ms','stimulus_visible_ms','initial_active_ms','initial_wall_ms',
    'advice_wait_ms','final_active_ms','final_wall_ms','rating_ms','break_ms','total_wall_ms','total_active_ms',
    'hidden_ms','visibility_interruptions','resumed','viewport_width','viewport_height','device_pixel_ratio',
    'stimulus_render_width','stimulus_render_height','prefetch_request_ms','prefetch_remaining_ms',
    'stimulus_fetch_ms','advice_preview_ms','advice_preview_wall_ms']


def clean_timing(body):
    if not isinstance(body,dict):return {}
    result={}
    for key in TIMING_FIELDS:
        v=body.get(key)
        if v is None:continue
        if isinstance(v,bool):v=int(v)
        try:v=float(v)
        except (ValueError,TypeError):raise ValueError('Invalid timing value.')
        if not math.isfinite(v) or not 0<=v<=86400000:raise ValueError('Invalid timing value.')
        result[key]=round(v,3)
    return result


@app.post('/api/final')
def api_final():
    pid=require_session();body=request.get_json(silent=True) or {}
    try:
        final=integer(body.get('estimate'));rt=milliseconds(body.get('rt_ms'));timing=clean_timing(body.get('telemetry'))
    except ValueError as e:return jsonify(error=str(e)),400
    token=body.get('trial_token')
    with store.session_transaction(pid) as (con,data):
        signature={k:body.get(k) for k in ['estimate','trust','feeling']}
        if token and token==data.get('last_token'):
            if signature!=data.get('last_payload'):return jsonify(error='This trial was already saved with different responses.'),409
            return jsonify(ok=True,already_saved=True)
        trial,sched=current(data);pending=data.get('pending')
        if trial is None or not pending or token!=data.get('token'):return jsonify(error='No matching trial in progress. Reload to resume.'),409
        try:
            trust=integer(body.get('trust'),1,7) if ratings_due(trial) else None
            feeling=integer(body.get('feeling'),1,7) if ratings_due(trial) and data['config'].get('rating_items','trust_and_feeling')=='trust_and_feeling' else None
        except ValueError:return jsonify(error='Please select a rating from 1 to 7 for each question.'),400
        timing={**clean_timing(pending.get('initial_telemetry')),**timing}
        initial,advice=pending['initial'],pending['advice'];truth=trial['true_count'];practice=trial['condition_id']=='PRACTICE'
        if not practice:
            row=dict(trial,pid=pid,participant_index=data['participant_index'],initial_estimate=initial,advice_number=advice,
                advice_text=pending['text'],advice_source=pending['source'],advice_attempts=pending['attempts'],
                advice_word_count=pending['word_count'],final_estimate=final,trust_rating=trust,feeling_rating=feeling,
                initial_error_pct=design.signed_pct(initial,truth),final_error_pct=design.signed_pct(final,truth),
                advice_error_pct=design.signed_pct(advice,truth),woa=design.woa(initial,final,advice),
                rt_initial_ms=pending['rt_initial'],rt_final_ms=rt,advice_latency_ms=pending['latency_ms'],audio_played=False,modality='text')
            store.save_trial(row,con)
        diagnostic=dict(pending['diagnostic'],**timing,ui_version=APP_VERSION,stimulus_render_version=STIMULUS_RENDER_VERSION,
            adviser_name=adviser_name(data,trial['condition_id']),stimulus_format='webp_lossless',advice_preview_target_ms=data['config'].get('advice_preview_ms',0),rating_items=data['config'].get('rating_items','trust_and_feeling'),
            condition_id=trial['condition_id'],trial_position=trial['trial_position'],
            global_trial=trial['global_trial'],practice=practice,is_test=data['config']['is_test'],
            adviser_mode=data['config']['adviser_mode'],target_stimulus_ms=STIMULUS_MS,target_wait_ms=ADVISER_MIN_DELAY_MS,
            ratings_due=ratings_due(trial),timing_complete=all(k in timing for k in ['total_wall_ms','advice_wait_ms','stimulus_visible_ms','rating_ms']))
        store.save_diagnostics(con,pid,trial['global_trial'],diagnostic)
        data['cursor']+=1;data['pending']=None;data['prefetched']=None;data['last_token']=token;data['last_payload']=signature;data['token']=None
        if data['cursor']>=len(sched):
            data['complete']=True
            con.execute(update(store.participants).where(store.participants.c.pid==pid).values(finished_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)))
        return jsonify(ok=True)


@app.route('/debrief')
def debrief():
    pid=require_session();data=store.session_data(pid)
    if not data['complete']:return redirect(url_for('task'))
    store.update_participant(pid,debriefed=True)
    return render_template('debrief.html',pid=pid,pilot=data['config']['is_test'],offline=data['config']['adviser_mode']=='offline',
        adviser_protocol=data['config'].get('adviser_protocol','legacy_v7'),rating_items=data['config'].get('rating_items','trust_and_feeling'),completed=sum(not r['practice'] for r in store.diagnostic_rows(pid)),summary=store.participant_summary(pid) if SHOW_END_SCORE else None)


@app.get('/researcher/live-review')
def live_review():
    if not session.get('researcher'):return redirect(url_for('researcher'))
    profiles={k:dict(v,available=adviser.has_api_key(v['provider'])) for k,v in adviser.model_profiles().items()}
    default=next((k for k in ['gemini_fast','gpt_stronger','server'] if profiles[k]['available']),'server')
    return render_template('live_review.html',profiles=profiles,default_profile=default,config=dict(csrf=csrf()))


@app.route('/researcher',methods=['GET','POST'])
def researcher():
    error=None
    if request.method=='POST':
        if ADMIN_TOKEN and hmac.compare_digest(request.form.get('token',''),ADMIN_TOKEN):session['researcher']=True
        else:error='Researcher token not recognised.'
    if not session.get('researcher'):return render_template('researcher_login.html',error=error,configured=bool(ADMIN_TOKEN))
    records=store.diagnostic_rows();people=store.export_rows(store.participants)
    profiles={k:dict(v,available=adviser.has_api_key(v['provider'])) for k,v in adviser.model_profiles().items()}
    default_profile=next((k for k in ['gemini_fast','gpt_stronger','server'] if profiles[k]['available']),'server')
    return render_template('researcher.html',conditions=design.CONDITIONS,report=build_report(records,people),
        model_profiles=profiles,default_profile=default_profile,has_any_key=any(v['available'] for v in profiles.values()),
        has_key=adviser.has_api_key(),model=adviser.ADVISER_MODEL,stimulus_ms=STIMULUS_MS,
        delay_ms=ADVISER_MIN_DELAY_MS,rating_every=RATING_EVERY,advice_preview_ms=ADVICE_PREVIEW_MS,projection=timing_projection(
            wait_s=ADVISER_MIN_DELAY_MS/1000,stimulus_s=STIMULUS_MS/1000,fixation_s=FIXATION_MS/1000,
            rating_every=RATING_EVERY,collect_ratings=COLLECT_RATINGS,advice_preview_s=ADVICE_PREVIEW_MS/1000))


@app.route('/admin')
def admin_downloads():
    return redirect(url_for('researcher'))


@app.get('/api/researcher/status')
def researcher_status():
    require_admin()
    return jsonify(version=APP_VERSION,stimulus_render_version=STIMULUS_RENDER_VERSION,stimulus_format='webp_lossless',
        advice_preview_ms=ADVICE_PREVIEW_MS,
        provider=adviser.resolved_provider(),model=adviser.resolved_model(),
        has_key=adviser.has_api_key(),database_dialect=store.engine.dialect.name,study_mode=STUDY_MODE,
        adviser_mode=ADVISER_MODE,word_range=[adviser.ADVISER_MIN_WORDS,adviser.ADVISER_MAX_WORDS],
        retry_policy_version=adviser.RETRY_POLICY_VERSION,max_attempts=adviser.ADVISER_MAX_ATTEMPTS,
        total_budget_s=adviser.ADVISER_TOTAL_BUDGET_SECONDS,model_profiles=adviser.model_profiles(),
        word_tolerance=adviser.ADVISER_WORD_TOLERANCE,
        minimum_wait_ms=ADVISER_MIN_DELAY_MS,stimulus_ms=STIMULUS_MS,private_gate=bool(ACCESS_CODE))


@app.get('/api/researcher/report')
def researcher_report():
    require_admin()
    return jsonify(build_report(store.diagnostic_rows(),store.export_rows(store.participants)))


def csv_text(rows):
    if not rows:return ''
    fields=list(dict.fromkeys(k for r in rows for k in r))
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
    for row in rows:
        cleaned={k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in row.items()}
        # Avoid spreadsheet formula execution when opening free-text exports.
        cleaned={k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in cleaned.items()}
        writer.writerow(cleaned)
    return out.getvalue()


def export_tables():
    diagnostics=store.diagnostic_rows();people=store.export_rows(store.participants)
    return dict(trials=store.export_rows(store.trials),participants=people,ratings=store.export_rows(store.message_ratings),
                diagnostics=diagnostics,timing_summary=build_report(diagnostics,people)['conditions'],
                model_comparison=build_report(diagnostics,people)['model_conditions'])


@app.get('/admin/export/<what>.csv')
def export(what):
    require_admin();tables=export_tables()
    if what not in tables:abort(404)
    return Response(csv_text(tables[what]),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename={what}.csv'})


@app.get('/admin/export/all.zip')
def export_all_zip():
    require_admin();tables=export_tables();memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED) as z:
        for name,rows in tables.items():z.writestr(name+'.csv',csv_text(rows))
        z.writestr('pilot_report.json',json.dumps(build_report(tables['diagnostics'],tables['participants']),default=str,indent=2))
        z.writestr('run_metadata.json',json.dumps(dict(ui_version=APP_VERSION,stimulus_render_version=STIMULUS_RENDER_VERSION,
            stimulus_format='webp_lossless',default_advice_preview_ms=ADVICE_PREVIEW_MS,
            study_seed=design.STUDY_SEED,
            adviser_model=adviser.resolved_model(),adviser_provider=adviser.resolved_provider(),study_mode=STUDY_MODE,default_adviser_mode=ADVISER_MODE,
            stimulus_ms=STIMULUS_MS,fixation_ms=FIXATION_MS,minimum_advice_wait_ms=ADVISER_MIN_DELAY_MS,
            rating_every=RATING_EVERY,prefill_final=PREFILL_FINAL,word_range=[adviser.ADVISER_MIN_WORDS,adviser.ADVISER_MAX_WORDS],
            retry_policy_version=adviser.RETRY_POLICY_VERSION,model_profiles=adviser.model_profiles(),
            word_tolerance=adviser.ADVISER_WORD_TOLERANCE,
            conditions=design.CONDITIONS,limits=['Offline rehearsals do not validate live model behaviour.',
            'Timing is browser instrumentation, not an eye-tracker trigger.',
            'Mechanical validity does not certify persuasive content or historical claims.']),indent=2))
    memory.seek(0)
    return send_file(memory,mimetype='application/zip',as_attachment=True,download_name='beast_pilot_results.zip')


@app.route('/rate')
def rate():
    require_admin();rater=session.setdefault('rater',uuid.uuid4().hex[:8])
    return render_template('rate.html',rater=rater,items=store.messages_for_rating(rater,40))


@app.post('/api/rate')
def api_rate():
    require_admin();body=request.get_json(silent=True) or {}
    try:
        row={k:integer(body.get(k),1,7) for k in ['personalization','warmth','valence','directiveness','convincingness']}
        row['trial_id']=integer(body.get('trial_id'),1,2147483647)
    except ValueError as e:return jsonify(error=str(e)),400
    row.update(rater_id=session.setdefault('rater',uuid.uuid4().hex[:8]))
    store.save_rating(row);return jsonify(ok=True)


@app.get('/healthz')
def healthz():return jsonify(ok=True,version=APP_VERSION)


if __name__=='__main__':
    app.run(host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','5000')),debug=False,threaded=True)
