# Ported from fyp.ipynb cell 263 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: store_css_code (mirrors store_html_code tests)
# Since commit 28b6811 (spec-base CSS) store_css_code stores the submitted
# sheet plus a Python-written spec-base block, ending in one newline
# (tested in tests/test_spec_base.py). These cases check that the submitted
# sheet is what is stored, so they compare without the block (ticket 05).
def _sheet(text):
    return _SPEC_BLOCKS_RE.sub("", text or "").strip()

from types import SimpleNamespace
import json

# Generation mode is the DEFAULT when no intent is in state, so every fixture
# below that omits `intent` is a generation call and the Design Token Contract
# applies to it. These cases are about storage and decoration coverage, not
# tokens, so they carry a valid :root and stay focused on what they test.
_CSS_TOKENS = (":root {\n"
               "  --color-primary: #1a73e8;\n"   # matches _DECO_SPEC_COV
               "  --color-surface: #ffffff;\n"
               "  --color-text: #1f2933;\n"
               "  --color-border: #d9e2ec;\n"
               "  --radius: 12px;\n"
               "  --space: 8px;\n"
               "}\n")

TEST_CSS = _CSS_TOKENS + ".product-card { border-radius: 8px; }"
r = store_css_code.func(TEST_CSS, SimpleNamespace(
    state={"css_code": "", "lint_passed": False}, tool_call_id="test-scc-001"))
assert _sheet(r.update.get("css_code")) == _sheet(TEST_CSS)
assert "lint_passed" not in r.update, "store_css_code must not touch lint_passed"
print("[Case 1 · NORMAL] Store: css_code saved to state, lint_passed left untouched.")
print(r.update["messages"][0].content)
print("PASS: store_css_code stores css_code, lint_passed untouched")

r = store_css_code.func(TEST_CSS, SimpleNamespace(
    state={"css_code": ".old{}", "lint_passed": True}, tool_call_id="test-scc-002"))
assert _sheet(r.update["css_code"]) == _sheet(TEST_CSS)
print("\n[Case 2 · NORMAL] Overwrite: a second store replaces the css_code already in state.")
print(r.update["messages"][0].content)
print("PASS: store_css_code overwrites existing css_code\n")

# ── New cases (2026-07-08): decoration_specification coverage check ─────────
_DECO_SPEC_COV = {"pages": [{"pageName": "listing", "componentDecorations": [
    {"componentId": "add-to-cart-btn", "className": "add-to-cart-btn",
     "baseStyles": {"background-color": "#1a73e8"}},
]}]}

# Since commit 28b6811 Python writes a rule for every component whose
# decoration pins a style, so the coverage guard can only refuse a component
# whose decoration pins none. Cases 3 and 7 test the guard with such a one.
_DECO_SPEC_UNPINNED = {"pages": [{"pageName": "listing", "componentDecorations": [
    {"componentId": "add-to-cart-btn", "className": "add-to-cart-btn",
     "baseStyles": {}},
]}]}

def _rt_css_gen(css_code, **state_extra):
    state = {"css_code": css_code}
    state.update(state_extra)
    return SimpleNamespace(state=state, tool_call_id="test-scc-gen")

# Case 3: generate + decoration component with NO matching CSS rule -> rejected
r3 = store_css_code.func(".navbar { color: red; }", _rt_css_gen(
    ".navbar { color: red; }", intent="generate",
    decoration_specification=_DECO_SPEC_UNPINNED))
assert "css_code" not in r3.update, "FAIL: rejected call must not store css_code"
msg3 = r3.update["messages"][0].content
assert "add-to-cart-btn" in msg3
print("[Case 3 · GUARD] Decoration with no rule: the coverage guard rejects the submission.")
print(msg3)
print("PASS: uncovered decoration component rejected\n")

# Case 4: matching rule present -> accepted
_CSS_WITH_RULE = (_CSS_TOKENS + ".navbar { color: var(--color-primary); }\n"
                  ".add-to-cart-btn { background-color: var(--color-primary); }")
r4 = store_css_code.func(_CSS_WITH_RULE, _rt_css_gen(
    _CSS_WITH_RULE, intent="generate", decoration_specification=_DECO_SPEC_COV))
assert _sheet(r4.update.get("css_code")) == _sheet(_CSS_WITH_RULE)
print("[Case 4 · NORMAL] Matching rule present: the submission is accepted.")
print(r4.update["messages"][0].content)
print("PASS: matching rule present -> accepted\n")

