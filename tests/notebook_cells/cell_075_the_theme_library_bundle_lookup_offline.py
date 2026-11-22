# Ported from fyp.ipynb cell 75 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the theme library + bundle lookup  (offline, no LLM)
_TL = 0

# TL-1: no schema -> the default theme
_t = _build_token_bundle()
assert _t["label"] == "Warm artisanal", _t
_TL += 1
print("PASS TL-1 - no schema falls back to warm-artisanal")

# TL-2: an explicit design_schema.theme.name is honoured (and normalised)
_t2 = _build_token_bundle({"theme": {"name": "Warm Artisanal"}})
assert _t2 is _THEME_LIBRARY["warm-artisanal"], _t2
_TL += 1
print("PASS TL-2 - theme.name is read and normalised")

# TL-3: an unknown theme falls back, never raises
_t3 = _build_token_bundle({"theme": {"name": "neon-cyberpunk"}})
assert _t3["label"] == "Warm artisanal", _t3
_TL += 1
print("PASS TL-3 - an unknown theme falls back to the default")

# TL-4: a malformed schema never raises
for _bad in (None, {}, {"theme": None}, {"theme": "x"}, "nope", 5):
    assert _build_token_bundle(_bad)["label"] == "Warm artisanal"
_TL += 1
print("PASS TL-4 - a malformed schema degrades to the default, never crashes")

# TL-5: the bundle clears the Design Token Contract floor by construction
assert len(_THEME_LIBRARY[_THEME_DEFAULT]["tokens"]) >= 6, "below the :root floor"
_root = _theme_root_block(_build_token_bundle())
assert _root.startswith(":root {") and "--color-accent" in _root
_TL += 1
print("PASS TL-5 - >=6 tokens and a valid :root block (clears the CSS token floor)")

# TL-6: the six DesignTokens buckets are filled from the flat token list
_gt = _bundle_global_tokens(_build_token_bundle())
assert set(_gt) == {"colors", "typography", "spacing", "borders", "shadows", "radii"}
assert _gt["colors"].get("--color-accent") == "#b5642a", _gt["colors"]
assert _gt["typography"].get("--font-heading") and _gt["spacing"] and _gt["radii"] and _gt["shadows"]
_TL += 1
print("PASS TL-6 - flat tokens group into the six DesignTokens buckets")

# TL-7: the decoration instruction carries the verbatim tokens + the fonts
_blk = _theme_tokens_block(_build_token_bundle())
assert "globalTokens EXACTLY" in _blk and "#b5642a" in _blk and "Fraunces" in _blk, _blk
_TL += 1
print("PASS TL-7 - the tokens block names the fonts and the exact colour values")

# TL-8: every theme in the library is well-formed (>=6 tokens, groups fill)
for _tname, _tb in _THEME_LIBRARY.items():
    assert {"label", "mood", "google_fonts", "tokens", "type_scale_px"} <= set(_tb), _tname
    assert len(_tb["tokens"]) >= 6, f"{_tname}: below the :root floor"
    _g = _bundle_global_tokens(_tb)
    assert _g["colors"] and _g["typography"], f"{_tname}: colours/typography empty"
_TL += 1
print(f"PASS TL-8 - all {len(_THEME_LIBRARY)} themes are well-formed")

# TL-9: every theme name reaches the Context Engineering prompt (no drift)
_cat = _theme_choice_catalog()
for _n in _THEME_LIBRARY:
    assert _n in _cat, f"{_n} missing from the theme catalog"
_ce_rendered = _intent_extraction_prompt.format(query="x", theme_catalog=_cat)
for _n in _THEME_LIBRARY:
    assert _n in _ce_rendered, f"{_n} never reaches the CE prompt"
_TL += 1
print(f"PASS TL-9 - all {len(_THEME_LIBRARY)} theme names reach the CE prompt")

# TL-10: the shared layout preset rides in every bundle's globalTokens, and the
# theme's own spacing survives alongside it
_gt_lay = _bundle_global_tokens(_build_token_bundle())
for _k in ("--page-gutter", "--grid-min", "--card-aspect", "--section-gap"):
    assert _k in _gt_lay["spacing"], f"{_k} missing from globalTokens spacing"
assert "--space-4" in _gt_lay["spacing"], "the theme's own spacing was dropped"
_TL += 1
print("PASS TL-10 - the shared layout preset is folded into every bundle")

assert _TL == 10
print(f"theme library: {_TL}/10 PASSED")
