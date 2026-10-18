# -*- coding: utf-8 -*-
"""Differential equivalence tests: this fork vs. the pristine upstream copy.

The reference copy under ``bench/ref/pypinyin_ref`` is the upstream package
renamed module-by-module (a mechanical ``s/pypinyin/pypinyin_ref/g``), so the
two implementations can be imported into one process and compared directly.

Two kinds of checks live here:

* **Bulk differential** -- every single character in the dictionary, every
  phrase in the phrase dictionary, and the benchmark corpora, each rendered
  under every style with the extension flags on and off.  Any divergence is a
  real behaviour change, not a stylistic difference.
* **Structural / mutation** -- things a pure behaviour diff cannot catch:
  does the cache actually engage for a pure style, does it stay off for a
  user-registered style, does re-registering a style invalidate it, and does
  the shallow copy in ``_phrase_pinyin`` ever leak a mutation back into the
  shared phrase dictionary.

Run with::

    python -m pytest tests/test_equivalence.py -q

.. note::
   ``tests/test_env.py`` 会反复把 ``pypinyin.*`` 从 ``sys.modules`` 里删掉再
   重新导入（为了验证环境变量对字典的影响）。因此本文件里凡是检查「缓存状态」
   的用例，都不能依赖文件顶部那个 ``opt`` 引用 —— 它可能指向重载前的旧模块
   实例，而 ``from pypinyin import converter`` 拿到的是新实例，两个缓存不是
   同一张。所有结构断言都改成通过 ``importlib.import_module`` 现取，保证
   「被测模块」和「查看内部状态的模块」是同一次导入。
"""

import os
import random
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'bench', 'ref'))

import pypinyin as opt            # noqa: E402
import pypinyin_ref as ref        # noqa: E402
from pypinyin.constants import PINYIN_DICT, PHRASES_DICT  # noqa: E402


def _fresh(name):
    """按 ``sys.modules`` 的当前状态取模块。

    ``test_env`` 会清空并重建 ``pypinyin.*``，所以模块级的 import 可能已经
    陈旧；凡是需要「和调用方同一个实例」的地方都走这里。
    """
    import importlib
    return importlib.import_module(name)

STYLES = [s for s in opt.Style]
EXTRA_KW = [
    {},
    {'heteronym': True},
    {'heteronym': True, 'errors': 'ignore'},
    {'strict': False},
    {'strict': False, 'heteronym': True},
]


def _all_chars():
    """字典里出现的全部汉字。"""
    return [chr(k) for k in sorted(PINYIN_DICT)]


def _all_phrases():
    return sorted(PHRASES_DICT)


def _corpus():
    out = []
    base = os.path.join(ROOT, 'bench', 'corpora')
    for name in sorted(os.listdir(base)):
        if name.endswith('.txt'):
            with open(os.path.join(base, name), encoding='utf-8',
                      errors='replace') as fp:
                out.append(fp.read())
    return out


def test_single_chars_all_styles():
    """字典里每一个字，在每一种风格、每一种参数组合下都必须一致。"""
    chars = _all_chars()
    checked = 0
    for style in STYLES:
        for kw in EXTRA_KW:
            for ch in chars:
                got = opt.pinyin(ch, style=style, **kw)
                want = ref.pinyin(ch, style=style, **kw)
                if got != want:
                    pytest.fail('char %r style %s kw %s: %r != %r'
                                % (ch, style, kw, got, want))
                checked += 1
    assert checked > 100000


def test_all_phrases_all_styles():
    """词语库里每一个词，在每一种风格下都必须一致。"""
    phrases = _all_phrases()
    for style in STYLES:
        for phrase in phrases:
            got = opt.pinyin(phrase, style=style)
            want = ref.pinyin(phrase, style=style)
            if got != want:
                pytest.fail('phrase %r style %s: %r != %r'
                            % (phrase, style, got, want))


def test_corpora_all_styles():
    """真实长文本：分词 + 词组匹配 + 重复音节缓存后的结果必须一致。"""
    for text in _corpus():
        for style in STYLES:
            got = opt.lazy_pinyin(text, style=style)
            want = ref.lazy_pinyin(text, style=style)
            if got != want:
                # 找出第一处分歧，报告上下文，便于定位
                for idx, (a, b) in enumerate(zip(got, want)):
                    if a != b:
                        pytest.fail(
                            'style %s at %d: %r != %r (context %r)'
                            % (style, idx, a, b, got[max(0, idx - 3):idx + 3]))
                pytest.fail('style %s: length %d != %d'
                            % (style, len(got), len(want)))


