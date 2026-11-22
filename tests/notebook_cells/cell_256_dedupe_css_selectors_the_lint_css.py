# Ported from fyp.ipynb cell 256 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _dedupe_css_selectors + the _lint_css_source dedupe wrapper.
# Collapsing duplicate top-level selectors is the Group 3 fix for PO-10
# po0735889c, where the CSS modify agent appended a second .product-rating /
# .deal-countdown / .add-to-cart block (each holding the fix) instead of editing
# the first in place, so stylelint's no-duplicate-selectors failed, the fix loop
# capped, and the duplicate shipped. The merge is cascade- and !important-aware,
# so it renders identically.
def _dd_balanced(css):
    d = 0
    for ch in css:
        if ch == "{": d += 1
        elif ch == "}": d -= 1
        if d < 0: return False
    return d == 0

def _dd_sel_hits(css, sel):
    return len(re.findall(re.escape(sel) + r"\s*\{", css))

# 1 simple duplicate: the later value wins, one rule remains
_o, _k = _dedupe_css_selectors(".x{color:red}\n.x{color:blue}")
assert _k == 1 and "blue" in _o and "red" not in _o and _dd_sel_hits(_o, ".x") == 1

# 2 union of properties across the two copies is preserved
_o, _k = _dedupe_css_selectors(".x{color:red;font-size:2px}\n.x{color:blue}")
assert _k == 1 and "blue" in _o and "font-size: 2px" in _o and _dd_sel_hits(_o, ".x") == 1

# 3 a same-selector rule INSIDE @media is a different context -> left untouched
_src3 = ".x{a:1px}\n@media (max-width:5px){.x{a:2px}}\n.x{a:3px}"
_o, _k = _dedupe_css_selectors(_src3)
assert _k == 1 and "@media (max-width:5px){.x{a:2px}}" in _o and _dd_sel_hits(_o, ".x") == 2

# 4 an earlier !important is NOT clobbered by a later normal value
_o, _k = _dedupe_css_selectors(".x{color:red !important}\n.x{color:blue}")
assert _k == 1 and "red !important" in _o and "blue" not in _o
# 4b but a later !important does win over an earlier normal value
_o, _k = _dedupe_css_selectors(".x{color:red}\n.x{color:blue !important}")
assert _k == 1 and "blue !important" in _o and "red" not in _o

# 5 an interleaved third selector -> the merged rule keeps the LAST position, so
# the cascade against other equal-specificity selectors is unchanged
_o, _k = _dedupe_css_selectors(".x{a:1px}\n.y{a:2px}\n.x{a:3px}")
assert _k == 1 and "a: 3px" in _o and _o.find(".x") > _o.find(".y") and _dd_sel_hits(_o, ".x") == 1

# 6 no duplicate -> byte-for-byte identity (zero risk on the clean common case)
_src6 = ".a{c:1}\n.b{c:2}\n@media(x){.a{c:9}}"
_o, _k = _dedupe_css_selectors(_src6)
assert _k == 0 and _o == _src6

# 7 a multi-selector list duplicated with different spacing still merges
_o, _k = _dedupe_css_selectors(".a, .b{x:1px}\n.a,.b{x:2px}")
assert _k == 1 and "x: 2px" in _o and "1px" not in _o

# 8 the po0735889c shape: three duplicated selectors, all collapsed, valid CSS
_src8 = (".product-rating{display:flex}\n.deal-countdown{color:red}\n.add-to-cart{p:1px}\n"
         "/* tail block appended by modify */\n"
         ".product-rating{display:inline-flex}\n.deal-countdown{color:blue}\n.add-to-cart{p:2px}")
_o, _k = _dedupe_css_selectors(_src8)
assert (_k == 3 and "display: inline-flex" in _o and "display:flex" not in _o
        and _dd_sel_hits(_o, ".product-rating") == 1
        and _dd_sel_hits(_o, ".deal-countdown") == 1
        and _dd_sel_hits(_o, ".add-to-cart") == 1 and _dd_balanced(_o))

# ---- the wrapper writes the collapsed CSS back through css_code -------------
# _lint_css_source dedupes, lints the collapsed code, and (only when a merge
# happened) injects css_code so the caller stores the collapsed file. Stub the
# real linter so this stays offline (no stylelint subprocess).
_dd_orig_impl = _lint_css_source_impl
try:
    globals()["_lint_css_source_impl"] = lambda code, rt: Command(
        update={"lint_passed": True, "messages": [ToolMessage(content="No issues found.",
                                                              tool_call_id="dd")]})
    _wc = _lint_css_source(".x{a:1px}\n.x{a:2px}", object())
    assert _wc.update.get("css_code", "").count(".x {") == 1 and "a: 2px" in _wc.update["css_code"], \
        "wrapper must write the collapsed css_code back on a merge"
    _wc2 = _lint_css_source(".x{a:1px}", object())
    assert "css_code" not in _wc2.update, "no duplicate -> wrapper must not touch css_code"
finally:
    globals()["_lint_css_source_impl"] = _dd_orig_impl
assert _lint_css_source_impl is _dd_orig_impl, "the test must restore the real linter"

print("PASS: _dedupe_css_selectors (8 cases) + wrapper css_code write-back")
# [proof] the number this change moves. On the real po0735889c stylesheet the
# collapse removes 3 duplicate top-level rules (.product-rating / .deal-countdown
# / .add-to-cart), so stylelint's no-duplicate-selectors never fires. Before this,
# that run shipped all 3 duplicates: the modify fix loop hit _LINT_ATTEMPT_CAP on
# the no-duplicate-selectors error and saved best-effort with the dupes intact.
_proof_o, _proof_k = _dedupe_css_selectors(_src8)
print(f"[proof] dedupe collapses {_proof_k} duplicate top-level rule(s) before lint "
      f"(po0735889c shipped 3 uncollapsed: fix loop capped on no-duplicate-selectors).")
