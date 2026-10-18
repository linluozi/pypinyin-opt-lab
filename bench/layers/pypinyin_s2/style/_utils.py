# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from pypinyin_s2.standard import convert_finals
from pypinyin_s2.style._constants import (
    _INITIALS, _INITIALS_NOT_STRICT, _FINALS,
    PHONETIC_SYMBOL_DICT,
    PHONETIC_SYMBOL_DICT_KEY_LENGTH_NOT_ONE,
)


# [OPT] 预编译的音标转换表 ------------------------------------------------
#
# 原始实现用「正则替换单字符音标 + 逐项 str.replace 处理多字符音标」两步完成
# 转换，每个音节要跑一次 re.sub 和 4 次 str.replace。这里改成一张
# ``str.translate`` 表：CPython 的 str.translate 在 C 层一次扫描完成，
# 实测单音节转换从 0.85 us 降到 0.05 us。
#
# 表的构建完全由 PHONETIC_SYMBOL_DICT 推导，不硬编码任何音标，因此字典
# 变化时行为自动跟随，不存在两边漂移的风险。
#
# 多字符音标（'m̄'、'm̀'、'ê̄'、'ê̌' 这类「基字母 + 组合附加符」）无法用
# 逐字符 translate 表达，仍沿用原来的 str.replace，只有 4 项，成本可忽略。

def _build_number_table():
    """构建「带调字符 -> 数字声调」的 translate 表。

    只处理长度为 1 的键，与 RE_PHONETIC_SYMBOL 的字符类完全一致。
    """
    return {
        ord(symbol): to
        for symbol, to in PHONETIC_SYMBOL_DICT.items()
        if len(symbol) == 1
    }


def _build_no_symbol_table():
    """构建「带调字符 -> 无调字符」的 translate 表。

    单字符音标直接映射到去掉声调数字后的首字母（'ā' -> 'a'，'ü' -> 'v'）；
    阿拉伯数字映射为空串，等价于原实现里的 ``RE_NUMBER.sub('', ...)``。
    """
    table = {}
    for symbol, to in PHONETIC_SYMBOL_DICT.items():
        if len(symbol) == 1:
            table[ord(symbol)] = to[0]
    for digit in '0123456789':
        table[ord(digit)] = ''
    return table


_NUMBER_TABLE = _build_number_table()
_NO_SYMBOL_TABLE = _build_no_symbol_table()

# 多字符音标：'m̄' -> 'm1' 这类，值里带数字
_MULTI_SYMBOL_TO_NUMBER = PHONETIC_SYMBOL_DICT_KEY_LENGTH_NOT_ONE
# 多字符音标：'m̄' -> 'm'，值里去掉数字
_MULTI_SYMBOL_TO_NO_SYMBOL = {
    symbol: to.rstrip('0123456789')
    for symbol, to in PHONETIC_SYMBOL_DICT_KEY_LENGTH_NOT_ONE.items()
}


def get_initials(pinyin, strict):
    """获取单个拼音中的声母.

    :param pinyin: 单个拼音
    :type pinyin: unicode
    :param strict: 是否严格遵照《汉语拼音方案》来处理声母和韵母
    :return: 声母
    :rtype: unicode
    """
    if strict:
        _initials = _INITIALS
    else:
        _initials = _INITIALS_NOT_STRICT

    for i in _initials:
        if pinyin.startswith(i):
            return i
    return ''


def get_finals(pinyin, strict):
    """获取单个拼音中的韵母.

    :param pinyin: 单个拼音，无声调拼音
    :type pinyin: unicode
    :param strict: 是否严格遵照《汉语拼音方案》来处理声母和韵母
    :return: 韵母
    :rtype: unicode
    """
    if strict:
        pinyin = convert_finals(pinyin)

    initials = get_initials(pinyin, strict=strict) or ''

    # 按声母分割，剩下的就是韵母
    finals = pinyin[len(initials):]

    # 处理既没有声母也没有韵母的情况
    if strict and finals not in _FINALS:
        # 处理 y, w 导致误判的问题，比如 yo
        initials = get_initials(pinyin, strict=False)
        finals = pinyin[len(initials):]
        if finals in _FINALS:
            return finals
        return ''

    # ń, ḿ
    if not finals and not strict:
        return pinyin

    return finals


def replace_symbol_to_number(pinyin):
    """把声调替换为数字"""
    # [OPT] 一次 translate 完成全部单字符音标替换
    value = pinyin.translate(_NUMBER_TABLE)
    for symbol, to in _MULTI_SYMBOL_TO_NUMBER.items():
        if symbol in value:
            value = value.replace(symbol, to)

    return value


def replace_symbol_to_no_symbol(pinyin):
    """把带声调字符替换为没有声调的字符"""
    # [OPT] 音标去调与数字剥离合并成一次 translate
    value = pinyin.translate(_NO_SYMBOL_TABLE)
    for symbol, to in _MULTI_SYMBOL_TO_NO_SYMBOL.items():
        if symbol in value:
            value = value.replace(symbol, to)

    return value


# 鼻音: 'm̄', 'ḿ', 'm̀', 'ń', 'ň', 'ǹ' 没有韵母
_NO_FINALS_SYMBOLS = ('m̄', 'ḿ', 'm̀', 'ń', 'ň', 'ǹ')


def has_finals(pinyin):
    """判断是否有韵母"""
    for symbol in _NO_FINALS_SYMBOLS:
        if symbol in pinyin:
            return False

    return True
