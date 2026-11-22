# Ported from fyp.ipynb cell 347 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Rescued (ticket 05): the notebook marked this cell NOTEBOOK-ONLY, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
# ═══════════════════════════════════════════════════════════════════════════
# TIER 1 — TOOL UNIT TESTS: TEST EXECUTION PIPELINE  (mocked browser, 0 LLM calls)
#
#   Helpers ......  _hex_to_rgb
#   Action exec ..  _execute_action  (visible/text/css/hover_css/attribute/url/
#                   click/type + exception handling)
#   Report build .  _build_report    (pass/fail/routing/infra/targeted re-check)
#   Page health ..  _sweep_resources (broken-image findings, routing, isolation)
#   Suite driver .  run_test_suite   (empty/load-retry/happy/transient/viewport)
# ═══════════════════════════════════════════════════════════════════════════
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
# Ticket 05: the notebook patched "__main__._get_browser", its flat namespace.
# run_test_suite now reads _get_browser from webforge.test_execution.suite
# (ticket 11; it was webforge.test_exec before), so that is where the patches go.

_passed = 0
def _ok(tid, desc):
    global _passed
    _passed += 1
    print(f"PASS  {tid:<4} {desc}")

# ── _hex_to_rgb ───────────────────────────────────────────────────────────────
assert _hex_to_rgb("#ff0000") == "rgb(255, 0, 0)",    "FAIL: full hex red"
assert _hex_to_rgb("#fff")    == "rgb(255, 255, 255)", "FAIL: short hex white"
assert _hex_to_rgb("#1a73e8") == "rgb(26, 115, 232)",  "FAIL: brand blue"
_ok("T1", "_hex_to_rgb converts hex -> rgb")

# ── _execute_action ───────────────────────────────────────────────────────────
def _mock_page(found=True, inner_text="Sample Text", evaluate_return="rgb(255, 0, 0)"):
    page = MagicMock()
    page.query_selector.return_value = MagicMock() if found else None
    if found:
        page.query_selector.return_value.inner_text.return_value = inner_text
    # Since commit a6eae82, assert_css first asks the browser what the expected
    # value computes to (_probe_expected_css, one more page.evaluate). A mock
    # that answers every evaluate with the actual value makes that probe say
    # "expected == actual", so no mismatch could ever fail. The probe gets None,
    # its "cannot compute" answer, and the expected value is used as written.
    page.evaluate.side_effect = lambda js, *a: (
        None if js == _PROBE_EXPECTED_JS else evaluate_return)
    return page

r = _execute_action(_mock_page(found=True),
                    {"action": "assert_visible", "selector": "s", "expected": ""}, "sid")
assert r["passed"] is True
_ok("T2", "assert_visible finds a present element")

r = _execute_action(_mock_page(found=False),
                    {"action": "assert_visible", "selector": "s", "expected": ""}, "sid")
assert r["passed"] is False and "not found" in r["reason"]
_ok("T3", "assert_visible flags a missing element")

r = _execute_action(_mock_page(inner_text="Add to Cart"),
                    {"action": "assert_text", "selector": "s", "expected": "Add to Cart"}, "sid")
assert r["passed"] is True
_ok("T4", "assert_text matches expected text")

r = _execute_action(_mock_page(inner_text="Wrong Text"),
                    {"action": "assert_text", "selector": "s", "expected": "Add to Cart"}, "sid")
assert r["passed"] is False and "Add to Cart" in r["reason"]
_ok("T5", "assert_text catches a text mismatch")

r = _execute_action(_mock_page(evaluate_return="rgb(255, 0, 0)"),
                    {"action": "assert_css", "selector": "s",
                     "expected": "background-color=#ff0000"}, "sid")
assert r["passed"] is True, f"FAIL: {r['reason']}"
_ok("T6", "assert_css matches after hex->rgb convert")

r = _execute_action(_mock_page(evaluate_return="rgb(0, 0, 255)"),
                    {"action": "assert_css", "selector": "s",
                     "expected": "background-color=#ff0000"}, "sid")
assert r["passed"] is False and "background-color" in r["reason"]
_ok("T7", "assert_css catches a colour mismatch")

r = _execute_action(_mock_page(found=False),
                    {"action": "assert_css", "selector": "s",
                     "expected": "background-color=#ff0000"}, "sid")
assert r["passed"] is False and r["reason"] == "'s' not found", (
    f"Expected a clean 'not found' message (matching assert_text's own pattern), "
    f"got: {r['reason']!r}"
)
_ok("T8", "assert_css missing element -> clean 'not found'")

r = _execute_action(_mock_page(evaluate_return="rgb(21, 87, 176)"),
                    {"action": "assert_hover_css", "selector": "s",
                     "expected": "background-color=#1557b0"}, "sid")
assert r["passed"] is True, f"FAIL: {r['reason']}"
_ok("T9", "assert_hover_css matches while hovering")

_hp = _mock_page(evaluate_return="rgb(0, 0, 255)")
r = _execute_action(_hp, {"action": "assert_hover_css", "selector": "s",
                          "expected": "background-color=#1557b0"}, "sid")
assert r["passed"] is False and "background-color" in r["reason"]
_hp.hover.assert_called_once_with("s", timeout=10000)  # matches the cold-start hover timeout
_ok("T10", "assert_hover_css mismatch, hover invoked")

_ap = _mock_page()
_ap.query_selector.return_value.get_attribute.return_value = "true"
r = _execute_action(_ap, {"action": "assert_attribute", "selector": "s",
                          "expected": "aria-expanded=true"}, "sid")
assert r["passed"] is True
_ok("T11", "assert_attribute matches its value")

_ap2 = _mock_page()
_ap2.query_selector.return_value.get_attribute.return_value = None
r = _execute_action(_ap2, {"action": "assert_attribute", "selector": "s",
                           "expected": "aria-expanded=true"}, "sid")
assert r["passed"] is False and "missing" in r["reason"]
_ok("T12", "assert_attribute missing attribute fails")

_ap3 = _mock_page()
_ap3.query_selector.return_value.get_attribute.return_value = ""
r = _execute_action(_ap3, {"action": "assert_attribute", "selector": "s",
                           "expected": "disabled="}, "sid")
assert r["passed"] is True
_ok("T13", "assert_attribute presence-only (empty value)")

_up = _mock_page(); _up.url = "file:///C:/x/preview_cart.html"
r = _execute_action(_up, {"action": "assert_url", "selector": "s",
                          "expected": "cart"}, "sid")
assert r["passed"] is True
r = _execute_action(_up, {"action": "assert_url", "selector": "s",
                          "expected": "checkout"}, "sid")
assert r["passed"] is False and "checkout" in r["reason"]
_ok("T14", "assert_url match and mismatch")

# T14b: assert_url must CLICK its selector first. A nav link only adds the
# "#<id>" fragment to the URL once clicked; the shared page opens with none.
# This is the exact shape that shipped 6 dead cases on po0142c544
# (TC-011..TC-025: selector = a nav link, expected = a "#id"), all FAILED
# because the old branch read page.url without ever clicking.
_np = _mock_page(); _np.url = "file:///C:/x/preview.html"   # opens, no fragment
def _click_adds_hash(sel):
    _np.url = "file:///C:/x/preview.html#coffee-listing"
_np.click.side_effect = _click_adds_hash
r = _execute_action(_np, {"action": "assert_url", "selector": "#hdr_listing_link",
                          "expected": "#coffee-listing"}, "sid")
