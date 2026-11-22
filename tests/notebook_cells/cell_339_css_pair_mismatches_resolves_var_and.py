# Ported from fyp.ipynb cell 339 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _css_pair_mismatches resolves var() and skips non-computable
# keywords, and skips uncomputable values -- grid track lists and relative units
# (A1 + A1b, 2026-08-29). getComputedStyle reports the browser's USED value,
# so an expected 'var(--page-max-width)' (resolves to '1200px') or a bare
# 'margin: 0 auto' (resolves to used pixels) could never match and drove an
# unwinnable correction loop (PO-08 TC-021). The fix must ALSO still catch a
# genuinely wrong value, or it would silence real bugs.
def _a1_core():
    browser = _get_browser()
    page = browser.new_page()
    try:
        page.set_content(
            "<!doctype html><html><head><style>"
            ":root{--page-max-width:1200px;}"
            "#hero{max-width:var(--page-max-width);margin:0 auto;color:rgb(0, 0, 0);}"
            "</style></head><body><div id='hero'>x</div></body></html>"
        )
        return {
            "var_and_auto": _css_pair_mismatches(
                page, "#hero", "max-width=var(--page-max-width)|margin=0 auto"),
            "var_only": _css_pair_mismatches(
                page, "#hero", "max-width=var(--page-max-width)"),
            "real_bug": _css_pair_mismatches(
                page, "#hero", "color=rgb(255, 0, 0)"),
        }
    finally:
        page.close()

def _a1b_core():
    # A grid whose columns use repeat()/minmax()/fr and whose gap is a rem token.
    # getComputedStyle returns resolved pixels, so a string compare is unwinnable
    # -- these pairs must be SKIPPED (empty mismatches). A genuinely wrong px
    # value on a computable property (padding) must still be CAUGHT.
    browser = _get_browser()
    page = browser.new_page()
    try:
        page.set_content(
            "<!doctype html><html><head><style>"
            ":root{--grid-gap:1rem;}"
            "#grid{display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));"
            "gap:var(--grid-gap);padding:8px;}"
            "</style></head><body><div id='grid'><i></i><i></i></div></body></html>"
        )
        return {
            "grid_tracks": _css_pair_mismatches(
                page, "#grid", "grid-template-columns=repeat(2, minmax(0, 1fr))"),
            "gap_rem": _css_pair_mismatches(page, "#grid", "gap=var(--grid-gap)"),
            "real_px_bug": _css_pair_mismatches(page, "#grid", "padding=99px"),
        }
    finally:
        page.close()

_a1 = _pw_run(_a1_core)
assert _a1["var_and_auto"] == [], \
    f"A1 FAIL: var() must resolve to 1200px and 'auto' must be skipped, got {_a1['var_and_auto']}"
assert _a1["var_only"] == [], \
    f"A1 FAIL: a lone var() expected value must resolve and match, got {_a1['var_only']}"
assert _a1["real_bug"], \
    "A1 FAIL: a genuinely wrong colour must still be reported -- the fix must not disable real detection"

_a1b = _pw_run(_a1b_core)
assert _a1b["grid_tracks"] == [], \
    f"A1b FAIL: a repeat()/minmax()/fr track list must be skipped, got {_a1b['grid_tracks']}"
assert _a1b["gap_rem"] == [], \
    f"A1b FAIL: a rem-valued gap resolves to px and must be skipped, got {_a1b['gap_rem']}"
assert _a1b["real_px_bug"], \
    "A1b FAIL: a genuinely wrong px value on a computable property must still be caught"

assert _has_uncomputable_value("repeat(2, minmax(0, 1fr))")
assert _has_uncomputable_value("1rem") and _has_uncomputable_value("0.5fr")
assert _has_uncomputable_value("clamp(1rem, 4vw, 3.5rem)")
assert not _has_uncomputable_value("16px") and not _has_uncomputable_value("rgb(0, 0, 0)")
assert _has_noncomputable_keyword("0 auto")
assert _has_noncomputable_keyword("inherit")
assert not _has_noncomputable_keyword("1200px")
assert not _has_noncomputable_keyword("rgb(0, 0, 0)")
print("[A1] PASS: var() resolved, 'auto'/keywords skipped, real mismatches still caught")
print("[A1b] PASS: grid track lists and relative units skipped, real px bugs still caught")

