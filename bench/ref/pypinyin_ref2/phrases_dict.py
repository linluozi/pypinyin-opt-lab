# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from codecs import open
import json
import os

_current_dir = os.path.dirname(os.path.realpath(__file__))
# 数据文件不复制：直接读主包的 JSON，避免仓库里存多份 2.5 MB 词库
_json_path = os.path.normpath(os.path.join(
    _current_dir, '../../../pypinyin', 'phrases_dict.json'))

phrases_dict = {}


def _load_phrases_dict():
    global phrases_dict
    with open(_json_path, encoding='utf8') as fp:
        phrases_dict = json.loads(fp.read())


_load_phrases_dict()
