# Ported from fyp.ipynb cell 380 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: sync_hover_test_cases
from types import SimpleNamespace

_HOV_SPEC = {"globalTokens": {}, "pages": [{"pageName": "plp",
    "componentDecorations": [
        {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
         "baseStyles": {"background-color": "#1a73e8"},
         "stateVariants": [{"stateName": "disabled", "styles": {"opacity": "0.5"}},
                           {"stateName": "hover",    "styles": {"background-color": "#ff0000",
                                                                "cursor": "pointer"}}]},
        {"componentId": "navbar", "className": "navbar",
         "baseStyles": {"color": "#000000"}, "stateVariants": []}]}]}

_HOV_TCS = [
    {"id": "TC-001", "component": "add-to-cart-button", "action": "assert_hover_css",
     "selector": ".add-to-cart-btn", "expected": "background-color=#00ff00",
     "passed": None, "description": "d"},
    {"id": "TC-002", "component": "add-to-cart-button", "action": "assert_css",
     "selector": ".add-to-cart-btn", "expected": "background-color=#1a73e8",
     "passed": None, "description": "d"},
    {"id": "TC-003", "component": "navbar", "action": "assert_hover_css",
     "selector": "#navbar", "expected": "color=#111111",
     "passed": None, "description": "d"},
]

def _merged(before, cmd):
    """Apply the delta a sync tool returns, exactly as the state reducer does.

    The tools return only the cases they changed, so a test that wants to reason
    about the WHOLE suite has to merge first. This is the same _merge_test_cases
    the State channel uses, so the tests see what production sees.
    """
    return _merge_test_cases(before, cmd.update.get("test_cases", []))


def _rt_hov(test_cases, deco_spec=_HOV_SPEC):
    return SimpleNamespace(
        state={"decoration_specification": deco_spec, "test_cases": test_cases},
        tool_call_id="hov-001"
    )

# Case 1: assert_hover_css rebuilt from the hover stateVariant (real nested shape)
h1 = sync_hover_test_cases.func("add-to-cart-button", _rt_hov(_HOV_TCS))
_mh1 = _merged(_HOV_TCS, h1)
assert _mh1[0]["expected"] == "background-color=#ff0000|cursor=pointer", f"FAIL: {_mh1[0]['expected']}"
assert [t["id"] for t in h1.update["test_cases"]] == ["TC-001"], \
    f"FAIL: delta should hold only the patched case, got {h1.update['test_cases']}"
print(f"[Case 1] {h1.update['messages'][0].content}")
print("PASS: assert_hover_css rebuilt from the hover stateVariant\n")

# Case 2: the same component's assert_css case is NOT touched (that is sync_css's job)
assert _mh1[1]["expected"] == "background-color=#1a73e8", \
    "FAIL: assert_css case mutated by the hover sync"
print("PASS: assert_css case for the same component untouched\n")

# Case 3: another component's hover case is NOT touched
assert _mh1[2]["expected"] == "color=#111111", \
    "FAIL: another component's assert_hover_css mutated"
print("PASS: other components untouched\n")

# Case 4: component has decoration but NO hover variant -> graceful skip, nothing updated
h4 = sync_hover_test_cases.func("navbar", _rt_hov(_HOV_TCS))
assert "test_cases" not in h4.update, "FAIL: must not update when there is no hover variant"
assert "no hover statevariant" in h4.update["messages"][0].content.lower()
print(f"[Case 4] {h4.update['messages'][0].content}")
print("PASS: component without a hover variant skipped safely\n")

# Case 5: component absent from the decoration spec -> graceful skip
h5 = sync_hover_test_cases.func("ghost-btn", _rt_hov(_HOV_TCS))
assert "test_cases" not in h5.update
print(f"[Case 5] {h5.update['messages'][0].content}")
print("PASS: unknown component skipped safely\n")

# Case 6: LEGACY flat decoration shape still resolves (parity with sync_css_test_cases)
_HOV_LEGACY = {"add-to-cart-button": {"baseStyles": {},
    "stateVariants": [{"stateName": "hover", "styles": {"background-color": "#ff0000",
                                                        "cursor": "pointer"}}]}}
h6 = sync_hover_test_cases.func("add-to-cart-button", _rt_hov(_HOV_TCS, _HOV_LEGACY))
assert _merged(_HOV_TCS, h6)[0]["expected"] == "background-color=#ff0000|cursor=pointer"
print(f"[Case 6] {h6.update['messages'][0].content}")
print("PASS: legacy flat decoration shape still resolves\n")

# Case 7: compatibility — the three sync tools return the SAME Command contract
#         and each patches ONLY its own action, so they can be called in any order.
_shared = [dict(t) for t in _HOV_TCS]
# Chained: the second tool sees the first tool's result, as it would in sequence.
_c  = sync_css_test_cases.func("add-to-cart-button", _rt_hov(_shared))
_seq = _merged(_shared, _c)
_h  = sync_hover_test_cases.func("add-to-cart-button", _rt_hov(_seq))
_seq = _merged(_seq, _h)
assert _seq[1]["expected"] == "background-color=#1a73e8"                  # from sync_css
assert _seq[0]["expected"] == "background-color=#ff0000|cursor=pointer"   # from sync_hover
assert set(_h.update) == set(_c.update) == {"test_cases", "messages"}
print(f"[Case 7] chained sync_css then sync_hover — both edits survive")
print("PASS: sync_css / sync_hover / sync_text are mutually compatible (disjoint actions)\n")