# Case 5 (regression safety): intent="modify" -> coverage check exempt
r5 = store_css_code.func(".navbar { color: red; }", _rt_css_gen(
    ".navbar { color: red; }", intent="modify",
    decoration_specification=_DECO_SPEC_COV))
assert r5.update.get("css_code") == ".navbar { color: red; }", \
    "FAIL: modify mode must be exempt from coverage check"
print("[Case 5 · NORMAL] Modify mode: the coverage check is skipped, so the code is stored.")
print(r5.update["messages"][0].content)
print("PASS: modify mode exempt from coverage check\n")

# Case 6 (backward compat): no decoration_specification in state at all
# (old-style fixtures, like Cases 1-8 above) -> skipped gracefully
_CSS_NAV = _CSS_TOKENS + ".navbar { color: var(--color-primary); }"
r6 = store_css_code.func(_CSS_NAV, _rt_css_gen(_CSS_NAV))
assert _sheet(r6.update.get("css_code")) == _sheet(_CSS_NAV)
print("[Case 6 · EDGE] No decoration_specification: the check is skipped without crashing.")
print(r6.update["messages"][0].content)
print("PASS: missing decoration_specification -> check skipped, no crash")


# ── New cases (2026-07-21): string-spec coercion ────────────────────────────

# Case 7 (REGRESSION): a JSON-STRING decoration spec must still be enforced
r7 = store_css_code.func(".navbar { color: red; }", _rt_css_gen(
    ".navbar { color: red; }", intent="generate",
    decoration_specification=json.dumps(_DECO_SPEC_UNPINNED)))
assert "css_code" not in r7.update, "FAIL: string spec must not disable the check"
assert "add-to-cart-btn" in r7.update["messages"][0].content
print("\n[Case 7 · GUARD] JSON-string spec: coerced, so the coverage guard still rejects.")
print(r7.update["messages"][0].content)
print("PASS: string spec coerced, coverage check still active\n")

# Case 8 (GUARD): unparseable string spec -> loud [INTERNAL] refusal
r8 = store_css_code.func(".navbar { color: red; }", _rt_css_gen(
    ".navbar { color: red; }", intent="generate",
    decoration_specification="{not valid json"))
assert "css_code" not in r8.update
assert "[INTERNAL]" in r8.update["messages"][0].content
print("[Case 8 · GUARD] Unparseable spec: refused loudly with an [INTERNAL] message.")
print(r8.update["messages"][0].content)
print("PASS: unparseable spec -> [INTERNAL] refusal")


# ── Design Token Contract (added 2026-08-10) ────────────────────────────────
# WebCoderBench scores Component Style Consistency and Visual Harmony Degree.
# Naming the palette once in :root and referencing it everywhere is what makes
# consistency the default. Before this guard, every stylesheet this system had
# ever produced scored 0 tokens and 100% hard-coded colours.
#
# Two rules of DIFFERENT strength on purpose: the :root block is required (a
# refusal), the tokenisation ratio only warns. The coverage-guard retry loop
# has no attempt cap, so refusing on a matter of degree is the one thing that
# could make it spin.
print("\n[Case 9 · GUARD] No :root block -> REFUSED, with a worked example.")
_TK_BAD = ".product-card { color: #1f2933; background: #ffffff; }"
r9 = store_css_code.func(_TK_BAD, _rt_css_gen(_TK_BAD, intent="generate"))
assert "css_code" not in r9.update, "FAIL: a tokenless stylesheet was stored"
_m9 = r9.update["messages"][0].content
assert "Design Token Contract" in _m9 and "--color-primary" in _m9, _m9
print(_m9)
print("PASS: refused, and the message SHOWS the fix rather than describing it\n")

print("[Case 10 · EDGE] A :root with too few properties is still refused.")
_TK_THIN = ":root { --a: #fff; --b: #000; }\n.x { color: var(--a); }"
r10 = store_css_code.func(_TK_THIN, _rt_css_gen(_TK_THIN, intent="generate"))
assert "css_code" not in r10.update
assert "2 custom propert" in r10.update["messages"][0].content
print("PASS: 2 of the required 6 -> refused, and the count is named\n")

print("[Case 11 · NORMAL] Tokens declared and used -> stored, no advisory.")
_TK_GOOD = (_CSS_TOKENS +
            ".product-card { background: var(--color-surface); "
            "border: 1px solid var(--color-border); color: var(--color-text); }")