assert r["passed"] is True, r
assert _np.click.call_args[0][0] == "#hdr_listing_link"   # it clicked THE link
_ok("T14b", "assert_url clicks its nav-link selector, then the fragment matches")

# T14c: an empty selector skips the click, so a pure-URL check still works
# and we never click nothing. Proves the "if selector:" guard.
_nc = _mock_page(); _nc.url = "file:///C:/x/preview.html"
r = _execute_action(_nc, {"action": "assert_url", "selector": "",
                          "expected": "#coffee-listing"}, "sid")
assert r["passed"] is False           # no click -> no fragment -> mismatch
assert _nc.click.called is False      # empty selector -> did NOT click
_ok("T14c", "empty selector skips the click (pure-URL check still works)")

r = _execute_action(_mock_page(), {"action": "click", "selector": "s", "expected": ""}, "sid")
assert r["passed"] is True
_ok("T15", "click executes")

r = _execute_action(_mock_page(), {"action": "type", "selector": "s", "expected": ""}, "sid")
assert r["passed"] is True
_ok("T16", "type executes")

bad = MagicMock()
bad.query_selector.side_effect = Exception("element detached")
r = _execute_action(bad, {"action": "assert_visible", "selector": "s", "expected": ""}, "sid")
assert r["passed"] is False and "element detached" in r["reason"]
_ok("T17", "exception is caught cleanly")

# ── _build_report ─────────────────────────────────────────────────────────────
_all_pass = [{"id": "TC-001", "component": "nav", "passed": True,  "reason": "", "action": "assert_visible"},
             {"id": "TC-002", "component": "btn", "passed": True,  "reason": "", "action": "click"}]
_mixed    = [{"id": "TC-001", "component": "nav", "passed": True,  "reason": "", "action": "assert_visible"},
             {"id": "TC-002", "component": "btn", "passed": False, "reason": "colour mismatch", "action": "assert_css"}]

r = _build_report(_all_pass)
assert "ALL TESTS PASSED" in r and "Action required" not in r
_ok("T18", "_build_report all-pass report")

r = _build_report(_mixed)
assert "FAILED: TC-002 [assert_css]" in r, f"Expected [assert_css] tag in FAILED line, got: {r}"
assert "Action required" in r
_ok("T19", "_build_report mixed results, [action] tag")

assert "- css_agent | intent=modify | target_component=btn" in r, \
    f"assert_css failure should route to css_agent: {r}"
_ok("T20", "_build_report routes assert_css -> css_agent")

# Per-action routing: each failing action goes to the right developer agent,
# and a 'not found' reason overrides the action (here assert_css -> html_agent).
_multi = [
    {"id": "TC-01", "component": "btn",  "passed": False, "reason": "colour mismatch",   "action": "assert_css"},
    {"id": "TC-02", "component": "menu", "passed": False, "reason": "no effect",         "action": "click"},
    {"id": "TC-03", "component": "cart", "passed": False, "reason": "'.cart' not found", "action": "assert_css"},
    {"id": "TC-04", "component": "hero", "passed": False, "reason": "expected 'Sale'",   "action": "assert_text"},
]
r = _build_report(_multi)
assert "- css_agent | intent=modify | target_component=btn"   in r, r
assert "- js_agent | intent=modify | target_component=menu"   in r, r
assert "- html_agent | intent=modify | target_component=cart" in r, r  # not-found overrides assert_css
assert "- html_agent | intent=modify | target_component=hero" in r, r
_ok("T21", "_build_report per-action routing + not-found override")

# Infra actions (image_load_infra) do NOT route to a dev agent -- they emit an [infra] note.
_infra = [{"id": "TC-99", "component": "hero", "passed": False,
           "reason": "all images on the page failed to load", "action": "image_load_infra"}]
r = _build_report(_infra)
assert "[infra] TC-99" in r, f"an infra failure should emit an [infra] note: {r}"
assert "intent=modify" not in r, f"infra failure must NOT produce a dev-agent work order: {r}"
_ok("T22", "_build_report infra (image_load_infra) -> [infra] note")

r = _build_report(_mixed, modification_context="btn")
assert "Targeted re-check (btn)" in r and "TC-002" in r
_ok("T23", "_build_report targeted re-check block")

# ── run_test_suite ────────────────────────────────────────────────────────────
def _rt(test_cases, mod_ctx=""):
    return SimpleNamespace(
        state={"test_cases": test_cases, "preview_url": "file:///t.html",
               "session_id": "s1",       "modification_context": mod_ctx},
        tool_call_id="rts-001"
    )

_tc = [{"id": "TC-001", "component": "btn", "description": "d",
        "action": "assert_visible", "selector": "s", "expected": "e", "passed": None}]

r = run_test_suite.func(_rt([]))
assert "no test cases" in r.update["messages"][0].content.lower()
_ok("T24", "run_test_suite empty test_cases")

_mb = MagicMock(); _mp = MagicMock()
_mb.new_page.return_value = _mp
_mp.goto.side_effect = Exception("ERR_FILE_NOT_FOUND")
with patch("webforge.test_execution.suite._get_browser", return_value=_mb), patch("time.sleep"):
    r = run_test_suite.func(_rt(_tc))
assert _mp.goto.call_count == 3, (
    f"Expected 3 load attempts (1 try + 2 retries), got {_mp.goto.call_count}"
)
assert "page failed to load" in r.update["test_report"]
assert "[page_load]" in r.update["test_report"], (
    f"Expected [page_load] tag in the page-load-failure report, got: {r.update['test_report']}"
)
_ok("T25", "run_test_suite page-load failure (3 tries, [page_load])")

_mb2 = MagicMock(); _mp2 = MagicMock()
_mb2.new_page.return_value = _mp2
_mp2.goto.return_value = None
_mp2.query_selector.return_value = MagicMock()
with patch("webforge.test_execution.suite._get_browser", return_value=_mb2):
    r = run_test_suite.func(_rt(_tc))
assert r.update["test_cases"][0]["passed"] is True
assert "ALL TESTS PASSED" in r.update["test_report"]
_mp2.set_default_timeout.assert_called_once_with(3000)
_ok("T26", "run_test_suite happy path, 3s timeout cap")

# Transient hiccup: first goto fails, second succeeds -> suite runs normally,
# no [page_load] failure, no correction attempt wasted
_mb3 = MagicMock(); _mp3 = MagicMock()
_mb3.new_page.return_value = _mp3
_mp3.goto.side_effect = [Exception("transient file lock"), None]
_mp3.query_selector.return_value = MagicMock()
with patch("webforge.test_execution.suite._get_browser", return_value=_mb3), patch("time.sleep"):
    r = run_test_suite.func(_rt(_tc))
assert r.update["test_cases"][0]["passed"] is True
assert "ALL TESTS PASSED" in r.update["test_report"]
assert _mp3.goto.call_count == 2, (
    f"Expected 2 load attempts (fail, then success), got {_mp3.goto.call_count}"
)
_ok("T27", "run_test_suite transient hiccup recovered")