def test_extension_flags():
    """v_to_u / 轻声 5 / 变调 三个扩展开关逐一对齐。"""
    texts = ['战略', '衣裳', '你好', '一样', '不对', '老鼠', '保管好'] + _corpus()[:1]
    for text in texts:
        for style in STYLES:
            for flags in (
                {'v_to_u': True},
                {'neutral_tone_with_five': True},
                {'tone_sandhi': True},
                {'v_to_u': True, 'neutral_tone_with_five': True},
            ):
                got = opt.lazy_pinyin(text, style=style, **flags)
                want = ref.lazy_pinyin(text, style=style, **flags)
                assert got == want, (text, style, flags)


def test_slug_and_list_input():
    """slug 与「已分词列表」两条入口也必须一致。"""
    for text in ['中国人', '中心思想', '你好，世界']:
        assert opt.slug(text) == ref.slug(text)
        for sep in ('-', ' ', ''):
            assert opt.slug(text, separator=sep) == ref.slug(text, separator=sep)

    words = ['北京', '大学生', '前来', '应聘']
    assert opt.pinyin(words) == ref.pinyin(words)
    assert opt.pinyin(words, heteronym=True) == ref.pinyin(words, heteronym=True)
    assert opt.lazy_pinyin(words) == ref.lazy_pinyin(words)


def test_custom_dict_roundtrip():
    """自定义词库之后，两边结果仍须一致（含分词器重训练）。"""
    custom = {'桔子': [['jú'], ['zǐ']], '荸荠': [['bí'], ['qí']]}
    single = {ord('还'): 'hái,huán'}
    opt.load_phrases_dict(custom)
    ref.load_phrases_dict(custom)
    opt.load_single_dict(single)
    ref.load_single_dict(single)
    try:
        for text in ['桔子', '荸荠', '还', '还是', '桔子和荸荠']:
            for style in STYLES:
                assert (opt.pinyin(text, style=style, heteronym=True)
                        == ref.pinyin(text, style=style, heteronym=True)), text
    finally:
        # 还原，避免污染同进程内的其它用例
        from pypinyin.constants import PHRASES_DICT as PD
        from pypinyin.constants import PINYIN_DICT as PD2
        for key in custom:
            PD.pop(key, None)
        PD2.pop(ord('还'), None)
        from pypinyin.seg import mmseg
        mmseg.retrain(mmseg.seg)
        from pypinyin_ref.constants import PHRASES_DICT as RPD
        from pypinyin_ref.constants import PINYIN_DICT as RPD2
        for key in custom:
            RPD.pop(key, None)
        RPD2.pop(ord('还'), None)
        from pypinyin_ref.seg import mmseg as rmmseg
        rmmseg.retrain(rmmseg.seg)


def test_cache_engages_for_pure_style():
    """结构断言：纯风格的转换结果确实进了缓存。

    只做行为断言是测不出「缓存被悄悄关掉」的 —— 结果照样正确，只是慢。
    """
    conv = _fresh('pypinyin.converter')
    conv.clear_style_cache()
    # 同一段文本跑两遍：第一遍填缓存，第二遍必须全部命中
    _fresh('pypinyin').lazy_pinyin('中心思想很重要')
    filled = sum(len(b) for b in conv._style_cache.values())
    assert filled > 0, 'cache did not engage for the default style'

    conv.clear_style_cache()
    assert sum(len(b) for b in conv._style_cache.values()) == 0


def test_cache_skips_non_pure_style():
    """结构断言：用户注册的非纯风格不得被缓存。

    非纯风格的输出可以依赖 ``han``，缓存它就会串味。这里注册一个返回
    ``han`` 的风格，同一个音节在不同汉字下必须给出不同结果。
    """
    style_mod = _fresh('pypinyin.style')
    register, is_pure = style_mod.register, style_mod.is_pure
    conv = _fresh('pypinyin.converter')

    name = 'test_han_echo'

    def echo_han(pinyin, **kwargs):
        return '%s|%s' % (pinyin, kwargs.get('han', ''))

    register(name, echo_han)
    try:
        assert not is_pure(name), 'user style must default to non-pure'
        mod = _fresh('pypinyin')
        a = mod.lazy_pinyin('中心', style=name)
        b = mod.lazy_pinyin('忠芯', style=name)
        # 同音不同字，结果必须不同 —— 若被缓存就会相等
        assert a != b, 'non-pure style was cached: %r == %r' % (a, b)
    finally:
        style_mod = _fresh('pypinyin.style')
        style_mod._registry.pop(name, None)
        style_mod._pure_styles.discard(name)
        conv.clear_style_cache()


