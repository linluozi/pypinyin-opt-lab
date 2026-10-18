# -*- coding: utf-8 -*-
"""Style.INITIALS 风格"""
from __future__ import unicode_literals

from pypinyin_s3.constants import Style
from pypinyin_s3.style import register
from pypinyin_s3.style._utils import get_initials


@register(Style.INITIALS, pure=True)
def convert(pinyin, **kwargs):
    strict = kwargs.get('strict', True)
    return get_initials(pinyin, strict)
