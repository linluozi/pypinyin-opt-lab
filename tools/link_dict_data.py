# -*- coding: utf-8 -*-
"""Point the reference/layer copies at the main package's dictionary JSON.

Keeping three 2.5 MB copies of ``phrases_dict.json`` inside the repo would add
~14 MB for no reason.  Each copy gets a relative path back to ``pypinyin/``
instead.  Run this after regenerating ``bench/ref`` or ``bench/layers``.
"""
from __future__ import print_function

import os
import sys

BASES = [
    'bench/ref/pypinyin_ref',
    'bench/ref/pypinyin_ref2',
    'bench/layers/pypinyin_s1',
    'bench/layers/pypinyin_s2',
    'bench/layers/pypinyin_s3',
]

MARKER = '_json_path = '


def patch(base, fn, jsonname):
    """Point one module at the shared JSON.  Idempotent: re-running is a no-op."""
    path = os.path.join(base, fn)
    with open(path, encoding='utf-8') as fp:
        src = fp.read()

    rel = os.path.relpath('pypinyin', base).replace(os.sep, '/')
    new = (
        '_current_dir = os.path.dirname(os.path.realpath(__file__))\n'
        '# 数据文件不复制：直接读主包的 JSON，避免仓库里存多份 2.5 MB 词库\n'
        '_json_path = os.path.normpath(os.path.join(\n'
        '    _current_dir, %r, %r))\n'
    ) % (rel, jsonname)

    if "os.path.normpath(os.path.join(" in src:
        # 已经打过补丁：只确保那份复制出来的 JSON 不留在仓库里
        copied = os.path.join(base, jsonname)
        if os.path.exists(copied):
            os.remove(copied)
        return False

    start = src.index('_current_dir = ')
    end = src.index('\n', src.index(MARKER)) + 1
    with open(path, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(src[:start] + new + src[end:])

    copied = os.path.join(base, jsonname)
    if os.path.exists(copied):
        os.remove(copied)
    return True


def main():
    for base in BASES:
        if not os.path.isdir(base):
            print('skip %s (missing)' % base)
            continue
        changed = patch(base, 'pinyin_dict.py', 'pinyin_dict.json')
        changed |= patch(base, 'phrases_dict.py', 'phrases_dict.json')
        print('%s %s' % ('patched' if changed else 'already ok', base))
    return 0


if __name__ == '__main__':
    sys.exit(main())
