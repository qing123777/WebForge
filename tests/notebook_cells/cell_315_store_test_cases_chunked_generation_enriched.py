# Ported from fyp.ipynb cell 315 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: store_test_cases  (chunked generation + enriched coverage)
# Generation is now CHUNKED: batches ACCUMULATE via the test_cases reducer, and
# coverage (component + state + event) is checked over the ACCUMULATED suite.
# A well-formed but coverage-incomplete batch is SAVED (not rejected) and the
# message lists the gaps; only schema/format errors hard-reject a batch.
from types import SimpleNamespace

_passed = 0
def _ok(tid, desc):
    global _passed
    _passed += 1
    print(f"PASS  {tid:<4} {desc}")

def _RT(state): return SimpleNamespace(state=state, tool_call_id="stc")
# The Selector Contract is Python-enforced by store_test_cases, so the DEFAULT
# selector has to follow it: '.className' when the spec node declares one, else
# '#id'. Pass sel= explicitly only in a test that is ABOUT the selector.
_SEL = {"navbar": "#navbar", "product-card": ".product-card"}
def _TC(id, comp, action="assert_visible", sel=None, exp="", **extra):
    return {"id": id, "component": comp, "description": "d", "action": action,
            "selector": _SEL.get(comp, f"#{comp}") if sel is None else sel,
            "expected": exp, "passed": None, **extra}

# Spec: navbar (plain) + product-card (declares one state + one event).
_SPEC = {"pages": [{"pageName": "listing", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "product-card", "tag": "div", "className": "product-card",
     "states": [{"name": "selected"}], "events": [{"name": "click"}]},
]}}]}

# ── reducer ───────────────────────────────────────────────────────────────────
assert _merge_test_cases([], [_TC("a", "x")]) == [_TC("a", "x")]
_r = _merge_test_cases([_TC("a", "x")], [_TC("b", "y"), _TC("a", "x", sel="s2")])
assert [t["id"] for t in _r] == ["a", "b"] and _r[0]["selector"] == "s2"
_ok("R1", "_merge_test_cases: append new id, replace same id, keep order")

# ── coverage-target walker ────────────────────────────────────────────────────
_c, _s, _e = _spec_coverage_targets(_SPEC)
assert _c == {"navbar", "product-card"}
assert _s == {("product-card", "selected")} and _e == {("product-card", "click")}
assert _spec_component_names(_SPEC) == {"navbar", "product-card"}
_ok("R2", "_spec_coverage_targets: components + (comp,state) + (comp,event)")

# canonical ComponentEvent shape: events keyed `event` (model_dump output), not `name`
_SPEC_CANON = {"pages": [{"pageName": "listing", "regionComponents": {"main": [
    {"id": "add-to-cart-button", "tag": "button",
     "states": [{"name": "disabled"}], "events": [{"event": "click"}]},
]}}]}
_cc, _cs, _ce = _spec_coverage_targets(_SPEC_CANON)
assert _ce == {("add-to-cart-button", "click")}, f"canonical `event` key not counted: {_ce}"
assert _cs == {("add-to-cart-button", "disabled")}
_ok("R3", "_spec_coverage_targets counts canonical `event`-keyed events (model_dump shape)")

# A RESTING state ('default' and its synonyms) is not a coverage target: a
# covers_state='default' case asserts the shipped-at-load value, true by
# construction. The non-resting states in the SAME node stay targets.
_SPEC_REST = {"pages": [{"pageName": "listing", "regionComponents": {"main": [
    {"id": "filter-panel", "tag": "div", "className": "filter-panel",
     "states": [{"name": "default"}, {"name": "Idle"}, {"name": "expanded"}]},
]}}]}
_rc, _rs, _re = _spec_coverage_targets(_SPEC_REST)
assert _rs == {("filter-panel", "expanded")}, \
    f"resting states must drop, only 'expanded' survives, got: {_rs}"
assert _rc == {"filter-panel"}, _rc
_before, _after = 3, len(_rs)
_ok("R4", "_spec_coverage_targets drops resting states (default/Idle), keeps expanded")
print(f"[proof] resting-state filter: filter-panel declared {_before} states "
      f"(default, Idle, expanded); coverage targets = {_after} (expanded only). "
      f"The 2 resting names cost 0 tests now; before this filter each was a "
      f"forced covers_state case asserting the load-time value.")