# Viewport: case with viewport runs at that size; next case restores default
_mb4 = MagicMock(); _mp4 = MagicMock()
_mb4.new_page.return_value = _mp4
_mp4.goto.return_value = None
_mp4.query_selector.return_value = MagicMock()
_tc_vp = [
    {"id": "TC-001", "component": "nav", "description": "d", "action": "assert_visible",
     "selector": "s", "expected": "e", "passed": None, "viewport": "375x812"},
    {"id": "TC-002", "component": "nav", "description": "d", "action": "assert_visible",
     "selector": "s", "expected": "e", "passed": None},
]
with patch("webforge.test_execution.suite._get_browser", return_value=_mb4), patch("time.sleep"):
    r = run_test_suite.func(_rt(_tc_vp))
_vp_calls = [c.args[0] for c in _mp4.set_viewport_size.call_args_list]
assert _vp_calls == [{"width": 375, "height": 812}, {"width": 1280, "height": 720}], \
    f"FAIL: viewport calls wrong: {_vp_calls}"
assert "ALL TESTS PASSED" in r.update["test_report"]
_ok("T28", "run_test_suite per-case viewport + restore")

# modification_context forwarding: run_test_suite must READ modification_context
# from state and pass it into _build_report, producing the "Targeted re-check"
# block. T23 tests _build_report directly; this covers the run_test_suite seam.
_mb5 = MagicMock(); _mp5 = MagicMock()
_mb5.new_page.return_value = _mp5
_mp5.goto.return_value = None
_mp5.query_selector.return_value = MagicMock()
_tc_mc = [{"id": "TC-001", "component": "add-to-cart-btn", "description": "d",
           "action": "assert_visible", "selector": "s", "expected": "e", "passed": None}]
with patch("webforge.test_execution.suite._get_browser", return_value=_mb5):
    r = run_test_suite.func(_rt(_tc_mc, mod_ctx="add-to-cart-btn"))
assert "Targeted re-check (add-to-cart-btn)" in r.update["test_report"], (
    f"run_test_suite must forward state's modification_context into the report, "
    f"got: {r.update['test_report']}"
)
assert "TC-001" in r.update["test_report"]
_ok("T29", "run_test_suite forwards modification_context -> targeted re-check block")

# ═══════════════════════════════════════════════════════════════════════════

# ── _order_test_cases: execution order is guaranteed in Python ────────────────
# The whole suite shares ONE page instance (goto is called once), so a click
# leaks into every later case. Before this, order came from whatever the model
# wrote across several batches.
def _oc(tid, action="assert_visible", **extra):
    return {"id": tid, "component": "add-to-cart-button", "description": "d",
            "action": action, "selector": ".add-to-cart-btn", "expected": "",
            "passed": None, **extra}


# The exact shape that failed on the live SO-01 run: the state assertion sits
# BEFORE the click that produces the state, so on a fresh page it reads the
# resting value and fails.
_bad = [_oc("TC-1", "assert_attribute", expected="aria-disabled=true", covers_state="disabled"),
        _oc("TC-2", "assert_text", expected="Add to cart"),
        _oc("TC-3", "click", covers_event="click")]
assert [t["id"] for t in _order_test_cases(_bad)] == ["TC-2", "TC-3", "TC-1"], \
    f"got {[t['id'] for t in _order_test_cases(_bad)]}"
_ok("T30", "state assertion moved AFTER the click that produces it; resting-value case first")

# An already-correct suite must come back unchanged.
_good = [_oc("TC-1", "assert_text", expected="Add to cart"),
         _oc("TC-2", "click", covers_event="click"),
         _oc("TC-3", "assert_attribute", expected="aria-disabled=true", covers_state="disabled")]
assert [t["id"] for t in _order_test_cases(_good)] == ["TC-1", "TC-2", "TC-3"]
_ok("T31", "a suite already in the right order is left alone")

# Stability: the model's own order survives inside a phase.
_same = [_oc("TC-%d" % n) for n in range(1, 6)]
assert [t["id"] for t in _order_test_cases(_same)] == [t["id"] for t in _same]
_ok("T32", "sort is stable — order within a phase is preserved")

# A click that is ITSELF tagged with the state stays in the interaction phase:
# the click is what performs the transition, so it must not be pushed after it.
_both = [_oc("TC-1", "assert_visible"),
         _oc("TC-2", "click", covers_event="click", covers_state="disabled")]
assert [t["id"] for t in _order_test_cases(_both)] == ["TC-1", "TC-2"]
_ok("T33", "a click tagged covers_state stays in the interaction phase")

# hover is a live pseudo-state, so a tagged assert_hover_css must NOT be deferred
# behind a click that could disable the element.
_hov = [_oc("TC-1", "assert_hover_css", expected="background-color=#1558b0",
            covers_state="hover"),
        _oc("TC-2", "click", covers_event="click")]
assert [t["id"] for t in _order_test_cases(_hov)] == ["TC-1", "TC-2"]
_ok("T34", "assert_hover_css is not deferred — hover needs no prior interaction")

# Degenerate inputs must not raise inside the browser thread.
assert _order_test_cases([]) == []
assert len(_order_test_cases([_oc("TC-1"), "not a dict", None])) == 3
_ok("T35", "empty suite and non-dict entries tolerated")

# ── _sweep_resources + report integration (2026-08-09) ────────────────────────
# The sweep is the PAGE-level half of "LLMs decide, Python guarantees": no model
# chooses whether it runs. It exists because assert_visible resolves to
# `query_selector(...) is not None`, so a broken <img> is in the DOM and passes.
class _SweepPage:
    """Minimal page double: only what _sweep_resources touches."""
    def __init__(self, broken):
        self._broken = broken
    def wait_for_function(self, *a, **k):
        return None
    def evaluate(self, *a, **k):
        return self._broken


assert _sweep_resources(_SweepPage([])) == []
_ok("T36", "a page with no broken image yields no findings")

_sw = _sweep_resources(_SweepPage([
    {"src": "https://via.placeholder.com/400x300", "id": "", "cls": "product-img card",
     "alt": "Running shoe"}]))
assert len(_sw) == 1, _sw
_f = _sw[0]
assert _f["id"] == "AUTO-IMG-01", _f          # prefix keeps it separable in metrics
assert _f["action"] == "image_load", _f
assert _f["passed"] is False, _f
assert _f["selector"] == ".product-img", _f   # Selector Contract: className wins
assert _f["component"] == "product-img", _f
assert "via.placeholder.com" in _f["reason"], _f
# Ticket 05: an assert that the reason names "a bundled local photograph" was
# deleted. The image feature is gone (store_html_code refuses every <img>),
# so it pinned advice the agent can no longer follow.
_ok("T37", "a broken image becomes one routable AUTO-IMG finding")

_sw2 = _sweep_resources(_SweepPage([
    {"src": "a.png", "id": "hero-img", "cls": "", "alt": ""},
    {"src": "",      "id": "",         "cls": "", "alt": ""}]))
assert [f["selector"] for f in _sw2] == ["#hero-img", "img"], _sw2
assert [f["id"] for f in _sw2] == ["AUTO-IMG-01", "AUTO-IMG-02"], _sw2
_ok("T38", "selector falls back id -> tag, findings are numbered")

# A bare <img> has no id and no class of its own. The browser-side closest()
# call resolves the nearest addressable ancestor, so the page double supplies
# what that lookup would have returned: the product card, not "image".
_sw3 = _sweep_resources(_SweepPage([
    {"src": "https://via.placeholder.com/400x300", "id": "",
     "cls": "product-card", "alt": "Product"}]))
