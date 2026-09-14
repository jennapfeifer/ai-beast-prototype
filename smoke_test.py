"""End-to-end smoke test with GPT adviser generation stubbed out (no API calls)."""
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

import adviser

# Validator itself: GPT drafts use a placeholder and no visible numbers; the
# server inserts the fixed recommendation only after draft validation.
draft = " ".join(["word"] * 24 + [adviser.PLACEHOLDER])
assert adviser.draft_is_valid(draft)[0]
assert not adviser.draft_is_valid(draft + " 7")[0], "draft must not quote a prior/current number"
assert not adviser.draft_is_valid(draft.replace(adviser.PLACEHOLDER, adviser.PLACEHOLDER + " " + adviser.PLACEHOLDER))[0]
valid = draft.replace(adviser.PLACEHOLDER, "123")
assert adviser.message_is_valid(valid, 123)[0]
assert not adviser.message_is_valid(valid + " 7", 123)[0], "stray visible number must fail"
assert not adviser.message_is_valid("short 123", 123)[0], "short message must fail"

# Grounding helper must recognize clear resistance rather than claiming the
# participant has been following the adviser.
resistant_history = [
    {"initial_estimate": 100, "advice_number": 125, "final_estimate": 100},
    {"initial_estimate": 120, "advice_number": 150, "final_estimate": 118},
    {"initial_estimate": 80, "advice_number": 100, "final_estimate": 81},
]
summary = adviser.history_behavior_summary(resistant_history).lower()
assert "mostly stayed close" in summary or "moved away" in summary
assert "do not claim" in summary

adaptive_calls = []

def stub_generate(style, initial, advice, history=None, attempts=None, key="", **kwargs):
    history = history or []
    if style == "adaptive":
        adaptive_calls.append({"key": key, "n": len(history), "history": [dict(h) for h in history]})
    # Stub bypasses the real validator; return enough metadata for app storage.
    text = f"stub {style} recommendation {advice} for this trial"
    return {
        "text": text,
        "source": "stub",
        "attempts": 0,
        "word_count": adviser.words(text),
        "validation": "stub",
    }

adviser.generate_message = stub_generate

import app as A
A.generate_message = stub_generate
A.app.config["TESTING"] = True

assert A.design.STUDY_SEED == 20260909

c = A.app.test_client()
assert c.get("/").status_code == 200
r = c.post("/start", data={}, follow_redirects=False)
assert r.status_code == 302, r.status_code

seen = []
n = 0
while True:
    st = c.get("/api/state").get_json()
    if st["done"]:
        break
    assert "modality" not in st, "voice/modality must not be exposed in text-only app"
    n += 1
    est = max(1, int(st["overall"] % 50) + 20)
    adv = c.post("/api/initial", json={"estimate": est, "rt_ms": 3000}).get_json()
    assert "advice_text" in adv, adv
    assert "speak" not in adv and "show_text" not in adv, "voice fields should be gone"
    if st["practice"]:
        assert not st["ratings_due"]
    elif st["trial_in_block"] % 2 == 0:
        assert st["ratings_due"]
    else:
        assert not st["ratings_due"]
    fin = c.post(
        "/api/final",
        json={
            "estimate": est + 3,
            "rt_ms": 2000,
            "trust": 4 if st["ratings_due"] else None,
            "feeling": 4 if st["ratings_due"] else None,
        },
    ).get_json()
    assert fin.get("ok"), fin
    if not st["practice"]:
        seen.append(st["image"].split("/")[-1].replace(".png", ""))

print(f"trials run: {n}")
print(f"recorded trials: {len(seen)}  distinct images: {len(set(seen))}")
assert n == 105
assert len(seen) == 104 and len(set(seen)) == 104, "each experimental image must appear exactly once"

rows = A.store.export_rows(A.store.trials)
assert len(rows) == 104
conds = {}
for row in rows:
    conds.setdefault(row["condition_id"], []).append(row)
assert len(conds) == 8 and all(len(v) == 13 for v in conds.values())

# Ratings occur only after every second trial: 2,4,6,8,10,12.
for cid, rs in conds.items():
    rated = sorted(r["trial_position"] for r in rs if r["trust_rating"] is not None)
    assert rated == [2, 4, 6, 8, 10, 12], (cid, rated)
    assert all((r["trust_rating"] is None) == (r["feeling_rating"] is None) for r in rs)

# C3-C5 share NEW25 UP numbers by truth; C6-C8 share NEW25 DOWN numbers.
def by_truth(cid):
    return {r["true_count"]: r["advice_number"] for r in conds[cid]}

assert by_truth("C3") == by_truth("C4") == by_truth("C5")
assert by_truth("C6") == by_truth("C7") == by_truth("C8")

for cid, expected in [("C1", 0.0), ("C3", 25.0), ("C6", -25.0)]:
    m = sum(r["advice_error_pct"] for r in conds[cid]) / 13
    print(f"{cid} mean advice error: {m:+.2f}%")
    assert abs(m - expected) < 1e-9

# 144 special case: all fixed truth-relative schedules give 144; C2 is initial-relative.
a144 = {
    r["advice_number"] for r in rows
    if r["true_count"] == 144 and r["condition_id"] != "C2"
}
assert a144 == {144}, a144

# Adaptive adviser must get ALL prior trials in its own block: 0,1,...,12 for C5 and C8.
by_condition = {"C5": [], "C8": []}
for call in adaptive_calls:
    parts = call["key"].split("|")
    cid = parts[1]
    if cid in by_condition:
        by_condition[cid].append(call)

for cid, calls in by_condition.items():
    lengths = [x["n"] for x in calls]
    assert lengths == list(range(13)), (cid, lengths)
    for call in calls[1:]:
        assert all("advice_text" in h for h in call["history"]), "exact prior messages must be retrieved"
        assert all(h["advice_text"].startswith("stub") for h in call["history"])
    # By the final adaptive call, ratings exist on even prior trials only.
    last_hist = calls[-1]["history"]
    rated_positions = [h["trial_position"] for h in last_hist if h["trust_rating"] is not None]
    assert rated_positions == [2, 4, 6, 8, 10, 12], (cid, rated_positions)
    print(f"{cid} adaptive history lengths: {lengths}")

# Counterbalancing: eight production rows are distinct, and each condition occurs
# once in each serial position across the cycle.
orders = [A.design.balanced_condition_order(i) for i in range(8)]
assert len({tuple(x) for x in orders}) == 8
for pos in range(8):
    assert {o[pos] for o in orders} == set(A.design.CONDITIONS)

# TEST rows do not consume the production counterbalancing index.
assert A.store.next_participant_index() == 1
A.store.create_participant("TESTROW", 7, None, "text", A.design.balanced_condition_order(7), notes="TEST")
assert A.store.next_participant_index() == 1

# Legacy DB columns remain, but new rows are text-only.
assert {r["modality"] for r in rows} == {"text"}
assert {r["audio_played"] for r in rows} == {False}
assert c.post("/api/tts", json={"text": "hello"}).status_code == 404

# Blind message-rating pipeline still works.
items = A.store.messages_for_rating("rater1", limit=3)
assert items
A.store.save_rating({
    "rater_id": "rater1", "trial_id": items[0]["id"], "personalization": 5,
    "warmth": 4, "valence": 4, "directiveness": 6, "convincingness": 3,
})
assert len(A.store.export_rows(A.store.message_ratings)) == 1

print("ALL CHECKS PASSED")

try:
    DB.unlink()
except OSError:
    pass
