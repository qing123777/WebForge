# Ported from fyp.ipynb cell 267 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: extract_css_component
from types import SimpleNamespace

_CSS_SAMPLE = """
body {
  margin: 0;
}

.product-card {
  background: white;
  padding: 1rem;
}

.product-card:hover {
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}

#navbar {
  background: #1a73e8;
  color: white;
}
""".strip()

_mk_rt_css = lambda comp, css=_CSS_SAMPLE: SimpleNamespace(
    state={"css_code": css, "target_component": comp},
    tool_call_id="test-ecc"
)

# Case 1: .class selector — matching rules returned
r1 = extract_css_component.func(_mk_rt_css(".product-card"))
msg1 = r1.update["messages"][0].content
assert ".product-card" in msg1 or "product-card" in msg1
assert "background: white" in msg1
assert "navbar" not in msg1
print("[Case 1 · NORMAL] .class selector: resolves to the right rules.")
print(f"Extracted:\n{msg1[:120]}")
print("PASS: .class selector resolves to the right rules\n")

# Case 2: #id selector
r2 = extract_css_component.func(_mk_rt_css("#navbar"))
msg2 = r2.update["messages"][0].content
assert "navbar" in msg2
assert "product-card" not in msg2
print("[Case 2 · NORMAL] #id selector: resolves to the correct block.")
print(msg2[:80])
print("PASS: #id selector finds correct block\n")

# Case 3: bare word fallback
r3 = extract_css_component.func(_mk_rt_css("navbar"))
msg3 = r3.update["messages"][0].content
assert "navbar" in msg3
print("[Case 3 · NORMAL] Bare word: the fallback finds the #navbar block.")
print(msg3[:80])
print("PASS: bare-word fallback finds #navbar block\n")

# Case 4: component not found
r4 = extract_css_component.func(_mk_rt_css(".footer"))
assert "no css blocks found" in r4.update["messages"][0].content.lower()
print("[Case 4 · EDGE] Selector matches nothing: reported, not crashed.")
print(r4.update['messages'][0].content)
print("PASS: not-found handled\n")

# Case 5: empty css_code
r5 = extract_css_component.func(SimpleNamespace(
    state={"css_code": "", "target_component": ".product-card"},
    tool_call_id="test-ecc-empty"
))
assert "empty" in r5.update["messages"][0].content.lower()
print("[Case 5 · EDGE] Empty css_code: handled gracefully.")
print(r5.update['messages'][0].content)
print("PASS: empty css_code handled\n")

# Case 6: EVERY matching block is returned, not just the first — the base rule
#   and its :hover variant, joined by marker lines the diff must preserve.
r6 = extract_css_component.func(_mk_rt_css(".product-card"))
msg6 = r6.update["messages"][0].content
assert "background: white" in msg6 and "box-shadow" in msg6, msg6
assert msg6.count("WebForge block") == 2 and "block 2 of 2" in msg6
print("[Case 6 · NORMAL] Base + :hover: every matching block returned, not just the first.")
print(f"Extracted:\n{msg6}")
print("PASS: base rule and :hover variant both returned\n")

# Case 7: a single match carries no marker lines at all, so the one-block case
#   is byte-identical to what the model saw before multi-block support.
r7 = extract_css_component.func(_mk_rt_css("#navbar"))
assert "WebForge block" not in r7.update["messages"][0].content
assert r7.update["messages"][0].content.startswith("#navbar {")
print("[Case 7 · INVARIANT] Single match: no marker lines are added.")
print("WebForge block marker present: False")
print("PASS: single-match extraction is unmarked\n")


# ── Suggestion 2 (batching) additions ───────────────────────────────────────
# Case 8 [NORMAL] explicit component= parameter overrides the state target
_r8c = extract_css_component.func(_mk_rt_css("#navbar"), component=".product-card")
_m8c = _r8c.update["messages"][0].content
assert "product-card" in _m8c and "navbar" not in _m8c, "component= must win over state"
print("[Case 8 · NORMAL] explicit component= parameter selects the block, overriding state.")
print("PASS: component= overrides state target_component\n")

# Case 9 [INVARIANT] a successful extract resets the per-component lint budget
_r9c = extract_css_component.func(SimpleNamespace(
    state={"css_code": _CSS_SAMPLE, "target_component": "#navbar",
           "lint_attempts": 2, "lint_escalated": True}, tool_call_id="ecc-9"))
assert _r9c.update.get("lint_attempts") == 0 and _r9c.update.get("lint_escalated") is False, \
    "extract must reset the session-global lint budget so a batch cannot blow the cap"