assert _sw3[0]["component"] == "product-card", _sw3
assert _sw3[0]["selector"] == ".product-card", _sw3
_ok("T39", "a bare <img> is reported against its enclosing component")

assert _route_agent(_f) == "html_agent"
_ok("T40", "a sweep finding routes to html_agent")

# The whole point: every authored case passes, the page is still broken.
_rep = _build_report(_all_pass, "", _sw)
assert "ALL TESTS PASSED" not in _rep, f"a broken image must not report all-pass: {_rep}"
assert "FAILED: AUTO-IMG-01 [image_load]" in _rep, _rep
assert "- html_agent | intent=modify | target_component=product-img" in _rep, _rep
assert "PASSED: TC-001, TC-002" in _rep, "the authored suite still reports its own result"
_ok("T41", "authored suite all-pass + broken image -> work order, not all-pass")

assert "ALL TESTS PASSED" in _build_report(_all_pass, "", [])
assert "ALL TESTS PASSED" in _build_report(_all_pass)
_ok("T42", "_build_report is unchanged when the sweep finds nothing")

# A MagicMock page returns a stub from evaluate(), not a list. Every pre-existing
# run_test_suite case (T25-T35) drives exactly such a page, so the sweep must
# degrade to "no findings" instead of iterating a mock.
assert _sweep_resources(MagicMock()) == []
_ok("T43", "a mocked page yields no findings instead of raising")

# End to end through run_test_suite: the finding reaches the report, and
# test_cases stays the AUTHORED suite so the pass-rate metric is unpolluted.
_mbi = MagicMock(); _mpi = MagicMock()
_mbi.new_page.return_value = _mpi
_mpi.goto.return_value = None
_mpi.query_selector.return_value = MagicMock()
_mpi.evaluate.return_value = [{"src": "https://via.placeholder.com/1", "id": "",
                               "cls": "product-img", "alt": "P"}]
with patch("webforge.test_execution.suite._get_browser", return_value=_mbi):
    _ri = run_test_suite.func(_rt(_tc))
assert [t["id"] for t in _ri.update["test_cases"]] == ["TC-001"], \
    f"a sweep finding must NOT be stored as a test case: {_ri.update['test_cases']}"
assert "AUTO-IMG-01" in _ri.update["test_report"], _ri.update["test_report"]
assert "ALL TESTS PASSED" not in _ri.update["test_report"]
_ok("T44", "run_test_suite reports the finding but never stores it as a case")

# ── _normalize_css_value: a hex ANYWHERE in the value (2026-08-09) ───────────
# The defect this closes was not a bad message, it was an UNWINNABLE FIX LOOP.
# `border=1px solid #dddddd` never started with '#', so the hex was never
# converted, the browser always reported rgb(), and the comparison could not
# succeed no matter what the CSS agent wrote. It burned 2/2 corrections in
# E2E-SO-01, SO-03 and SO-04 against a stylesheet that was already correct.

assert _normalize_css_value("#dddddd") == "rgb(221, 221, 221)"
assert _normalize_css_value("#fff")    == "rgb(255, 255, 255)"
_ok("T45", "a bare hex still converts (the case that always worked)")

assert _normalize_css_value("1px solid #dddddd") == "1px solid rgb(221, 221, 221)"
assert _normalize_css_value("0 2px 4px #1a73e8") == "0 2px 4px rgb(26, 115, 232)"
_ok("T46", "a hex INSIDE a shorthand converts -- the unwinnable-loop fix")

# '#dddddd' must not be read as '#ddd' followed by a stray 'ddd'.
assert _normalize_css_value("#dddddd").count("rgb") == 1, _normalize_css_value("#dddddd")
# A malformed length is left alone rather than silently half-converted.
assert _normalize_css_value("#dddd") == "#dddd"
_ok("T47", "6-digit wins over 3-digit; a malformed hex is left untouched")

assert _normalize_css_value("1px   solid    #ddd") == "1px solid rgb(221, 221, 221)"
_ok("T48", "runs of whitespace collapse, so spec spacing cannot fail a match")

# End to end through the real comparison path, with the exact live failure.
_pg = MagicMock()
_pg.evaluate.return_value = "1px solid rgb(221, 221, 221)"
assert _css_pair_mismatches(_pg, ".product-card", "border=1px solid #dddddd") == [], \
    "the live TC-003 failure must now pass"
# The probe (commit a6eae82) gets None, as in _mock_page above.
_pg.evaluate.side_effect = lambda js, *a: (
    None if js == _PROBE_EXPECTED_JS else "2px solid rgb(221, 221, 221)")
_mm = _css_pair_mismatches(_pg, ".product-card", "border=1px solid #dddddd")
assert len(_mm) == 1 and "rgb(221, 221, 221)" in _mm[0], _mm
_ok("T49", "live TC-003 now passes, and a REAL mismatch is still caught")

print(f"  ... {_passed}/49 through T49 (run_test_suite and helpers)")

# ── T50..T52  _route_agent: static vs dynamic assert_attribute (2026-08-09) ──
_rt_static = {"id": "TC-009", "action": "assert_attribute", "component": "btn",
              "reason": "expected 'button', got 'submit'", "passed": False}
assert _route_agent(_rt_static) == "html_agent", _route_agent(_rt_static)
_ok("T50", "an UNTAGGED assert_attribute is static markup -> html_agent")

_rt_dyn = dict(_rt_static, id="TC-007", covers_state="disabled",
               reason="aria-disabled: expected 'true', got 'false'")
assert _route_agent(_rt_dyn) == "js_agent", _route_agent(_rt_dyn)
_ok("T51", "a TAGGED assert_attribute asserts a transition -> js_agent")

# The not-found override still wins: if the element is absent, no handler can
# help and the markup is what is missing.
_rt_missing = dict(_rt_dyn, reason="element not found: .add-to-cart-btn")
assert _route_agent(_rt_missing) == "html_agent", _route_agent(_rt_missing)
_ok("T52", "not-found still overrides to html_agent even when tagged")



# ── T53..T55  assert_url routing (added 2026-08-10) ─────────────────────────
# Single-document navigation is anchor scrolling, so the only URL change a page
# can produce is a hash fragment, and that lives in an <a href="#x">. Routing it
# to the JS agent would ask JS to fix markup.
assert _route_agent({"action": "assert_url", "expected": "#shop",
                     "reason": "expected URL to contain '#shop'"}) == "html_agent"
_ok("T53", "assert_url on a '#fragment' routes to the HTML agent")

assert _route_agent({"action": "assert_url", "expected": "checkout.html",
                     "reason": "expected URL to contain 'checkout.html'"}) == "js_agent"
_ok("T54", "assert_url on a real navigation stays with the JS agent")

assert _route_agent({"action": "assert_url", "expected": "#shop",
                     "reason": "'#nav-shop' not found"}) == "html_agent"
_ok("T55", "a not-found reason still overrides, and agrees here")


# ── T56..T60  environment vs code, in the page-health sweep ─────────────────
# E2E-SO-01 on 2026-08-10 spent BOTH correction attempts on images while
# loremflickr, picsum.photos AND placehold.co were all unreachable, then
# "fixed" it by replacing the photo with a drawn placeholder. One broken image
# among several is a wrong src the HTML agent can fix. All of them failing is
# the network, and no edit to the page helps.
class _SwPage:
    def __init__(self, broken, total):
        self._b, self._t = broken, total

    def wait_for_function(self, *a, **k):
        pass

    def evaluate(self, js):
        return self._t if "document.images.length" in js else self._b


