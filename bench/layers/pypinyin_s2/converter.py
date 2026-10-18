# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from pypinyin_s2.compat import text_type, callable_check
from pypinyin_s2.constants import (
    PHRASES_DICT, PINYIN_DICT,
    RE_HANS
)
from pypinyin_s2.contrib.uv import V2UMixin
from pypinyin_s2.contrib.neutral_tone import NeutralToneWith5Mixin
from pypinyin_s2.contrib.tone_sandhi import ToneSandhiMixin
from pypinyin_s2.exceptions import PinyinNotFoundException
from pypinyin_s2.utils import _remove_dup_and_empty
from pypinyin_s2.style import auto_discover
from pypinyin_s2.style import convert as convert_style
from pypinyin_s2.style import is_pure
from pypinyin_s2.style import generation as style_generation

auto_discover()


# [OPT] 音节级风格转换缓存 ------------------------------------------------
#
# 观察：一篇 1.6 万字的文章会吐出 9 千多个音节，其中只有 800 多个是「不同」
# 的 —— 「的」「是」「一」这类高频音节出现几百次（见 assets/fig4_hitrate.png）。
# 而风格转换是纯函数：同样的 (音节, 风格, strict, 配置) 永远得到同样的输出，
# 重复计算纯属浪费。
#
# 缓存按 (风格, strict, 配置) 分桶，键是原始带声调音节。命中时直接在
# ``convert_styles`` 里查表，一次 ``dict.get`` 取代整条五层调用链
# （见 assets/fig3_callchain.png）。
#
# 三条安全边界，任一不成立就退回上游的逐字路径：
#
# 1. 风格实现被标记为纯函数（``pure=True``）。内置 18 个风格逐一声明；用户
#    通过 ``register`` 注册的实现默认不算纯，除非自己显式声明 —— 这样
#    「输出依赖 han」的自定义风格绝不会被缓存串味。
# 2. 转换链上的方法全部来自白名单（``_SAFE_METHODS``）。用户子类只要覆盖了
#    ``convert_style`` / ``pre_convert_style`` / ``post_convert_style`` /
#    ``post_pinyin`` 中任何一个，就说明它有自己的算法，自动落到慢路径。
# 3. 风格注册表版本号未变。一旦有人重新注册风格，版本号 +1，整张缓存作废。
#
# 条目总数超过 ``_CACHE_LIMIT`` 即清空重来，避免超大的自定义词库撑爆内存。

_CACHE_LIMIT = 200000
_style_cache = {}
_cache_generation = -1
_cache_entries = 0

# [OPT] 快路径安全白名单
#
# ``_CACHED_METHODS`` 列出转换链上可被改写的方法名，``_SAFE_METHODS`` 在模块
# 末尾（所有类定义完成后）填入「确认与 han 无关」的函数对象。判断方式是按名
# 解析出真正生效的函数再比对身份 —— 因此任何自定义覆盖都会落到慢路径。
#
# 之所以只认身份而不认类名：用户完全可能写一个 ``class My(UltimateConverter)``
# 并覆盖 ``post_pinyin``，那已经是另一套算法，不能假设它与原版等价。
_CACHED_METHODS = (
    'convert_style',
    'pre_convert_style',
    'post_convert_style',
    'post_pinyin',
)
_SAFE_METHODS = set()
#: 类 -> 转换链是否安全，避免每次转换都走 MRO 查找
_CHAIN_SAFE_CACHE = {}


def _cache_bucket(*key):
    """取（或建）一个缓存桶，并在注册表变化时让整张缓存失效。

    :param key: 缓存键。至少包含风格与 strict，``UltimateConverter`` 还会
                把 v_to_u / 轻声 5 / 变调三个开关折进来。
    :return: dict，键为原始音节，值为该风格下的转换结果
    """
    global _cache_generation, _cache_entries

    gen = style_generation()
    if gen != _cache_generation:
        # 有人动过风格注册表，旧结果不再可信
        _style_cache.clear()
        _cache_entries = 0
        _cache_generation = gen

    bucket = _style_cache.get(key)
    if bucket is None:
        bucket = {}
        _style_cache[key] = bucket
    return bucket


