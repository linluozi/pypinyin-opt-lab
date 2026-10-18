# -*- coding: utf-8 -*-
"""Compare the remote repository tree with the working copy.

Verifies three things, in this order of cheapness:

1. every local file exists on the remote, with the same byte count;
2. no file exists only on the remote (a stale artifact from an earlier push);
3. for a sample of binary/text files, the content round-trips byte-for-byte
   through the contents API.

This is the check that matters before claiming "the repository is pushed" --
``git ls-remote`` only proves a ref moved, not that the ref points at the right
content.

Usage::

    python tools/verify_remote.py <owner> <repo> [--sample 8]
"""
from __future__ import print_function

import base64
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def api(path):
    out = subprocess.check_output(['gh', 'api', path], stderr=subprocess.PIPE)
    return json.loads(out.decode('utf-8'))


def remote_files(owner, repo):
    def walk(path=''):
        endpoint = 'repos/%s/%s/contents' % (owner, repo)
        if path:
            endpoint += '/' + path
        for item in api(endpoint):
            if item['type'] == 'dir':
                for sub in walk(item['path']):
                    yield sub
            else:
                yield item['path'], item['size']
    return dict(walk())


def local_files():
    """Files git would actually track -- not everything on disk.

    ``__pycache__`` and ``*.pyc`` are ignored, so counting them as "missing on
    the remote" would report a false mismatch.  ``git ls-files`` is the
    authoritative list.
    """
    out = subprocess.check_output(
        ['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8')
    result = {}
    for rel in out.split('\0'):
        if not rel:
            continue
        result[rel] = os.path.getsize(os.path.join(ROOT, rel))
    return result


def fetch_bytes(owner, repo, path):
    """Read a file's bytes through the contents API.

    The contents API returns an **empty** ``content`` field for files above
    1 MB (it only offers ``git_url`` there), so those cannot be compared this
    way.  Returning ``None`` lets the caller skip them with an explicit note
    instead of reporting a bogus difference.
    """
    data = api('repos/%s/%s/contents/%s' % (owner, repo, path))
    if not data.get('content'):
        return None
    return base64.b64decode(data['content'])


def fetch_blob_bytes(owner, repo, path):
    """Bytes of a file, working for any size.

    Small files go through ``contents`` (one call).  Large ones go through the
    git blob API, addressed by the blob SHA that ``contents`` still reports.
    """
    data = api('repos/%s/%s/contents/%s' % (owner, repo, path))
    if data.get('content'):
        return base64.b64decode(data['content'])
    blob = api('repos/%s/%s/git/blobs/%s' % (owner, repo, data['sha']))
    if blob.get('encoding') != 'base64':
        return None
    return base64.b64decode(blob['content'])


def main():
    owner, repo = sys.argv[1:3]
    sample = 8
    if '--sample' in sys.argv:
        sample = int(sys.argv[sys.argv.index('--sample') + 1])

    local = local_files()
    remote = remote_files(owner, repo)
    print('local files %d, remote files %d' % (len(local), len(remote)))

    missing = sorted(set(local) - set(remote))
    extra = sorted(set(remote) - set(local))
    size_diff = sorted(p for p in set(local) & set(remote)
                       if local[p] != remote[p])

    ok = True
    if missing:
        print('MISSING on remote (%d): %r' % (len(missing), missing[:6]))
        ok = False
    if extra:
        print('EXTRA on remote (%d): %r' % (len(extra), extra[:6]))
        ok = False
    if size_diff:
        print('SIZE differs (%d):' % len(size_diff))
        for p in size_diff[:6]:
            print('   %-50s local=%d remote=%d' % (p, local[p], remote[p]))
        ok = False

    # 抽样逐字节比对：优先挑大文件，它们最容易被传输改动；
    # 超过 1 MB 的走 git blob API 而不是 contents，否则拿到空 content
    candidates = sorted(
        (p for p in local if p in remote),
        key=lambda p: -local[p])[:sample]
    skipped = []
    for path in candidates:
        with open(os.path.join(ROOT, path), 'rb') as fp:
            mine = fp.read()
        theirs = fetch_blob_bytes(owner, repo, path)
        if theirs is None:
            skipped.append(path)
            continue
        same = mine == theirs
        print('  %-52s %s' % (path, 'byte-identical' if same else 'DIFFERS'))
        if not same:
            ok = False
    for path in skipped:
        print('  %-52s skipped (no inline content)' % path)

    print('RESULT:', 'OK' if ok else 'MISMATCH')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