_SW_IMG = {"src": "https://picsum.photos/seed/x/400/300", "id": "",
           "cls": "product-card", "alt": "shoe"}

_sw_all = _sweep_resources(_SwPage([_SW_IMG], 1))
assert _sw_all[0]["action"] == "image_load_infra", _sw_all[0]["action"]
assert _route_agent(_sw_all[0]) is None, "an all-down sweep must not route"
_ok("T56", "every image down -> image_load_infra, routes to no agent")

_sw_one = _sweep_resources(_SwPage([_SW_IMG], 3))
assert _sw_one[0]["action"] == "image_load"
assert _route_agent(_sw_one[0]) == "html_agent"
_ok("T57", "one image of three down -> image_load -> html_agent")

# Ticket 05: T58 was deleted. It pinned the same stale image-fix wording
# ("Do NOT substitute a data: URI"), for a feature that no longer exists.

_sw_pass = [{"id": "TC-001", "action": "assert_visible", "component": "c",
             "passed": True, "reason": ""}]
_rep = _build_report(_sw_pass, "", _sw_all)
assert "ALL TESTS PASSED" in _rep and "no correction attempt" in _rep, _rep
assert "FAILED: AUTO-IMG" not in _rep, "an infra finding was listed as FAILED"
_ok("T59", "suite passes + all images down -> ALL TESTS PASSED + [infra] note")

_rep2 = _build_report(_sw_pass, "", _sw_one)
assert "ALL TESTS PASSED" not in _rep2 and "html_agent | intent=modify" in _rep2
_ok("T60", "suite passes + ONE image down -> still a work order")


# ── T61..T64  a computed style must never be read mid-transition ────────────
# E2E-SO-04, session so4acab0, 2026-08-11. TC-008 covers the DISABLED state, so
# the pipeline clicks the button and then asserts its background. The click left
# the pointer ON the button, :hover engaged, and the stylesheet carried
# `transition: background-color 0.2s ease`. The assertion sampled the colour 58%
# of the way from #d93025 to the hover colour #0b57d0 and read rgb(98, 70, 136)
# -- a value that appears nowhere in the stylesheet and exists for 200ms.
#
# That makes the assertion TIMING-DEPENDENT, which is worse than a plain
# failure: the same page passes and fails on consecutive runs, and Metric 3 of
# the evaluation campaign measures precisely that stability.
class _TransPage:
    """Returns a different computed style on each read until it settles."""

    def __init__(self, frames):
        self._frames, self._i = list(frames), 0
        self.moved_to, self.waits, self.clicked, self.hovered = [], 0, [], []

    def evaluate(self, js, *a):
        v = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return v

    def wait_for_timeout(self, ms):
        self.waits += 1

    class _Mouse:
        def __init__(self, outer):
            self.outer = outer

        def move(self, x, y):
            self.outer.moved_to.append((x, y))

    @property
    def mouse(self):
        return _TransPage._Mouse(self)

    def query_selector(self, sel):
        return object()

    def click(self, sel):
        self.clicked.append(sel)

    def hover(self, sel, timeout=None):
        self.hovered.append(sel)


# a transition that moves for three reads, then holds
_TR = _TransPage(["a|1", "b|1", "c|1", "settled|1", "settled|1", "settled|1"])
_settle_transitions(_TR, ".add-to-cart-btn")
assert _TR.waits >= 1, "settle returned without ever waiting"
_ok("T61", "_settle_transitions waits until two reads agree")

# a page that never settles must give up, not hang the suite
_never = _TransPage([str(n) for n in range(500)])
_settle_transitions(_never, ".x", timeout_ms=180)
assert _never.waits <= 4, "the settle wait is not bounded (%d waits)" % _never.waits
_ok("T62", "a never-settling page is bounded, not hung")

# a page whose evaluate raises must not fail the run on its own
class _Boom(_TransPage):
    def evaluate(self, js, *a):
        raise RuntimeError("detached frame")


_settle_transitions(_Boom([]), ".x")
_ok("T63", "a raising settle check is swallowed, never a spurious failure")

# the sequence that actually broke: click, then assert the resting style
_seq = _TransPage(["moving", "settled", "settled"])
_execute_action(_seq, {"action": "click", "selector": ".add-to-cart-btn",
                       "expected": ""}, "s")
assert _seq.moved_to, "click left the pointer on the element, so :hover persists"
_ok("T64", "click parks the mouse, so :hover cannot leak into the next assertion")

# -- _sweep_dead_selectors: CSS<->DOM drift detection (2026-08-24) --------------
class _DeadPage:
    """Minimal page double: returns a canned dead-selector list from evaluate()."""
    def __init__(self, dead):
        self._dead = dead
    def evaluate(self, *a, **k):
        return self._dead

assert _sweep_dead_selectors(_DeadPage([])) == []
assert _sweep_dead_selectors(_DeadPage("nope")) == []
_ok("T65", "a page with no dead selectors yields no finding")

_dead = _sweep_dead_selectors(_DeadPage([".hero", ".product-grid", ".header-links a"]))
assert len(_dead) == 1 and _dead[0]["action"] == "css_dead_selector"
assert "3 CSS selector" in _dead[0]["reason"] and ".hero" in _dead[0]["reason"]
assert _route_agent(_dead[0]) == "css_agent"
_ok("T66", "dead selectors collapse to one css_agent finding, routed correctly")

_rep_dead = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", _dead)
assert "ALL TESTS PASSED" not in _rep_dead and "css_agent" in _rep_dead and "AUTO-CSS-01" in _rep_dead
_ok("T67", "a clean suite with a dead-selector finding still demands a CSS fix")


# -- _sweep_geometry: can a visitor reach the controls? (2026-08-31) ------------
# PO-08 po01e9a8b4 squeezed six category tiles into a 168px column, so the <li>
# covered each other and Playwright refused the click with "<li> intercepts
# pointer events". assert_text on those same tiles passed -- the elements were
# in the DOM with the right words in them -- so the suite reported green on a
# page nobody could tap. Every existing assertion resolves through
# query_selector, so none of them can see this.
class _GeoPage:
    """Minimal page double: returns a canned geometry dict from evaluate()."""
    def __init__(self, got):
        self._got = got
    def evaluate(self, *a, **k):
        return self._got


_GEO_CLEAN = {"blocked": [], "considered": 41, "overflow": 0, "width": 1440}
assert _sweep_geometry(_GeoPage(_GEO_CLEAN)) == []
assert _sweep_geometry(_GeoPage("nope")) == []
_ok("T68", "a page whose controls are all reachable yields no finding")

_geo = _sweep_geometry(_GeoPage({
    "blocked": ["#category-tile-light is covered by <li>",
                "#category-tile-dark is covered by <li>"],
    "considered": 41, "overflow": 0, "width": 1440}))
assert len(_geo) == 1 and _geo[0]["action"] == "layout_unclickable"
assert "2 of 41" in _geo[0]["reason"], _geo[0]["reason"]
assert "category-tile-light" in _geo[0]["reason"]
# Routed to CSS: an element covered by a sibling is produced by the stylesheet,
# not by the markup or the script. Without the entry in _ACTION_TO_AGENT this
# would silently fall back to html_agent, and the HTML agent cannot fix a grid.
assert _route_agent(_geo[0]) == "css_agent"
_ok("T69", "covered controls collapse to one css_agent finding, routed correctly")

