"""BEAST Fieldwork: the human experiment, with separate protected pilot tools."""
from __future__ import annotations
import adviser_flexible
import base64, csv, datetime as dt, hashlib, hmac, io, json, logging, math, os, secrets, time, uuid, zipfile, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for, send_file
from sqlalchemy import update
import adviser, design, social_design, store
from pilot import build_report, timing_projection

# v2.36.3 researcher-only model-comparison presets. These extend the existing
# adviser presets without changing participant prompts or generation logic.
_BASE_MODEL_PROFILES = adviser.model_profiles

def _model_profiles_with_midrange_options():
    profiles = _BASE_MODEL_PROFILES()
    common = dict(
        attempts=adviser.ADVISER_MAX_ATTEMPTS,
        budget=adviser.ADVISER_TOTAL_BUDGET_SECONDS,
        retry_policy_version=adviser.RETRY_POLICY_VERSION,
    )
    profiles['gpt_terra'] = dict(
        label='GPT-5.6 Terra · no reasoning',
        provider='openai', model='gpt-5.6-terra', reasoning='none', timeout=15, **common
    )
    profiles['gemini_36'] = dict(
        label='Gemini 3.6 Flash · minimal thinking',
        provider='gemini', model='gemini-3.6-flash', reasoning='minimal', timeout=15, **common
    )
    profiles['gpt_6_sol'] = dict(
        label='GPT-6 Sol · no reasoning',
        provider='openai', model='gpt-6-sol', reasoning='none', timeout=15, **common
    )
    return profiles

adviser.model_profiles = _model_profiles_with_midrange_options

APP_VERSION = 'fieldwork-2.62-grounded-social-sparse-rationale'
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
ADVICE_PREVIEW_MS = int(os.getenv('ADVICE_PREVIEW_MS','4000'))
ADVICE_MODALITY = os.getenv('ADVICE_MODALITY','text').strip().lower()
TTS_PROVIDER = os.getenv('TTS_PROVIDER','gemini').strip().lower()
GEMINI_TTS_MODEL = os.getenv('GEMINI_TTS_MODEL','gemini-3.8-flash-tts').strip()
GEMINI_TTS_VOICE = os.getenv('GEMINI_TTS_VOICE','Kore').strip()
TTS_MODEL = os.getenv('TTS_MODEL','gpt-4o-mini-tts').strip()
TTS_VOICE = os.getenv('TTS_VOICE','marin').strip()
TTS_RESPONSE_FORMAT = os.getenv('TTS_RESPONSE_FORMAT','wav').strip().lower()
if TTS_RESPONSE_FORMAT not in {'wav','mp3'}:
    raise RuntimeError('TTS_RESPONSE_FORMAT must be wav or mp3.')
TTS_TIMEOUT_S = max(5.0,float(os.getenv('TTS_TIMEOUT_S','30')))

# Natural speech defaults to Gemini 3.8 Flash TTS for stronger, more controllable prosody.
# The same speaker identity is used across conditions; only delivery style changes.
def natural_voice_backend():
    # Never change speaker/provider silently. Use only the configured backend.
    if TTS_PROVIDER == 'gemini':
        return 'gemini' if os.getenv('GEMINI_API_KEY','').strip() else 'unavailable'
    if TTS_PROVIDER == 'openai':
        return 'openai' if os.getenv('OPENAI_API_KEY','').strip() else 'unavailable'
    if TTS_PROVIDER == 'browser':
        return 'browser'
    return 'unavailable'

def shared_voice_identity():
    backend=natural_voice_backend()
    if backend == 'gemini':
        return GEMINI_TTS_VOICE
    if backend == 'openai':
        return TTS_VOICE
    return GEMINI_TTS_VOICE

AGENT_TTS_VOICES = tuple(shared_voice_identity() for _ in design.CONDITIONS)

if ADVICE_MODALITY not in {'text','voice_text'}:
    raise RuntimeError('ADVICE_MODALITY must be text or voice_text.')
if ADVICE_PREVIEW_MS not in {0,3000,4000,5000}:
    raise RuntimeError('ADVICE_PREVIEW_MS must be 0, 3000, 4000 or 5000.')
STUDY_CONTACT = os.getenv('STUDY_CONTACT','')
ETHICS_DETAILS = os.getenv('ETHICS_DETAILS','')
logging.basicConfig(level=logging.INFO)
from assets import ensure_stimuli, ensure_stimulus, STIMULUS_DIR, STIMULUS_RENDER_VERSION
store.init_db()

# Warm the deterministic stimulus cache after import without blocking Gunicorn startup.
def _warm_stimuli_in_background():
    try:
        # Let Gunicorn bind its port before doing CPU-heavy image generation.
        time.sleep(2.0)
        ensure_stimuli()
    except Exception as exc:
        app.logger.warning('Background stimulus warmup failed: %s', exc)

import threading
threading.Thread(target=_warm_stimuli_in_background, name='stimulus-warmup', daemon=True).start()


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



def _task_order(participant_index, task_mode):
    if task_mode == 'both':
        return ['numerosity','social'] if participant_index % 2 == 0 else ['social','numerosity']
    return [task_mode]


