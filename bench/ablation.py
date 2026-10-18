#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ablation: attribute the total speed-up to individual changes.

A single "before vs after" number cannot tell you *which* change earned the
gain, and summing isolated micro-benchmarks over-attributes (each change is
measured against a different baseline).  So this script keeps four builds of
the package alive in one process and times **adjacent pairs**:

    ref  -> s1   translate tables for tone-symbol conversion
    s1   -> s2   syllable-level conversion cache + fast path
    s2   -> s3   C-level Han/non-Han chunking

Each pair is timed with the same ABBA interleaving as ``bench.py``, so the
numbers below are "this change, on top of the previous ones" -- which is the
only attribution that adds up to the total.

Usage::

    python bench/ablation.py [--rounds 13]
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
sys.path.insert(0, os.path.join(HERE, 'layers'))

STEPS = [
    ('ref', 's1', 'translate tables for tone conversion'),
    ('s1', 's2', 'syllable cache + lookup fast path'),
    ('s2', 's3', 'C-level Han chunking'),
    ('s3', 'opt', 'total (s3 == opt)'),
]

MODULES = {
    'ref': 'pypinyin_ref',
    's1': 'pypinyin_s1',
    's2': 'pypinyin_s2',
    's3': 'pypinyin_s3',
    'opt': 'pypinyin',
}


def load(name):
    import importlib
    return importlib.import_module(MODULES[name])


def corpus():
    with open(os.path.join(HERE, 'corpora', 'pingguo.txt'),
              encoding='utf-8', errors='replace') as fp:
        return fp.read()


def time_call(fn, repeat):
    start = time.perf_counter()
    for _ in range(repeat):
        fn()
    return (time.perf_counter() - start) / repeat


def compare(mod_a, mod_b, repeat, rounds):
    text = corpus()
    fn_a = lambda: mod_a.lazy_pinyin(text)      # noqa: E731
    fn_b = lambda: mod_b.lazy_pinyin(text)      # noqa: E731

    for _ in range(3):
        time_call(fn_a, repeat)
        time_call(fn_b, repeat)

    ratios = []
    for _ in range(rounds):
        a1 = time_call(fn_a, repeat)
        b1 = time_call(fn_b, repeat)
        b2 = time_call(fn_b, repeat)
        a2 = time_call(fn_a, repeat)
        ratios.append(((a1 + a2) / 2.0) / ((b1 + b2) / 2.0))
    return statistics.median(ratios)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=13)
    ap.add_argument('--repeat', type=int, default=2)
    args = ap.parse_args()

    mods = {name: load(name) for name in MODULES}
    rows = []
    for left, right, label in STEPS:
        ratio = compare(mods[left], mods[right], args.repeat, args.rounds)
        rows.append({'from': left, 'to': right, 'label': label,
                     'ratio': ratio})
        print('%-6s -> %-4s  %.3fx   %s' % (left, right, ratio, label))

    path = os.path.join(HERE, 'ablation.json')
    with open(path, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump({'steps': rows}, fp, ensure_ascii=False, indent=2)
        fp.write('\n')
    print('wrote %s' % path)


if __name__ == '__main__':
    main()