def clear_style_cache():
    """清空音节级风格转换缓存。

    修改了风格实现、或在运行时给转换器类打了方法补丁、或需要回收这部分
    内存时调用。正常使用无需手动调用：重新注册风格会自动让缓存失效。
    """
    global _cache_entries
    _style_cache.clear()
    _cache_entries = 0
    _CHAIN_SAFE_CACHE.clear()


class Converter(object):

    def convert(self, words, style, heteronym, errors, strict, **kwargs):
        # TODO: use ``abc`` module
        raise NotImplementedError  # pragma: no cover


class DefaultConverter(Converter):

    def __init__(self, **kwargs):
        pass

    def convert(self, words, style, heteronym, errors, strict, **kwargs):
        """根据参数把汉字转成相应风格的拼音结果。

        :param words: 汉字字符串
        :type words: unicode
        :param style: 拼音风格
        :param heteronym: 是否启用多音字
        :type heteronym: bool
        :param errors: 如何处理没有拼音的字符
        :param strict: 只获取声母或只获取韵母相关拼音风格的返回结果
                       是否严格遵照《汉语拼音方案》来处理声母和韵母，
                       详见 :ref:`strict`
        :type strict: bool
        :return: 按风格转换后的拼音结果
        :rtype: list

        """
        pys = []
        # 初步过滤没有拼音的字符
        if RE_HANS.match(words):
            pys = self._phrase_pinyin(words, style=style, heteronym=heteronym,
                                      errors=errors, strict=strict)
            post_data = self.post_pinyin(words, heteronym, pys)
            if post_data is not None:
                pys = post_data

            pys = self.convert_styles(
                pys, words, style, heteronym, errors, strict)

        else:
            py = self.handle_nopinyin(words, style=style, errors=errors,
                                      heteronym=heteronym, strict=strict)
            if py:
                pys.extend(py)

        return _remove_dup_and_empty(pys)

    def pre_convert_style(self, han, orig_pinyin, style, strict, **kwargs):
        """在把原始带声调的拼音按拼音风格转换前会调用 ``pre_convert_style`` 方法。

        如果返回值不为 ``None`` 会使用返回的结果代替 ``orig_pinyin``
        来进行后面的风格转换。

        :param han: 要处理的汉字
        :param orig_pinyin: 汉字对应的原始带声调拼音
        :param style: 要转换的拼音风格
        :param strict: 只获取声母或只获取韵母相关拼音风格的返回结果
                       是否严格遵照《汉语拼音方案》来处理声母和韵母，
                       详见 :ref:`strict`
        :param kwargs: 其他关键字参数，暂时无用，用于以后扩展新的参数。
        :return: ``None`` 或代替 ``orig_pinyin`` 参与拼音风格转换的拼音字符串。

        """
        pass

    def convert_style(self, han, orig_pinyin, style, strict, **kwargs):
        """按 ``style`` 的值对 ``orig_pinyin`` 进行处理，返回处理后的拼音

        转换风格前会调用 ``pre_convert_style`` 方法，
        转换后会调用 ``post_convert_style`` 方法。

        :param han: 要处理的单个汉字
        :param orig_pinyin: 汉字对应的原始带声调拼音
        :param style: 拼音风格
        :param strict: 只获取声母或只获取韵母相关拼音风格的返回结果
                       是否严格遵照《汉语拼音方案》来处理声母和韵母，
                       详见 :ref:`strict`
        :param kwargs: 其他关键字参数，暂时无用，用于以后扩展新的参数。
        :return: 按拼音风格转换处理后的拼音

        """
        pre_data = self.pre_convert_style(
            han, orig_pinyin, style=style, strict=strict)
        if pre_data is not None:
            pinyin = pre_data
        else:
            pinyin = orig_pinyin

        converted_pinyin = self._convert_style(
            han, pinyin, style=style, strict=strict, default=pinyin)

        post_data = self.post_convert_style(
            han, pinyin, converted_pinyin, style=style, strict=strict)
        if post_data is None:
            post_data = converted_pinyin

        return post_data

    def post_convert_style(self, han, orig_pinyin, converted_pinyin,
                           style, strict, **kwargs):
        """在把原始带声调的拼音按拼音风格转换前会调用 ``pre_convert_style`` 方法。

        如果返回值不为 ``None`` 会使用返回的结果代替 ``converted_pinyin``
        作为拼音风格转换后的最终拼音结果。

        :param han: 要处理的汉字
        :param orig_pinyin: 汉字对应的原始带声调拼音
        :param converted_pinyin: 按拼音风格转换处理后的拼音
        :param style: 要转换的拼音风格
        :param strict: 只获取声母或只获取韵母相关拼音风格的返回结果
                       是否严格遵照《汉语拼音方案》来处理声母和韵母，
                       详见 :ref:`strict`
        :param kwargs: 其他关键字参数，暂时无用，用于以后扩展新的参数。
        :return: ``None`` 或代替 ``converted_pinyin`` 作为拼音风格转换后的拼音结果。

        """
        pass

    def pre_handle_nopinyin(self, chars, style, heteronym, errors,
                            strict, **kwargs):
        """处理没有拼音的字符串前会调用 ``pre_handle_nopinyin`` 方法。

        如果返回值不为 ``None`` 会使用返回的结果作为处理没有拼音字符串的结果，
        不再使用内置方法进行处理。

        :param chars: 待处理的没有拼音的字符串
        :param errors: 如何处理
        :param heteronym: 是否需要处理多音字
        :param kwargs: 其他关键字参数，暂时无用，用于以后扩展新的参数。
        :return: ``None`` 或代替 ``chars`` 参与拼音风格转换的拼音字符串
                  或拼音结果 list。

        """
        pass

    def handle_nopinyin(self, chars, style, heteronym, errors,
                        strict, **kwargs):
        """处理没有拼音的字符串。

        处理前会调用 ``pre_handle_nopinyin`` 方法，
        处理后会调用 ``post_handle_nopinyin`` 方法。

        :param chars: 待处理的没有拼音的字符串
        :param style: 拼音风格
        :param errors: 如何处理
        :param heteronym: 是否需要处理多音字
        :param strict: 只获取声母或只获取韵母相关拼音风格的返回结果
                       是否严格遵照《汉语拼音方案》来处理声母和韵母，
                       详见 :ref:`strict`
        :return: 处理后的拼音结果，如果为 ``None`` 或空 list 表示忽略这个字符串.
        :rtype: list
        """
        pre_data = self.pre_handle_nopinyin(
            chars, style, errors=errors, heteronym=heteronym, strict=strict)

        if pre_data is not None:
            py = pre_data
        else:
            pre_data = chars
            py = self._convert_nopinyin_chars(
                pre_data, style, errors=errors,
                heteronym=heteronym, strict=strict)

        post_data = self.post_handle_nopinyin(
            chars, style, errors=errors, heteronym=heteronym, strict=strict,
            pinyin=py)
        if post_data is not None:
            py = post_data

        if not py:
            return []
        if isinstance(py, list):
            # 包含多音字信息
            if isinstance(py[0], list):
                if heteronym:
                    return py
                # [[a, b], [c, d]]
                # [[a], [c]]
                return [[x[0]] for x in py]

            return [[i] for i in py]
        else:
            return [[py]]

    def post_handle_nopinyin(self, chars, style, heteronym,
                             errors, strict,
                             pinyin, **kwargs):
        """处理完没有拼音的字符串后会调用 ``post_handle_nopinyin`` 方法。

        如果返回值不为 ``None`` 会使用返回的结果作为处理没有拼音的字符串的结果。

        :param chars: 待处理的没有拼音的字符串
        :param errors: 如何处理
        :param heteronym: 是否需要处理多音字
        :param strict: 只获取声母或只获取韵母相关拼音风格的返回结果
                       是否严格遵照《汉语拼音方案》来处理声母和韵母，
                       详见 :ref:`strict`
        :param pinyin: 处理后的拼音信息，值为空 list 或包含拼音信息的 list
        :param kwargs: 其他关键字参数，暂时无用，用于以后扩展新的参数。
        :return: ``None`` 或代替 ``pinyin`` 做为处理结果。

        """
        pass

    def post_pinyin(self, han, heteronym, pinyin, **kwargs):
        """找到汉字对应的拼音后，会调用 ``post_pinyin`` 方法。

        如果返回值不为 ``None`` 会使用返回的结果作为 han 的拼音数据。

        :param han: 单个汉字或者词语
        :param heteronym: 是否需要处理多音字
        :param pinyin: 单个汉字的拼音数据或词语的拼音数据 list
        :type pinyin: list
        :param kwargs: 其他关键字参数，暂时无用，用于以后扩展新的参数。
        :return: ``None`` 或代替 ``pinyin`` 作为 han 的拼音 list。

        """
        pass

    def _phrase_pinyin(self, phrase, style, heteronym, errors, strict):
        """词语拼音转换.

        :param phrase: 词语
        :param errors: 指定如何处理没有拼音的字符
        :param strict: 只获取声母或只获取韵母相关拼音风格的返回结果
                       是否严格遵照《汉语拼音方案》来处理声母和韵母，
                       详见 :ref:`strict`
        :return: 拼音列表
        :rtype: list
        """
        pinyin_list = []
        if phrase in PHRASES_DICT:
            # [OPT] 词语库里每个词条的拼音都是嵌套 list，而下面的
            # ``convert_styles`` 只会整格替换（``pinyin_list[idx] = [...]``），
            # 从不原地改动内层 list。所以这里不需要 deepcopy 的完整性保证，
            # 只需要一层浅拷贝来隔开外层 list 的写入。实测 deepcopy 在本
            # 语料上占 17% 总耗时，浅拷贝后这部分几乎归零。
            #
            # 注意 ``heteronym`` 为真时会遍历内层 list（``for x in item``），
            # 但只读不写，因此浅拷贝同样安全。
            pinyin_list = [item[:] for item in PHRASES_DICT[phrase]]
        else:
            for han in phrase:
                py = self._single_pinyin(han, style, heteronym, errors, strict)
                pinyin_list.extend(py)

        return pinyin_list

    def convert_styles(self, pinyin_list, phrase, style, heteronym, errors,
                       strict, **kwargs):
        """转换多个汉字的拼音结果的风格

        [OPT] 快路径：当本转换器的风格转换链只由「已知与 han 无关」的实现
        组成时，逐字结果只取决于 (原音节, 风格, strict, 配置)，于是整段可以
        直接在缓存里查表 —— 一次 ``dict.get`` 取代
        「convert_style -> pre_convert_style -> _convert_style ->
        dict 查找 -> post_convert_style」这五层调用。实测这条链占单字总耗时
        的 69%，逐层调用是纯架构开销，缓存命中率再高也省不掉。

        慢路径保留上游原样，任何不在白名单里的改写都会自动落到这里。
        """
        cache_key = self._cache_key(style, strict)
        if cache_key is not None:
            bucket = _cache_bucket(cache_key)
            conv = self._conv_cached
            if heteronym:
                return [
                    [conv(bucket, x, style, strict, phrase[idx]) for x in item]
                    for idx, item in enumerate(pinyin_list)
                ]
            return [
                [conv(bucket, item[0], style, strict, phrase[idx])]
                for idx, item in enumerate(pinyin_list)
            ]

        for idx, item in enumerate(pinyin_list):
            han = phrase[idx]
            if heteronym:
                pinyin_list[idx] = [
                        self.convert_style(
                            han, orig_pinyin=x, style=style, strict=strict)
                        for x in item
                    ]
            else:
                orig_pinyin = item[0]
                pinyin_list[idx] = [
                    self.convert_style(
                        han, orig_pinyin=orig_pinyin, style=style,
                        strict=strict)]

        return pinyin_list

    # -- 快路径 -----------------------------------------------------------

    def _cache_key(self, style, strict):
        """返回该风格/模式下的缓存键；不适合缓存时返回 ``None``。

        默认实现：风格必须是纯函数，且本类的转换链未被改写，此时键就是
        ``(风格, strict)``。子类（如 ``UltimateConverter``）会把额外的配置
        折进键里，见 ``_build_cache_key``。
        """
        if not is_pure(style) or not self._chain_is_safe():
            return None
        return self._build_cache_key(style, strict)

    def _build_cache_key(self, style, strict):
        """子类覆盖这里来把额外配置折进缓存键。"""
        return (style, strict)

    def _chain_is_safe(self):
        """转换链上的每个可改写方法是否都来自「与 han 无关」的实现。

        逐个按方法解析（沿 MRO 找真正生效的那个函数），只接受白名单里的
        函数对象。任何用户自定义的覆盖 —— 哪怕只是无害地包一层 —— 都会让
        结果落到慢路径，宁可慢一点也不冒串味的风险。

        判定结果按类缓存：类一旦定义完，其方法解析关系就不会变（运行时给类
        打补丁这种极端用法下调用 ``clear_style_cache()`` 即可）。不做缓存时
        这个判断每次转换都要走 4 次 MRO 查找，实测占总耗时 12%。
        """
        cls = type(self)
        safe = _CHAIN_SAFE_CACHE.get(cls)
        if safe is None:
            safe = all(
                getattr(cls, name) in _SAFE_METHODS
                for name in _CACHED_METHODS
            )
            _CHAIN_SAFE_CACHE[cls] = safe
        return safe

    def _conv_cached(self, bucket, orig_pinyin, style, strict, han):
        """查表得到逐字**最终**结果，未命中才真正跑一遍完整转换链。

        缓存的是 ``convert_style`` 的返回值（已含 pre/post 加工），因此命中
        与未命中的结果逐字节相同；mixin 的配置已经体现在缓存键里。
        """
        if orig_pinyin in bucket:
            return bucket[orig_pinyin]

        value = self.convert_style(
            han, orig_pinyin=orig_pinyin, style=style, strict=strict)
        self._remember(bucket, orig_pinyin, value)
        return value

    def _single_pinyin(self, han, style, heteronym, errors, strict):
        """单字拼音转换.

        :param han: 单个汉字
        :param errors: 指定如何处理没有拼音的字符，详情请参考
                       :py:func:`~pypinyin_s2.pinyin`
        :param strict: 只获取声母或只获取韵母相关拼音风格的返回结果
                       是否严格遵照《汉语拼音方案》来处理声母和韵母，
                       详见 :ref:`strict`
        :return: 返回拼音列表，多音字会有多个拼音项
        :rtype: list
        """
        num = ord(han)
        # 处理没有拼音的字符
        if num not in PINYIN_DICT:
            return self.handle_nopinyin(
                han, style=style, errors=errors,
                heteronym=heteronym, strict=strict)

        pys = PINYIN_DICT[num].split(',')  # 字的拼音列表
        return [pys]

    def _convert_style(self, han, pinyin, style, strict, default,
                       **kwargs):
        """调用注册表里的风格实现。

        这里不做缓存：缓存统一在 ``convert_styles`` 的快路径里做（那一层能
        一次查完整段，省掉五层调用）。``_conv_cached`` 在未命中时调用的就是
        本方法，若这里再套一层缓存，会变成两份状态、两套失效逻辑。
        """
        if not kwargs:
            kwargs = {}
        kwargs['han'] = han

        return convert_style(pinyin, style, strict, default=default, **kwargs)

    # -- 缓存辅助 ---------------------------------------------------------

    @staticmethod
    def _remember(bucket, pinyin, value):
        """把一次转换结果写进缓存桶；条目数到达上限则整张清空重来。"""
        global _cache_entries
        if _cache_entries >= _CACHE_LIMIT:
            clear_style_cache()
        bucket[pinyin] = value
        _cache_entries += 1

    def _convert_nopinyin_chars(self, chars, style, heteronym, errors, strict):
        """转换没有拼音的字符。

        """
        if callable_check(errors):
            return errors(chars)

        if errors == 'default':
            return chars
        elif errors == 'ignore':
            return None
        elif errors == 'exception':
            raise PinyinNotFoundException(chars)
        elif errors == 'replace':
            if len(chars) > 1:
                return ''.join(text_type('%x' % ord(x)) for x in chars)
            else:
                return text_type('%x' % ord(chars))