def _block_ids_for_config(participant_index, task_mode, conditions=None):
    wanted=set(conditions or design.CONDITIONS)
    blocks=[]
    for task_type in _task_order(participant_index, task_mode):
        order = design.balanced_condition_order(participant_index) if task_type=='numerosity' else social_design.condition_order(participant_index)
        blocks.extend(f'{task_type}:{cid}' for cid in order if cid in wanted)
    return blocks


def _limited_social_rows(task_rows, n):
    if not n or n>=6:return task_rows
    result=[]
    for block_id in dict.fromkeys(r['block_id'] for r in task_rows):
        block=[r for r in task_rows if r['block_id']==block_id]
        up_need=n//2+(1 if n%2 else 0);down_need=n-up_need;chosen=[]
        for r in block:
            if r['direction']=='UP' and up_need>0:chosen.append(r);up_need-=1
            elif r['direction']=='DOWN' and down_need>0:chosen.append(r);down_need-=1
        for i,r in enumerate(chosen,start=1):r['trial_position']=i
        result.extend(chosen)
    return result


def schedule(data):
    conf=data['config']
    task_mode=conf.get('task_mode','numerosity')
    selected=set(conf.get('conditions') or design.CONDITIONS)
    n=conf.get('trials_per_block')
    rows=[]
    tasks=_task_order(data['participant_index'],task_mode)
    for task_type in tasks:
        if task_type=='numerosity':
            task_rows=design.build_schedule(data['participant_index'])
            if n and n<12:
                subset=set(design.balanced_trial_subset(data['participant_index'],n))
                task_rows=[r for r in task_rows if r['true_count'] in subset]
                for block_id in dict.fromkeys(r['block_id'] for r in task_rows):
                    for i,r in enumerate([x for x in task_rows if x['block_id']==block_id],start=1):r['trial_position']=i
        else:
            task_rows=social_design.build_schedule(data['participant_index'])
            task_rows=_limited_social_rows(task_rows,min(int(n or 6),6))
        task_rows=[r for r in task_rows if r['condition_id'] in selected]
        rows.extend(task_rows)
    for i,r in enumerate(rows,start=1):r['global_trial']=i
    if conf.get('skip_practice'):
        return rows
    first_task=tasks[0]
    practice=design.practice_schedule() if first_task=='numerosity' else social_design.practice_schedule()
    return practice+rows

def ratings_due(trial):
    return (COLLECT_RATINGS and not trial.get('suppress_ratings',False)
            and trial['condition_id']!='PRACTICE' and trial['trial_position']%RATING_EVERY==0)


def current(data):
    sched=schedule(data)
    return (sched[data['cursor']] if data['cursor']<len(sched) else None),sched


def assign_adviser_names(participant_index=0, block_ids=None):
    return design.adviser_name_mapping_for_blocks(participant_index, block_ids or [f'numerosity:{c}' for c in design.CONDITIONS])


def adviser_name(data, trial_or_condition):
    if isinstance(trial_or_condition, dict):
        trial=trial_or_condition
        condition=trial.get('condition_id')
        block_id=trial.get('block_id') or f"{trial.get('task_type','numerosity')}:{condition}"
    else:
        condition=trial_or_condition
        block_id=f"numerosity:{condition}"
    if condition == 'PRACTICE':
        return 'Practice adviser'
    names = data.get('config', {}).get('adviser_names') or {}
    return names.get(block_id) or names.get(condition) or 'Adviser'

def assign_adviser_voices():
    # Every named agent uses the same speaker identity.
    return {condition:shared_voice_identity() for condition in design.CONDITIONS}


def adviser_voice(data,condition):
    return shared_voice_identity()


def adviser_voice_slot(data,condition):
    return 0

CONDITION_AGENT_STYLE = {
    'N':'neutral',
    'P':'static',
    'A':'adaptive',
}