r11 = store_css_code.func(_TK_GOOD, _rt_css_gen(_TK_GOOD, intent="generate"))
assert _sheet(r11.update.get("css_code")) == _sheet(_TK_GOOD)
assert "ADVISORY" not in r11.update["messages"][0].content
print("PASS: a tokenised stylesheet passes silently\n")

print("[Case 12 · EDGE] Too many literals -> ADVISORY, but the CSS is STILL SAVED.")
_TK_MIX = _CSS_TOKENS + "".join(f".c{n} {{ color: #11223{n}; }}" for n in range(6))
r12 = store_css_code.func(_TK_MIX, _rt_css_gen(_TK_MIX, intent="generate"))
assert _sheet(r12.update.get("css_code")) == _sheet(_TK_MIX), \
    "FAIL: an advisory must never block the save -- that is what makes it loop-safe"
_m12 = r12.update["messages"][0].content
assert "ADVISORY" in _m12 and "not a rejection" in _m12, _m12
print(_m12)
print("PASS: reported, not refused, so the retry loop cannot spin on a ratio\n")

print("[Case 13 · EDGE] A few literals are free, and modify mode is exempt.")
_TK_FEW = _CSS_TOKENS + ".a { color: #111; } .b { color: #222; }"
r13 = store_css_code.func(_TK_FEW, _rt_css_gen(_TK_FEW, intent="generate"))
assert "ADVISORY" not in r13.update["messages"][0].content, "free allowance failed"
r13b = store_css_code.func(_TK_BAD, _rt_css_gen(_TK_BAD, intent="modify"))
assert r13b.update.get("css_code") == _TK_BAD, "FAIL: modify mode must stay exempt"
print("PASS: 2 literals pass silently; modify mode skips the contract entirely\n")

print("[Case 14 · EDGE] Non-colour var() must not inflate the ratio.")
# border-radius starts with "border" but carries no palette decision. Counting
# var(--radius) as colour tokenisation would let a stylesheet with no tokenised
# COLOURS at all clear the 60% bar.
_tk = _css_design_tokens(_CSS_TOKENS + ".a { border-radius: var(--radius); "
                         "padding: var(--space); }")
assert _tk["tokenised"] == 0, f"FAIL: {_tk}"
_tk2 = _css_design_tokens(_CSS_TOKENS + ".a { border-top-color: var(--color-border); }")
assert _tk2["tokenised"] == 1, f"FAIL: {_tk2}"
_tk3 = _css_design_tokens(_CSS_TOKENS + ".a { background: url(x.png#f); "
                          "color: inherit; outline: none; }")
assert _tk3["literal"] == 0, f"FAIL: a url() fragment read as a hex colour: {_tk3}"
_tk4 = _css_design_tokens("@media (prefers-color-scheme: dark) { :root { "
                          "--color-surface: #000; --b:#111; --c:#222; --d:#333; "
                          "--e:#444; --f:#555; } } .a { background: var(--color-surface); }")
assert len(_tk4["root_props"]) == 6 and _tk4["literal"] == 0, f"FAIL: {_tk4}"
print("     border-radius no, border-top-color yes, url(#f) no, dark-mode :root ok")
print("PASS: the classifier separates colour from geometry\n")

print("[Case 15 · ABLATION] _DESIGN_TOKEN_ENFORCED=False measures without blocking.")
# Arm B of the design-token experiment: CSS prompt rule ON, Python guard OFF.
# The shortfall must still be REPORTED -- an unenforced run that said nothing
# would be indistinguishable from a passing one in the transcript.
_tk_saved_flag = _DESIGN_TOKEN_ENFORCED
try:
    _DESIGN_TOKEN_ENFORCED = False
    r15 = store_css_code.func(_TK_BAD, _rt_css_gen(_TK_BAD, intent="generate"))
    assert _sheet(r15.update.get("css_code")) == _sheet(_TK_BAD), "FAIL: unenforced must not block"
    _m15 = r15.update["messages"][0].content
    assert "[UNENFORCED]" in _m15 and "would have REFUSED" in _m15, _m15
    print("   ", _m15.split("[UNENFORCED]")[1][:92].strip())
finally:
    _DESIGN_TOKEN_ENFORCED = _tk_saved_flag
r15b = store_css_code.func(_TK_BAD, _rt_css_gen(_TK_BAD, intent="generate"))
assert "css_code" not in r15b.update, "FAIL: the flag did not restore to enforcing"
assert _DESIGN_TOKEN_ENFORCED is True, "FAIL: the notebook must ship enforcing"
print("PASS: measured when off, refuses when on, and ships on\n")

