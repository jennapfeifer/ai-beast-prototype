"""
AI-BEAST — human study web app.

Flow: consent -> instructions -> 1 warm-up trial -> 8 rounds x 13 trials
      (checkpoint/break between rounds) -> debrief.

Per trial: image -> initial estimate -> AI number + short note -> number-line final estimate ->
           periodic trust + feeling ratings.

The true count is never shown to the participant. Numerical advice follows NEW25;
static/adaptive wording uses the historical broad-persuasion policy in adviser.py.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import random
import time
import uuid

from flask import (
    Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for,
)

import design
import store
from adviser import resolved_provider, resolved_model, generate_message

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-me")
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
ADVISER_MIN_DELAY_MS = int(os.getenv("ADVISER_MIN_DELAY_MS", "700"))
STIMULUS_MS = int(os.getenv("STIMULUS_MS", "5000"))  # 0 = untimed
COLLECT_RATINGS = os.getenv("COLLECT_RATINGS", "1") not in {"0", "false"}
RATING_EVERY = max(1, int(os.getenv("RATING_EVERY", "2")))
PREFILL_FINAL = os.getenv("PREFILL_FINAL", "0") not in {"0", "false"}
RESEARCHER_MODE = os.getenv("RESEARCHER_MODE", "0") not in {"0", "false"}
SHOW_END_SCORE = os.getenv("SHOW_END_SCORE", "1") not in {"0", "false"}

store.init_db()


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


# --- session helpers --------------------------------------------------------

def full_schedule(participant_index: int):
    """Practice trials plus the participant's 104-trial schedule.

    Researcher mode may filter conditions / shorten blocks for testing. The
    underlying counterbalanced order is not changed; test sessions are flagged.
    """
    sched = design.build_schedule(participant_index)
    only = session.get("only_conditions")
    if only:
        sched = [t for t in sched if t["condition_id"] in only]
    n = session.get("trials_per_block")
    if n:
        sched = [t for t in sched if t["trial_position"] <= n]
    practice = [] if session.get("skip_practice") else design.practice_schedule()
    return practice + sched


def current_trial():
    idx = session.get("cursor", 0)
    sched = full_schedule(session["participant_index"])
    if idx >= len(sched):
        return None, sched
    return sched[idx], sched


def require_session():
    if "pid" not in session:
        abort(403, "No active session. Start from the beginning.")


# --- pages ------------------------------------------------------------------

@app.route("/")
def consent():
    return render_template(
        "consent.html",
        external_id=request.args.get("PROLIFIC_PID", ""),
        # Test-session parameters survive POST /start only in researcher mode.
        researcher_mode=RESEARCHER_MODE,
        conditions=request.args.get("conditions", "") if RESEARCHER_MODE else "",
        trials=request.args.get("trials", "") if RESEARCHER_MODE else "",
        skip_practice=request.args.get("skip_practice", "") if RESEARCHER_MODE else "",
        test_index=request.args.get("test_index", "0") if RESEARCHER_MODE else "0",
        condition_defs=design.CONDITIONS if RESEARCHER_MODE else {},
    )


@app.post("/start")
def start():
    # Parse researcher-only test controls BEFORE assigning the participant index.
    # Test sessions are marked TEST immediately and do not consume production
    # counterbalancing rows.
    picked = []
    trials_per_block = None
    skip_practice = False
    test_index = 0
    is_test = False

    if RESEARCHER_MODE:
        raw = (request.args.get("conditions") or request.form.get("conditions") or "").upper()
        picked = [c.strip() for c in raw.replace(";", ",").split(",") if c.strip() in design.CONDITIONS]
        try:
            n = int(request.args.get("trials") or request.form.get("trials") or 0)
            if 0 < n <= len(design.TRUE_COUNTS):
                trials_per_block = n
        except ValueError:
            pass
        skip_practice = _truthy(request.args.get("skip_practice") or request.form.get("skip_practice"))
        try:
            test_index = int(request.args.get("test_index") or request.form.get("test_index") or 0) % 8
        except ValueError:
            test_index = 0
        is_test = bool(picked or trials_per_block or skip_practice or request.form.get("researcher_test"))

    participant_index = test_index if is_test else store.next_participant_index()
    pid = uuid.uuid4().hex[:12]
    order = design.balanced_condition_order(participant_index)

    store.create_participant(
        pid=pid,
        participant_index=participant_index,
        external_id=request.form.get("external_id") or None,
        modality="text",
        condition_order=order,
        notes="TEST" if is_test else None,
    )
    session.clear()

    if is_test:
        if picked:
            session["only_conditions"] = picked
        if trials_per_block and trials_per_block < len(design.TRUE_COUNTS):
            session["trials_per_block"] = trials_per_block
        if skip_practice:
            session["skip_practice"] = True
        session["test_index"] = test_index

    session["pid"] = pid
    session["participant_index"] = participant_index
    session["cursor"] = 0
    session["pending"] = None
    return redirect(url_for("instructions"))


@app.route("/instructions")
def instructions():
    require_session()
    return render_template("instructions.html", skip_practice=bool(session.get("skip_practice")))


@app.route("/task")
def task():
    require_session()
    return render_template(
        "task.html",
        min_delay=ADVISER_MIN_DELAY_MS,
        stimulus_ms=STIMULUS_MS,
        collect_ratings=int(COLLECT_RATINGS),
        rating_every=RATING_EVERY,
        prefill_final=int(PREFILL_FINAL),
        researcher_mode=int(RESEARCHER_MODE),
        n_practice=len(design.PRACTICE_COUNTS),
        n_trials=len(design.TRUE_COUNTS) * len(design.CONDITIONS),
    )


@app.route("/debrief")
def debrief():
    pid = session.get("pid")
    summary = None
    if pid:
        store.update_participant(pid, debriefed=True)
        if SHOW_END_SCORE:
            summary = store.participant_summary(pid)
    return render_template("debrief.html", summary=summary, show_end_score=SHOW_END_SCORE)


# --- trial API --------------------------------------------------------------

@app.get("/api/state")
def api_state():
    require_session()
    trial, sched = current_trial()
    if trial is None:
        store.update_participant(
            session["pid"],
            finished_at=__import__("datetime").datetime.utcnow(),
        )
        return jsonify({"done": True})

    n_practice = 0 if session.get("skip_practice") else len(design.PRACTICE_COUNTS)
    idx = session["cursor"]
    is_practice = trial["condition_id"] == "PRACTICE"

    # Display round numbers follow the actually included blocks. In a full study
    # this is 1..8; in researcher mode a single selected condition displays 1/1.
    included_conditions = []
    for x in sched:
        cid = x["condition_id"]
        if cid != "PRACTICE" and cid not in included_conditions:
            included_conditions.append(cid)
    display_block = (included_conditions.index(trial["condition_id"]) + 1) if not is_practice else 0
    n_blocks_display = len(included_conditions)
    n_in_block_display = (
        sum(1 for x in sched if x["condition_id"] == trial["condition_id"])
        if not is_practice else len(design.PRACTICE_COUNTS)
    )
    show_break = (not is_practice) and trial["trial_position"] == 1 and display_block > 1
    ratings_due = bool(
        COLLECT_RATINGS and (not is_practice) and trial["trial_position"] % RATING_EVERY == 0
    )

    return jsonify({
        "done": False,
        "practice": is_practice,
        "break_due": show_break,
        "ratings_due": ratings_due,
        "block": display_block,
        "n_blocks": n_blocks_display,
        "trial_in_block": trial["trial_position"],
        "n_in_block": n_in_block_display,
        "overall": max(0, idx - n_practice) + 1,
        "overall_total": len(sched) - n_practice,
        "image": url_for("static", filename=f"stimuli/{trial['stimulus_id']}.png"),
        "min_delay_ms": ADVISER_MIN_DELAY_MS,
        "stimulus_ms": STIMULUS_MS,
        "researcher": ({
            "condition": trial["condition_id"],
            "condition_label": trial["condition_label"],
            "style": trial["adviser_style"],
            "direction": trial["direction"],
            "true_count": trial["true_count"],
            "stimulus_id": trial["stimulus_id"],
            "variant": trial["variant"],
            "pid": session["pid"],
            "participant_index": session["participant_index"],
            "condition_order": design.balanced_condition_order(session["participant_index"]),
            "original_condition_order_position": trial["condition_order_position"],
            "filter": session.get("only_conditions"),
            "test_index": session.get("test_index"),
        } if RESEARCHER_MODE else None),
    })


@app.post("/api/initial")
def api_initial():
    require_session()
    trial, _ = current_trial()
    if trial is None:
        return jsonify({"done": True}), 400

    data = request.get_json(force=True)
    try:
        initial = int(round(float(data["estimate"])))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Enter a whole number."}), 400
    if not (1 <= initial <= design.MAX_ESTIMATE):
        return jsonify({"error": f"Enter a number between 1 and {design.MAX_ESTIMATE}."}), 400

    rt_initial = int(data.get("rt_ms") or 0)
    truth = trial["true_count"]
    style = trial["adviser_style"]
    is_practice = trial["condition_id"] == "PRACTICE"

    if is_practice:
        advice = design.clamp_int(initial * random.uniform(0.9, 1.1))
    else:
        # NEW25 numerical architecture: truth-relative fixed schedules in C3-C8.
        advice = design.advice_number(trial["condition_id"], truth, initial)

    # Completed rows in this block are used in two different ways:
    # - adaptive: ALL details are exposed to the adviser model as persuasion history;
    # - neutral/static: prior note text is used only by the server-side
    #   repetition validator and is never shown to the adviser model.
    block_rows = [] if is_practice else store.block_history(session["pid"], trial["condition_id"])
    history = block_rows if style == "adaptive" else []
    previous_messages = [r.get("advice_text") for r in block_rows if r.get("advice_text")]

    # Practice uses a deterministic non-persuasive message and does not spend an API call.
    generation_style = "fixed" if is_practice else style
    t0 = time.time()
    msg = generate_message(
        style=generation_style,
        initial=initial,
        advice=advice,
        history=history,
        previous_messages=previous_messages,
        key=f"{session['participant_index']}|{trial['condition_id']}|{trial['trial_position']}",
    )
    latency_ms = int((time.time() - t0) * 1000)

    session["pending"] = {
        "initial": initial,
        "advice": advice,
        "text": msg["text"],
        "source": msg["source"],
        "attempts": msg["attempts"],
        "word_count": msg["word_count"],
        "rt_initial": rt_initial,
        "latency_ms": latency_ms,
    }
    session.modified = True

    return jsonify({
        "advice_text": msg["text"],
        "advice_number": advice,
        "latency_ms": latency_ms,
        "researcher": ({
            "initial": initial,
            "advice": advice,
            "true_count": truth,
            "advice_error_pct": round(design.signed_pct(advice, truth), 1),
            "initial_error_pct": round(design.signed_pct(initial, truth), 1),
            "source": msg["source"],
            "attempts": msg["attempts"],
            "word_count": msg["word_count"],
            "validation": msg.get("validation"),
            "history_used": len(history),
            "prior_messages_checked": len(previous_messages),
        } if RESEARCHER_MODE else None),
    })


@app.post("/api/final")
def api_final():
    require_session()
    trial, _ = current_trial()
    pending = session.get("pending")
    if trial is None or not pending:
        return jsonify({"error": "No trial in progress."}), 400

    data = request.get_json(force=True)
    try:
        final = int(round(float(data["estimate"])))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Enter a whole number."}), 400
    if not (1 <= final <= design.MAX_ESTIMATE):
        return jsonify({"error": f"Enter a number between 1 and {design.MAX_ESTIMATE}."}), 400

    trust = data.get("trust")
    feeling = data.get("feeling")
    trust = int(trust) if trust not in (None, "") else None
    feeling = int(feeling) if feeling not in (None, "") else None

    if trial["condition_id"] != "PRACTICE":
        truth = trial["true_count"]
        initial, advice = pending["initial"], pending["advice"]
        store.save_trial({
            "pid": session["pid"],
            "participant_index": session["participant_index"],
            "global_trial": trial["global_trial"],
            "condition_id": trial["condition_id"],
            "condition_label": trial["condition_label"],
            "adviser_style": trial["adviser_style"],
            "direction": trial["direction"],
            "condition_order_position": trial["condition_order_position"],
            "trial_position": trial["trial_position"],
            "stimulus_id": trial["stimulus_id"],
            "true_count": truth,
            "variant": trial["variant"],
            "initial_estimate": initial,
            "advice_number": advice,
            "advice_text": pending["text"],
            "advice_source": pending["source"],
            "advice_attempts": pending["attempts"],
            "advice_word_count": pending["word_count"],
            "final_estimate": final,
            "trust_rating": trust,
            "feeling_rating": feeling,
            "initial_error_pct": design.signed_pct(initial, truth),
            "final_error_pct": design.signed_pct(final, truth),
            "advice_error_pct": design.signed_pct(advice, truth),
            "woa": design.woa(initial, final, advice),
            "rt_initial_ms": pending["rt_initial"],
            "rt_final_ms": int(data.get("rt_ms") or 0),
            "advice_latency_ms": pending["latency_ms"],
            # Legacy schema fields retained for backwards-compatible exports.
            "audio_played": False,
            "modality": "text",
        })

    session["cursor"] = session.get("cursor", 0) + 1
    session["pending"] = None
    session.modified = True
    return jsonify({"ok": True})


@app.post("/api/demographics")
def api_demographics():
    require_session()
    d = request.get_json(force=True)
    age = d.get("age")
    store.update_participant(
        session["pid"],
        age=int(age) if str(age).isdigit() else None,
        gender=(d.get("gender") or None),
    )
    return jsonify({"ok": True})


# --- blind message rating ---------------------------------------------------

@app.route("/rate")
def rate():
    if not COLLECT_RATINGS:
        abort(404)
    rater = request.args.get("rater") or uuid.uuid4().hex[:8]
    items = store.messages_for_rating(rater, limit=40)
    return render_template("rate.html", rater=rater, items=items)


@app.post("/api/rate")
def api_rate():
    d = request.get_json(force=True)
    store.save_rating({
        "rater_id": d["rater_id"],
        "trial_id": int(d["trial_id"]),
        "personalization": int(d["personalization"]),
        "warmth": int(d["warmth"]),
        "valence": int(d["valence"]),
        "directiveness": int(d["directiveness"]),
        "convincingness": int(d["convincingness"]),
    })
    return jsonify({"ok": True})


# --- export -----------------------------------------------------------------

def _csv_text(rows):
    if not rows:
        return ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _csv_response(rows, name):
    return Response(
        _csv_text(rows), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}"},
    )


def _admin_authorized():
    return bool(ADMIN_TOKEN and request.args.get("token") == ADMIN_TOKEN)


@app.get("/admin")
def admin_downloads():
    if not _admin_authorized():
        abort(403)
    token = request.args.get("token")
    # Small built-in page: avoids another template just for researcher downloads.
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>AI-BEAST downloads</title>
    <style>body{{font-family:system-ui;max-width:720px;margin:3rem auto;padding:0 1rem;line-height:1.5}}
    a{{display:inline-block;margin:.35rem .5rem .35rem 0;padding:.6rem .9rem;border:1px solid #ccc;border-radius:6px;text-decoration:none;color:#111}}</style>
    </head><body><h1>AI-BEAST data downloads</h1>
    <p><a href='/admin/export/all.zip?token={token}'>Download everything (.zip)</a></p>
    <p><a href='/admin/export/trials.csv?token={token}'>Trial-level results</a>
    <a href='/admin/export/participants.csv?token={token}'>Participant table</a>
    <a href='/admin/export/ratings.csv?token={token}'>Blind message ratings</a></p>
    <p><small>TEST sessions are marked in participants.csv (notes=TEST). Exclude those from the real analysis.</small></p>
    </body></html>"""


@app.get("/admin/export/all.zip")
def export_all_zip():
    if not _admin_authorized():
        abort(403)
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("trials.csv", _csv_text(store.export_rows(store.trials)))
        z.writestr("participants.csv", _csv_text(store.export_rows(store.participants)))
        z.writestr("ratings.csv", _csv_text(store.export_rows(store.message_ratings)))
    mem.seek(0)
    return send_file(mem, mimetype="application/zip", as_attachment=True, download_name="ai_beast_results.zip")


@app.get("/admin/export/<what>.csv")
def export(what):
    if not _admin_authorized():
        abort(403)
    table = {
        "trials": store.trials,
        "participants": store.participants,
        "ratings": store.message_ratings,
    }.get(what)
    if table is None:
        abort(404)
    return _csv_response(store.export_rows(table), f"{what}.csv")


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "adviser_provider": resolved_provider(), "adviser_model": resolved_model(), "delivery": "text-only", "rating_every": RATING_EVERY})


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))