def condition_agent_style(condition, fallback=None):
    if condition == 'PRACTICE':
        return 'fixed'
    return CONDITION_AGENT_STYLE.get(condition, fallback)


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
    mode=request.form.get('adviser_mode',ADVISER_MODE) if researcher else 'live'
    if mode not in {'offline','live'}: return 'Invalid adviser mode.',400
    profile_id=request.form.get('model_profile','server') if researcher else 'gpt_6_sol'
    profiles=adviser.model_profiles()
    if profile_id not in profiles:return 'Unknown model choice. Reload the researcher workspace.',400
    profile=profiles[profile_id]
    if mode=='live' and not adviser.has_api_key(profile['provider']):
        key_name='GEMINI_API_KEY' if profile['provider']=='gemini' else 'OPENAI_API_KEY'
        return f'Live adviser key is not configured for {profile["provider"]}. Set {key_name} in Render Environment or select an offline rehearsal.',400
    if STUDY_MODE=='production' and not researcher and (mode!='live' or not STUDY_CONTACT or not ETHICS_DETAILS):
        return 'Production is not configured: live adviser, approved study information and contact details are required.',503
    conditions=[]
    n=12
    task_mode='numerosity'
    if researcher:
        conditions=[x for x in request.form.getlist('conditions') if x in design.CONDITIONS]
        task_mode=(request.form.get('task_mode','numerosity') or 'numerosity').strip().lower()
        if task_mode not in {'numerosity','social','both'}: return 'Invalid task mode.',400
        try: n=integer(request.form.get('trials','12'),1,12)
        except ValueError as e: return str(e),400
    try:preview_ms=integer(request.form.get('advice_preview_ms',str(ADVICE_PREVIEW_MS)),0,5000) if researcher else ADVICE_PREVIEW_MS
    except ValueError:return 'Invalid advice display setting.',400
    if preview_ms not in {0,3000,4000,5000}:return 'Invalid advice display setting.',400
    advice_modality=(request.form.get('advice_modality',ADVICE_MODALITY) if researcher else 'voice_text').strip().lower()
    if advice_modality not in {'text','voice_text'}:return 'Invalid advice modality.',400
    conf=dict(conditions=conditions,trials_per_block=n,task_mode=task_mode,skip_practice=researcher and request.form.get('skip_practice')=='1',
              adviser_protocol='grounded_social_sparse_rationale_v2',advice_preview_ms=preview_ms,advice_modality=advice_modality,rating_items='trust_only',adviser_names={},adviser_voices=assign_adviser_voices(),
              test_index=integer(request.form.get('test_index','0'),0,5) if researcher else 0,
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
    experimental=[r for r in sched if r['condition_id']!='PRACTICE']
    return render_template('instructions.html',n_trials=len(experimental),
      n_blocks=len(dict.fromkeys(r.get('block_id',r['condition_id']) for r in experimental)),practice=not data['config']['skip_practice'],
      task_mode=data['config'].get('task_mode','numerosity'),
      numerosity_trials=sum(r.get('task_type','numerosity')=='numerosity' for r in experimental),
      social_trials=sum(r.get('task_type')=='social' for r in experimental),
      stimulus_seconds=STIMULUS_MS/1000,ratings=COLLECT_RATINGS,rating_every=RATING_EVERY,pilot=data['config']['is_test'],
      advice_preview_ms=data['config'].get('advice_preview_ms',0),advice_modality=data['config'].get('advice_modality','text'),rating_items=data['config'].get('rating_items','trust_and_feeling'))


@app.route('/task')
def task():
    pid=require_session();data=store.session_data(pid)
    return render_template('task.html',config=dict(csrf=csrf(),min_delay_ms=ADVISER_MIN_DELAY_MS,stimulus_ms=STIMULUS_MS,
        fixation_ms=FIXATION_MS,collect_ratings=COLLECT_RATINGS,rating_every=RATING_EVERY,prefill_final=PREFILL_FINAL,
        researcher_mode=bool(session.get('researcher') and data['config'].get('researcher')),max_estimate=design.MAX_ESTIMATE,
        pilot=data['config']['is_test'],offline=data['config']['adviser_mode']=='offline',request_timeout_ms=90000,
        advice_preview_ms=data['config'].get('advice_preview_ms',0),advice_modality=data['config'].get('advice_modality','text'),
        voice_backend=natural_voice_backend(),prefetch_enabled=True,rating_items=data['config'].get('rating_items','trust_and_feeling')))


@app.get('/api/state')
def api_state():
    pid=require_session()
    with store.session_transaction(pid) as (con,data):
        trial,sched=current(data)
        if trial is None: return jsonify(done=True)
        token=ensure_token(data)
        practice=trial['condition_id']=='PRACTICE'
        experimental=[r for r in sched if r['condition_id']!='PRACTICE']
        block_ids=list(dict.fromkeys(r.get('block_id',r['condition_id']) for r in experimental))
        completed=sum(r['condition_id']!='PRACTICE' for r in sched[:data['cursor']])
        block_id=trial.get('block_id',trial['condition_id'])
        block=0 if practice else block_ids.index(block_id)+1
        task_type=trial.get('task_type','numerosity')
        out=dict(done=False,trial_token=token,practice=practice,block=block,n_blocks=len(block_ids),block_id=block_id,
                 task_type=task_type,adviser_style=condition_agent_style(trial['condition_id'],trial.get('adviser_style')),
                 adviser_name=adviser_name(data,trial),trial_in_block=trial['trial_position'],n_in_block=sum(r.get('block_id',r['condition_id'])==block_id for r in sched),
                 overall=completed+1,completed=completed,overall_total=len(experimental),
                 image=(url_for('stimulus',token=token) if task_type=='numerosity' else None),
                 scenario_text=trial.get('scenario_text'),question_text=trial.get('question_text'),
                 rationale_required=bool(trial.get('rationale_required', True)),
                 rationale_prompt=trial.get('rationale_prompt') or ('What mainly led you to that estimate?' if task_type=='numerosity' else 'What mainly influenced your judgment?'),
                 scale_min=trial.get('scale_min',1),scale_max=trial.get('scale_max',design.MAX_ESTIMATE),
                 break_due=not practice and trial['trial_position']==1 and block>1,
                 voice_tone='persuasive' if trial['condition_id'] in {'P','A'} else 'neutral',
                 voice_slot=adviser_voice_slot(data,trial['condition_id']),
                 ratings_due=ratings_due(trial),rating_window=RATING_EVERY,pending=None,researcher=None)
        if data['pending']:
            out['pending']={k:data['pending'].get(k) for k in ['initial','rationale','rationale_rt_ms','text','rt_initial','latency_ms','advice']}
        if session.get('researcher') and data['config'].get('researcher'):
            out['researcher']=dict(condition=trial['condition_id'],block_id=block_id,task_type=task_type,
                scenario_id=trial.get('scenario_id'),style=condition_agent_style(trial['condition_id'],trial.get('adviser_style')),direction=trial['direction'],
                true_count=trial.get('true_count'),pid=pid,participant_index=data['participant_index'],mode=data['config']['adviser_mode'],
                agent_voice=adviser_voice(data,trial['condition_id']),voice_tone=out['voice_tone'],voice_profile=_voice_profile(trial['condition_id']),
                block_order=block_ids,**(data['pending'].get('diagnostic',{}) if data['pending'] else {}))
        return jsonify(out)


@app.get('/stimulus/<token>')
def stimulus(token):
    pid=require_session();data=store.session_data(pid);trial,_=current(data)
    if not trial or trial.get('task_type','numerosity')!='numerosity' or data.get('pending') or not data.get('token') or not hmac.compare_digest(token,data['token']):abort(404)
    # Generate only this deterministic image if the background cache has not reached it yet.
    path=ensure_stimulus(trial['stimulus_id'],trial['true_count'],trial['variant'])
    return send_file(path,mimetype='image/webp',max_age=0,download_name='dot-field.webp')


def advice_payload(pending,data):
    trial,_=current(data)
    result=dict(adviser_name=adviser_name(data,trial),advice_text=pending['text'],advice_number=pending['advice'],latency_ms=pending['latency_ms'],
                voice_tone='persuasive' if trial['condition_id'] in {'P','A'} else 'neutral',
                voice_slot=adviser_voice_slot(data,trial['condition_id']))
    if session.get('researcher') and data['config'].get('researcher'):
        result['researcher']={**pending['diagnostic'],'agent_voice':adviser_voice(data,trial['condition_id']),'voice_tone':result['voice_tone'],'voice_profile':_voice_profile(trial['condition_id'])}
    return result


def prepared_advice(con,data,trial,initial,rationale=None):
    """Resolve one trial's recommendation and participant-facing adviser note."""
    practice=trial['condition_id']=='PRACTICE'
    style=condition_agent_style(trial['condition_id'], trial.get('adviser_style'))
    task_type=trial.get('task_type','numerosity')
    if practice:
        advice=int(trial.get('advice_number') or (design.clamp_int((initial or 50)*1.05) if task_type=='numerosity' else 40))
    elif task_type=='social':
        advice=int(trial['advice_number'])
    else:
        advice=design.advice_number(trial['condition_id'],trial['true_count'],initial,trial['direction'])
    protocol=data['config'].get('adviser_protocol')
    cached=data.get('prefetched')
    # Adaptive messages need the current rationale only on rationale-designated trials.
    rationale_required=bool(trial.get('rationale_required', True))
    cache_allowed=(style!='adaptive' or not rationale_required)
    if cache_allowed and cached and cached.get('token')==data.get('token') and cached.get('advice')==advice:
        return advice,cached['message'],dict(cached['diagnostic'],prefetched=True,advice=advice,initial_context_available=False,
                                             rationale_context_available=False)
    rows=[] if practice else store.block_history(data['_pid'],trial['condition_id'],con,task_type=task_type)
    # In the social task the adaptive manipulation is current-rationale responsiveness,
    # not claims about prior response history. Numerosity retains the history logic.
    history=rows if (style=='adaptive' and task_type!='social') else []
    profile=data['config'].get('model_profile') or adviser.model_profiles()['server']
    key=f"{data['participant_index']}|{trial['condition_id']}|{trial['trial_position']}"
    t=time.perf_counter()
    if practice:
        msg=adviser.control_message(advice,key)
        msg.update(live_model=False,history_route='practice',prompt_version='practice-control')
    elif task_type=='social':
        # Social arguments are researcher-specified. The model is not allowed to
        # invent an explanation for an ambiguous scenario. P and A use the same
        # scenario-grounded argument; A only adds a literal link to the current
        # participant rationale on the two designated rationale trials.
        text=social_design.advice_message(trial['condition_id'],advice,trial.get('argument_text',''),rationale if rationale_required else '')
        msg=dict(text=text,source='grounded_social_argument_bank:'+trial['condition_id'],attempts=0,
                 word_count=adviser.words(text),validation='researcher_specified_argument_bank',
                 history_route='not_used_social',live_model=False,prompt_version='grounded-social-v2',
                 attempt_log=[],model_response_received=False,review_required=False,review_reasons=[],
                 grounding_record_check='researcher_argument_bank',adaptation_check=('literal_current_rationale_link' if trial['condition_id']=='A' and rationale else 'not_applicable'),
                 persuasion_check='standardized_grounded_argument' if trial['condition_id'] in {'P','A'} else 'neutral_control',
                 generation_status='grounded_social_argument_bank')
    elif data['config']['adviser_mode']=='offline':
        # Offline is a mechanical rehearsal. It deliberately does not pretend to validate LLM responsiveness.
        if style=='neutral': text=f'My estimate for this round is {advice}, simply offered as another judgment to consider.'
        elif style=='static': text=f'Please give {advice} serious weight when choosing your final judgment for this round.'
        elif rationale:
            text=f'You based your judgment on that reason; please give {advice} more weight before deciding.'
        else: text=f'Please give {advice} more weight when choosing your final judgment for this round.'
        msg=dict(text=text,source='offline_rehearsal:'+style,attempts=0,word_count=adviser.words(text),validation='offline_rehearsal',
                 history_route='offline',live_model=False,prompt_version='offline-rationale-social-v1',attempt_log=[])
    else:
        scenario={'text':trial.get('scenario_text'),'question':trial.get('question_text')} if task_type=='social' else None
        with adviser.use_model_profile(profile):
            msg=adviser_flexible.generate_message(style=style,initial=None,advice=advice,history=history,
                previous_messages=[r['advice_text'] for r in rows if r.get('advice_text')],key=key,
                task_type=task_type,current_rationale=(rationale if style=='adaptive' else None),scenario=scenario)
    diagnostic=dict(history_rows=len(history),expected_history_rows=trial['trial_position']-1 if (style=='adaptive' and task_type!='social') else 0,
        history_positions=[r['trial_position'] for r in history],displayed_message=msg['text'],source=msg['source'],attempts=msg['attempts'],
        validation=msg['validation'],word_count=msg['word_count'],live_model=msg.get('live_model',False),
        history_route=msg.get('history_route'),generation_ms=round((time.perf_counter()-t)*1000),
        history_check=msg.get('history_check'),prompt_version=msg.get('prompt_version'),prompt_sha256=msg.get('prompt_sha256'),
        attempt_log=msg.get('attempt_log',[]),fallback=msg['source'].startswith('fallback:'),adviser_protocol=protocol or 'legacy_v7',
        initial_context_available=False,rationale_context_available=bool(style=='adaptive' and rationale_required and rationale),
        task_type=task_type,block_id=trial.get('block_id'),scenario_id=trial.get('scenario_id'),
        participant_rationale=(rationale if style=='adaptive' and rationale_required else None),prefetched=False,
        rationale_required=rationale_required,argument_text=trial.get('argument_text'),argument_direction=trial.get('argument_direction'),
        provider=msg.get('provider',('researcher_argument_bank' if task_type=='social' else profile['provider'])),
        model=msg.get('model',('scripted_grounded_social' if task_type=='social' else profile['model'])),
        reasoning=msg.get('reasoning',('none' if task_type=='social' else profile['reasoning'])),request_timeout_s=(0 if task_type=='social' else profile['timeout']),advice=advice)
    diagnostic.update(model_response_received=msg.get('model_response_received',False),
        trust_context_in_prompt=msg.get('trust_context_in_prompt',False),
        feeling_context_in_prompt=msg.get('feeling_context_in_prompt',False),
        trust_check=msg.get('trust_check','not_checked_offline' if data['config']['adviser_mode']=='offline' else 'not_applicable'))
    for field in ('trust_latest_rating','trust_latest_trial','trust_previous_rating','trust_change','trust_age_trials',
                  'feeling_latest_rating','feeling_latest_trial','feeling_previous_rating','feeling_change','feeling_age_trials',
                  'adaptive_focus','adaptive_strategy','adaptation_check','feeling_check','repetition_check','repetition_similarity',
                  'review_required','review_reasons','rating_strategies','grounding_record_check','model_basis',
                  'generation_status','rating_influence_status','persuasion_check','max_attempts','total_budget_s',
                  'retry_policy_version','retry_count','recovered_after_retry','stop_reason','budget_overrun','target_word_range',
                  'word_tolerance','word_count_check','direction_check','adaptive_summary','adaptive_summary_in_prompt',
                  'first_draft','displayed_draft','length_retry_used','length_retry_success'):
        diagnostic[field]=msg.get(field)
    return advice,msg,diagnostic


def _voice_profile(condition_id: str) -> str:
    if condition_id in {'P','A'}:
        return 'same_voice_persuasive_high_contrast'
    return 'same_voice_neutral_restrained'


def _voice_instructions(condition_id: str) -> str:
    """Keep one speaker identity; manipulate only delivery tone."""
    if condition_id in {'P','A'}:
        return (
            'Keep exactly the same speaker identity and the same moderate speaking pace as every other trial. '
            'Use a clearly persuasive tone: noticeably warmer, more confident, socially engaged, encouraging, and slightly insistent. '
            'Use stronger conviction and clear vocal emphasis on the recommendation and action words. '
            'Make the persuasive intent easy to hear, but stay natural and one-to-one, never theatrical or like an advertisement.'
        )
    return (
        'Keep exactly the same speaker identity and the same moderate speaking pace as every other trial. '
        'Use a clearly neutral tone: calm, restrained, matter-of-fact, and low in warmth and motivational energy. '
        'Use only ordinary emphasis needed for clarity. Do not sound encouraging, persuasive, excited, or personally invested.'
    )

def _voice_speed(condition_id: str) -> float:
    # Keep synthesis speed identical across every condition. Vocal manipulation is
    # carried only by the acting/prosody instructions, not speaking rate.
    return 1.0


def _synth_openai(spoken: str, condition_id: str):
    api_key=os.getenv('OPENAI_API_KEY','').strip()
    if not api_key:
        return None
    payload=json.dumps(dict(model=TTS_MODEL,voice=TTS_VOICE,input=spoken,
        instructions=_voice_instructions(condition_id),response_format=TTS_RESPONSE_FORMAT,speed=_voice_speed(condition_id))).encode('utf-8')
    accept='audio/wav' if TTS_RESPONSE_FORMAT=='wav' else 'audio/mpeg'
    req=urllib.request.Request('https://api.openai.com/v1/audio/speech',data=payload,method='POST',headers={
        'Authorization':f'Bearer {api_key}','Content-Type':'application/json','Accept':accept})
    with urllib.request.urlopen(req,timeout=TTS_TIMEOUT_S) as response:
        mimetype='audio/wav' if TTS_RESPONSE_FORMAT=='wav' else 'audio/mpeg'
        return response.read(), mimetype


_gemini_tts_client = None

def _synth_gemini(spoken: str, condition_id: str):
    global _gemini_tts_client
    key=os.getenv('GEMINI_API_KEY','').strip()
    if not key:
        return None
    from google import genai
    if _gemini_tts_client is None:
        _gemini_tts_client=genai.Client(api_key=key)
    interaction=_gemini_tts_client.interactions.create(
        model=GEMINI_TTS_MODEL,
        input=[{
            'type':'user_input',
            'content':[{
                'type':'text',
                'text':spoken,
                'annotations':[{'type':'speech_metadata','style':_voice_instructions(condition_id)}],
            }],
        }],
        response_format={'type':'audio'},
        generation_config={'speech_config':[{'voice':GEMINI_TTS_VOICE}]},
    )
    audio_block=getattr(interaction,'output_audio',None)
    data=getattr(audio_block,'data',None) if audio_block is not None else None
    if not data:
        return None
    return base64.b64decode(data), 'audio/wav'


@app.post('/api/voice')
def api_voice():
    pid=require_session();body=request.get_json(silent=True) or {}
    backend=natural_voice_backend()
    if backend == 'unavailable':
        return jsonify(error='The configured natural voice is not available on this server.'),503
    if backend == 'browser':
        return jsonify(error='Server-side natural voice is not configured.'),503
    with store.session_transaction(pid) as (_con,data):
        trial,_=current(data)
        if trial is None or body.get('trial_token')!=data.get('token'):
            return jsonify(error='Voice is not available for this trial.'),409
        source=data.get('pending')
        prefetched=data.get('prefetched')
        if source is None and prefetched and prefetched.get('token')==data.get('token'):
            source={'text':prefetched['message']['text'],'advice':prefetched.get('advice')}
        if source is None:
            return jsonify(error='Voice is not available for this trial.'),409
        spoken=source['text']
        condition_id=trial['condition_id']

    # Never switch providers on failure: this prevents speaker identity from
    # changing between trials. Gemini gets one immediate retry; after that the
    # trial remains text-only rather than substituting another speaker.
    if backend == 'gemini':
        for attempt in (1, 2):
            try:
                result=_synth_gemini(spoken,condition_id)
                if result:
                    audio,mimetype=result
                    return Response(audio,mimetype=mimetype,headers={
                        'X-BEAST-Voice-Backend':'gemini-3.8-flash-tts',
                        'X-BEAST-Voice':GEMINI_TTS_VOICE,
                        'X-BEAST-Voice-Profile':_voice_profile(condition_id),
                        'X-BEAST-Voice-Attempt':str(attempt),
                        'X-BEAST-Audio-Format':'wav'})
            except Exception as exc:
                app.logger.warning('Gemini voice generation failed on attempt %s: %s',attempt,exc)
                if attempt == 1:
                    time.sleep(0.15)
        return jsonify(error='Gemini voice could not be generated for this trial.'),503

    if backend == 'openai':
        try:
            result=_synth_openai(spoken,condition_id)
            if result:
                audio,mimetype=result
                return Response(audio,mimetype=mimetype,headers={
                    'X-BEAST-Voice-Backend':'openai-tts',
                    'X-BEAST-Voice':TTS_VOICE,
                    'X-BEAST-Voice-Profile':_voice_profile(condition_id),
                    'X-BEAST-Voice-Attempt':'1',
                    'X-BEAST-Audio-Format':TTS_RESPONSE_FORMAT})
        except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
            app.logger.warning('OpenAI voice generation failed: %s',exc)
        return jsonify(error='OpenAI voice could not be generated for this trial.'),503

    return jsonify(error='Natural voice could not be generated.'),503


@app.post('/api/prefetch')
def api_prefetch():
    """Prefetch when the current trial does not require participant-specific rationale input."""
    pid=require_session();body=request.get_json(silent=True) or {}
    with store.session_transaction(pid) as (con,data):
        trial,_=current(data)
        if trial is None or not data.get('token') or body.get('trial_token')!=data.get('token'):
            return jsonify(error='This trial is no longer current.'),409
        style=condition_agent_style(trial['condition_id'],trial.get('adviser_style'))
        if data.get('pending') or trial['condition_id']=='PRACTICE' or (style=='adaptive' and bool(trial.get('rationale_required', True))):
            return jsonify(ok=True,prefetched=False)
        existing=data.get('prefetched')
        if existing and existing.get('token')==data.get('token'):
            msg=existing['message']; diagnostic=existing['diagnostic']
            result=dict(adviser_name=adviser_name(data,trial),advice_text=msg['text'],
                        advice_number=existing.get('advice'),latency_ms=diagnostic.get('generation_ms',0),
                        voice_tone='persuasive' if trial['condition_id'] in {'P','A'} else 'neutral',
                        voice_slot=adviser_voice_slot(data,trial['condition_id']))
            if session.get('researcher') and data['config'].get('researcher'):
                result['researcher']={**diagnostic,'agent_voice':adviser_voice(data,trial['condition_id']),'voice_tone':result['voice_tone'],'voice_profile':_voice_profile(trial['condition_id'])}
            return jsonify(ok=True,prefetched=True,advice=result)
        data['_pid']=pid
        advice,msg,diagnostic=prepared_advice(con,data,trial,None,None)
        data['prefetched']=dict(token=data['token'],advice=advice,message=msg,diagnostic=diagnostic)
        result=dict(adviser_name=adviser_name(data,trial),advice_text=msg['text'],advice_number=advice,
                    latency_ms=diagnostic.get('generation_ms',0),
                    voice_tone='persuasive' if trial['condition_id'] in {'P','A'} else 'neutral',
                    voice_slot=adviser_voice_slot(data,trial['condition_id']))
        if session.get('researcher') and data['config'].get('researcher'):
            result['researcher']={**diagnostic,'agent_voice':adviser_voice(data,trial['condition_id']),'voice_tone':result['voice_tone'],'voice_profile':_voice_profile(trial['condition_id'])}
        return jsonify(ok=True,prefetched=True,advice=result)


@app.post('/api/initial')
def api_initial():
    pid=require_session();body=request.get_json(silent=True) or {}
    with store.session_transaction(pid) as (con,data):
        trial,_=current(data)
        if trial is None or body.get('trial_token')!=data.get('token'):
            return jsonify(error='This trial is no longer current. Reload to resume.'),409
        try:
            initial=integer(body.get('estimate'),int(trial.get('scale_min',1)),int(trial.get('scale_max',design.MAX_ESTIMATE)))
            rt=milliseconds(body.get('rt_ms'))
            rationale_rt=milliseconds(body.get('rationale_rt_ms'))
        except ValueError as e:return jsonify(error=str(e)),400
        rationale_required=bool(trial.get('rationale_required', True))
        rationale=str(body.get('rationale') or '').strip()
        if rationale_required and not rationale:
            return jsonify(error='Please give a short reason for your first judgment.'),400
        if not rationale_required:
            rationale=''
            rationale_rt=0
        max_rationale_chars=100 if trial.get('task_type')=='social' else 240
        if len(rationale)>max_rationale_chars:
            return jsonify(error=f'Please keep your reason to {max_rationale_chars} characters or fewer.'),400
        if data['pending']:
            if data['pending']['initial']!=initial or data['pending'].get('rationale')!=rationale:
                return jsonify(error='An initial answer is already recorded for this trial.'),409
            return jsonify(advice_payload(data['pending'],data))
        data['_pid']=pid
        advice,msg,diagnostic=prepared_advice(con,data,trial,initial,rationale)
        elapsed=diagnostic['generation_ms']
        pending=dict(initial=initial,rationale=rationale,rationale_rt_ms=rationale_rt,advice=advice,text=msg['text'],source=msg['source'],attempts=msg['attempts'],
            word_count=msg['word_count'],rt_initial=rt,latency_ms=elapsed,diagnostic=diagnostic,
            initial_telemetry=body.get('telemetry') if isinstance(body.get('telemetry'),dict) else {})
        data['pending']=pending
        return jsonify(advice_payload(pending,data))


TIMING_FIELDS=['fixation_ms','stimulus_load_ms','stimulus_visible_ms','initial_active_ms','initial_wall_ms',
    'advice_wait_ms','final_active_ms','final_wall_ms','rating_ms','break_ms','total_wall_ms','total_active_ms',
    'hidden_ms','visibility_interruptions','resumed','viewport_width','viewport_height','device_pixel_ratio',
    'stimulus_render_width','stimulus_render_height','prefetch_request_ms','prefetch_remaining_ms',
    'stimulus_fetch_ms','rationale_ms','advice_preview_ms','advice_preview_wall_ms']


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
    token=body.get('trial_token')
    with store.session_transaction(pid) as (con,data):
        trial,sched=current(data);pending=data.get('pending')
        if trial is None or not pending or token!=data.get('token'):
            if token and token==data.get('last_token'):
                signature={k:body.get(k) for k in ['estimate','trust','feeling']}
                if signature!=data.get('last_payload'):return jsonify(error='This trial was already saved with different responses.'),409
                return jsonify(ok=True,already_saved=True)
            return jsonify(error='No matching trial in progress. Reload to resume.'),409
        try:
            final=integer(body.get('estimate'),int(trial.get('scale_min',1)),int(trial.get('scale_max',design.MAX_ESTIMATE)))
            rt=milliseconds(body.get('rt_ms'));timing=clean_timing(body.get('telemetry'))
            trust=integer(body.get('trust'),1,7) if ratings_due(trial) else None
            feeling=integer(body.get('feeling'),1,7) if ratings_due(trial) and data['config'].get('rating_items','trust_and_feeling')=='trust_and_feeling' else None
        except ValueError as e:return jsonify(error=str(e)),400
        signature={k:body.get(k) for k in ['estimate','trust','feeling']}
        timing={**clean_timing(pending.get('initial_telemetry')),**timing}
        initial,advice=pending['initial'],pending['advice'];truth=trial.get('true_count');practice=trial['condition_id']=='PRACTICE'
        task_type=trial.get('task_type','numerosity')
        if not practice:
            if truth is not None:
                initial_error=design.signed_pct(initial,truth); final_error=design.signed_pct(final,truth); advice_error=design.signed_pct(advice,truth)
            else:
                initial_error=final_error=advice_error=None
            row=dict(trial,pid=pid,participant_index=data['participant_index'],initial_estimate=initial,advice_number=advice,
                advice_text=pending['text'],advice_source=pending['source'],advice_attempts=pending['attempts'],
                advice_word_count=pending['word_count'],final_estimate=final,trust_rating=trust,feeling_rating=feeling,
                initial_error_pct=initial_error,final_error_pct=final_error,advice_error_pct=advice_error,woa=design.woa(initial,final,advice),
                rt_initial_ms=pending['rt_initial'],rt_final_ms=rt,advice_latency_ms=pending['latency_ms'],
                audio_played=bool(body.get('audio_played',False)),modality=data['config'].get('advice_modality','text'))
            store.save_trial(row,con)
            store.save_trial_context(dict(pid=pid,global_trial=trial['global_trial'],task_type=task_type,
                block_id=trial.get('block_id'),scenario_id=trial.get('scenario_id'),scenario_text=trial.get('scenario_text'),
                question_text=trial.get('question_text'),participant_rationale=pending.get('rationale'),
                rationale_rt_ms=pending.get('rationale_rt_ms')),con)
        diagnostic=dict(pending['diagnostic'],**timing,ui_version=APP_VERSION,stimulus_render_version=STIMULUS_RENDER_VERSION,
            adviser_name=adviser_name(data,trial),stimulus_format='webp_lossless' if task_type=='numerosity' else 'text_scenario',
            advice_preview_target_ms=data['config'].get('advice_preview_ms',0),advice_modality=data['config'].get('advice_modality','text'),
            audio_played=bool(body.get('audio_played',False)),rating_items=data['config'].get('rating_items','trust_and_feeling'),
            condition_id=trial['condition_id'],block_id=trial.get('block_id'),task_type=task_type,scenario_id=trial.get('scenario_id'),
            trial_position=trial['trial_position'],global_trial=trial['global_trial'],practice=practice,is_test=data['config']['is_test'],
            rationale_required=bool(trial.get('rationale_required', True)),rationale_collected=bool(pending.get('rationale')),rationale_length=len(pending.get('rationale') or ''),
            adviser_mode=data['config']['adviser_mode'],target_stimulus_ms=STIMULUS_MS if task_type=='numerosity' else 0,
            target_wait_ms=ADVISER_MIN_DELAY_MS,ratings_due=ratings_due(trial),
            timing_complete=all(k in timing for k in ['total_wall_ms','advice_wait_ms','rating_ms']))
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
        delay_ms=ADVISER_MIN_DELAY_MS,rating_every=RATING_EVERY,advice_preview_ms=ADVICE_PREVIEW_MS,advice_modality=ADVICE_MODALITY,natural_voice_available=natural_voice_backend()!='browser',tts_voice=shared_voice_identity(),
        projection=timing_projection(
            wait_s=ADVISER_MIN_DELAY_MS/1000,stimulus_s=STIMULUS_MS/1000,fixation_s=FIXATION_MS/1000,
            rating_every=RATING_EVERY,collect_ratings=COLLECT_RATINGS,advice_preview_s=ADVICE_PREVIEW_MS/1000))


