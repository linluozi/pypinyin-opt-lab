# -*- coding: utf-8 -*-
"""其他几个拼音风格实现:

Style.NORMAL
Style.FIRST_LETTER
"""
from __future__ import unicode_literals

from pypinyin_s2.constants import Style
from pypinyin_s2.style import register
from pypinyin_s2.style._utils import replace_symbol_to_no_symbol


class OthersConverter(object):
    def to_normal(self, pinyin, **kwargs):
        pinyin = replace_symbol_to_no_symbol(pinyin)
        return pinyin

    def to_first_letter(self, pinyin, **kwargs):
        # 用数字表示声调
        pinyin = self.to_normal(pinyin)
        return pinyin[0]


converter = OthersConverter()
register(Style.NORMAL, func=converter.to_normal, pure=True)
register(Style.FIRST_LETTER, func=converter.to_first_letter, pure=True)