class _v2UConverter(V2UMixin, DefaultConverter):
    pass


class _neutralToneWith5Converter(NeutralToneWith5Mixin, DefaultConverter):
    pass


class _toneSandhiConverter(ToneSandhiMixin, DefaultConverter):
    pass


class UltimateConverter(DefaultConverter):
    def __init__(self, v_to_u=False, neutral_tone_with_five=False,
                 tone_sandhi=False, **kwargs):
        super(UltimateConverter, self).__init__(**kwargs)
        self._v_to_u = v_to_u
        self._neutral_tone_with_five = neutral_tone_with_five
        self._tone_sandhi = tone_sandhi

    def _cache_config(self):
        """[OPT] 影响缓存结果的实例配置快照。"""
        return (
            bool(self._v_to_u),
            bool(self._neutral_tone_with_five),
            bool(self._tone_sandhi),
        )

    def _build_cache_key(self, style, strict):
        """[OPT] 把三个 mixin 开关折进缓存键。

        这三个开关都会改写逐字的最终结果（v→ü、轻声标 5、变调），但都不读
        han，因此「同一音节 + 同一开关组合」就等于同一结果。若不把它们折进
        键里，先调 ``v_to_u=True`` 再调 ``False`` 就会读到被污染的缓存。

        变调开关只影响 ``post_pinyin``（整词级），而 ``_conv_cached`` 缓存的
        是 ``convert_style`` 的返回值 —— 两者不重叠，但把它一并放进键里成本
        为零，也就不必在这个细节上留一个「需要记住」的例外。
        """
        return (style, strict) + self._cache_config()

    def post_convert_style(self, han, orig_pinyin, converted_pinyin,
                           style, strict, **kwargs):
        post_data = super(UltimateConverter, self).post_convert_style(
            han, orig_pinyin, converted_pinyin, style, strict, **kwargs)
        if post_data is not None:
            converted_pinyin = post_data

        if self._v_to_u:
            post_data = _v2UConverter().post_convert_style(
                han, orig_pinyin, converted_pinyin, style, strict, **kwargs)
            if post_data is not None:
                converted_pinyin = post_data

        if self._neutral_tone_with_five:
            post_data = _neutralToneWith5Converter().post_convert_style(
                han, orig_pinyin, converted_pinyin, style, strict, **kwargs)
            if post_data is not None:
                converted_pinyin = post_data

        return converted_pinyin

    def post_pinyin(self, han, heteronym, pinyin, **kwargs):
        post_data = super(UltimateConverter, self).post_pinyin(
            han, heteronym, pinyin, **kwargs)
        if post_data is not None:
            pinyin = post_data

        if self._tone_sandhi:
            post_data = _toneSandhiConverter().post_pinyin(
                han, heteronym, pinyin, **kwargs)
            if post_data is not None:
                pinyin = post_data

        return pinyin


_mixConverter = UltimateConverter


# [OPT] 填充快路径安全白名单。
#
# 这里列出的函数都已逐个核对：它们只读 (pinyin, style, strict) 与实例上的
# 开关，不读 han，因此对它们的结果做缓存是安全的。
#
# * ``DefaultConverter.convert_style`` —— 默认的 pre/post 钩子都是空实现
# * ``UltimateConverter.convert_style`` —— 继承默认实现
# * ``UltimateConverter.post_convert_style`` / ``post_pinyin`` ——
#   V2U / 轻声 5 / 变调三个 mixin 均不读 han
#
# ``pre_convert_style`` 与 ``post_convert_style`` 取的是 ``DefaultConverter``
# 上的空实现；``UltimateConverter`` 覆盖了 ``post_convert_style``，所以两个
# 类分别登记自己的那一版。
_SAFE_METHODS.update([
    DefaultConverter.convert_style,
    DefaultConverter.pre_convert_style,
    DefaultConverter.post_convert_style,
    DefaultConverter.post_pinyin,
    UltimateConverter.convert_style,
    UltimateConverter.post_convert_style,
    UltimateConverter.post_pinyin,
])
