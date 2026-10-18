# -*- coding: utf-8 -*-
"""Rewrite a commit message through the Git Data API.

Needed when ``git push`` cannot reach github.com (proxy down) but
``api.github.com`` is still reachable.  Only the message changes; the tree is
reused as-is, so the repository contents are untouched.

Usage::

    python tools/api_reword_commit.py <owner> <repo> <branch> <message-file>
"""
from __future__ import print_function

import base64
import json
import subprocess
import sys


def gh(*args, **kwargs):
    cmd = ['gh', 'api'] + list(args)
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    if kwargs.get('raw'):
        return out
    return json.loads(out.decode('utf-8'))


def main():
    owner, repo, branch, msg_path = sys.argv[1:5]
    with open(msg_path, encoding='utf-8') as fp:
        message = fp.read().strip()

    ref = gh('repos/%s/%s/git/ref/heads/%s' % (owner, repo, branch))
    old_sha = ref['object']['sha']
    commit = gh('repos/%s/%s/git/commits/%s' % (owner, repo, old_sha))
    print('current commit %s' % old_sha[:12])
    print('tree           %s' % commit['tree']['sha'][:12])

    payload = json.dumps({
        'message': message,
        'tree': commit['tree']['sha'],
        'parents': [p['sha'] for p in commit['parents']],
    })
    new = json.loads(subprocess.check_output(
        ['gh', 'api', '-X', 'POST',
         'repos/%s/%s/git/commits' % (owner, repo), '--input', '-'],
        input=payload.encode('utf-8')).decode('utf-8'))
    print('new commit     %s' % new['sha'][:12])

    result = json.loads(subprocess.check_output(
        ['gh', 'api', '-X', 'PATCH',
         'repos/%s/%s/git/refs/heads/%s' % (owner, repo, branch),
         '-F', 'sha=%s' % new['sha'], '-F', 'force=true']).decode('utf-8'))
    print('ref updated -> %s' % result['object']['sha'][:12])

    # tree 相同就证明文件内容逐字节一致
    check = gh('repos/%s/%s/git/commits/%s' % (owner, repo, new['sha']))
    assert check['tree']['sha'] == commit['tree']['sha'], 'tree changed!'
    print('tree unchanged, contents byte-identical')


if __name__ == '__main__':
    main()
