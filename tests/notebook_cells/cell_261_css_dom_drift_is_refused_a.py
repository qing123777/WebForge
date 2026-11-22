# Ported from fyp.ipynb cell 261 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: CSS/DOM drift is refused, a reset is not (2026-08-31).
# REGRESSION for PO-08 po018f8158. The stylesheet shipped 18 selectors that
# matched nothing. store_css_code SAW all 18 and only wrote an ADVISORY, so the
# agent saved anyway, and 14 of them left the navigation, the pagination and
# the product headings unstyled. Both linters reported clean and every test
# passed, because a test asserts on selectors that DO match.
#
# The reason it was advisory is in the old comment: some dead selectors are
# correct. These cases pin the line that separates them.
# Since commit 28b6811 (spec-base CSS) store_css_code stores the submitted
# sheet plus a Python-written spec-base block, ending in one newline
# (tested in tests/test_spec_base.py). These cases check that the submitted
# sheet is what is stored, so they compare without the block (ticket 05).
def _sheet(text):
    return _SPEC_BLOCKS_RE.sub("", text or "").strip()

from types import SimpleNamespace

_DR_HTML = """<!doctype html><html><head><title>t</title></head><body>
<nav class="roast-level-nav"><ul><li><a href="#x">Light</a></li></ul></nav>
<div class="card"><h4>Name</h4><p>Notes</p></div>
</body></html>"""

_dr_passed = 0


def _dr(label, cond):
    global _dr_passed
    assert cond, f"FAIL {label}"
    _dr_passed += 1
    print(f"PASS {label}")


_sels = lambda rows: {r[0] for r in rows}

# ── the detector itself ────────────────────────────────────────────────────
# 1. A bare element rule is a reset. The page having no <img> is not a defect,
#    and refusing it would teach the agent to delete correct CSS.
_r = _css_drifted_selectors("img { display: block; } input { font: inherit; }",
                            _DR_HTML)
_dr("DR-1  a bare element rule matching nothing is NOT drift", _r == [])

# 2. The container is on the page and the descendant is not. This is the one
#    that is refused, and the fix is a lookup rather than a judgement call.
_r = _css_drifted_selectors(".roast-level-nav button { color: red; }", _DR_HTML)
_dr("DR-2  container present + descendant absent IS drift", len(_r) == 1)
_dr("DR-3  the message names the container and its REAL children",
    _r[0][2] == ".roast-level-nav" and "<a>" in _r[0][3])

# 3. A selector that matches is never reported.
_r = _css_drifted_selectors(".roast-level-nav a { color: red; }", _DR_HTML)
_dr("DR-4  a selector that matches is not reported", _r == [])

# 4. State variants and pseudo-elements match nothing while the page is at
#    rest. Flagging them would be a wall.
_r = _css_drifted_selectors(
    ".card a:hover { color: red; }\n"
    ".card [data-state='open'] { display: block; }\n"
    ".card p::first-line { font-weight: 700; }", _DR_HTML)
_dr("DR-5  :hover / [data-*] / :: are exempt, not drift", _r == [])

# 5. No page to compare against means no evidence. Fail OPEN, never refuse.
_dr("DR-6  an empty page yields no refusal (fails open)",
    _css_drifted_selectors(".a b { color: red; }", "") == [])

# 6. The whole point of the split, on the shape that actually shipped.
_r = _css_drifted_selectors(
    "img { display: block; }\n"
    ".roast-level-nav button { color: red; }\n"
    ".card h3 { font-size: 2rem; }", _DR_HTML)
_dr("DR-7  a mixed sheet reports only the drifted rules",
    _sels(_r) == {".roast-level-nav button", ".card h3"})

# ── the refusal inside store_css_code ──────────────────────────────────────
_DR_TOKENS = (":root {\n  --color-primary: #1a73e8;\n  --color-surface: #fff;\n"
              "  --color-text: #1f2933;\n  --color-border: #d9e2ec;\n"
              "  --radius: 12px;\n  --space: 8px;\n}\n")
_DR_SPEC = {"pages": [{"pageName": "listing", "componentDecorations": [
    {"componentId": "roast-level-nav", "className": "roast-level-nav",
     "baseStyles": {"padding": "8px"}}]}]}
_DR_BAD = _DR_TOKENS + ".roast-level-nav { padding: 8px; }\n" \
                       ".roast-level-nav button { color: red; }\n"
_DR_OK = _DR_TOKENS + ".roast-level-nav { padding: 8px; }\n" \
                      ".roast-level-nav a { color: red; }\n"


def _dr_rt(**extra):
    st = {"css_code": "", "intent": "generate", "session_id": "drifttest",
          "decoration_specification": _DR_SPEC}
    st.update(extra)
    return SimpleNamespace(state=st, tool_call_id="test-drift")


_dr_real = globals()["_read_preview_source"]
globals()["_read_preview_source"] = lambda sid, ext: (
    _DR_HTML if ext == "html" else "")
