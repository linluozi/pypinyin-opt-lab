# -*- coding: utf-8 -*-
"""Rebuild ``bench/ref`` and ``bench/layers`` from the current package.

Why generated copies at all?  The differential tests and the ablation need
*another* copy of the package importable under a different module name in the
same process.  Keeping them generated (rather than hand-maintained) means they
can never drift away from what they claim to be.

* ``bench/ref/pypinyin_ref``  — pristine upstream, mechanically renamed
* ``bench/ref/pypinyin_ref2`` — byte-identical copy of ``ref``, used to measure
  the benchmark's noise floor
* ``bench/layers/pypinyin_s1`` — fork with only the ``translate`` change
* ``bench/layers/pypinyin_s2`` — s1 + syllable cache
* ``bench/layers/pypinyin_s3`` — s2 + chunked segmentation (== the fork)

The upstream snapshot is taken from a git ref of ``python-pinyin``; pass the
path to a checkout with ``--upstream``.  Data files are shared with the main
package via ``tools/link_dict_data.py`` instead of being copied.

Usage::

    python tools/build_refs.py --upstream /path/to/python-pinyin
"""

from __future__ import print_function

import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: Files the fork actually changed, relative to the package root.  ``s1`` and
#: ``s2`` are defined by which subset they receive.
LAYER_FILES = {
    's1': ['style/_utils.py'],
    's2': [
        'style/_utils.py', 'style/__init__.py', 'converter.py',
        'style/initials.py', 'style/tone.py', 'style/others.py',
        'style/finals.py', 'style/bopomofo.py', 'style/cyrillic.py',
        'style/wadegiles.py', 'style/gwoyeu.py', 'style/braille_mainland.py',
    ],
    's3': [
        'style/_utils.py', 'style/__init__.py', 'converter.py',
        'style/initials.py', 'style/tone.py', 'style/others.py',
        'style/finals.py', 'style/bopomofo.py', 'style/cyrillic.py',
        'style/wadegiles.py', 'style/gwoyeu.py', 'style/braille_mainland.py',
        'constants.py', 'seg/simpleseg.py',
    ],
}

#: Subdirectories that only matter for distribution, not for running.
SKIP_DIRS = ('legacy', 'tools', '__pyinstaller', '__pycache__')


def copy_package(src, dst, rename_to):
    """Copy the package, keeping only what is needed to run it.

    The JSON dictionaries are copied too -- ``link_dict_data.py`` repoints the
    modules at the shared copy afterwards and deletes the local ones.  Copying
    first and deleting later keeps this script independent of whether
    ``link_dict_data.py`` has already run on the previous generation.
    """
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns(
            'legacy', 'tools', '__pyinstaller', '__pycache__'))
    rename_module(dst, rename_to)


def rename_module(root, new_name):
    """Rewrite ``import pypinyin`` to the copied module name."""
    pattern = re.compile(r'\bpypinyin\b')
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding='utf-8') as fp:
                src = fp.read()
            out = pattern.sub(new_name, src)
            if out != src:
                with open(path, 'w', encoding='utf-8', newline='\n') as fp:
                    fp.write(out)


def overlay(dst, files, rename_to):
    """Copy the fork's changed files on top of a reference copy."""
    for rel in files:
        src = os.path.join(ROOT, 'pypinyin', rel)
        target = os.path.join(dst, rel)
        with open(src, encoding='utf-8') as fp:
            text = fp.read()
        # 上游副本里用的是改名后的模块名，这里同步替换
        text = text.replace('pypinyin.', rename_to + '.')
        text = text.replace('from pypinyin import', 'from %s import' % rename_to)
        with open(target, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--upstream', default=None,
                    help='checkout of mozillazg/python-pinyin at the base commit')
    args = ap.parse_args()

    upstream = args.upstream
    if upstream is None:
        print('--upstream not given; leaving bench/ref untouched and only '
              'rebuilding bench/layers from the current bench/ref copy.')
        upstream = os.path.join(ROOT, 'bench', 'ref', 'pypinyin_ref')

    ref = os.path.join(ROOT, 'bench', 'ref')
    copy_package(os.path.join(upstream, 'pypinyin'),
                 os.path.join(ref, 'pypinyin_ref'), 'pypinyin_ref')
    copy_package(os.path.join(upstream, 'pypinyin'),
                 os.path.join(ref, 'pypinyin_ref2'), 'pypinyin_ref2')

    layers = os.path.join(ROOT, 'bench', 'layers')
    for name, files in LAYER_FILES.items():
        dst = os.path.join(layers, 'pypinyin_' + name)
        copy_package(os.path.join(upstream, 'pypinyin'), dst,
                     'pypinyin_' + name)
        overlay(dst, files, 'pypinyin_' + name)

    subprocess.check_call(
        [sys.executable, os.path.join(HERE, 'link_dict_data.py')], cwd=ROOT)
    print('done')


if __name__ == '__main__':
    main()