# Case 8: PARALLEL, the shape that raised InvalidUpdateError. Both tools read the
# SAME pre-state, as they do inside one superstep, and both deltas are merged by
# the reducer. Neither edit is lost, which is what returning the whole suite
# would have broken.
_p_css   = sync_css_test_cases.func("add-to-cart-button", _rt_hov(_shared))
_p_hover = sync_hover_test_cases.func("add-to-cart-button", _rt_hov(_shared))
_par = _merge_test_cases(_merge_test_cases(_shared, _p_css.update["test_cases"]),
                         _p_hover.update["test_cases"])
assert _par[0]["expected"] == "background-color=#ff0000|cursor=pointer", \
    f"FAIL: the hover patch was lost: {_par[0]['expected']}"
assert _par[1]["expected"] == "background-color=#1a73e8", \
    f"FAIL: the css patch was lost: {_par[1]['expected']}"
assert [t["id"] for t in _par] == ["TC-001", "TC-002", "TC-003"], \
    f"FAIL: the suite grew or lost cases: {[t['id'] for t in _par]}"
assert _par == _seq, "FAIL: parallel and sequential must reach the same suite"
print("[Case 8] parallel sync_css + sync_hover — both deltas merge, order-independent")
print("PASS: two sync tools in ONE superstep no longer collide or overwrite")


# ── Cases 9-12: the page is the source of truth, not the specification ───────
# E2E-SO-06 failed on 2026-08-16 because this tool read the hover colour out of
# decoration_specification. A modify run never writes back to the specification,
# so it still held the colour from generation, and the rebase moved the
# expectation BACKWARDS onto a value the page had stopped using.
#
# Every case above passes against that broken version, because none of them give
# the tool a page to read. Without a session_id the live lookup returns nothing
# and the specification value is used as the fallback either way. These four
# separate the two on purpose.
import pathlib as _hv_path

_HV_SID = "hovsync1"
_HV_SPEC_COLOUR = "#ff0000"   # what the specification still says
_HV_PAGE_COLOUR = "#0b5394"   # what the CSS agent just wrote to the page

_hv_file = _PREVIEW_ROOT / f"preview_{_HV_SID}.css"
_hv_existed = _hv_file.exists()
_hv_backup = _hv_file.read_text(encoding="utf-8") if _hv_existed else None
_hv_file.parent.mkdir(parents=True, exist_ok=True)
_hv_file.write_text(
    ".add-to-cart-btn { background-color: #1a73e8; }\n"
    ".add-to-cart-btn:hover { background-color: " + _HV_PAGE_COLOUR + "; "
    "cursor: pointer; }\n", encoding="utf-8")

try:
    def _rt_live(test_cases, deco_spec=_HOV_SPEC, modification_context=""):
        return SimpleNamespace(
            state={"decoration_specification": deco_spec,
                   "test_cases": test_cases, "session_id": _HV_SID,
                   "modification_context": modification_context},
            tool_call_id="hov-live")

    # Case 9: the page wins. This is the assertion E2E-SO-06 makes.
    _h9 = sync_hover_test_cases.func("add-to-cart-button", _rt_live(_HOV_TCS))
    _m9 = _merged(_HOV_TCS, _h9)[0]["expected"]
    assert _HV_PAGE_COLOUR in _m9, (
        f"Case 9 FAIL: the rebase used the specification, not the page. Expected "
        f"{_HV_PAGE_COLOUR} (what the stylesheet says), got {_m9!r}. A modify run "
        f"never updates the specification, so reading it rebases the test onto "
        f"the colour the page no longer uses and the suite fails forever.")
    assert _HV_SPEC_COLOUR not in _m9, \
        f"Case 9 FAIL: the stale specification colour survived the rebase: {_m9!r}"
    print("PASS Case 9  - the hover rebase reads the page, not the specification")

    # Case 10: a correction round is refused, exactly as sync_css_test_cases is.
    # Rebasing there would move the goalposts and hide the failure the loop is
    # trying to repair, and it would look like a pass.
    _h10 = sync_hover_test_cases.func(
        "add-to-cart-button",
        _rt_live(_HOV_TCS, modification_context="hover colour was wrong"))
    assert "test_cases" not in _h10.update, \
        ("Case 10 FAIL: the suite was rebased during a correction round, so a "
         "page that is genuinely broken would now pass.")
    assert "refused" in _h10.update["messages"][0].content.lower(), \
        "Case 10 FAIL: the refusal does not say it refused"
    print("PASS Case 10 - a rebase during an internal correction round is refused")

    # Case 11: the specification is NOT written -- modify mode never updates it,
    # and writing the un-reduced decoration_specification channel is exactly
    # what made two syncs in one superstep raise InvalidUpdateError (SO-06).
    assert "decoration_specification" not in _h9.update, \
        "Case 11 FAIL: sync_hover wrote the spec; it must write only test_cases"
    assert set(_h9.update) == {"test_cases", "messages"}, _h9.update
    print("PASS Case 11 - the specification is left untouched; only test_cases is written")

    # Case 12: the resting style is not collateral damage -- _live_hover_styles
    # reads ONLY :hover blocks, so the resting colour must not leak into the
    # hover EXPECTATION the test now carries.
    assert "#1a73e8" not in _m9, \
        f"Case 12 FAIL: the resting colour leaked into the hover expectation: {_m9!r}"
    print("PASS Case 12 - the resting colour never leaks into the hover expectation")
finally:
    if _hv_existed:
        _hv_file.write_text(_hv_backup, encoding="utf-8")
    else:
        _hv_file.unlink(missing_ok=True)
print()