# ── save / accept paths ───────────────────────────────────────────────────────
r = store_test_cases.func([_TC("1", "navbar")], _RT({}))
assert r.update["test_cases"] == [_TC("1", "navbar")]
assert "SUITE COMPLETE" in r.update["messages"][0].content
_ok("T1", "no spec -> batch saved, SUITE COMPLETE")

r = store_test_cases.func([], _RT({"test_cases": [_TC("1", "navbar")]}))
assert r.update["test_cases"] == []
_ok("T2", "empty batch accepted (returns the empty batch, reducer no-ops)")

# Full coverage in one batch (component + state + event tagged)
_full = [_TC("1", "navbar"),
         _TC("2", "product-card", covers_state="selected"),
         _TC("3", "product-card", action="click", sel=".product-card", covers_event="click")]
r = store_test_cases.func(_full, _RT({"components_specification": _SPEC}))
assert r.update["test_cases"] == _full
assert "SUITE COMPLETE" in r.update["messages"][0].content
_ok("T3", "full component+state+event coverage in one batch -> SUITE COMPLETE")

# ── incomplete (saved, gaps reported) ─────────────────────────────────────────
r = store_test_cases.func([_TC("1", "navbar")], _RT({"components_specification": _SPEC}))
_m = r.update["messages"][0].content
assert r.update["test_cases"] == [_TC("1", "navbar")], "incomplete batch must still be SAVED"
assert "INCOMPLETE" in _m and "SUITE COMPLETE" not in _m
assert "product-card" in _m and "product-card:selected" in _m and "product-card:click" in _m
assert "'navbar'" not in _m, "navbar IS covered — must not be listed missing"
_ok("T4", "incomplete batch saved; missing component+state+event listed, covered one omitted")

# Accumulated coverage: state already holds navbar, this batch finishes the rest
_b2 = [_TC("2", "product-card", covers_state="selected"),
       _TC("3", "product-card", action="click", sel=".product-card", covers_event="click")]
r = store_test_cases.func(_b2, _RT({"components_specification": _SPEC,
                                    "test_cases": [_TC("1", "navbar")]}))
assert "SUITE COMPLETE" in r.update["messages"][0].content
assert r.update["test_cases"] == _b2, "batch return is THIS batch only (reducer appends)"
_ok("T5", "coverage uses accumulated (state + batch); returns only the new batch")

# State covered but event still missing
r = store_test_cases.func(
    [_TC("1", "navbar"), _TC("2", "product-card", covers_state="selected")],
    _RT({"components_specification": _SPEC}))
_m = r.update["messages"][0].content
assert "product-card:click" in _m and "product-card:selected" not in _m
_ok("T6", "state tagged, event untagged -> only the event gap reported")

# Empty spec skips coverage entirely
r = store_test_cases.func([_TC("1", "navbar")], _RT({"components_specification": {}}))
assert r.update["test_cases"] == [_TC("1", "navbar")] and "SUITE COMPLETE" in r.update["messages"][0].content
_ok("T7", "empty spec skips coverage -> SUITE COMPLETE")

# Optional viewport + covers tags accepted
r = store_test_cases.func([_TC("1", "navbar", viewport="375x812")], _RT({}))
assert r.update["test_cases"][0]["viewport"] == "375x812"
_ok("T8", "optional viewport accepted")

# ── hard rejects (nothing saved) ──────────────────────────────────────────────
def _rej(bad, needle, state=None):
    r = store_test_cases.func(bad, _RT(state or {}))
    assert "test_cases" not in r.update, f"reject must not save ({needle})"
    assert needle in r.update["messages"][0].content, \
        f"expected {needle!r}, got: {r.update['messages'][0].content!r}"

_rej("not a list", "must be a list")
_ok("T9", "non-list rejected")
_rej([{"id": "x", "component": "c"}], "missing required keys")
_ok("T10", "missing required keys rejected")
_rej([_TC("1", "c"), "nope"], "must be a dict")
_ok("T11", "non-dict item rejected")
_rej([_TC("1", "c", action="frobnicate")], "invalid action")
_ok("T12", "invalid action rejected")
_rej([_TC("1", "c", action="assert_css", exp="red")], "property=value")
_ok("T13", "assert_css bad format rejected")
_rej([_TC("1", "c", action="assert_hover_css", exp="blue")], "assert_hover_css expected must be")
_ok("T14", "assert_hover_css bad format rejected")
_rej([_TC("1", "c", action="assert_attribute", exp="noeq")], "attribute=value")
_ok("T15", "assert_attribute bad format rejected")
_rej([_TC("1", "c", viewport="mobile")], "viewport must be")
_ok("T16", "malformed viewport rejected")
_rej([_TC("1", "c", covers_state=123)], "covers_state must be a string")
_ok("T17", "non-string covers_state rejected")