print("[Case 16 \u00b7 EDGE] A rule matching no element is reported, not refused.")
# E2E-SO-01 on 2026-08-10: the CSS agent styled the price with
# `.product-card strong` while the HTML agent wrote `<span>`, so the price
# inherited the muted paragraph colour and rendered as secondary text. Both
# files were valid, both linters clean, every test passed.
_RC_HTML = ('<html><body><div class="product-card"><h3>Shoe</h3>'
            '<p><span>$89.99</span></p></div></body></html>')
_RC_CSS = (_CSS_TOKENS +
           ".product-card { background: var(--color-surface); }\n"
           ".product-card strong { font-weight: 700; }\n"
           "nav ul { display: flex; }\n"
           '.product-card[aria-busy="true"] { opacity: 0.5; }\n'
           ".product-card h3:hover { color: var(--color-primary); }\n"
           "@media (width <= 40rem) { .ghost-rule { padding: 0; } }")
_rc_dead = _css_dead_selectors(_RC_CSS, _RC_HTML)
assert ".product-card strong" in _rc_dead, _rc_dead
assert "nav ul" in _rc_dead, _rc_dead
assert ".ghost-rule" in _rc_dead, "an @media wrapper hid a dead rule: %s" % _rc_dead
assert not any("[aria-" in d or ":hover" in d for d in _rc_dead), (
    "a state variant was flagged; those are SUPPOSED to match nothing at rest: "
    "%s" % _rc_dead)
print("     dead:", _rc_dead)
print("PASS: dead rules found, state variants and pseudo-classes exempt\n")

print("[Case 17 \u00b7 GUARD] Drift is REFUSED; a reset is still only advised.")
# CHANGED 2026-08-31 (B1). This case used to assert that `.product-card strong`
# earned an advisory and the sheet was stored anyway. Run po018f8158 overturned
# that: fourteen rules of exactly this shape shipped, and the navigation, the
# pagination and the product headings rendered unstyled while html-validate and
# stylelint both reported clean. The advisory is kept for the half that really
# is a matter of degree, and only for that half. The two halves, side by side:
#
#   .product-card strong  .product-card IS on the page and <strong> is not, so
#                         the agent found the component and then guessed the
#                         wrong child tag. REFUSED -- the container's real
#                         children can be handed to it, making the fix a lookup
#                         rather than a judgement call.
#   nav ul, .ghost-rule   nothing anchors these to the page at all. A reset, or
#                         a defensive rule for markup that may not exist.
#                         ADVISORY, exactly as before.
_RC_RESET = (_CSS_TOKENS +
             ".product-card { background: var(--color-surface); }\n"
             "nav ul { display: flex; }\n"
             "@media (width <= 40rem) { .ghost-rule { padding: 0; } }")
_rc_prev = globals().get("_read_preview_source")
globals()["_read_preview_source"] = lambda sid, ext: _RC_HTML if ext == "html" else ""
try:
    _r = store_css_code.func(_RC_CSS, _rt_css_gen(_RC_CSS, intent="generate",
                                                  session_id="rc"))
    _m = _r.update["messages"][0].content
    assert "css_code" not in _r.update, "FAIL: drift must refuse, not store"
    assert ".product-card strong" in _m, _m
    assert "<span>" in _m or "<h3>" in _m, "the real children were not named: %s" % _m
    print("    refused:", _m.splitlines()[0][:88])

    _r = store_css_code.func(_RC_RESET, _rt_css_gen(_RC_RESET, intent="generate",
                                                    session_id="rc"))
    _m = _r.update["messages"][0].content
    assert _sheet(_r.update.get("css_code")) == _sheet(_RC_RESET), "FAIL: an advisory blocked the save"
    assert "match no element" in _m and "not a rejection" in _m, _m
    print("   ", _m.split("ADVISORY")[1][:92].strip().replace("\n", " "))

    # Modify edits one block and lints the whole file, so neither half applies.
    _r = store_css_code.func(_RC_CSS, _rt_css_gen(_RC_CSS, intent="modify",
                                                  session_id="rc"))
    _m = _r.update["messages"][0].content
    assert "match no element" not in _m and "CSS/DOM drift" not in _m
finally:
    if _rc_prev is not None:
        globals()["_read_preview_source"] = _rc_prev
print("PASS: drift refused, reset advised, both silent in modify\n")

