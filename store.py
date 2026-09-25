"""
Storage. SQLite by default; set DATABASE_URL to a Postgres URL on Render.

WARNING: Render's free web-service filesystem is ephemeral. A SQLite file will
be wiped on every deploy and on instance restart. Use a Postgres instance (or a
paid persistent disk) for any real data collection.
"""
from __future__ import annotations

import os
import json
import datetime as dt
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, Float, Text,
    DateTime, Boolean, select, func, insert, update,
)

DB_URL = os.getenv("DATABASE_URL", "sqlite:///beast.db")
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
meta = MetaData()

participants = Table(
    "participants", meta,
    Column("pid", String(64), primary_key=True),
    Column("participant_index", Integer, nullable=False),
    Column("external_id", String(128)),
    Column("modality", String(16)),
    Column("condition_order", Text),
    Column("consented", Boolean, default=False),
    Column("age", Integer),
    Column("gender", String(32)),
    Column("started_at", DateTime),
    Column("finished_at", DateTime),
    Column("debriefed", Boolean, default=False),
    Column("notes", Text),
)

trials = Table(
    "trials", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("pid", String(64), index=True),
    Column("participant_index", Integer),
    Column("global_trial", Integer),
    Column("condition_id", String(16)),
    Column("condition_label", String(32)),
    Column("adviser_style", String(16)),
    Column("direction", String(16)),
    Column("condition_order_position", Integer),
    Column("trial_position", Integer),
    Column("stimulus_id", String(32)),
    Column("true_count", Integer),
    Column("variant", Integer),
    Column("initial_estimate", Integer),
    Column("advice_number", Integer),
    Column("advice_text", Text),
    Column("advice_source", String(32)),
    Column("advice_attempts", Integer),
    Column("advice_word_count", Integer),
    Column("final_estimate", Integer),
    Column("trust_rating", Integer),
    Column("feeling_rating", Integer),
    Column("initial_error_pct", Float),
    Column("final_error_pct", Float),
    Column("advice_error_pct", Float),
    Column("woa", Float),
    Column("rt_initial_ms", Integer),
    Column("rt_final_ms", Integer),
    Column("advice_latency_ms", Integer),
    Column("audio_played", Boolean),
    Column("modality", String(16)),
    Column("created_at", DateTime),
)

message_ratings = Table(
    "message_ratings", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("rater_id", String(64), index=True),
    Column("trial_id", Integer, index=True),
    Column("personalization", Integer),
    Column("warmth", Integer),
    Column("valence", Integer),
    Column("directiveness", Integer),
    Column("convincingness", Integer),
    Column("created_at", DateTime),
)

def init_db() -> None:
    meta.create_all(engine)

def next_participant_index() -> int:
    with engine.begin() as con:
        n = con.execute(
            select(func.count()).select_from(participants).where(participants.c.notes.is_(None))
        ).scalar_one()
    return int(n)

def create_participant(pid: str, participant_index: int, external_id: Optional[str],
                       modality: str, condition_order: List[str], notes: Optional[str] = None) -> None:
    with engine.begin() as con:
        con.execute(insert(participants).values(
            pid=pid, participant_index=participant_index, external_id=external_id,
            modality=modality, condition_order=json.dumps(condition_order),
            consented=True, started_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None), notes=notes,
        ))

def update_participant(pid: str, **fields: Any) -> None:
    with engine.begin() as con:
        con.execute(update(participants).where(participants.c.pid == pid).values(**fields))