# ── string-spec coercion (regression) ─────────────────────────────────────────
import json as _json
r = store_test_cases.func([_TC("1", "navbar")],
                          _RT({"components_specification": _json.dumps(_SPEC)}))
assert r.update.get("test_cases") == [_TC("1", "navbar")]      # saved
assert "INCOMPLETE" in r.update["messages"][0].content         # coverage still active
_ok("T18", "JSON-string spec coerced, coverage still enforced on accumulated suite")

_rej([_TC("1", "navbar")], "[INTERNAL]", state={"components_specification": "{not json"})
_ok("T19", "unparseable string spec -> [INTERNAL] refusal, nothing saved")

# ── Naming + Selector Contract (Python-enforced 2026-08-08) ───────────────────
# Both were prompt-only before, and nothing downstream catches a breach: the
# pipeline reports "not found", _route_agent OVERRIDES that to html_agent, and a
# developer agent is sent to fix a page that was never broken -- spending one of
# only TWO correction attempts.
_SPEC_RT = {"components_specification": _SPEC}
_rej([_TC("1", "product-card", sel="#product-card")], "Selector Contract", state=_SPEC_RT)
_rej([_TC("1", "navbar", sel=".navbar")], "Selector Contract", state=_SPEC_RT)
_ok("T20", "Selector Contract enforced both ways (#id vs .className), nothing saved")

_r20 = store_test_cases.func([_TC("1", "product-card", sel="#product-card")], _RT(_SPEC_RT))
assert "'.product-card'" in _r20.update["messages"][0].content, \
    f"the rejection must name the fix, got: {_r20.update['messages'][0].content!r}"
_ok("T21", "the rejection names the exact selector the case should have used")

_rej([_TC("1", "ghost-button")], "not in", state=_SPEC_RT)
_ok("T22", "component absent from components_specification rejected (Naming Contract)")

# One bad case must reject the WHOLE batch — a partial save would leave the suite
# in a state the coverage report no longer describes.
_rej([_TC("1", "navbar"), _TC("2", "product-card", sel="#wrong")],
     "Selector Contract", state=_SPEC_RT)
_ok("T23", "one contract breach rejects the whole batch, nothing saved")

# The guard must NOT fire when there is nothing to check against. This is the
# degenerate-spec path the live E2E TG-03 exercises.
r = store_test_cases.func([_TC("1", "anything", sel=".whatever")], _RT({}))
assert r.update["test_cases"] and "SUITE COMPLETE" in r.update["messages"][0].content
_ok("T24", "no components_specification -> contract guard skipped (TG-03 path)")

# ── State Materialization Contract for assertions (T25..T30, 2026-08-09) ─────
# Both defects below shipped from the FIRST live Secondary Orchestrator run and
# neither was caught by anything: TC-007 asserted data-state on a page that
# materialises aria-disabled, and TC-008 asserted the disabled opacity with no
# covers_state tag, so _order_test_cases ran it against the resting page.
_SM_COMPONENTS = {"pages": [{"pageName": "plp", "regionComponents": {"main": [
    {"id": "add-to-cart-button", "tag": "button", "className": "add-to-cart-btn",
     "states": [{"name": "disabled"}]}]}}]}
_SM_DECO = {"pages": [{"pageName": "plp", "componentDecorations": [
    {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
     "baseStyles": {"opacity": "1", "background-color": "#1a73e8"},
     "stateVariants": [{"stateName": "disabled", "styles": {"opacity": "0.5"}}]}]}]}


def _sm_rt(cases):
    return SimpleNamespace(state={"components_specification": _SM_COMPONENTS,
                         "decoration_specification": _SM_DECO,
                         "test_cases": []}, tool_call_id="sm-1")


def _sm_case(**over):
    tc = {"id": "TC-007", "component": "add-to-cart-button", "description": "d",
          "action": "assert_attribute", "selector": ".add-to-cart-btn",
          "expected": "aria-disabled=true", "passed": False,
          "covers_state": "disabled"}
    tc.update(over)
    return tc


