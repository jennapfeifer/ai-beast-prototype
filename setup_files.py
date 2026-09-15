#!/usr/bin/env python3
"""Check/repair the AI-BEAST folder layout without overwriting current templates."""
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def main():
    if not (HERE / "app.py").exists():
        raise SystemExit("Run this from the folder that contains app.py.")

    (HERE / "templates").mkdir(exist_ok=True)
    sdir = HERE / "static"
    sdir.mkdir(exist_ok=True)

    # Browser uploads sometimes leave these two assets at project root. Keep the
    # canonical copies in static/ but never overwrite a newer static file.
    for asset in ("style.css", "task.js"):
        loose = HERE / asset
        target = sdir / asset
        if not target.exists() and loose.exists():
            shutil.copy2(loose, target)
            print(f"copied {asset} -> static/{asset}")
        elif target.exists():
            print(f"static/{asset} ready")
        else:
            print(f"MISSING: static/{asset}")

    required_templates = ["base.html", "consent.html", "instructions.html", "task.html", "debrief.html", "rate.html"]
    missing = [x for x in required_templates if not (HERE / "templates" / x).exists()]
    if missing:
        raise SystemExit("Missing templates: " + ", ".join(missing))

    stim = sdir / "stimuli"
    n = len(list(stim.glob("*.png"))) if stim.exists() else 0
    print(f"static/stimuli: {n} images" + ("" if n >= 105 else "  -> run: python stimuli.py --size 512 --force"))

    checks = [
        ("app.py", "advice_number", "separate numerical advice API"),
        ("adviser.py", "gemini-3.7-flash", "fast Gemini adviser option"),
        ("adviser.py", "image_specific_evidence", "no invented image evidence"),
        ("static/task.js", "initial-numberline", "click-to-estimate first response"),
        ("static/task.js", "estimate-pair", "equal You/AI comparison display"),
        ("static/task.js", "trial-beads", "within-round progress display"),
        ("static/style.css", ".estimate-chip", "matched You/AI marker styles"),
        ("templates/instructions.html", "click the number line", "game-style instructions"),
        ("templates/debrief.html", "final estimation score", "end-only performance summary"),
    ]
    old = []
    for rel, needle, label in checks:
        path = HERE / rel
        ok = path.exists() and needle in path.read_text(encoding="utf-8")
        print(f"  [{'ok' if ok else 'OLD'}] {label}")
        if not ok:
            old.append(rel)
    if old:
        raise SystemExit("Some files are out of date: " + ", ".join(sorted(set(old))))

    print("\nFiles ready.")


if __name__ == "__main__":
    main()
