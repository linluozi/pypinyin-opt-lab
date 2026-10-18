# -*- coding: utf-8 -*-
"""Publish one commit through the Git Data API when ``git push`` is blocked.

Only the *delta* is uploaded: every blob whose bytes already exist in the
remote tree keeps its remote SHA, so adding two files does not re-upload the
whole repository.  Before the branch ref moves, the assembled tree SHA is
compared with the local ``HEAD^{tree}`` -- and only if they are equal, meaning
every file is byte-identical, does the script move the ref.

Usage::

    python tools/api_publish.py <owner> <repo> <branch>
"""

from __future__ import print_function

import base64
import json
import subprocess
import sys


def run(cmd, stdin=None):
    return subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)


def git(*args):
    proc = run(['git'] + list(args))
    if proc.returncode:
        raise SystemExit(proc.stderr.decode('utf-8', 'replace'))
    return proc.stdout


def git_str(*args):
    return git(*args).decode('utf-8').strip()


def api(path, data=None, method=None):
    cmd = ['gh', 'api']
    if method:
        cmd += ['-X', method]
    cmd.append(path)
    payload = None
    if data is not None:
        cmd += ['--input', '-']
        payload = json.dumps(data).encode('utf-8')
    proc = run(cmd, stdin=payload)
    if proc.returncode:
        raise SystemExit(proc.stderr.decode('utf-8', 'replace'))
    return json.loads(proc.stdout.decode('utf-8'))


def local_entries(rev):
    """``git ls-tree`` of a tree object as a list of dicts."""
    out = git_str('ls-tree', '-z', rev)
    entries = []
    for line in out.split('\0'):
        if not line:
            continue
        meta, path = line.split('\t', 1)
        mode, otype, sha = meta.split()
        entries.append({'path': path, 'mode': mode, 'type': otype, 'sha': sha})
    return entries


def remote_subtree_map(remote_tree_sha, prefix=''):
    """Flatten the remote tree to ``{path: (mode, type, sha)}``.

    Non-recursive API calls per directory rather than one recursive call,
    because the recursive form lists entries relative to the tree it was asked
    for, and mixing the two makes path joining error-prone.
    """
    data = api('repos/%s/%s/git/trees/%s' % (OWNER, REPO, remote_tree_sha))
    out = {}
    for e in data.get('tree', []):
        path = prefix + e['path']
        out[path] = (e['mode'], e['type'], e['sha'])
        if e['type'] == 'tree':
            out.update(remote_subtree_map(e['sha'], path + '/'))
    return out


def upload_blob(sha):
    content = git('cat-file', 'blob', sha)
    blob = api('repos/%s/%s/git/blobs' % (OWNER, REPO), data={
        'content': base64.b64encode(content).decode('ascii'),
        'encoding': 'base64',
    })
    return blob['sha']


def main():
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    global OWNER, REPO
    OWNER, REPO, branch = sys.argv[1:4]

    local_head = git_str('rev-parse', 'HEAD')
    local_tree = git_str('rev-parse', 'HEAD^{tree}')
    remote_head = api('repos/%s/%s/git/ref/heads/%s' % (OWNER, REPO, branch))
    remote_head = remote_head['object']['sha']
    remote_root = api('repos/%s/%s/git/commits/%s'
                      % (OWNER, REPO, remote_head))['tree']['sha']

    print('local  %s  tree %s' % (local_head[:12], local_tree[:12]))
    print('remote %s  tree %s' % (remote_head[:12], remote_root[:12]))
    if local_tree == remote_root:
        print('trees already identical; nothing to do')
        return

    known = remote_subtree_map(remote_root)

    # 递归重建整棵树：未变化的 blob 复用远端 sha，变化的才上传。
    #
    # 子目录不能「按路径命中就复用远端 tree sha」—— 一个目录里新增了文件，
    # 它自己的 tree sha 就必然变，但路径没变。正确做法是递归下去按内容判断，
    # 只有当某个子目录里所有条目都逐字节相同时，它重算出来的 tree sha 才会
    # 与远端一致（Git 的 tree sha 由内容决定，这正是它可信的原因）。
    def rebuild(tree_rev, prefix):
        entries = []
        for e in local_entries(tree_rev):
            path = prefix + e['path']
            if e['type'] == 'tree':
                sha = rebuild(e['sha'], path + '/')
                entries.append({'path': e['path'], 'mode': e['mode'],
                                'type': 'tree', 'sha': sha})
                continue

            hit = known.get(path)
            if hit and hit[0] == e['mode'] and hit[2] == e['sha']:
                sha = e['sha']
            else:
                sha = upload_blob(e['sha'])
                print('  uploaded %s' % path)
            entries.append({'path': e['path'], 'mode': e['mode'],
                            'type': 'blob', 'sha': sha})
        tree = api('repos/%s/%s/git/trees' % (OWNER, REPO),
                   data={'tree': entries})
        return tree['sha']

    new_tree = rebuild(local_tree, '')
    print('assembled tree %s' % new_tree[:12])
    if new_tree != local_tree:
        raise SystemExit('ABORT: tree mismatch (%s != %s); contents differ, '
                         'branch not moved' % (new_tree, local_tree))

    message = git_str('log', '-1', '--format=%B', local_head)
    new_commit = api('repos/%s/%s/git/commits' % (OWNER, REPO), data={
        'message': message,
        'tree': new_tree,
        'parents': [remote_head],
    })
    print('commit %s' % new_commit['sha'][:12])

    api('repos/%s/%s/git/refs/heads/%s' % (OWNER, REPO, branch),
        data={'sha': new_commit['sha'], 'force': True})
    print('branch %s moved to %s' % (branch, new_commit['sha'][:12]))
    print('remote tree == local tree, contents byte-identical')


OWNER = REPO = None

if __name__ == '__main__':
    main()
