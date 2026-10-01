"""API-free validation for the current three-condition BEAST design."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import subprocess
import sys

import design

ROOT = Path(__file__).resolve().parent


def main() -> int:
    assert set(design.CONDITIONS) == {'N', 'P', 'A'}
    orders = [tuple(design.balanced_condition_order(i)) for i in range(6)]
    assert len(set(orders)) == 6

    for participant in range(24):
        rows = design.build_schedule(participant)
        assert len(rows) == 36
        groups = {cid: [r for r in rows if r['condition_id'] == cid] for cid in design.CONDITIONS}
        assert all(len(group) == 12 for group in groups.values())
        for group in groups.values():
            assert Counter(r['direction'] for r in group) == Counter({'UP': 6, 'DOWN': 6})
            assert 144 not in {r['true_count'] for r in group}
        for truth in design.EXPERIMENT_COUNTS:
            matched = [next(r for r in groups[cid] if r['true_count'] == truth) for cid in design.CONDITIONS]
            assert len({r['direction'] for r in matched}) == 1
            assert len({design.advice_number(r['condition_id'], truth, direction=r['direction']) for r in matched}) == 1

    for truth in design.EXPERIMENT_COUNTS:
        assert sum(design.direction_map(p)[truth] == 'UP' for p in range(12)) == 6

    participant_pages = [ROOT/'templates'/'consent.html', ROOT/'templates'/'instructions.html', ROOT/'templates'/'task.html']
    participant_text = '\n'.join(path.read_text() for path in participant_pages)
    for stale in ('named AI agent', 'several named AI agents', '104 images', '8 rounds'):
        assert stale not in participant_text
    assert 'Jamie' not in participant_text
    assert 'AI adviser' not in participant_text

    name_rows=[]
    for participant in range(6):
        order=design.balanced_condition_order(participant)
        names=design.adviser_name_mapping(participant)
        assert set(names.values()) == set(design.ADVISER_NAMES)
        for pos,cid in enumerate(order, start=1):
            name_rows.append((pos,cid,names[cid]))
    for cid in design.CONDITIONS:
        for name in design.ADVISER_NAMES:
            assert sum(c==cid and n==name for _,c,n in name_rows)==2
    for pos in (1,2,3):
        for name in design.ADVISER_NAMES:
            assert sum(p==pos and n==name for p,_,n in name_rows)==2

    subprocess.run([sys.executable, '-m', 'py_compile', 'design.py', 'app.py', 'pilot.py', 'adviser_flexible.py'], cwd=ROOT, check=True)
    if subprocess.run(['which', 'node'], capture_output=True).returncode == 0:
        subprocess.run(['node', '--check', 'static/task.js'], cwd=ROOT, check=True)
        subprocess.run(['node', '--check', 'static/live_review.js'], cwd=ROOT, check=True)

    print('PASS: current three-condition design and static checks')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