try:
    # 7. Drift refuses, and refusing must not store the stylesheet.
    _c = store_css_code.func(_DR_BAD, _dr_rt())
    _m = _c.update["messages"][0].content
    _dr("DR-8  drift is REFUSED and the css_code is not stored",
        "css_code" not in _c.update and "CSS/DOM drift" in _m)
    _dr("DR-9  the refusal hands over the real child tag to use",
        ".roast-level-nav button" in _m and "<a>" in _m)

    # 8. The counter has to advance, or the loop below it is unbounded. This is
    #    also what proves the CssState channel exists: LangGraph drops a write
    #    to a channel the schema does not declare, silently.
    _dr("DR-10 the refusal advances coverage_attempts",
        _c.update.get("coverage_attempts") == 1)

    # 9. At the cap the guard stops refusing. A stylesheet the agent cannot
    #    repair must still reach disk -- but it may never do so quietly.
    _c = store_css_code.func(_DR_BAD, _dr_rt(coverage_attempts=2))
    _m = _c.update["messages"][0].content
    _dr("DR-11 past the cap the sheet is SAVED, not refused forever",
        _sheet(_c.update.get("css_code")) == _sheet(_DR_BAD))
    _dr("DR-12 the capped save says so loudly, never silently",
        "[DRIFT CAP REACHED]" in _m)

    # 10. A clean sheet is unaffected. A guard that fires on correct work is a
    #     wall, and this is the case that would catch it.
    _c = store_css_code.func(_DR_OK, _dr_rt())
    _dr("DR-13 a sheet with no drift is stored untouched",
        _sheet(_c.update.get("css_code")) == _sheet(_DR_OK)
        and "CSS/DOM drift" not in _c.update["messages"][0].content)

    # 11. Modify edits one block and lints the whole file; the drift check is a
    #     generation-mode contract, exactly like the coverage check above it.
    _c = store_css_code.func(_DR_BAD, _dr_rt(intent="modify"))
    _dr("DR-14 modify mode is exempt, as it is for every other coverage guard",
        _c.update.get("css_code") == _DR_BAD)

    # ── Region Coverage Contract (B2, 2026-08-31) ──────────────────────────
    # PO-08 po018f8158 shipped filter-sort-bar and cart-drawer flush against
    # the window edge. Every stage was correct: layout marked them
    # ownedBy: JavaScript, the components generator's empty-region guard
    # exempts a JavaScript-owned region, decoration is keyed off components,
    # and the CSS agent only ever saw components + decoration. The wrong
    # premise is at the end -- JavaScript owns a region's CONTENTS, never its
    # container's gutter.
    _RG_HTML = ("<html><body>"
                "<section id=\"hero\"><div class=\"hero-panel\"><h1>x</h1></div></section>"
                "<section id=\"cart-drawer\"><p>filled at runtime</p></section>"
                "</body></html>")
    _RG_LAYOUT = {"pages": [{"pageName": "listing", "regions": [
        {"name": "hero", "ownedBy": "HTML"},
        {"name": "cart-drawer", "ownedBy": "JavaScript"}]}]}
    _RG_CSS = _DR_TOKENS + ".hero-panel { padding: 8px; max-width: 1200px; }\n"

    _r = _css_unstyled_regions(_RG_CSS, _RG_HTML, _RG_LAYOUT)
    _dr("RG-1  a region whose subtree IS styled passes, unstyled one is named",
        _r == [("cart-drawer", "JavaScript")])

    # The gutter usually sits on an inner panel, not on the <section>. Demanding
    # a rule on the container itself would have refused 7 correct regions out of
    # 9 on the real run. Reaching anything inside is the test.
    _dr("RG-2  styling an inner panel counts; the container need not be named",
        not any(n == "hero" for n, _ in _r))

    # A reset gives no region its gutter, so it must not read as coverage.
    _dr("RG-3  a bare tag rule is a reset and does NOT count as coverage",
        {n for n, _ in _css_unstyled_regions(
            _DR_TOKENS + "section { margin: 0; }", _RG_HTML, _RG_LAYOUT)}
        == {"hero", "cart-drawer"})

    _dr("RG-4  ownedBy JavaScript is not an exemption",
        _css_unstyled_regions(_RG_CSS, _RG_HTML, _RG_LAYOUT)[0][1] == "JavaScript")

    # A region the page never emitted is a different defect, and one this guard
    # would only report as noise.
    _RG_MISSING = {"pages": [{"pageName": "l", "regions": [
        {"name": "never-emitted", "ownedBy": "HTML"}]}]}
    _dr("RG-5  a region absent from the page is skipped, not blamed on the CSS",
        _css_unstyled_regions(_RG_CSS, _RG_HTML, _RG_MISSING) == [])

    _dr("RG-6  no layout and no page both fail OPEN, never into a refusal",
        _css_unstyled_regions(_RG_CSS, _RG_HTML, {}) == []
        and _css_unstyled_regions(_RG_CSS, "", _RG_LAYOUT) == [])

    globals()["_read_preview_source"] = lambda sid, ext: (
        _RG_HTML if ext == "html" else "")
    _c = store_css_code.func(_RG_CSS, _BaNS_rg := _dr_rt(
        decoration_specification={}, layout_specification=_RG_LAYOUT))
    _m = _c.update["messages"][0].content
    _dr("RG-7  store_css_code REFUSES and stores nothing",
        "css_code" not in _c.update and "Region coverage" in _m)
    _dr("RG-8  the refusal names the region and denies the JavaScript excuse",
        "#cart-drawer" in _m and "ownedBy: JavaScript" in _m)

    _c = store_css_code.func(_RG_CSS, _dr_rt(
        decoration_specification={}, layout_specification=_RG_LAYOUT,
        coverage_attempts=2))
    _dr("RG-9  past the shared cap it is saved, not refused forever",
        _c.update.get("css_code") == _RG_CSS)
    globals()["_read_preview_source"] = lambda sid, ext: (
        _DR_HTML if ext == "html" else "")
finally:
    globals()["_read_preview_source"] = _dr_real

assert globals()["_read_preview_source"] is _dr_real, \
    "the cell must restore what it borrowed"

# 14 drift cases + 9 region cases.
_DR_TOTAL = 14 + 9
assert _dr_passed == _DR_TOTAL, f"expected {_DR_TOTAL}, counted {_dr_passed}"
print(f"CSS/DOM drift + region coverage: {_dr_passed}/{_DR_TOTAL} PASSED (no model calls)")