print("[Case 9 · INVARIANT] extract resets lint_attempts/lint_escalated for the new component.")
print("PASS: per-component lint budget reset on extract\n")

# ── Naming Contract resolution (2026-08-09) ──────────────────────────────────
# A correction work order names the specification ID; the stylesheet uses the
# className. Every live Secondary Orchestrator scenario reported
# "add-to-cart-button was not found in the current CSS" for a component that was
# right there under .add-to-cart-btn, wasting a correction attempt each time.
_NC_CSS = (".product-card {\n  border: 1px solid #dddddd;\n}\n"
           ".add-to-cart-btn {\n  opacity: 1;\n}\n"
           ".add-to-cart-btn[aria-disabled=\"true\"] {\n  opacity: 0.5;\n}\n")
_NC_DECO = {"pages": [{"pageName": "plp", "componentDecorations": [
    {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
     "baseStyles": {"opacity": "1"}},
    {"componentId": "product-card", "className": "product-card",
     "baseStyles": {"border": "1px solid #dddddd"}},
]}]}


def _rt_nc(component, css=_NC_CSS, deco=_NC_DECO):
    return SimpleNamespace(
        state={"css_code": css, "target_component": component,
               "decoration_specification": deco},
        tool_call_id="nc-1")


# [NC-1] the exact live failure: spec id -> className
_r = extract_css_component.func(_rt_nc("add-to-cart-button"))
_m = _r.update["messages"][0].content
assert "No CSS blocks found" not in _m, f"FAIL: spec id still unresolved:\n{_m}"
assert ".add-to-cart-btn {" in _m, _m
assert 'aria-disabled' in _m, "both blocks must come back, base + state variant"
print("[NC-1 · GUARD] A work order naming the specification id now resolves to the "
      "className the stylesheet actually uses.")
print("PASS: id -> className resolution\n")

# [NC-2] the className itself keeps working, and so does an explicit selector
for _name in ("add-to-cart-btn", ".add-to-cart-btn"):
    _m2 = extract_css_component.func(_rt_nc(_name)).update["messages"][0].content
    assert "No CSS blocks found" not in _m2, f"FAIL for {_name}: {_m2}"
print("[NC-2 · NORMAL] The className and an explicit .selector are unaffected.")
print("PASS: existing call shapes unchanged\n")

# [NC-3] the space form the orchestrator has been seen to emit
_m3 = extract_css_component.func(_rt_nc("add to cart button")).update["messages"][0].content
assert "No CSS blocks found" not in _m3, f"FAIL: space form unresolved: {_m3}"
print("[NC-3 · EDGE] 'add to cart button' resolves via the hyphenated form.")
print("PASS: space form handled\n")

# [NC-4] a genuinely absent component still fails, and the message now says
# what IS available -- that message is the model's only channel to the fix.
_m4 = extract_css_component.func(_rt_nc("ghost-widget")).update["messages"][0].content
assert "No CSS blocks found" in _m4
assert ".add-to-cart-btn" in _m4 and ".product-card" in _m4, \
    f"FAIL: the not-found message must list the selectors present: {_m4}"
print("[NC-4 · GUARD] An absent component still fails, and the message names the "
      "selectors the stylesheet does define.")
print(_m4)
print("PASS: actionable not-found message\n")

# [NC-5] with no decoration_specification the tool degrades to its old behaviour
_m5 = extract_css_component.func(_rt_nc("add-to-cart-button", deco=None)
                                 ).update["messages"][0].content
assert "No CSS blocks found" in _m5, "without the spec there is nothing to map with"
_m5b = extract_css_component.func(_rt_nc("product-card", deco=None)
                                  ).update["messages"][0].content
assert "No CSS blocks found" not in _m5b, "a name that matches literally must still work"
print("[NC-5 · EDGE] No decoration_specification: literal matching still works, and "
      "the mapping is simply unavailable rather than raising.")
print("PASS: degrades cleanly with no spec\n")

print("All 5 Naming Contract resolution cases passed - extract_css_component")

