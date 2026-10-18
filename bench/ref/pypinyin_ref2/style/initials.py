# -*- coding: utf-8 -*-
"""Style.INITIALS 风格"""
from __future__ import unicode_literals

from pypinyin_ref2.constants import Style
from pypinyin_ref2.style import register
from pypinyin_ref2.style._utils import get_initials


@register(Style.INITIALS)
def convert(pinyin, **kwargs):
    strict = kwargs.get('strict', True)
    return get_initials(pinyin, strict)
