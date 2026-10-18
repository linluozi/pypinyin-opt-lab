#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Interleaved A/B benchmark for the pypinyin optimisation fork.

Design notes (why it is written this way):

* **One workload per process.**  Absolute timings do not transfer between
  cases: different corpora, different allocator pressure, and the previous
  case can leave the interpreter in a different specialisation state.  So
  ``--case`` selects exactly one workload and the driver spawns a fresh
  process for it.
* **Paired, interleaved rounds.**  Both implementations live in the same
  process (they are separate module names, with separate dictionaries), and
  every round times A then B then B then A.  The reported figure is the
  median of the *per-round ratios*, never the ratio of two medians --
  machine drift then cancels instead of being charged to one side.  The
  ABBA order also cancels first-order position effects.
* **A noise floor, not a guess.**  ``--baseline ref2`` times a byte-identical
  copy of the upstream package against ``ref``.  Whatever that pair reports
  is measurement noise; effects smaller than it are not claimed.
* **Only the call under test is inside the timing window.**  Inputs are
  prepared once, outside the loop, and each sample repeats the call enough
  times that per-call overhead does not dominate the clock resolution.
* **Keep the whole run short.**  This laptop drops to roughly half clock
  after ~30 s of sustained load (measured: a fixed pure-Python loop goes
  from 5.3 ms to 10.1 ms and stays there).  A long run therefore mixes two
  clock regimes and inflates the spread enormously.  The default repeat
  counts below are tuned so a case finishes in a few seconds, well inside
  the fast regime.
"""

from __future__ import print_function

import argparse
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(HERE, 'ref'))

CORPORA = {
    'pingguo': 'pingguo.txt',    # 15.9 kB encyclopaedia, 9.1 k Han chars
    'zhongguo': 'zhongguo.txt',  # 38.1 kB, 32.2 k Han chars
    'liangzi': 'liangzi.txt',    # 32.5 kB, 11.1 k Han chars
}

SHORT_TEXT = '中心思想很重要'
MID_TEXT = '北京大学生前来应聘，他说的确实有道理。'

_CORPUS_CACHE = {}


def load_corpus(name):
    if name not in _CORPUS_CACHE:
        path = os.path.join(HERE, 'corpora', CORPORA[name])
        with open(path, encoding='utf-8', errors='replace') as fp:
            _CORPUS_CACHE[name] = fp.read()
    return _CORPUS_CACHE[name]


def import_impl(which):
    if which == 'ref':
        import pypinyin_ref as mod
    elif which == 'ref2':
        import pypinyin_ref2 as mod
    else:
        import pypinyin as mod
    return mod


def make_call(mod, case):
    """Return ``(callable, repeats_per_sample)`` for one benchmark case.

    ``repeats_per_sample`` is chosen so a single sample lasts long enough to
    dwarf ``perf_counter`` resolution on Windows (~100 ns) while keeping the
    whole run under a few seconds.
    """
    if case == 'lazy_short':
        text = SHORT_TEXT
        return (lambda: mod.lazy_pinyin(text)), 2000
    if case == 'lazy_mid':
        text = MID_TEXT
        return (lambda: mod.lazy_pinyin(text)), 1000
    if case == 'lazy_pingguo':
        text = load_corpus('pingguo')
        return (lambda: mod.lazy_pinyin(text)), 2
    if case == 'lazy_zhongguo':
        text = load_corpus('zhongguo')
        return (lambda: mod.lazy_pinyin(text)), 1
    if case == 'lazy_liangzi':
        text = load_corpus('liangzi')
        return (lambda: mod.lazy_pinyin(text)), 1
    if case == 'lazy_tone_pingguo':
        text = load_corpus('pingguo')
        return (lambda: mod.lazy_pinyin(text, style=mod.Style.TONE)), 2
    if case == 'lazy_first_pingguo':
        text = load_corpus('pingguo')
        return (lambda: mod.lazy_pinyin(text, style=mod.Style.FIRST_LETTER)), 2
    if case == 'pinyin_pingguo':
        text = load_corpus('pingguo')
        return (lambda: mod.pinyin(text)), 2
    if case == 'pinyin_hetero_pingguo':
        text = load_corpus('pingguo')
        return (lambda: mod.pinyin(text, heteronym=True)), 2
    if case == 'slug_pingguo':
        text = load_corpus('pingguo')
        return (lambda: mod.slug(text)), 2
    if case == 'pinyin_list_mid':
        words = MID_TEXT.split('，')
        return (lambda: mod.pinyin(words)), 1000
    raise SystemExit('unknown case: %s' % case)


def time_sample(fn, repeat):
    start = time.perf_counter()
    for _ in range(repeat):
        fn()
    return (time.perf_counter() - start) / repeat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--baseline', default='ref',
                    help="left-hand side: 'ref' or 'ref2' (noise floor)")
    ap.add_argument('--target', default='opt',
                    help="right-hand side: 'opt'")
    ap.add_argument('--rounds', type=int, default=15)
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    left = import_impl(args.baseline)
    right = import_impl(args.target)
    fn_l, rep = make_call(left, args.case)
    fn_r, rep_r = make_call(right, args.case)
    assert rep == rep_r, 'repeat count must match for a paired comparison'

    # Warm-up outside the measured window: let both sides touch their
    # dictionaries and settle the allocator.
    for _ in range(3):
        time_sample(fn_l, rep)
        time_sample(fn_r, rep)

    left_samples = []
    right_samples = []
    ratios = []
    for _ in range(args.rounds):
        # ABBA ordering: cancels linear drift and first-order position bias.
        a1 = time_sample(fn_l, rep)
        b1 = time_sample(fn_r, rep)
        b2 = time_sample(fn_r, rep)
        a2 = time_sample(fn_l, rep)
        a = (a1 + a2) / 2.0
        b = (b1 + b2) / 2.0
        left_samples.append(a)
        right_samples.append(b)
        ratios.append(a / b)

    out = {
        'case': args.case,
        'baseline': args.baseline,
        'target': args.target,
        'repeat': rep,
        'rounds': args.rounds,
        'baseline_median_s': statistics.median(left_samples),
        'target_median_s': statistics.median(right_samples),
        'ratio_median': statistics.median(ratios),
        'ratio_p25': statistics.quantiles(ratios, n=4)[0] if len(ratios) >= 4 else min(ratios),
        'ratio_p75': statistics.quantiles(ratios, n=4)[2] if len(ratios) >= 4 else max(ratios),
        'ratio_min': min(ratios),
        'ratio_max': max(ratios),
        'baseline_samples': left_samples,
        'target_samples': right_samples,
    }
    print(json.dumps(out, ensure_ascii=False))
    if args.json:
        with open(args.json, 'w', encoding='utf-8', newline='\n') as fp:
            json.dump(out, fp, ensure_ascii=False, indent=2)
            fp.write('\n')


if __name__ == '__main__':
    main()
