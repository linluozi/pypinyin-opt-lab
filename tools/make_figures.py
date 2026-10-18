#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Render the figures referenced by README.md into ``assets/``.

All numbers come from ``bench/results.json`` and ``bench/ablation.json``;
nothing is typed in by hand, so the figures cannot drift away from the
measurements.  Regenerate with::

    python bench/run_bench.py && python bench/ablation.py
    python tools/make_figures.py

Style: warm editorial (paper / ink / amber / terracotta), no cold blues.
Labels are English because CJK glyphs in matplotlib need a font the reader
may not have; the README carries the Chinese explanation instead.
"""

from __future__ import print_function

import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, 'assets')

INK = '#2b2119'
PAPER = '#faf6f0'
AMBER = '#c8892b'
TERRACOTTA = '#b4552f'
OLIVE = '#6b6b3a'
MUTED = '#8a7a68'
GRID = '#e2d8c9'


def _setup():
    plt.rcParams.update({
        'font.family': 'DejaVu Sans',
        'font.size': 10,
        'axes.facecolor': PAPER,
        'figure.facecolor': PAPER,
        'axes.edgecolor': GRID,
        'axes.labelcolor': INK,
        'text.color': INK,
        'xtick.color': MUTED,
        'ytick.color': MUTED,
        'axes.grid': False,
    })


def load(name):
    with open(os.path.join(ROOT, 'bench', name), encoding='utf-8') as fp:
        return json.load(fp)


# --------------------------------------------------------------------------
# Figure 1: wall-clock before/after, grouped by workload
# --------------------------------------------------------------------------

SHORT_LABELS = {
    'lazy_short': 'lazy · 7 chars',
    'lazy_mid': 'lazy · 22 chars',
    'pinyin_list_mid': 'pinyin(list) · pre-seg',
    'lazy_pingguo': 'lazy · 15.9 kB',
    'lazy_liangzi': 'lazy · 32.5 kB',
    'lazy_zhongguo': 'lazy · 38.1 kB',
    'lazy_tone_pingguo': 'lazy · TONE',
    'lazy_first_pingguo': 'lazy · FIRST_LETTER',
    'pinyin_pingguo': 'pinyin() · default',
    'pinyin_hetero_pingguo': 'pinyin() · heteronym',
    'slug_pingguo': 'slug() · default',
}


def fig_walltime(results):
    cases = [c for c in results['cases'] if c['ref_s'] > 0.001]
    cases.sort(key=lambda c: c['ratio'])

    fig, ax = plt.subplots(figsize=(9.2, 5.6), dpi=170)
    ys = range(len(cases))
    height = 0.36

    ref = [c['ref_s'] * 1000 for c in cases]
    opt = [c['opt_s'] * 1000 for c in cases]

    ax.barh([y + height / 2 for y in ys], ref, height,
            color=MUTED, label='upstream 0.55.0', zorder=3)
    ax.barh([y - height / 2 for y in ys], opt, height,
            color=AMBER, label='this fork', zorder=3)

    xmax = max(ref)
    for y, c in zip(ys, cases):
        # 数值标签贴在条形右端之外；倍率单独占一列，不压在条形上
        ax.text(c['ref_s'] * 1000 + xmax * 0.012, y + height / 2,
                '%.0f' % (c['ref_s'] * 1000),
                va='center', ha='left', fontsize=8, color=MUTED)
        ax.text(c['opt_s'] * 1000 + xmax * 0.012, y - height / 2,
                '%.0f' % (c['opt_s'] * 1000),
                va='center', ha='left', fontsize=8, color=TERRACOTTA)
        ax.text(1.0, y, '%.2fx' % c['ratio'], transform=ax.get_yaxis_transform(),
                va='center', ha='right', fontsize=9.5, color=INK,
                fontweight='bold')

    ax.set_yticks(list(ys))
    ax.set_yticklabels([SHORT_LABELS[c['case']] for c in cases], fontsize=9)
    ax.set_xlabel('wall clock per call (ms, lower is better)', fontsize=9.5)
    # 右侧留出倍率列，避免与条形重叠
    ax.set_xlim(0, xmax * 1.30)
    ax.grid(axis='x', color=GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)

    ax.set_title('Same output, less time  ·  Python 3.13, Windows 11, median of 15 rounds',
                 fontsize=11, color=INK, loc='left', pad=26)
    # 图例放在标题下方、绘图区之上，不压任何数据
    ax.legend(loc='lower left', bbox_to_anchor=(0.0, 1.005), ncol=2,
              frameon=False, fontsize=9, handlelength=1.4, columnspacing=1.6)
    fig.tight_layout(rect=(0.012, 0, 1, 0.93))
    path = os.path.join(ASSETS, 'fig1_walltime.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# Figure 2: ablation -- which change earned what
# --------------------------------------------------------------------------

STEP_LABELS = {
    'translate tables for tone conversion': 'translate tables\n(tone symbols)',
    'syllable cache + lookup fast path': 'syllable cache\n+ lookup fast path',
    'C-level Han chunking': 'C-level Han\nchunking',
}


def fig_ablation(ablation):
    steps = [s for s in ablation['steps'] if s['label'] in STEP_LABELS]

    fig, ax = plt.subplots(figsize=(7.6, 4.4), dpi=170)
    xs = range(len(steps))
    values = [s['ratio'] for s in steps]
    colors = [OLIVE, AMBER, TERRACOTTA]

    bars = ax.bar(list(xs), values, width=0.52, color=colors, zorder=3)
    ax.axhline(1.0, color=INK, linewidth=1.1, linestyle='--', zorder=4)
    ax.text(len(steps) - 0.42, 1.012, 'no change', fontsize=8.5,
            color=MUTED, ha='right', va='bottom')

    for x, s in zip(xs, steps):
        ax.text(x, s['ratio'] + 0.03, '%.3fx' % s['ratio'],
                ha='center', va='bottom', fontsize=11, fontweight='bold',
                color=INK)

    ax.set_xticks(list(xs))
    ax.set_xticklabels([STEP_LABELS[s['label']] for s in steps], fontsize=9.5)
    ax.set_ylim(0.9, max(values) * 1.16)
    ax.set_ylabel('speed-up of this step alone (x)', fontsize=9.5)
    ax.grid(axis='y', color=GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)

    total = 1.0
    for s in steps:
        total *= s['ratio']
    ax.set_title('Each change measured against the build just before it  '
                 '(product %.2fx)' % total,
                 fontsize=11, color=INK, loc='left', pad=14)
    fig.tight_layout()
    path = os.path.join(ASSETS, 'fig2_ablation.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# Figure 3: where the time went -- call-chain diagram
# --------------------------------------------------------------------------

def fig_callchain():
    """Draw the upstream per-character chain next to the cached fast path.

    The point of the figure is structural: upstream runs five Python calls per
    character; the fast path runs one dict lookup.  Box widths are chosen so
    the whole chain fits the canvas -- 2..98 units of a 100-unit axis, with a
    1.6-unit gap between boxes.
    """
    fig, ax = plt.subplots(figsize=(10.4, 5.0), dpi=170)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 52)
    ax.axis('off')

    def box(x, y, w, h, text, color, text_color=PAPER, fontsize=8.6, bold=False):
        patch = FancyBboxPatch((x, y), w, h,
                               boxstyle='round,pad=0.3,rounding_size=1.2',
                               linewidth=0, facecolor=color, zorder=3)
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, text, ha='center', va='center',
                fontsize=fontsize, color=text_color, zorder=4,
                fontweight='bold' if bold else 'normal')

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                                     arrowstyle='-|>', mutation_scale=11,
                                     linewidth=1.1, color=MUTED, zorder=2))

    def chain(items, y, h):
        """按权重把 items 铺满 2..98，返回每段的 (x, w)。"""
        gap = 1.6
        total_w = 96.0 - gap * (len(items) - 1)
        weight_sum = sum(w for _, w, _ in items)
        x = 2.0
        placed = []
        for label, weight, color in items:
            w = total_w * weight / weight_sum
            placed.append((x, w, label, color))
            x += w + gap
        for i, (bx, bw, label, color) in enumerate(placed):
            box(bx, y, bw, h, label, color, fontsize=8.2)
            if i < len(placed) - 1:
                arrow(bx + bw, y + h / 2, bx + bw + gap - 0.15, y + h / 2)
        return placed

    # -- upstream -----------------------------------------------------------
    ax.text(2, 48.6, 'UPSTREAM  ·  per character, every call',
            fontsize=10, color=MUTED, fontweight='bold')

    chain([
        ('convert()', 16.0, TERRACOTTA),
        ('_phrase_pinyin()\ndeepcopy', 18.0, '#c0754f'),
        ('post_pinyin()', 13.0, '#c98a63'),
        ('convert_styles()', 17.0, TERRACOTTA),
        ('convert_style()\npre / _convert_style / post', 21.0, '#a34b28'),
        ('registry\nconvert()', 15.0, '#8f3f21'),
    ], y=27.0, h=11.0)

    ax.text(2, 23.4,
            'five Python frames per character; the work inside them is a '
            'regex or a table lookup',
            fontsize=8.6, color=MUTED)

    # -- fork ---------------------------------------------------------------
    ax.text(2, 17.6, 'THIS FORK  ·  per character, cache hit',
            fontsize=10, color=AMBER, fontweight='bold')

    placed = chain([
        ('convert()', 16.0, TERRACOTTA),
        ('_phrase_pinyin()\nlist-copy', 20.0, '#c0754f'),
        ('convert_styles()\none dict.get', 24.0, AMBER),
        ('result', 14.0, OLIVE),
    ], y=6.0, h=8.6)

    ax.text(2, 2.6,
            'cache hit: no per-character Python frames at all.  Cache miss '
            '(first sighting of a syllable) falls back to the upstream chain, '
            'so output is identical by construction.',
            fontsize=8.4, color=MUTED, style='italic', va='top')

    fig.tight_layout()
    path = os.path.join(ASSETS, 'fig3_callchain.png')
    fig.savefig(path, bbox_inches='tight', facecolor=PAPER)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# Figure 4: cache hit rate -- why the cache pays off
# --------------------------------------------------------------------------

def fig_hitrate():
    """Syllable distribution of the benchmark corpus.

    Labels use TONE3 spelling (``de5``, ``nian2``) rather than the accented
    form: accented pinyin needs a font with combining-mark coverage, and a
    missing glyph renders as a tofu box that silently destroys the figure.
    TONE3 keeps the tone information, stays ASCII, and still distinguishes
    homographs by tone.
    """
    import collections
    import importlib
    import sys

    corpus_path = os.path.join(ROOT, 'bench', 'corpora', 'pingguo.txt')
    with open(corpus_path, encoding='utf-8', errors='replace') as fp:
        text = fp.read()

    sys.path.insert(0, ROOT)
    mod = importlib.import_module('pypinyin')
    style = mod.Style.TONE3
    seg = [w for w in mod.core._default_pinyin.seg(text) if w]
    tokens = []
    for word in seg:
        pys = mod.pinyin(word, style=style, heteronym=False)
        for p in pys:
            # 标点会原样留在结果里（errors='default'），它们不参与音节复用，
            # 留在图上只会让坐标轴出现缺字方框
            tok = p[0]
            if tok and tok[0].isalpha():
                tokens.append(tok)

    counts = collections.Counter(tokens)
    total = sum(counts.values())
    types = len(counts)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 4.2), dpi=170,
                                   gridspec_kw={'width_ratios': [1, 1.55]})

    # left: tokens vs types
    ax1.bar([0, 1], [total, types], width=0.5,
            color=[MUTED, AMBER], zorder=3)
    for x, v in ((0, total), (1, types)):
        ax1.text(x, v * 1.03, '{:,}'.format(v), ha='center', va='bottom',
                 fontsize=11, fontweight='bold', color=INK)
    ax1.set_xticks([0, 1])
    ax1.set_xticklabels(['syllables\nemitted', 'distinct\nsyllables'],
                        fontsize=9)
    ax1.set_ylim(0, total * 1.18)
    ax1.set_ylabel('count', fontsize=9)
    ax1.grid(axis='y', color=GRID, linewidth=0.7, zorder=0)
    ax1.set_axisbelow(True)
    for side in ('top', 'right'):
        ax1.spines[side].set_visible(False)
    ax1.set_title('one 15.9 kB article  ·  %.1fx reuse' % (total / types),
                  fontsize=10, color=INK, loc='left')

    # right: top syllables, showing repeats
    top = counts.most_common(14)
    labels = [t for t, _ in top][::-1]
    values = [c for _, c in top][::-1]
    ax2.barh(range(len(top)), values, height=0.62, color=AMBER, zorder=3)
    ax2.set_yticks(range(len(top)))
    ax2.set_yticklabels(labels, fontsize=9)
    for y, v in enumerate(values):
        ax2.text(v + max(values) * 0.015, y, str(v), va='center', ha='left',
                 fontsize=8, color=TERRACOTTA)
    ax2.set_xlabel('occurrences of this syllable (TONE3 spelling)',
                   fontsize=9)
    ax2.set_xlim(0, max(values) * 1.16)
    ax2.grid(axis='x', color=GRID, linewidth=0.7, zorder=0)
    ax2.set_axisbelow(True)
    for side in ('top', 'right'):
        ax2.spines[side].set_visible(False)
    ax2.set_title('the same few syllables repeat hundreds of times',
                  fontsize=10, color=INK, loc='left')

    fig.tight_layout()
    path = os.path.join(ASSETS, 'fig4_hitrate.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    return path, total, types


def main():
    _setup()
    if not os.path.isdir(ASSETS):
        os.makedirs(ASSETS)

    results = load('results.json')
    ablation = load('ablation.json')

    print(fig_walltime(results))
    print(fig_ablation(ablation))
    print(fig_callchain())
    path, total, types = fig_hitrate()
    print(path)
    print('tokens %d, types %d, ratio %.1f' % (total, types, total / types))


if __name__ == '__main__':
    main()