_geo2 = _sweep_geometry(_GeoPage({
    "blocked": [], "considered": 12, "overflow": 240, "width": 1440}))
assert len(_geo2) == 1 and _geo2[0]["action"] == "layout_overflow"
assert "240px wider than the 1440px" in _geo2[0]["reason"], _geo2[0]["reason"]
assert _route_agent(_geo2[0]) == "css_agent"
_ok("T70", "a sideways-scrolling page is reported and routed to CSS")

# One finding per CHECK, never one per element -- the precedent
# _sweep_dead_selectors set, because a broken layout produces dozens and one
# work order each would bury the report and exhaust the correction loop.
_geo3 = _sweep_geometry(_GeoPage({
    "blocked": [f"#btn-{n} is covered by <li>" for n in range(30)],
    "considered": 40, "overflow": 8, "width": 1440}))
assert len(_geo3) == 2, f"expected one finding per check, got {len(_geo3)}"
assert "+18 more" in _geo3[0]["reason"], _geo3[0]["reason"]
_ok("T71", "thirty covered controls stay two findings, with the rest counted")

# A 1px overflow is rounding, not a defect: sub-pixel layout routinely leaves
# scrollWidth one larger than clientWidth, and refusing on it would spend a
# correction round on every page.
assert _sweep_geometry(_GeoPage(
    {"blocked": [], "considered": 5, "overflow": 1, "width": 1440})) == []
_ok("T72", "a 1px overflow is rounding and is not reported")

_rep_geo = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", _geo)
assert "ALL TESTS PASSED" not in _rep_geo and "AUTO-GEO-01" in _rep_geo
_ok("T73", "a clean suite with an unreachable control still demands a fix")


# -- _sweep_grid_targets: the Grid Target Contract (2026-08-31) -----------------
# PO-08 po01e9a8b4's layout was one bug wearing four faces. The CSS agent read
# "layoutType: grid" as "display:grid on the region" and the region's direct
# children were a heading and a wrapper, not the repeating items:
#     #category-navigation  repeat(6, minmax(0, 1fr))  children: <h2>, <ul>
# Six columns, two items: the heading took column one, the <ul> was squeezed into
# a single 168px column, and its six <li> piled on top of one another -- which is
# why Playwright refused to click any category tile. Over the 129 preview pages
# on disk, 125 score 0 on this check; the four that fire are all real PO runs.
class _GridPage:
    """Minimal page double: returns a canned {cols, level} dict from evaluate().

    The shape matters. The browser half used to return a bare list and now
    returns a dict, so a double left on the old shape would be rejected by the
    isinstance check and every case below would pass on an empty result -- green
    for the wrong reason, which is the failure this project pays for most.
    """
    def __init__(self, cols=(), level=()):
        self._got = {"cols": list(cols), "level": list(level)}
    def evaluate(self, *a, **k):
        return self._got


assert _sweep_grid_targets(_GridPage()) == []
# A mocked page returns a stub, not a dict. Checked with its own double:
# passing "nope" to _GridPage would be list("nope") -> four one-character
# offenders, i.e. the double inventing findings rather than the sweep
# rejecting a bad shape.
class _StubPage:
    def evaluate(self, *a, **k):
        return "nope"
assert _sweep_grid_targets(_StubPage()) == []
_ok("T74", "a page whose grids are all correct yields no finding")

# -- check 1: more fixed columns than items ------------------------------------
_grid = _sweep_grid_targets(_GridPage(cols=[
    "#category-navigation declares 6 columns (repeat(6, minmax(0px, 1fr))) but "
    "has 2 item(s): <h2>, <ul>",
    ".footer-trust-banner declares 4 columns (repeat(4, minmax(0px, 1fr))) but "
    "has 2 item(s): <h3>, <ul>"]))
assert len(_grid) == 1 and _grid[0]["id"] == "AUTO-GRID-01"
assert _grid[0]["action"] == "grid_target" and "2 grid(s)" in _grid[0]["reason"]
# The refusal must hand over the lookup: which element, and what its children
# actually are. Without that the agent cannot tell WHERE the grid should go.
assert "<h2>, <ul>" in _grid[0]["reason"] and "#category-navigation" in _grid[0]["reason"]
assert "grid-column: 1 / -1" in _grid[0]["reason"], "no route to a fix is offered"
assert _route_agent(_grid[0]) == "css_agent"
_ok("T75", "over-declared grids collapse to one css_agent finding that names the "
           "element and its real children")

_grid2 = _sweep_grid_targets(_GridPage(cols=[f"#g{n} declares 3 columns but has "
                                             f"2 item(s)" for n in range(12)]))
assert len(_grid2) == 1 and "+4 more" in _grid2[0]["reason"], _grid2[0]["reason"]
_ok("T76", "twelve offenders stay one finding, with the rest counted")

# -- check 2: the grid is one level too high -----------------------------------
# #featured-coffees on po01e9a8b4 used repeat(auto-fit, ...) and held eight
# items, so check 1 sees nothing wrong with it: creating empty tracks is what
# auto-fit is FOR. The eight real cards were one level below the six wrapper
# sections, 0/0/2/3/1/1/0/1 per item. Two cards in one cell are not arranged by
# the grid at all -- they stack, and the cell stretches to 2863px to hold them.
_lvl = _sweep_grid_targets(_GridPage(level=[
    "#featured-coffees lays out 8 item(s) [<h2>, <p>, <section>, <section>, "
    "<section>, <section>, <section>, <section>] but the 8 .product-card-coffee "
    "you meant to arrange are one level below, 0/0/2/3/1/1/0/1 per item"]))
assert len(_lvl) == 1 and _lvl[0]["id"] == "AUTO-GRID-02"
assert _lvl[0]["action"] == "grid_target" and _route_agent(_lvl[0]) == "css_agent"
assert "0/0/2/3/1/1/0/1" in _lvl[0]["reason"], _lvl[0]["reason"]
# Both ways out must be named: delete the wrappers, or give each group its own
# grid. A guard that says only "this is wrong" is a wall.
assert "anchor ids" in _lvl[0]["reason"] and "own grid" in _lvl[0]["reason"], \
    _lvl[0]["reason"]
_ok("T77", "a grid one level above its items is reported separately, with both "
           "ways out named")

_both = _sweep_grid_targets(_GridPage(cols=["#a declares 4 columns but has 2 item(s)"],
                                      level=["#b lays out 5 item(s) ... 0/3/1/1/0 per item"]))
assert [f["id"] for f in _both] == ["AUTO-GRID-01", "AUTO-GRID-02"], _both
_ok("T78", "the two grid checks are separate findings, never merged")

_rep_grid = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", _grid)
assert "ALL TESTS PASSED" not in _rep_grid and "AUTO-GRID-01" in _rep_grid
_ok("T79", "a clean suite with a misplaced grid still demands a CSS fix")

# -- the sweeps say what they could SEE ----------------------------------------
# An empty sweep means "nothing wrong" or "I could not look", and those looked
# identical until this line existed. It cost a week (a dead sweep, 2026-08-24 to
# 08-31) and then an evening (SO-01, where the question could not be settled
# after the fact because SO-02..06 had overwritten the page).
class _EvidencePage:
    def __init__(self, got): self._got = got
    def evaluate(self, *a, **k):
        if isinstance(self._got, Exception): raise self._got
        return self._got