def save_trial(row: Dict[str, Any], connection=None) -> int:
    row = dict(row)
    row["created_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    allowed = {c.name for c in trials.columns}
    row = {k: v for k, v in row.items() if k in allowed}
    if connection is not None:
        res = connection.execute(insert(trials).values(**row))
    else:
        with engine.begin() as con:
            res = con.execute(insert(trials).values(**row))
    return int(res.inserted_primary_key[0])

def block_history(pid: str, condition_id: str, connection=None) -> List[Dict[str, Any]]:
    def read(con):
        return con.execute(
            select(trials.c.trial_position, trials.c.initial_estimate, trials.c.advice_number,
                   trials.c.advice_text, trials.c.final_estimate,
                   trials.c.trust_rating, trials.c.feeling_rating)
            .where(trials.c.pid == pid, trials.c.condition_id == condition_id)
            .order_by(trials.c.trial_position)
        ).mappings().all()
    if connection is not None:
        rows = read(connection)
    else:
        with engine.begin() as con:
            rows = read(con)
    return [dict(r) for r in rows]

def export_rows(table) -> List[Dict[str, Any]]:
    with engine.begin() as con:
        rows = con.execute(select(table)).mappings().all()
    return [dict(r) for r in rows]

def messages_for_rating(rater_id: str, limit: int = 40) -> List[Dict[str, Any]]:
    done = select(message_ratings.c.trial_id).where(message_ratings.c.rater_id == rater_id)
    with engine.begin() as con:
        rows = con.execute(
            select(trials.c.id, trials.c.advice_text)
            .where(trials.c.advice_text.isnot(None), trials.c.id.notin_(done))
            .order_by(func.random() if DB_URL.startswith("sqlite") else func.random())
            .limit(limit)
        ).mappings().all()
    return [dict(r) for r in rows]

def save_rating(row: Dict[str, Any]) -> None:
    row = dict(row)
    row["created_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    with engine.begin() as con:
        con.execute(insert(message_ratings).values(**row))

runtime_sessions = Table(
    "runtime_sessions", meta, Column("pid", String(64), primary_key=True),
    Column("payload", Text, nullable=False), Column("updated_at", DateTime),
)
trial_diagnostics = Table(
    "trial_diagnostics", meta, Column("id", Integer, primary_key=True),
    Column("pid", String(64), index=True), Column("global_trial", Integer),
    Column("payload", Text, nullable=False), Column("created_at", DateTime),
)
study_counters = Table(
    "study_counters", meta, Column("name", String(32), primary_key=True),
    Column("value", Integer, nullable=False),
)

@contextmanager
def write_transaction():
    with engine.connect() as con:
        if engine.dialect.name == "sqlite":
            con.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            con.begin()
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise

def create_session(pid, config, external_id=None):
    with write_transaction() as con:
        if config["is_test"]:
            index = config.get("test_index", 0)
        else:
            existing = con.execute(select(func.max(participants.c.participant_index)).where(participants.c.notes.is_(None))).scalar()
            start = (existing + 1) if existing is not None else 0
            if engine.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as upsert
            else:
                from sqlalchemy.dialects.sqlite import insert as upsert
            con.execute(upsert(study_counters).values(name="production", value=start).on_conflict_do_nothing(index_elements=["name"]))
            index = con.execute(select(study_counters.c.value).where(study_counters.c.name == "production").with_for_update()).scalar_one()
            con.execute(update(study_counters).where(study_counters.c.name == "production").values(value=index + 1))
        import design
        con.execute(insert(participants).values(pid=pid, participant_index=index, external_id=external_id,
            modality="text", condition_order=json.dumps(design.balanced_condition_order(index)), consented=True,
            started_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None), notes="TEST" if config["is_test"] else None))
        payload = {"participant_index": index, "cursor": 0, "config": config, "pending": None,
                   "token": None, "last_token": None, "last_payload": None, "complete": False}
        con.execute(insert(runtime_sessions).values(pid=pid, payload=json.dumps(payload), updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)))
    return index

@contextmanager
def session_transaction(pid):
    with write_transaction() as con:
        row = con.execute(select(runtime_sessions.c.payload).where(runtime_sessions.c.pid == pid).with_for_update()).scalar_one_or_none()
        if row is None:
            raise KeyError("Session not found")
        payload = json.loads(row)
        yield con, payload
        con.execute(update(runtime_sessions).where(runtime_sessions.c.pid == pid).values(payload=json.dumps(payload), updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)))

def session_data(pid):
    with engine.connect() as con:
        row = con.execute(select(runtime_sessions.c.payload).where(runtime_sessions.c.pid == pid)).scalar_one_or_none()
    return json.loads(row) if row else None

def save_diagnostics(con, pid, global_trial, payload):
    con.execute(insert(trial_diagnostics).values(pid=pid, global_trial=global_trial,
        payload=json.dumps(payload), created_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)))

def diagnostic_rows(pid=None):
    with engine.connect() as con:
        query = select(trial_diagnostics)
        if pid:
            query = query.where(trial_diagnostics.c.pid == pid)
        rows = con.execute(query).mappings().all()
    return [dict(id=r["id"], pid=r["pid"], created_at=r["created_at"].isoformat(), **json.loads(r["payload"])) for r in rows]

def participant_summary(pid: str) -> Optional[Dict[str, Any]]:
    with engine.begin() as con:
        rows = con.execute(
            select(trials.c.true_count, trials.c.initial_estimate, trials.c.final_estimate)
            .where(trials.c.pid == pid).order_by(trials.c.global_trial)
        ).mappings().all()
    if not rows:
        return None
    initial_ape = []
    final_ape = []
    final_abs = []
    improved_trials = 0
    for r in rows:
        truth = float(r["true_count"])
        if truth <= 0:
            continue
        initial_abs = abs(float(r["initial_estimate"]) - truth)
        final_abs_err = abs(float(r["final_estimate"]) - truth)
        initial_ape.append(initial_abs / truth * 100.0)
        final_ape.append(final_abs_err / truth * 100.0)
        final_abs.append(abs(int(r["final_estimate"]) - int(r["true_count"])))
        if final_abs_err < initial_abs:
            improved_trials += 1
    if not final_ape:
        return None
    mean_initial = sum(initial_ape) / len(initial_ape)
    mean_final = sum(final_ape) / len(final_ape)
    score = max(0, min(100, round(100.0 - mean_final)))
    initial_score = max(0, min(100, round(100.0 - mean_initial)))
    return {
        "n_trials": len(final_ape), "score": score, "initial_score": initial_score,
        "score_change": score - initial_score, "improved_trials": improved_trials,
        "mean_abs_pct_error": round(mean_final, 1), "closest_dots": min(final_abs),
    }
