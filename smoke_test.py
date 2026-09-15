"""End-to-end smoke test with live model generation stubbed out."""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "smoke_test_beast.db"
if DB.exists():
    DB.unlink()

os.environ.setdefault("SECRET_KEY", "test")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["RESEARCHER_MODE"] = "0"
os.environ["COLLECT_RATINGS"] = "1"
os.environ["RATING_EVERY"] = "2"
os.environ["SHOW_END_SCORE"] = "1"

import adviser

# Short visible notes contain no numbers and reject jargon/image-specific evidence.
valid_note = "I would reconsider your first impression and move toward this estimate."
assert adviser.message_is_valid(valid_note)[0]
assert not adviser.message_is_valid(valid_note + " 74")[0]
assert not adviser.message_is_valid("Dense clusters make this estimate much more convincing here.")[0]
assert not adviser.message_is_valid("I would anchor on this estimate before making your final decision.")[0]

resistant_history = [
    {"initial_estimate": 100, "advice_number": 125, "final_estimate": 100},
    {"initial_estimate": 120, "advice_number": 150, "final_estimate": 118},
    {"initial_estimate": 80, "advice_number": 100, "final_estimate": 81},
]
summary = adviser.history_behavior_summary(resistant_history).lower()
assert "mostly stayed close" in summary or "moved away" in summary

adaptive_calls = []

def stub_generate(style, initial, advice, history=None, attempts=None, key="", **kwargs):
    history = history or []
    if style == "adaptive":
        adaptive_calls.append({"key": key, "n": len(history), "history": [dict(h) for h in history]})
    text = {
        "fixed": "That's simply the estimate I would use for this display.",
        "neutral": "That's simply the estimate I would use for this trial.",
        "static": "I would reconsider your first impression and move toward this estimate.",
        "adaptive": "Taking earlier responses into account, I would give this estimate more weight.",
    }[style]
    return {"text": text, "source": "stub", "attempts": 0, "word_count": adviser.words(text), "validation": "stub"}

adviser.generate_message = stub_generate

import app as A
A.generate_message = stub_generate
A.app.config["TESTING"] = True
assert A.design.STUDY_SEED == 20260909

c = A.app.test_client()
assert c.get("/").status_code == 200
r = c.post("/start", data={}, follow_redirects=False)
assert r.status_code == 302

seen = []
n = 0
while True:
    st = c.get("/api/state").get_json()
    if st["done"]:
        break
    n += 1
    est = max(1, int(st["overall"] % 50) + 20)
    adv = c.post("/api/initial", json={"estimate": est, "rt_ms": 3000}).get_json()
    assert "advice_text" in adv and "advice_number" in adv, adv
    assert str(adv["advice_number"]) not in adv["advice_text"], "number should be rendered separately"
    if st["practice"]:
        assert not st["ratings_due"]
    elif st["trial_in_block"] % 2 == 0:
        assert st["ratings_due"]
    else:
        assert not st["ratings_due"]
    fin = c.post("/api/final", json={
        "estimate": est + 3,
        "rt_ms": 2000,
        "trust": 4 if st["ratings_due"] else None,
        "feeling": 4 if st["ratings_due"] else None,
    }).get_json()
    assert fin.get("ok"), fin
    if not st["practice"]:
        seen.append(st["image"].split("/")[-1].replace(".png", ""))

print(f"trials run: {n}")
print(f"recorded trials: {len(seen)}  distinct images: {len(set(seen))}")
assert n == 105
assert len(seen) == 104 and len(set(seen)) == 104

rows = A.store.export_rows(A.store.trials)
conds = {}
for row in rows:
    conds.setdefault(row["condition_id"], []).append(row)
assert len(conds) == 8 and all(len(v) == 13 for v in conds.values())

for cid, rs in conds.items():
    rated = sorted(r["trial_position"] for r in rs if r["trust_rating"] is not None)
    assert rated == [2, 4, 6, 8, 10, 12], (cid, rated)

def by_truth(cid):
    return {r["true_count"]: r["advice_number"] for r in conds[cid]}

assert by_truth("C3") == by_truth("C4") == by_truth("C5")
assert by_truth("C6") == by_truth("C7") == by_truth("C8")
for cid, expected in [("C1", 0.0), ("C3", 25.0), ("C6", -25.0)]:
    m = sum(r["advice_error_pct"] for r in conds[cid]) / 13
    print(f"{cid} mean advice error: {m:+.2f}%")
    assert abs(m - expected) < 1e-9

a144 = {r["advice_number"] for r in rows if r["true_count"] == 144 and r["condition_id"] != "C2"}
assert a144 == {144}

by_condition = {"C5": [], "C8": []}
for call in adaptive_calls:
    cid = call["key"].split("|")[1]
    if cid in by_condition:
        by_condition[cid].append(call)
for cid, calls in by_condition.items():
    lengths = [x["n"] for x in calls]
    assert lengths == list(range(13)), (cid, lengths)
    print(f"{cid} adaptive history lengths: {lengths}")

summary = A.store.participant_summary(rows[0]["pid"])
assert summary and 0 <= summary["score"] <= 100 and summary["n_trials"] == 104

# Explicitly test the researcher skip-warm-up path.
A.RESEARCHER_MODE = True
c2 = A.app.test_client()
r = c2.post("/start", data={"researcher_test":"1", "conditions":"C5", "trials":"2", "skip_practice":"1", "test_index":"0"}, follow_redirects=False)
assert r.status_code == 302
st = c2.get("/api/state").get_json()
assert not st["practice"]
assert st["n_blocks"] == 1 and st["n_in_block"] == 2

print("ALL CHECKS PASSED")
try:
    DB.unlink()
except OSError:
    pass