print("[Case 18 \u00b7 EDGE] No HTML on disk -> the check is skipped, not guessed.")
assert _css_dead_selectors(_RC_CSS, "") == []
assert _css_dead_selectors("", _RC_HTML) == []
assert list(_rule_preludes("@media (x) { .a { c: 1 } }")) == [".a"]
print("PASS: missing input degrades to no finding\n")

# ── Decoration Colour Contract (Cases 19-21) ─────────────────────────────────
# E2E-SO-01 session so2029f0, 2026-08-11. The spec pinned
# `border: 1px solid #dddddd` on the product card. The CSS agent tokenised the
# stylesheet exactly as the Design Token Contract asks, using its own
# --color-border: #d9e2ec, and assert_css compared the COMPUTED border and
# failed. Both of our rules were obeyed and they disagreed with each other, so
# the run spent a correction on a conflict of our own making.
_DC_SPEC = {"pages": [{"pageName": "plp", "componentDecorations": [
    {"componentId": "product-card", "className": "product-card",
     "baseStyles": {"border": "1px solid #dddddd"}, "stateVariants": []},
    {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
     "baseStyles": {"background-color": "#1a73e8", "color": "#ffffff"},
     "stateVariants": [{"stateName": "disabled", "styles": {"opacity": "0.5"}}]},
]}]}

print("[Case 19 \u00b7 GUARD] A tokenised near-miss is refused before the test suite sees it.")
_DC_MISS = (":root {\n  --color-border: #d9e2ec;\n  --color-primary: #1a73e8;\n"
            "  --color-surface: #ffffff;\n  --color-text: #1f2933;\n"
            "  --radius: 12px;\n  --space: 8px;\n}\n"
            ".product-card { border: 1px solid var(--color-border); }\n"
            ".add-to-cart-btn { background-color: var(--color-primary);"
            " color: var(--color-surface); }\n")
_gaps = _decoration_color_gaps(_DC_MISS, _DC_SPEC)
assert len(_gaps) == 1, _gaps
assert "product-card" in _gaps[0] and "rgb(221, 221, 221)" in _gaps[0], _gaps
print("   ", _gaps[0][:104])
print("PASS: the exact so2029f0 mismatch is caught, and only that one\n")

print("[Case 20 \u00b7 NORMAL] Tokenising is still free - only the VALUE is pinned.")
# The contract must not push the agent back to hard-coded literals. A custom
# property carrying the specified value passes exactly as an inline one does.
_DC_OK = _DC_MISS.replace("--color-border: #d9e2ec", "--color-border: #dddddd")
assert _decoration_color_gaps(_DC_OK, _DC_SPEC) == []
_DC_LITERAL = _DC_MISS.replace("var(--color-border)", "#DDD")
assert _decoration_color_gaps(_DC_LITERAL, _DC_SPEC) == [], "short hex not normalised"
_DC_RGB = _DC_MISS.replace("var(--color-border)", "rgb(221, 221, 221)")
assert _decoration_color_gaps(_DC_RGB, _DC_SPEC) == [], "rgb() not normalised"
_DC_RGBA = _DC_MISS.replace("var(--color-border)", "rgba(221 221 221 / 80%)")
assert _decoration_color_gaps(_DC_RGBA, _DC_SPEC) == [], "modern rgb syntax not read"
print("PASS: token, #DDD, rgb() and the slash syntax all satisfy it\n")

print("[Case 21 \u00b7 EDGE] No spec, no colours, and modify mode are all silent.")
assert _decoration_color_gaps(_DC_MISS, {}) == []
assert _decoration_color_gaps("", _DC_SPEC) != []          # empty CSS: everything missing
# a non-colour style must never be treated as a pinned colour
assert _decoration_color_gaps(_DC_OK, {"pages": [{"componentDecorations": [
    {"componentId": "x", "baseStyles": {"opacity": "0.5", "padding": "8px"}}]}]}) == []
# an unparseable value fails OPEN rather than producing an unactionable refusal
assert _decoration_color_gaps(_DC_OK, {"pages": [{"componentDecorations": [
    {"componentId": "x", "baseStyles": {"color": "color-mix(in srgb, teal, cyan)"}}]}]}) == []
_r = store_css_code.func(_DC_MISS, _rt_css_gen(
    _DC_MISS, intent="modify", session_id="dc",
    decoration_specification=_DC_SPEC))
assert _r.update.get("css_code") == _DC_MISS, "FAIL: modify mode is not exempt"
print("PASS: absent spec, non-colour styles and modify mode all pass through\n")

print("store_css_code: 3 decoration-colour cases passed (21 total).")