# A1c: an authored transform must be resolved to the matrix getComputedStyle
# reports, so a CORRECT stylesheet passes -- while a genuinely wrong transform
# is still caught. Before this, 'translateY(-2px)' vs 'matrix(1, 0, 0, 1, 0, -2)'
# failed forever (PO-08 TC-064, 2026-08-30).
def _a1c_core():
    browser = _get_browser()
    page = browser.new_page()
    try:
        page.set_content(
            "<!doctype html><html><head><style>"
            "#card{transform:translateY(-2px);}"
            "#flat{transform:none;}"
            "#pc{transform:translateX(50%);}"
            "</style></head><body>"
            "<div id='card'>a</div><div id='flat'>b</div><div id='pc'>c</div>"
            "</body></html>"
        )
        return {
            "authored_form": _css_pair_mismatches(
                page, "#card", "transform=translateY(-2px)"),
            "rem_form": _css_pair_mismatches(
                page, "#card", "transform=translateY(-0.125rem)"),
            "wrong_transform": _css_pair_mismatches(
                page, "#card", "transform=translateY(-99px)"),
            "none_form": _css_pair_mismatches(page, "#flat", "transform=none"),
            "percent_skipped": _css_pair_mismatches(
                page, "#pc", "transform=translateX(50%)"),
        }
    finally:
        page.close()

_a1c = _pw_run(_a1c_core)
assert _a1c["authored_form"] == [],     f"A1c FAIL: translateY(-2px) must resolve to the browser's matrix, got {_a1c['authored_form']}"
assert _a1c["rem_form"] == [],     f"A1c FAIL: a rem transform must resolve too, not be skipped as a relative unit, got {_a1c['rem_form']}"
assert _a1c["wrong_transform"],     "A1c FAIL: a genuinely wrong transform must still be reported"
assert _a1c["none_form"] == [],     f"A1c FAIL: transform=none must still compare as-is, got {_a1c['none_form']}"
assert _a1c["percent_skipped"] == [],     f"A1c FAIL: a percentage transform is box-relative and must be skipped, got {_a1c['percent_skipped']}"
print("[A1c] PASS: authored transforms resolve to the computed matrix, wrong ones still caught")

# A1d: a percentage length resolves to the used pixel value -- exactly the rem/fr
# situation one class wider. 'width=100%' on a full-width box computes to a px
# number and can never string-match, so it must be SKIPPED (po015df552 assert_css
# false failures). A genuinely wrong DISCRETE property (display) is still CAUGHT.
def _a1d_core():
    browser = _get_browser()
    page = browser.new_page()
    try:
        page.set_content(
            "<!doctype html><html><head><style>"
            "#col{display:flex;width:100%;padding-left:50%;}"
            "</style></head><body><div id='col'>x</div></body></html>"
        )
        return {
            "width_pct":   _css_pair_mismatches(page, "#col", "width=100%"),
            "padding_pct": _css_pair_mismatches(page, "#col", "padding-left=50%"),
            "real_bug":    _css_pair_mismatches(page, "#col", "display=grid"),
        }
    finally:
        page.close()

_a1d = _pw_run(_a1d_core)
assert _a1d["width_pct"] == [],   f"A1d FAIL: a percentage width must be skipped, got {_a1d['width_pct']}"
assert _a1d["padding_pct"] == [], f"A1d FAIL: a percentage padding must be skipped, got {_a1d['padding_pct']}"
assert _a1d["real_bug"], "A1d FAIL: a wrong discrete property (display) must still be reported"
print("[A1d] PASS: percentage lengths skipped like rem/fr, real discrete bugs still caught")

# A1e: a re-serialised shorthand (box-shadow, transition, ...) never string-matches
# the computed value -- the browser rewrites it (colour first, lengths to px,
# defaults filled). Skip by PROPERTY NAME; a wrong value on a normal longhand
# (color) is still CAUGHT.
def _a1e_core():
    browser = _get_browser()
    page = browser.new_page()
    try:
        page.set_content(
            "<!doctype html><html><head><style>"
            "#b{box-shadow:0 4px 6px rgba(0,0,0,0.1);transition:all 0.2s ease;color:rgb(0, 0, 0);}"
            "</style></head><body><div id='b'>x</div></body></html>"
        )
        return {
            "box_shadow": _css_pair_mismatches(page, "#b", "box-shadow=0 4px 6px rgba(0,0,0,0.1)"),
            "transition": _css_pair_mismatches(page, "#b", "transition=all 0.2s ease"),
            "real_bug":   _css_pair_mismatches(page, "#b", "color=rgb(255, 0, 0)"),
        }
    finally:
        page.close()

