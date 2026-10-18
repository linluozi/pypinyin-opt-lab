# NOTICE — what this fork changes

Upstream: [`mozillazg/python-pinyin`](https://github.com/mozillazg/python-pinyin),
commit `8595294b1a97845e30f11ecfdb3caa4e61ac3988` (v0.55.0), MIT licensed.
Original copyright (c) 2016 mozillazg, 闲耘 — retained in `LICENSE.txt`.

This fork is distributed under the same MIT licence. Every changed region is
marked with an `[OPT]` comment in the source, so a diff against upstream is
readable without external notes.

## Files changed

| File | Change |
|---|---|
| `pypinyin/style/_utils.py` | `str.translate` tables for tone-symbol conversion; dropped two now-unused regex imports |
| `pypinyin/style/__init__.py` | `pure` flag on `register()`, `is_pure()`, `generation()`, `_install()` |
| `pypinyin/style/{initials,tone,others,finals,bopomofo,cyrillic,wadegiles,gwoyeu,braille_mainland}.py` | added `pure=True` to each built-in `register()` call (18 styles) |
| `pypinyin/converter.py` | syllable-level cache, `convert_styles` fast path, chain-safety whitelist, `deepcopy` → list-copy, `clear_style_cache()` |
| `pypinyin/constants.py` | `RE_HANS_CHUNKS`, derived from `RE_HANS.pattern` |
| `pypinyin/seg/simpleseg.py` | `_seg()` uses `RE_HANS_CHUNKS.findall`; per-character loop kept as `_seg_by_char` fallback |

## Files added

| File | Purpose |
|---|---|
| `tests/test_equivalence.py` | differential + structural tests against a pristine upstream copy |
| `bench/bench.py` | paired benchmark, one workload per process |
| `bench/run_bench.py` | benchmark driver |
| `bench/ablation.py` | adjacent-pair attribution |
| `bench/ref/`, `bench/layers/` | pristine upstream and step-wise builds, for the diff and the ablation |
| `tools/make_figures.py` | regenerates `assets/*.png` from the JSON results |
| `README.md` | replaces upstream's `README.rst` as the primary document; upstream's is kept as `README.upstream.rst` |

## Public API

No breaking changes. `lazy_pinyin`, `pinyin`, `slug`, `load_single_dict`,
`load_phrases_dict`, `Style`, `Pinyin`, `DefaultConverter`,
`UltimateConverter` and `register()` all keep their signatures.

Two additive changes:

* `register(style, func=None, pure=False)` — new optional keyword. Existing
  calls behave exactly as before (`pure` defaults to `False`, i.e. no caching).
* `pypinyin.converter.clear_style_cache()` — new function.

## Behaviour that is deliberately preserved

* Empty string still segments to `['']`, not `[]`.
* A style registered without `pure=True` is never cached, so a style that reads
  `han` produces exactly the same output as upstream.
* Subclasses that override any of `convert_style`, `pre_convert_style`,
  `post_convert_style` or `post_pinyin` take the upstream per-character path.
* `PHRASES_DICT` and `PINYIN_DICT` are never mutated by a conversion.