# ── Multi-line selector groups (GS-1..GS-5, added 2026-08-09) ────────────────
# E2E-SO-01 produced a stylesheet whose add-to-cart rules were all written as
# groups. The extractor found ZERO blocks and the CSS agent reported the
# component did not exist, wasting half a correction round.
_GS_CSS = (
    ".navbar {\n  color: #111;\n}\n\n"
    ".add-to-cart-btn,\n"
    "button.add-to-cart-btn,\n"
    ".product-card button {\n"
    "  background-color: #1a73e8;\n"
    "  opacity: 1;\n"
    "}\n\n"
    ".add-to-cart-btn:hover,\n"
    "button.add-to-cart-btn:hover {\n"
    "  background-color: #1557b0;\n"
    "}\n\n"
    "@media (max-width: 600px) {\n"
    "  .add-to-cart-btn,\n"
    "  .product-card button {\n"
    "    width: 100%;\n"
    "  }\n"
    "}\n"
)
_GS_DECO = {"pages": [{"pageName": "plp", "componentDecorations": [
    {"componentId": "add-to-cart-button", "className": "add-to-cart-btn"}]}]}

print("[GS-1 · NORMAL] A grouped selector is found by its className.")
_gs = _extract_css_block_spans(_GS_CSS, "add-to-cart-btn")
assert len(_gs) == 3, f"FAIL: expected 3 blocks (base, :hover, @media inner), got {len(_gs)}"
print(f"found {len(_gs)} blocks")
print("PASS: base, :hover and the media-query override all matched\n")

print("[GS-2 · NORMAL] Each span is the WHOLE rule, prelude lines included.")
_first = _GS_CSS[_gs[0][0]:_gs[0][1]]
assert _first.startswith(".add-to-cart-btn,"), f"FAIL: span starts at {_first[:40]!r}"
assert _first.rstrip().endswith("}"), "FAIL: span does not close its block"
assert "background-color: #1a73e8" in _first, "FAIL: declarations missing"
assert ".navbar" not in _first, "FAIL: span leaked into the previous rule"
print(f"first span is {len(_first)} chars, opens at the group's FIRST line")
print("PASS: the span covers the full rule and nothing else\n")

print("[GS-3 · EDGE] An @media wrapper does not hide the rules nested in it.")
# The wrapper's own prelude does not name the component. Stepping over it (rather
# than skipping the whole block) is what keeps the inner rule reachable.
_inner = _GS_CSS[_gs[2][0]:_gs[2][1]]
assert "width: 100%" in _inner, f"FAIL: media-query inner rule not captured: {_inner!r}"
assert "@media" not in _inner, "FAIL: the wrapper itself was captured instead"
print("PASS: the inner rule is captured, the wrapper is not\n")

print("[GS-4 · NORMAL] Naming Contract resolution now reaches those blocks.")
_alias, _blocks = _resolve_css_component(_GS_CSS, "add-to-cart-button", _GS_DECO)
assert _alias == "add-to-cart-btn", f"FAIL: alias was {_alias!r}"
assert len(_blocks) == 3, f"FAIL: resolved to {len(_blocks)} blocks"
print(f"'add-to-cart-button' -> '{_alias}' -> {len(_blocks)} blocks")
print("PASS: spec id resolves to the className and finds every block\n")

print("[GS-5 · EDGE] The not-found message lists grouped selectors individually.")
# The old version listed only single-line selectors, so its message told the
# model the class did not exist. That is what made the agent give up.
_present = _css_selectors_present(_GS_CSS)
assert ".add-to-cart-btn" in _present, f"FAIL: not reported as present: {_present}"
assert "button.add-to-cart-btn" in _present, f"FAIL: group member missing: {_present}"
assert ".navbar" in _present, "FAIL: single-line selectors regressed"
print(f"reports {len(_present)} selectors, group members split out")
print("PASS: the recovery message is truthful\n")

print("[GS-6 · GUARD] A long stylesheet still surfaces the sought selector.")
# The real SO-01 stylesheet had .add-to-cart-btn as its 20th selector, so the
# first-12 list omitted it and read as complete. Both halves are checked here.
_GS_LONG = "".join(f".filler-{n} {{\n  color: #000;\n}}\n\n" for n in range(20)) + _GS_CSS
_pref = _css_selectors_present(_GS_LONG, prefer="add-to-cart-btn")
assert ".add-to-cart-btn" in _pref, f"FAIL: sought selector still hidden: {_pref}"
assert _pref[0] == ".add-to-cart-btn", f"FAIL: not ranked first: {_pref[:3]}"
assert any(s.startswith("(+") for s in _pref), f"FAIL: no truncation marker: {_pref}"
assert len(_css_selectors_present(_GS_LONG)) == 13, "FAIL: unprefered list changed size"
print(f"ranked first of {len(_pref)} entries, and the list admits it is partial")
print("PASS: the message names the selector the model needs\n")

print("All 6 grouped-selector cases passed - extract_css_component")