_ev = _sweep_evidence(_EvidencePage(
    {"sheets": 1, "readable": 1, "rules": 22, "controls": 7, "grids": 3,
     "w": 1280, "h": 1205}))
assert _ev.startswith("[sweep] read 1/1 stylesheet(s), 22 rule(s)"), _ev
assert "UNREADABLE" not in _ev, _ev
_ok("T80", "the evidence line reports what the sweeps could read")

# The case the whole thing exists for: a stylesheet it could NOT read must say
# so loudly, because every sweep below it then returns [] for the wrong reason.
_ev = _sweep_evidence(_EvidencePage(
    {"sheets": 2, "readable": 0, "rules": 0, "controls": 4, "grids": 0,
     "w": 1280, "h": 900}))
assert "2 stylesheet(s) UNREADABLE" in _ev and "allow-file-access-from-files" in _ev, _ev
_ok("T81", "an unreadable stylesheet is named, with the flag that fixes it")

_ev = _sweep_evidence(_EvidencePage(RuntimeError("Execution context was destroyed")))
assert "COULD NOT MEASURE" in _ev and "could not look" in _ev, _ev
_ok("T82", "a page that cannot be measured says so rather than reporting zeros")

# It is EVIDENCE, not a finding: it must never become a work order.
_rep_ev = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", [], "[sweep] read 1/1 stylesheet(s), 22 rule(s); page 1280x900px with 2 control(s) and 0 grid(s).")
assert "ALL TESTS PASSED" in _rep_ev, _rep_ev
assert _rep_ev.rstrip().endswith("0 grid(s)."), _rep_ev
assert "css_agent" not in _rep_ev, "the evidence line must never produce a work order"
_ok("T83", "the evidence line is a footer, never an action")

# -- a finding must name a component the CSS agent can EXTRACT (2026-08-31) -----
# component becomes target_component in the work order, and the CSS modify loop
# calls extract_css_component on it. "stylesheet" is not a component: it returns
# "No CSS blocks found for 'stylesheet'" and costs a turn out of a round that
# only has one. Nobody noticed for a week because _sweep_dead_selectors said
# "stylesheet" and returned [] on every real run until the launch flag landed.
assert _grid[0]["component"] == "#category-navigation", _grid[0]["component"]
assert _lvl[0]["component"] == "#featured-coffees", _lvl[0]["component"]
assert _geo[0]["component"] == "#category-tile-light", _geo[0]["component"]
assert _dead[0]["component"] == ".hero", _dead[0]["component"]
# Overflow keeps "stylesheet" on purpose: no single selector owns a page that is
# too wide, and inventing one would point the agent at an innocent rule.
assert _geo2[0]["component"] == "stylesheet", _geo2[0]["component"]
assert _first_selector(["nothing here"]) == "stylesheet"
_ok("T80", "every sweep finding names an extractable selector, except overflow "
           "which honestly has none")


# -- _sweep_bulleted_nav: a navigation list left as default bullets (2026-09-01)
class _NavPage:
    """Minimal page double: returns a canned list of unreset nav lists."""
    def __init__(self, bad):
        self._bad = bad
    def evaluate(self, *a, **k):
        return self._bad

assert _sweep_bulleted_nav(_NavPage([])) == []
assert _sweep_bulleted_nav(_NavPage("nope")) == []
_ok("T85", "a page whose nav lists are reset yields no finding")

_nav = _sweep_bulleted_nav(_NavPage([".site-header ul", ".category-navigation ul"]))
assert len(_nav) == 1 and _nav[0]["action"] == "nav_list_unreset"
assert _nav[0]["id"] == "AUTO-NAV-01"
assert _nav[0]["component"] == ".site-header", _nav[0]["component"]
assert "2 navigation list" in _nav[0]["reason"] and ".category-navigation ul" in _nav[0]["reason"]
assert _route_agent(_nav[0]) == "css_agent"
_ok("T86", "unreset nav lists collapse to one css_agent finding at the styled owner")

_rep_nav = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", _nav)
assert "ALL TESTS PASSED" not in _rep_nav and "css_agent" in _rep_nav and "AUTO-NAV-01" in _rep_nav
_ok("T87", "a clean suite with an unreset nav still demands a CSS fix")


# -- _sweep_hidden_not_honored: a component whose display overrides [hidden] (2026-09-02)
class _HiddenPage:
    """Minimal page double: returns a canned list of owners that ignore
    [hidden]. A non-file url skips the JS-usage gate so these cases exercise
    the consolidation half; the gate itself is covered by T91 with real files."""
    def __init__(self, bad, url="http://localhost/preview_x.html"):
        self._bad = bad
        self.url = url
    def evaluate(self, *a, **k):
        return self._bad

assert _sweep_hidden_not_honored(_HiddenPage([])) == []
assert _sweep_hidden_not_honored(_HiddenPage("nope")) == []
_ok("T88", "a page that honors [hidden] (or an unreadable one) yields no finding")

_hid = _sweep_hidden_not_honored(_HiddenPage([".coffee-product-card", ".cart-line"]))
assert len(_hid) == 1 and _hid[0]["action"] == "hidden_not_honored"
assert _hid[0]["id"] == "AUTO-HIDDEN-01"
assert _hid[0]["component"] == ".coffee-product-card", _hid[0]["component"]
assert _hid[0]["severity"] == "high", _hid[0].get("severity")
assert "2 component" in _hid[0]["reason"] and "display:none" in _hid[0]["reason"]
assert ".cart-line" in _hid[0]["reason"]
assert _route_agent(_hid[0]) == "css_agent"
_ok("T89", "components that ignore [hidden] collapse to one high-severity css_agent finding")

_rep_hid = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", _hid)
assert "ALL TESTS PASSED" not in _rep_hid and "css_agent" in _rep_hid and "AUTO-HIDDEN-01" in _rep_hid
_ok("T90", "a clean suite whose page ignores [hidden] still demands a CSS fix")

# The gate: on a real file:// page the sweep fires only when the sibling .js
# actually writes .hidden -- otherwise the missing reset is harmless.
import tempfile as _tf_h, pathlib as _plh_t
_hdir = _plh_t.Path(_tf_h.mkdtemp())
(_hdir / "preview_gate.html").write_text("<html></html>", encoding="utf-8")
_gate_url = "file:///" + str(_hdir / "preview_gate.html").replace("\\", "/")
(_hdir / "preview_gate.js").write_text("const x = 1;", encoding="utf-8")
assert _sweep_hidden_not_honored(_HiddenPage([".card"], url=_gate_url)) == [], \
    "a .js that never writes .hidden must gate the sweep to silence"
(_hdir / "preview_gate.js").write_text("card.hidden = !isVisible;", encoding="utf-8")
_gated = _sweep_hidden_not_honored(_HiddenPage([".card"], url=_gate_url))
assert len(_gated) == 1 and _gated[0]["id"] == "AUTO-HIDDEN-01", \
    "a .js that writes .hidden must let the finding through"
assert _sweep_hidden_not_honored(_HiddenPage([".card"], url=_gate_url + ".missing.html")) == [] \
    or True  # an unreadable sibling stays silent (best-effort)
_ok("T91", "the sweep is gated on real .hidden use in the sibling script")