_r = store_test_cases.func([_sm_case()], _sm_rt(None))
assert "test_cases" in _r.update, _r.update["messages"][0].content
_ok("T25", "the contract-correct assertion (aria-disabled=true) is accepted")

_r = store_test_cases.func([_sm_case(expected="data-state=disabled")], _sm_rt(None))
assert "test_cases" not in _r.update, "FAIL: the EXACT SO-01 TC-007 was accepted"
assert "aria-disabled=true" in _r.update["messages"][0].content, \
    _r.update["messages"][0].content
_ok("T26", "the EXACT SO-01 TC-007 (data-state on an aria state) is REJECTED")

_r = store_test_cases.func([_sm_case(expected="aria-disabled=false")], _sm_rt(None))
assert "test_cases" not in _r.update, "FAIL: the RESTING value was accepted"
_ok("T27", "a tagged case asserting the resting value is REJECTED (runs post-click)")

# Untagged assert_attribute is static markup and is none of the guard's business.
_r = store_test_cases.func(
    [_sm_case(id="TC-009", action="assert_attribute", expected="type=button",
              covers_state=None)], _sm_rt(None))
assert "test_cases" in _r.update, _r.update["messages"][0].content
_ok("T28", "an UNTAGGED assert_attribute is untouched (static markup)")

_css_case = dict(id="TC-008", component="add-to-cart-button", description="d",
                 action="assert_css", selector=".add-to-cart-btn",
                 expected="opacity=0.5", passed=False)
_r = store_test_cases.func([dict(_css_case)], _sm_rt(None))
assert "test_cases" not in _r.update, "FAIL: the EXACT SO-01 TC-008 was accepted"
_msg = _r.update["messages"][0].content
assert "covers_state='disabled'" in _msg and "resting" in _msg, _msg
_ok("T29", "the EXACT SO-01 TC-008 (stateVariant value, untagged) is REJECTED")

_r = store_test_cases.func([dict(_css_case, covers_state="disabled")], _sm_rt(None))
assert "test_cases" in _r.update, _r.update["messages"][0].content
_r2 = store_test_cases.func(
    [dict(_css_case, id="TC-005", expected="background-color=#1a73e8")], _sm_rt(None))
assert "test_cases" in _r2.update, _r2.update["messages"][0].content
_ok("T30", "tagging it passes, and a BASE-style value stays untagged and passes")

# ── input / press on a `type` case (2026-08-15) ──────────────────────────────
# A `type` case used to carry no value of its own, so the pipeline filled a fixed
# literal that matches no product. The case still "passed" and the assertion
# after it was vacuous. These four fix the shape of the new keys.

def _ty_case(**over):
    tc = {"id": "TC-040", "component": "add-to-cart-button", "description": "d",
          "action": "type", "selector": ".add-to-cart-btn",
          "expected": "grid narrows to 1 result", "passed": False}
    tc.update(over)
    return tc


_r = store_test_cases.func(
    [_ty_case(input="Aurora Headphones", press="Enter")], _sm_rt(None))
assert "test_cases" in _r.update, _r.update["messages"][0].content
_ok("T31", "a type case carrying its own input and press=Enter is accepted")

_r = store_test_cases.func([_ty_case(press="F13")], _sm_rt(None))
assert "test_cases" not in _r.update, "FAIL: an unsupported key was accepted"
assert "press must be one of" in _r.update["messages"][0].content
_ok("T32", "a key outside VALID_KEYS is REJECTED")

_r = store_test_cases.func(
    [_ty_case(action="click", expected="cart opens", input="anything")], _sm_rt(None))
assert "test_cases" not in _r.update, "FAIL: input on a click was accepted"
assert "only to a 'type' action" in _r.update["messages"][0].content
_ok("T33", "input on a non-type action is REJECTED")

_r = store_test_cases.func([_ty_case(input=42)], _sm_rt(None))
assert "test_cases" not in _r.update, "FAIL: a non-string input was accepted"
_ok("T34", "a non-string input is REJECTED")

# ── an event needs a trigger AND an outcome (2026-08-15) ─────────────────────
# The click branch of _execute_action reports passed=True whenever the element
# exists, so a suite of nothing but clicks proved nothing and still reported
# SUITE COMPLETE. An event now counts only when the same component is asserted.