@app.route('/admin')
def admin_downloads():
    return redirect(url_for('researcher'))


@app.get('/api/researcher/status')
def researcher_status():
    require_admin()
    return jsonify(version=APP_VERSION,stimulus_render_version=STIMULUS_RENDER_VERSION,stimulus_format='webp_lossless',
        advice_preview_ms=ADVICE_PREVIEW_MS,advice_modality=ADVICE_MODALITY,voice_backend=natural_voice_backend(),tts_voice=shared_voice_identity(),tts_model=(GEMINI_TTS_MODEL if natural_voice_backend()=='gemini' else TTS_MODEL),voice_pool=list(AGENT_TTS_VOICES[:8]),
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
    return dict(analysis_trials=store.analysis_trial_rows(),trials=store.export_rows(store.trials),trial_contexts=store.export_rows(store.trial_contexts),participants=people,ratings=store.export_rows(store.message_ratings),
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
            stimulus_format='webp_lossless',default_advice_preview_ms=ADVICE_PREVIEW_MS,default_advice_modality=ADVICE_MODALITY,
            study_seed=design.STUDY_SEED,
            adviser_model=adviser.resolved_model(),adviser_provider=adviser.resolved_provider(),study_mode=STUDY_MODE,default_adviser_mode=ADVISER_MODE,
            stimulus_ms=STIMULUS_MS,fixation_ms=FIXATION_MS,minimum_advice_wait_ms=ADVISER_MIN_DELAY_MS,
            rating_every=RATING_EVERY,prefill_final=PREFILL_FINAL,word_range=[adviser.ADVISER_MIN_WORDS,adviser.ADVISER_MAX_WORDS],
            retry_policy_version=adviser.RETRY_POLICY_VERSION,model_profiles=adviser.model_profiles(),
            word_tolerance=adviser.ADVISER_WORD_TOLERANCE,
            conditions=design.CONDITIONS,social_scenarios=len(social_design.SCENARIOS),social_rationales_per_block=2,rationale_max_chars={'social':100,'numerosity':240},limits=['Offline rehearsals do not validate live model behaviour.',
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