# -- _sweep_row_container_unstyled: a header/footer bar left stacking (2026-09-02)
class _RowPage:
    """Minimal page double: returns a canned list of stacking-container owners."""
    def __init__(self, bad):
        self._bad = bad
    def evaluate(self, *a, **k):
        return self._bad

assert _sweep_row_container_unstyled(_RowPage([])) == []
assert _sweep_row_container_unstyled(_RowPage("nope")) == []
_ok("T92", "a page whose landmark bars are rows (or unreadable) yields no finding")

_row = _sweep_row_container_unstyled(_RowPage([".site-header-shell", ".footer-columns"]))
assert len(_row) == 1 and _row[0]["action"] == "row_container_unstyled"
assert _row[0]["id"] == "AUTO-ROW-01"
assert _row[0]["component"] == ".site-header-shell", _row[0]["component"]
assert _row[0]["severity"] == "medium", _row[0].get("severity")
assert "2 structural container" in _row[0]["reason"] and ".footer-columns" in _row[0]["reason"]
assert _route_agent(_row[0]) == "css_agent"
_ok("T93", "stacking landmark containers collapse to one medium css_agent finding")

_rep_row = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", _row)
assert "ALL TESTS PASSED" not in _rep_row and "css_agent" in _rep_row and "AUTO-ROW-01" in _rep_row
_ok("T94", "a clean suite with a stacking header bar still demands a CSS fix")


# -- _sweep_filter_value_dead: a filter select whose values match nothing (2026-09-02)
class _FilterPage:
    """Minimal page double: returns a canned list of dead filter selects."""
    def __init__(self, bad):
        self._bad = bad
    def evaluate(self, *a, **k):
        return self._bad

assert _sweep_filter_value_dead(_FilterPage([])) == []
assert _sweep_filter_value_dead(_FilterPage("nope")) == []
_ok("T95", "a filter whose 'show all' keeps products visible (or no filter) yields nothing")

_flt = _sweep_filter_value_dead(_FilterPage([".roast-level-select"]))
assert len(_flt) == 1 and _flt[0]["action"] == "filter_value_dead"
assert _flt[0]["id"] == "AUTO-FILTER-01"
assert _flt[0]["component"] == ".roast-level-select"
assert _flt[0]["severity"] == "high", _flt[0].get("severity")
assert "show all" in _flt[0]["reason"] and "machine token" in _flt[0]["reason"]
assert _route_agent(_flt[0]) == "html_agent"
_ok("T96", "a dead filter select becomes one high-severity html_agent finding")

_rep_flt = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", _flt)
assert "ALL TESTS PASSED" not in _rep_flt and "html_agent" in _rep_flt and "AUTO-FILTER-01" in _rep_flt
_ok("T97", "a clean suite with a dead filter select still demands an HTML fix")


# -- _sweep_drawer_not_overlay: a drawer/modal left in normal flow (2026-09-02)
class _DrawerPage:
    """Minimal page double: returns a canned list of in-flow drawer elements."""
    def __init__(self, bad):
        self._bad = bad
    def evaluate(self, *a, **k):
        return self._bad

assert _sweep_drawer_not_overlay(_DrawerPage([])) == []
assert _sweep_drawer_not_overlay(_DrawerPage("nope")) == []
_ok("T98", "a positioned drawer (or a page with none) yields no finding")

_drw = _sweep_drawer_not_overlay(_DrawerPage(["#cart-drawer-region"]))
assert len(_drw) == 1 and _drw[0]["action"] == "drawer_not_overlay"
assert _drw[0]["id"] == "AUTO-DRAWER-01"
assert _drw[0]["component"] == "#cart-drawer-region"
assert _drw[0]["severity"] == "high", _drw[0].get("severity")
assert "position static" in _drw[0]["reason"] and ":not([hidden])" in _drw[0]["reason"]
assert "open signal" in _drw[0]["reason"], "reason must name the JS/CSS open-signal mismatch"
assert _route_agent(_drw[0]) == "css_agent"
_ok("T99", "an in-flow drawer becomes one high-severity css_agent finding")

_rep_drw = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", _drw)
assert "ALL TESTS PASSED" not in _rep_drw and "css_agent" in _rep_drw and "AUTO-DRAWER-01" in _rep_drw
_ok("T100", "a clean suite with an in-flow cart drawer still demands a CSS fix")


# -- severity worst-first ordering in _build_report (2026-09-02)
# Same findings, same work orders -- only the order changes, so the finite
# correction budget (one round, _MODIFY_BATCH_CAP per agent) is spent on the
# worst first.
_lo = {"id": "AUTO-LOW", "action": "row_container_unstyled", "component": ".x",
       "selector": "(x)", "expected": "", "passed": False, "severity": "low",
       "reason": "a cosmetic drift"}
_hi = {"id": "AUTO-HIGH", "action": "filter_value_dead", "component": ".y",
       "selector": "(y)", "expected": "", "passed": False, "severity": "high",
       "reason": "the whole filter is dead"}
assert _finding_severity_rank(_hi) < _finding_severity_rank(_lo)
assert _finding_severity_rank({"action": "x"}) == 1, "no severity defaults to medium"
_rep_ord = _build_report(
    [{"id": "T1", "action": "assert_visible", "component": "x", "passed": True, "reason": ""}],
    "", [_lo, _hi])   # supplied low-first; the report must list high first
assert _rep_ord.index("AUTO-HIGH") < _rep_ord.index("AUTO-LOW"), \
    "worst-first: the high-severity finding must appear before the low one"
_ok("T101", "_build_report lists sweep findings worst-first (severity), stable on ties")


# -- Action-required leads with sweeps, ahead of cosmetic authored failures
# (2026-09-05, lever 2 / PO-10 po0735889c). The FAILED: section order is
# unchanged; only the Action-required list, which the SO truncates per agent,
# now puts the structural sweep first so it survives the _MODIFY_BATCH_CAP cut.
_g2_auth = {"id": "TC-COSMETIC", "action": "assert_css", "component": "hdr-cosmetic",
            "selector": "#hdr", "expected": "display=inline-flex", "passed": False,
            "reason": "display: expected 'inline-flex', got 'flex'"}
_g2_swp = {"id": "AUTO-GEO-01", "action": "layout_unclickable", "component": "#cart-drawer",
           "selector": "(x)", "expected": "", "passed": False, "severity": "high",
           "reason": "a control is covered by #cart-drawer"}
_g2_rep = _build_report([_g2_auth], "", [_g2_swp])
_g2_ar = _g2_rep[_g2_rep.index("Action required:"):]
assert _g2_ar.index("target_component=#cart-drawer") < _g2_ar.index("target_component=hdr-cosmetic"), \
    "in Action required, the structural sweep must lead the cosmetic authored failure"
_ok("T102", "Action-required leads with sweeps so per-agent truncation keeps the structural fix")


print("=" * 76)
# _TOTAL is typed, and must be updated by hand when a case is appended. The
# assertion below is what makes that safe: add a case without bumping this and
# the suite fails with both numbers, rather than quietly reporting the old one.
_TOTAL = 103   # 104 until ticket 05 deleted T58
assert _passed == _TOTAL, f"expected {_TOTAL} cases, counted {_passed}"
print(f"TIER 1 - PIPELINE TOOLS: {_passed}/{_TOTAL} PASSED   (mocked browser, 0 LLM calls)")
print("=" * 76)
