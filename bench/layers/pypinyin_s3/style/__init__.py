# -*- coding: utf-8 -*-
from functools import wraps

# 存储各拼音风格对应的实现
_registry = {}

# [OPT] 记录「纯」风格实现：输出只由 (pinyin, strict) 决定，不依赖 han 等
# 上下文参数。只有这类实现才能进入转换结果缓存，详见 converter 模块。
#
# 内置的 18 个风格在各自模块里以 ``register(..., pure=True)`` 显式登记；
# 用户通过 ``register`` 注册的实现默认不算纯函数，除非显式声明 ``pure=True``。
_pure_styles = set()

# [OPT] 注册表版本号：每次注册新实现就 +1，供缓存判断是否需要整体失效。
_generation = 0


def convert(pinyin, style, strict, default=None, **kwargs):
    """根据拼音风格把原始拼音转换为不同的格式

    :param pinyin: 原始有声调的单个拼音
    :type pinyin: unicode
    :param style: 拼音风格
    :param strict: 只获取声母或只获取韵母相关拼音风格的返回结果
                   是否严格遵照《汉语拼音方案》来处理声母和韵母，
                   详见 :ref:`strict`
    :type strict: bool
    :param default: 拼音风格对应的实现不存在时返回的默认值
    :param kwargs: 兼容后续可能会新增的关键字参数。当前包含如下关键字参数:
                   ``han``: 当前拼音对应的原始汉字。

    :return: 按照拼音风格进行处理过后的拼音字符串
    :rtype: unicode
    """
    if style in _registry:
        return _registry[style](pinyin, strict=strict, **kwargs)
    return default


def is_pure(style):
    """该风格实现是否为纯函数（可安全缓存）。

    :param style: 拼音风格
    :return: 是纯函数返回 ``True``
    """
    return style in _pure_styles


def generation():
    """当前风格注册表的版本号，每次注册都会自增。

    缓存层用它判断「有没有人重新注册过风格」，从而决定是否整体失效。
    """
    return _generation


def _install(style, func, pure):
    """把实现写入注册表，并同步「纯函数」标记与注册表版本号。"""
    global _generation
    _registry[style] = func
    if pure:
        _pure_styles.add(style)
    else:
        _pure_styles.discard(style)
    _generation += 1


def register(style, func=None, pure=False):
    """注册一个拼音风格实现。
    自定义的函数应当使用 ``**kwargs`` 来兼容后续可能会新增的关键字参数，
    当前默认会传递如下参数：

    * ``pinyin``: 原始有声调的单个拼音
    * ``strict``: 是否开启 strict 模式
    * ``han``: 当前拼音对应的原始汉字

    :param pure: 声明该实现是纯函数，即返回值只由 ``pinyin`` 与 ``strict``
                 决定、不读取 ``han`` 等上下文参数。声明为纯函数后，其结果会
                 被按音节缓存，从而跳过重复的风格转换；如果实现实际依赖了
                 ``han``，请勿声明 ``pure=True``，否则结果会串味。

    ::

        @register('echo')
        def echo(pinyin, **kwargs):
            return pinyin

        # or
        register('echo', echo)
    """
    if func is not None:
        _install(style, func, pure)
        return

    def decorator(func):
        _install(style, func, pure)

        @wraps(func)
        def wrapper(pinyin, **kwargs):
            return func(pinyin, **kwargs)

        return wrapper
    return decorator


def auto_discover():
    """自动注册内置的拼音风格实现。

    每个内置风格都在自己的模块里以 ``pure=True`` 显式登记，因此这里不需要
    再做「谁是新导入的」这类推断 —— 早期实现曾用导入前后做差集的办法自动
    标记，但 ``pypinyin_s3.style.tone`` 会被其它模块提前导入，导致 TONE 系列
    风格漏标、缓存静默失效。显式声明没有这个盲区。
    """
    from pypinyin_s3.style import (  # noqa
        initials,
        tone,
        finals,
        bopomofo,
        cyrillic,
        wadegiles,
        others,
        gwoyeu,
        braille_mainland,
    )