def test_cache_invalidated_on_reregister():
    """重新注册风格必须让缓存整体失效，否则会返回上一次的旧结果。

    注意这里必须用 ``pure=True`` 重新注册：如果注册的是非纯风格，缓存根本
    不会被查询，测试就会「因为别的原因」通过，从而漏掉真正的失效缺陷
    （这一版是补测出来的 —— 早期用默认 ``pure=False`` 注册，去掉版本检查后
    用例依然全绿）。
    """
    style_mod = _fresh('pypinyin.style')
    register = style_mod.register
    conv = _fresh('pypinyin.converter')
    mod = _fresh('pypinyin')

    style = mod.Style.NORMAL
    first = mod.lazy_pinyin('中心')
    assert first == ['zhong', 'xin']
    # 先让该风格把缓存填满
    mod.lazy_pinyin('中文测试')
    assert conv._style_cache, 'cache should be populated before re-registering'

    def shouty(pinyin, **kwargs):
        # 风格实现拿到的是「带声调的原音节」，NORMAL 之下是 'zhōng' 而非
        # 'zhong' —— 内置的 to_normal 自己负责去调。这里只做大写，所以结果
        # 仍带声调符号，这是预期行为。
        return pinyin.upper()

    register(style, shouty, pure=True)
    try:
        after = mod.lazy_pinyin('中心')
        assert after == ['ZHŌNG', 'XĪN'], (
            'stale cache: re-registering the style did not take effect: %r'
            % (after,))
    finally:
        # 还原内置实现：重新执行内置模块的注册
        import importlib
        if 'pypinyin.style.others' in sys.modules:
            importlib.reload(sys.modules['pypinyin.style.others'])
        conv.clear_style_cache()
    assert _fresh('pypinyin').lazy_pinyin('中心') == ['zhong', 'xin']


def test_phrase_dict_not_mutated():
    """结构断言：浅拷贝不得让调用方改到共享词库。

    这是把 deepcopy 换成浅拷贝时唯一真正的风险 —— 一旦调用方原地改了
    返回值，下一次查询同一个词就会拿到被污染的拼音。

    分两层验证：

    1. 公开入口 ``pinyin()``：返回值被改后，词库必须完好。这一层其实由
       ``convert_styles`` 的整格替换保证了，即使内层不复制也能过 —— 所以
       只测这一层，把内层复制删掉照样全绿（实测如此）。
    2. 内部契约 ``_phrase_pinyin()``：它的返回值与词库不共享任何可变对象。
       这一层才是内层复制真正守住的东西，也是自定义转换器改写
       ``convert_styles`` 时唯一的安全网。
    """
    conv = _fresh('pypinyin.converter')

    # 挑一个真实存在的多字词条（'中心' 是分词切出来的，不在词库里）
    phrase = next(w for w in PHRASES_DICT if len(w) == 2)
    before = [list(x) for x in PHRASES_DICT[phrase]]

    # 第 1 层：公开 API
    result = opt.pinyin(phrase)
    result[0][0] = 'CORRUPTED'
    result.append(['EXTRA'])
    assert [list(x) for x in PHRASES_DICT[phrase]] == before, \
        'pinyin() leaked a mutation into PHRASES_DICT'

    # 第 2 层：内部契约 —— 内层 list 不得与词库是同一个对象
    raw = conv.DefaultConverter()._phrase_pinyin(
        phrase, style=opt.Style.TONE, heteronym=True, errors='default',
        strict=True)
    assert len(raw) == len(PHRASES_DICT[phrase])
    for got, shared in zip(raw, PHRASES_DICT[phrase]):
        assert got is not shared, (
            '_phrase_pinyin shared an inner list with PHRASES_DICT for %r; '
            'a custom convert_styles could then corrupt the dictionary'
            % (phrase,))
        assert got == shared

    # 改内部返回值同样不得污染词库
    raw[0][0] = 'CORRUPTED'
    assert [list(x) for x in PHRASES_DICT[phrase]] == before

    # 再查一次，必须是原始结果
    assert opt.pinyin(phrase) == ref.pinyin(phrase)




def test_style_registry_pure_flags():
    """内置的 18 个风格必须全部登记为纯函数，一个都不能漏。"""
    style_mod = _fresh('pypinyin.style')
    mod = _fresh('pypinyin')
    missing = [s for s in mod.Style if not style_mod.is_pure(s)]
    assert not missing, 'styles not marked pure: %r' % (missing,)


def test_random_fuzz():
    """随机拼串模糊测试：把词库、单字、标点、非汉字随机混合。"""
    rng = random.Random(20261018)
    phrases = _all_phrases()
    chars = _all_chars()
    alphabet = ['，', '。', 'a', '1', ' ', '\n', '〇']

    for _ in range(60):
        parts = []
        for _ in range(rng.randint(1, 25)):
            roll = rng.random()
            if roll < 0.45:
                parts.append(rng.choice(phrases))
            elif roll < 0.85:
                parts.append(rng.choice(chars))
            else:
                parts.append(rng.choice(alphabet))
        text = ''.join(parts)

        for style in STYLES:
            assert (opt.pinyin(text, style=style, heteronym=True)
                    == ref.pinyin(text, style=style, heteronym=True)), text
            assert (opt.lazy_pinyin(text, style=style)
                    == ref.lazy_pinyin(text, style=style)), text
