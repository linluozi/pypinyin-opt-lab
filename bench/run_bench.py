#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run every benchmark case and write ``bench/results.json``.

Each case is a separate process (see ``bench.py`` for why).  The noise floor
is measured first, by timing the byte-identical reference copy ``ref2``
against ``ref``: whatever that pair reports is not a real effect.

Usage::

    python bench/run_bench.py            # full run, ~3 min
    python bench/run_bench.py --quick    # fewer rounds, writes *_quick.json
"""

from __future__ import print_function

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CASES = [
    # (case id, human label, group)
    ('lazy_short', 'lazy_pinyin  · 7 chars', 'small'),
    ('lazy_mid', 'lazy_pinyin  · 22 chars', 'small'),
    ('pinyin_list_mid', 'pinyin(list) · pre-segmented', 'small'),
    ('lazy_pingguo', 'lazy_pinyin  · 15.9 kB', 'corpus'),
    ('lazy_liangzi', 'lazy_pinyin  · 32.5 kB', 'corpus'),
    ('lazy_zhongguo', 'lazy_pinyin  · 38.1 kB', 'corpus'),
    ('lazy_tone_pingguo', 'lazy_pinyin  · Style.TONE', 'style'),
    ('lazy_first_pingguo', 'lazy_pinyin  · FIRST_LETTER', 'style'),
    ('pinyin_pingguo', 'pinyin()     · default', 'style'),
    ('pinyin_hetero_pingguo', 'pinyin()     · heteronym', 'style'),
    ('slug_pingguo', 'slug()       · default', 'style'),
]


def run_case(case, baseline, target, rounds, python):
    cmd = [python, os.path.join(HERE, 'bench.py'),
           '--case', case, '--baseline', baseline, '--target', target,
           '--rounds', str(rounds)]
    out = subprocess.check_output(cmd, cwd=ROOT)
    return json.loads(out.decode('utf-8').strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=15)
    ap.add_argument('--quick', action='store_true',
                    help='fewer rounds; writes results_quick.json so a smoke '
                         'run can never overwrite the published numbers')
    ap.add_argument('--python', default=sys.executable)
    args = ap.parse_args()

    rounds = 5 if args.quick else args.rounds
    results = {'rounds': rounds, 'cases': [], 'noise': []}

    print('measuring noise floor (ref vs ref2, byte-identical)...')
    for case in ('lazy_short', 'lazy_pingguo', 'pinyin_pingguo'):
        rec = run_case(case, 'ref', 'ref2', rounds, args.python)
        results['noise'].append({
            'case': case,
            'ratio': rec['ratio_median'],
            'p25': rec['ratio_p25'],
            'p75': rec['ratio_p75'],
        })
        print('  %-22s %.3fx  [%.3f, %.3f]'
              % (case, rec['ratio_median'], rec['ratio_p25'], rec['ratio_p75']))

    print('measuring ref vs opt...')
    for case, label, group in CASES:
        rec = run_case(case, 'ref', 'opt', rounds, args.python)
        results['cases'].append({
            'case': case,
            'label': label,
            'group': group,
            'ref_s': rec['baseline_median_s'],
            'opt_s': rec['target_median_s'],
            'ratio': rec['ratio_median'],
            'p25': rec['ratio_p25'],
            'p75': rec['ratio_p75'],
        })
        print('  %-28s %.3fx   %.4f s -> %.4f s'
              % (label, rec['ratio_median'],
                 rec['baseline_median_s'], rec['target_median_s']))

    name = 'results_quick.json' if args.quick else 'results.json'
    path = os.path.join(HERE, name)
    with open(path, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)
        fp.write('\n')
    print('wrote %s' % path)


if __name__ == '__main__':
    main()