_a1e = _pw_run(_a1e_core)
assert _a1e["box_shadow"] == [], f"A1e FAIL: box-shadow must be skipped by property name, got {_a1e['box_shadow']}"
assert _a1e["transition"] == [], f"A1e FAIL: transition must be skipped by property name, got {_a1e['transition']}"
assert _a1e["real_bug"], "A1e FAIL: a wrong colour on a normal longhand must still be reported"
print("[A1e] PASS: re-serialised shorthands skipped by name, real longhand bugs still caught")

print(f"[proof] assert_css skip table widened: 'width=100%' now yields {len(_a1d['width_pct'])} "
      f"mismatch(es) and 'box-shadow' {len(_a1e['box_shadow'])} (each was 1 permanent false "
      f"failure on po015df552, e.g. TC-018/020/048/052/054). A wrong display still yields "
      f"{len(_a1d['real_bug'])} and a wrong colour {len(_a1e['real_bug'])}, so real bugs stay caught.")


# A1f: four notation-equivalent forms the browser re-serialises, so an authored
# value can never string-match the computed one (PO-10 po0735889c). Each must be
# treated as a match (empty mismatches); a genuinely wrong value is still CAUGHT.
def _a1f_core():
    browser = _get_browser()
    page = browser.new_page()
    try:
        page.set_content(
            "<!doctype html><html><head><style>"
            "#e{background-color:transparent;background-position:center;"
            "width:fit-content;font-family:'Inter', system-ui, sans-serif;}"
            "#real{background-color:rgb(0, 128, 0);}"
            "</style></head><body><div id='e'>x</div><div id='real'>y</div></body></html>"
        )
        return {
            "transparent": _css_pair_mismatches(page, "#e", "background-color=transparent"),
            "bg_center":   _css_pair_mismatches(page, "#e", "background-position=center"),
            "fit_content": _css_pair_mismatches(page, "#e", "width=fit-content"),
            "font_quotes": _css_pair_mismatches(page, "#e", "font-family='Inter', system-ui, sans-serif"),
            "real_bug":    _css_pair_mismatches(page, "#real", "background-color=rgb(255, 0, 0)"),
        }
    finally:
        page.close()

_a1f = _pw_run(_a1f_core)
assert _a1f["transparent"] == [], f"A1f FAIL: 'transparent' must equal rgba(0, 0, 0, 0), got {_a1f['transparent']}"
assert _a1f["bg_center"] == [],   f"A1f FAIL: background-position 'center' must be skipped, got {_a1f['bg_center']}"
assert _a1f["fit_content"] == [], f"A1f FAIL: 'fit-content' must be skipped like a sizing keyword, got {_a1f['fit_content']}"
assert _a1f["font_quotes"] == [], f"A1f FAIL: font-family quotes must be ignored, got {_a1f['font_quotes']}"
assert _a1f["real_bug"], "A1f FAIL: a genuinely wrong background-color must still be reported"
print("[A1f] PASS: transparent/center/fit-content/font-quotes treated as matches, real bugs still caught")
print(f"[proof] assert_css notation-equivalence widened (PO-10 po0735889c): "
      f"transparent->{len(_a1f['transparent'])}, bg-position center->{len(_a1f['bg_center'])}, "
      f"fit-content->{len(_a1f['fit_content'])}, font-family quotes->{len(_a1f['font_quotes'])} "
      f"mismatch(es) (each was 1 permanent false failure: TC-006/010/020/035). A wrong "
      f"background-color still yields {len(_a1f['real_bug'])}, so real bugs stay caught.")


# A1g: the Test Generation model sometimes writes a property name in the JS
# camelCase form ('borderRadius') instead of the dashed CSS form. getPropertyValue
# recognises ONLY the dashed name, so a camelCase name reads back as '' and a
# correct stylesheet fails forever (PO-10 TC-004/005/006/008/010..., all "got ''").
# The kebab normaliser makes the camelCase name measure the real value; a genuinely
# wrong value is still CAUGHT, and the already-dashed form is unaffected.
def _a1g_core():
    browser = _get_browser()
    page = browser.new_page()
    try:
        page.set_content(
            "<!doctype html><html><head><style>"
            "#x{border-radius:10px;font-size:14px;font-weight:600;"
            "white-space:nowrap;min-width:24px;}"
            "</style></head><body><div id='x'>x</div></body></html>"
        )
        return {
            "camel_radius": _css_pair_mismatches(page, "#x", "borderRadius=10px"),
            "camel_multi":  _css_pair_mismatches(
                page, "#x",
                "fontSize=14px|fontWeight=600|whiteSpace=nowrap|minWidth=24px"),
            "kebab_radius": _css_pair_mismatches(page, "#x", "border-radius=10px"),
            "camel_wrong":  _css_pair_mismatches(page, "#x", "borderRadius=99px"),
        }
    finally:
        page.close()