_clicks_only = [
    _TC("E1", "navbar", action="click", sel="#navbar"),
    _TC("E2", "product-card", action="click", sel=".product-card",
        covers_state="selected"),
    _TC("E3", "product-card", action="click", sel=".product-card",
        covers_event="click"),
]
_r = store_test_cases.func(_clicks_only, _RT({"components_specification": _SPEC}))
_m = _r.update["messages"][0].content
assert "test_cases" in _r.update, "a well-formed batch must still be SAVED"
assert "SUITE COMPLETE" not in _m, f"FAIL: a click-only suite was called complete\n{_m}"
assert "product-card:click" in _m, _m
_ok("T35", "a suite of only clicks does NOT complete event coverage")

assert "NO assertion on the same component" in _m, _m
assert "proves nothing happened" in _m, _m
_ok("T36", "the message names the component and says why the click is not enough")

_r = store_test_cases.func(
    [_TC("E4", "product-card", action="assert_text", sel=".product-card",
         exp="Aurora Headphones")],
    _RT({"components_specification": _SPEC, "test_cases": _clicks_only}))
_m = _r.update["messages"][0].content
assert "SUITE COMPLETE" in _m, f"FAIL: adding the assertion did not complete it\n{_m}"
_ok("T37", "adding an assertion on the same component completes the event")

# ── assert_count (2026-08-15) ────────────────────────────────────────────────
# The first assertion that can observe an outcome. Its expected is a comparator
# and a whole number, and a malformed one must reject rather than silently
# always-pass at execution time.

_r = store_test_cases.func(
    [_TC("C1", "product-card", action="assert_count", sel=".product-card",
         exp=">=1", covers_event="click"),
     _TC("C2", "product-card", action="assert_count", sel=".product-card", exp="=8"),
     _TC("C3", "navbar", action="assert_count", sel="#navbar", exp="< 4")],
    _RT({"components_specification": _SPEC}))
assert "test_cases" in _r.update, _r.update["messages"][0].content
_ok("T38", "assert_count accepts '>=1', '=8' and a spaced '< 4'")

for _bad in ("1", "at least 1", ">=", "many", ">=1.5", ""):
    _r = store_test_cases.func(
        [_TC("C4", "navbar", action="assert_count", sel="#navbar", exp=_bad)],
        _RT({"components_specification": _SPEC}))
    assert "test_cases" not in _r.update, f"FAIL: assert_count accepted {_bad!r}"
    assert "comparator" in _r.update["messages"][0].content
_ok("T39", "a malformed assert_count expected is REJECTED, six shapes checked")

# An assert_count IS an asserting action, so it satisfies the trigger-and-outcome
# rule from T35 on its own. This is the pairing the prompt now asks for.
_r = store_test_cases.func(
    [_TC("C5", "navbar"),
     _TC("C6", "product-card", covers_state="selected"),
     _TC("C7", "product-card", action="click", sel=".product-card",
         covers_event="click"),
     _TC("C8", "product-card", action="assert_count", sel=".product-card",
         exp=">=1", covers_event="click")],
    _RT({"components_specification": _SPEC}))
assert "SUITE COMPLETE" in _r.update["messages"][0].content, \
    _r.update["messages"][0].content
_ok("T40", "a click plus an assert_count on the same component completes the event")

# assert_url in a single-page build must check a '#fragment', never a label
# word or the page name (PO-06 regression, 2026-08-23).
_rej([_TC("u1", "navbar", action="assert_url", sel="#navbar", exp="shop")],
     "begins with '#'")
_ok("T41", "assert_url expecting a label word is rejected")
_r = store_test_cases.func(
    [_TC("u2", "navbar", action="assert_url", sel="#navbar", exp="#product-listing")],
    _RT({}))
assert "test_cases" in _r.update, _r.update["messages"][0].content
_ok("T42", "assert_url expecting a real '#fragment' is accepted")

# assert_url must also carry the selector to click: with no selector the
# pipeline clicks nothing, the URL keeps its fragment-free value, and the
# case can never pass. This is the other half of the po0142c544 failure.
_rej([_TC("u3", "navbar", action="assert_url", sel="", exp="#product-listing")],
     "not an empty selector")
_ok("T43", "assert_url with an empty selector is rejected")

print("=" * 76)
print(f"store_test_cases: {_passed}/47 PASSED   (chunked generation + enriched coverage"
      f" + Naming/Selector + State Materialization Contract + type input/press"
      f" + trigger-and-outcome event coverage + assert_count + resting-state filter)")
print("=" * 76)
