"""Contrastive adviser probe. Offline by default; --live explicitly calls the API.

This tests prompt routing and records messages for human review. It does not prove
that persuasion is effective. Run on the server environment you intend to pilot.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import random
import time

import adviser
import design


def histories(direction):
    cid = 'C4' if direction == 'UP' else 'C7'
    result = {}
    for scenario in ('resisted', 'followed'):
        rows = []
        for position, truth in enumerate([112, 128, 160], 1):
            initial = int(truth * (0.8 if direction == 'UP' else 1.2))
            advice = design.advice_number(cid, truth, initial)
            rows.append(dict(trial_position=position, initial_estimate=initial,
                advice_number=advice, final_estimate=initial if scenario == 'resisted' else advice,
                advice_text=adviser.control_message(advice, f'0|{cid}|{position}')['text'],
                trust_rating=(2 if scenario == 'resisted' else 6) if position == 2 else None,
                feeling_rating=(3 if scenario == 'resisted' else 5) if position == 2 else None))
        result[scenario] = rows
    return result


def digest(prompt):
    return hashlib.sha256(json.dumps(prompt, ensure_ascii=False).encode()).hexdigest()


def run_probe(live=False, repetitions=1):
    if live and not adviser.has_api_key():
        raise RuntimeError('--live requires the selected provider API key. No calls made.')
    generate = adviser.generate_message if live else adviser.generate_offline_message
    results, routing = [], []
    for direction in ('UP', 'DOWN'):
        scenarios = histories(direction)
        initial = None
        advice = design.advice_number('C4' if direction == 'UP' else 'C7', 128, initial)
        # Hold the current estimate and recommendation fixed within each
        # direction while changing only the history given to the probe.
        for style in ('static', 'adaptive'):
            prompts = {name: adviser.build_prompt(style, initial, advice, rows) for name, rows in scenarios.items()}
            identical = prompts['resisted'] == prompts['followed']
            routing.append(dict(direction=direction, style=style, prompt_identical=identical,
                                expected_identical=style == 'static', passed=identical == (style == 'static')))
            for repetition in range(1, repetitions + 1):
                for scenario, history in scenarios.items():
                    key = f'probe|{direction}|{style}|{repetition}'
                    start = time.perf_counter()
                    message = generate(style, initial, advice, history=history,
                        previous_messages=[r['advice_text'] for r in history], key=key)
                    results.append(dict(item_id=f'{direction}-{style}-{scenario}-{repetition}', direction=direction,
                        style=style, scenario=scenario, repetition=repetition, initial=initial, advice=advice,
                        history=history if style == 'adaptive' else [],
                        supplied_probe_history=history, prompt_sha256=digest(prompts[scenario]),
                        elapsed_ms=round((time.perf_counter() - start) * 1000), **message))
    live_count = sum(bool(r.get('live_model')) for r in results)
    return dict(created_at=dt.datetime.now(dt.timezone.utc).isoformat(), mode='live' if live else 'offline',
        model=adviser.ADVISER_MODEL if live else 'deterministic rehearsal', repetitions=repetitions,
        summary=dict(items=len(results), routing_passed=all(r['passed'] for r in routing),
            live_messages=live_count, fallback_messages=sum(r['source'].startswith('fallback:') for r in results),
            meaningfully_adaptive='NOT AUTOMATICALLY ASSESSED', behavioural_effect='NOT TESTED'),
        routing=routing, results=results,
        limitations=['Different live messages alone do not prove adaptation: model outputs are stochastic.',
          'Review whether each history claim is supported and whether wording uses that history persuasively.',
          'Static prompts must be identical between histories; static outputs need not be identical.',
          'Offline branches are illustrative code paths, not evidence about GPT.',
          'A behavioural effect requires human pilot data; this probe uses synthetic histories.',
          'Retry budget is checked between requests; SDK timeouts are not an exact wall-clock deadline.'])


def write_report(report, folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'adaptation-probe.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    items = list(report['results']); random.Random(20260909).shuffle(items)
    with (folder / 'message-review.csv').open('w', newline='', encoding='utf-8') as f:
        fields = ['review_id', 'message', 'personalization_1_to_7', 'convincingness_1_to_7', 'notes']
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for i, row in enumerate(items, 1):writer.writerow(dict(review_id=i, message=row['text']))
    (folder / 'review-key.json').write_text(json.dumps({i: row['item_id'] for i, row in enumerate(items, 1)}, indent=2))
    esc = html.escape
    cards = ''.join(f'<article><small>{esc(r["item_id"])} · {esc(r["source"])} · {r["elapsed_ms"]} ms</small>'
        f'<blockquote>{esc(r["text"])}</blockquote><p>Validation: {esc(r["validation"])}; attempts: {r["attempts"]}</p>'
        f'<details><summary>History supplied to this prompt</summary><pre>{esc(json.dumps(r["history"], indent=2))}</pre></details></article>' for r in report['results'])
    document = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>BEAST adaptation probe</title><style>body{max-width:1000px;margin:40px auto;padding:20px;background:#f4f6ee;color:#233d34;font:16px/1.6 system-ui}article{background:white;padding:24px;margin:20px 0;border:1px solid #d8dfd0;border-radius:12px}h1{font-size:36px}small{color:#52685d}blockquote{font-size:21px;margin:12px 0}pre{overflow:auto;font-size:12px}</style>'
    document += f'<h1>Contrastive adaptation probe</h1><p><b>Mode: {esc(report["mode"])}.</b> Synthetic histories; no behavioural effect tested.</p><pre>{esc(json.dumps(report["summary"], indent=2))}</pre><p>Compare resisted vs followed within each style and direction. Inspect the JSON for prompt hashes. Use message-review.csv for a first blind rating, then review the corresponding history for unsupported claims.</p>'
    document += cards + '<h2>Interpretation limits</h2><ul>' + ''.join(f'<li>{esc(x)}</li>' for x in report['limitations']) + '</ul>'
    (folder / 'adaptation-probe.html').write_text(document, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Call the configured model; API charges apply.')
    parser.add_argument('--repetitions', type=int, default=1, help='1–10; 8 messages per repetition, each may retry.')
    parser.add_argument('--out', type=Path, default=Path('probe-results'))
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10:parser.error('--repetitions must be 1–10')
    if args.live and not adviser.has_api_key():parser.error('--live requires the selected provider API key; no calls made')
    print(f'Running {8*args.repetitions} messages in {"LIVE" if args.live else "OFFLINE"} mode.', flush=True)
    report = run_probe(args.live, args.repetitions); write_report(report, args.out)
    print(json.dumps(report['summary'], indent=2)); print(f'Review: {args.out / "adaptation-probe.html"}')
    if not report['summary']['routing_passed']:raise SystemExit(1)
    if args.live and report['summary']['live_messages'] != report['summary']['items']:
        raise SystemExit('Incomplete live probe: inspect fallbacks in the report.')


if __name__ == '__main__':main()