_a1g = _pw_run(_a1g_core)
assert _a1g["camel_radius"] == [], f"A1g FAIL: a matching camelCase borderRadius must pass, got {_a1g['camel_radius']}"
assert _a1g["camel_multi"] == [], f"A1g FAIL: matching camelCase multi-word props must pass, got {_a1g['camel_multi']}"
assert _a1g["kebab_radius"] == [], f"A1g FAIL: the dashed form must still pass (no regression), got {_a1g['kebab_radius']}"
assert _a1g["camel_wrong"], "A1g FAIL: a genuinely wrong camelCase value must still be reported"
print("[A1g] PASS: camelCase property names measured correctly, dashed form unaffected, real bugs still caught")
print(f"[proof] assert_css camelCase normalised (PO-10): 'borderRadius=10px' -> {len(_a1g['camel_radius'])} "
      f"mismatch(es), a 4-pair camelCase batch -> {len(_a1g['camel_multi'])}; BEFORE the fix each read back "
      f"'' and was 1 permanent false failure (PO-10 TC-004/005/006/008/010, 39 failures total, all \"got ''\"). "
      f"A wrong 'borderRadius=99px' still yields {len(_a1g['camel_wrong'])} and the dashed 'border-radius=10px' "
      f"still {len(_a1g['kebab_radius'])}, so real bugs and the existing dashed path are intact.")


# A1h: an inline-level display on a flex or grid ITEM blockifies to its block twin,
# and getComputedStyle reports that used value. So an authored 'inline-flex' child of
# a flex/grid parent reads back 'flex' and the keyword can never string-match (PO-08
# TC-016/018/022/024/027/031/035/048, 8 permanent false failures, all "got flex").
# The blockify equivalence treats the twin as a match; a display in a NON-flex parent
# is unchanged, and a genuinely wrong display is still CAUGHT.
def _a1h_core():
    browser = _get_browser()
    page = browser.new_page()
    try:
        page.set_content(
            "<!doctype html><html><head><style>"
            ".fbar{display:flex}.gbar{display:grid}.plain{display:block}"
            ".bf{display:inline-flex}.bg{display:inline-grid}"
            "</style></head><body>"
            "<div class='fbar'><button class='bf' id='a'>a</button></div>"
            "<div class='gbar'><button class='bg' id='gi'>g</button></div>"
            "<div class='plain'><button class='bf' id='c'>c</button></div>"
            "</body></html>"
        )
        return {
            "flex_child":  _css_pair_mismatches(page, "#a",  "display=inline-flex"),
            "grid_child":  _css_pair_mismatches(page, "#gi", "display=inline-grid"),
            "block_child": _css_pair_mismatches(page, "#c",  "display=inline-flex"),
            "wrong_grid":  _css_pair_mismatches(page, "#a",  "display=grid"),
            "wrong_inline_block": _css_pair_mismatches(page, "#a", "display=inline-block"),
        }
    finally:
        page.close()

_a1h = _pw_run(_a1h_core)
assert _a1h["flex_child"] == [],  f"A1h FAIL: inline-flex blockified to flex must match, got {_a1h['flex_child']}"
assert _a1h["grid_child"] == [],  f"A1h FAIL: inline-grid blockified to grid must match, got {_a1h['grid_child']}"
assert _a1h["block_child"] == [], f"A1h FAIL: inline-flex in a block parent stays inline-flex and must match, got {_a1h['block_child']}"
assert _a1h["wrong_grid"], "A1h FAIL: expecting grid on a flex item (got flex) must still be reported"
assert _a1h["wrong_inline_block"], "A1h FAIL: expecting inline-block (->block) on a flex item (got flex) must still be reported"
print("[A1h] PASS: inline-* display blockified on a flex/grid item treated as a match, block-parent and real display bugs still caught")
print(f"[proof] assert_css display blockification (PO-08 po014f3528): 'display=inline-flex' on a flex-item -> "
      f"{len(_a1h['flex_child'])} mismatch(es) and 'inline-grid' on a grid-item -> {len(_a1h['grid_child'])}; "
      f"BEFORE the fix each read back 'flex'/'grid' and was 1 permanent false failure (8 of PO-08's 15: "
      f"TC-016/018/022/024/027/031/035/048). A wrong 'display=grid' still yields {len(_a1h['wrong_grid'])} and "
      f"'inline-block'->block still {len(_a1h['wrong_inline_block'])}, so real display bugs stay caught.")
