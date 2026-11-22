# Ported from fyp.ipynb cell 349 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Rescued (ticket 05): the notebook marked this cell NOTEBOOK-ONLY, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
# E2E (live browser, NO LLM): Test Execution pipeline + report routing.
# Run manually. Launches real Chromium via Playwright against a hand-written
# fixture page, so it isolates the deterministic pipeline and the per-action
# report routing from the LLM agents. Set WEBFORGE_HEADED=1 to watch the browser.
import pathlib as _pl
from types import SimpleNamespace as _SNS

_E2E_SID  = "e2epipe1"
_E2E_ROOT = _pl.Path.cwd() / "static" / "preview"
_E2E_ROOT.mkdir(parents=True, exist_ok=True)
_E2E_FILE = _E2E_ROOT / f"preview_{_E2E_SID}.html"
_E2E_FILE.write_text(
    '<!DOCTYPE html>\n'
    '<html><head><meta charset="utf-8"><style>\n'
    '  .add-to-cart-btn { background-color: #1a73e8; color: #ffffff; }\n'
    '  .add-to-cart-btn:hover { background-color: #1557b0; }\n'
    '</style></head>\n'
    '<body>\n'
    '  <nav class="navbar">Home</nav>\n'
    '  <button class="add-to-cart-btn" data-testid="cart-btn">Add to Cart</button>\n'
    '  <a class="nav-jump" href="#target-section">Jump to section</a>\n'
    '  <section id="target-section">Target section</section>\n'
    '</body></html>\n',
    encoding="utf-8",
)
_E2E_URL = "file:///" + str(_E2E_FILE).replace("\\", "/")

# 6 pass / 3 fail. Passes exercise the read-only assertion actions live
# (visible, text, css, hover_css, attribute) plus assert_url, which now CLICKS
# its own selector before reading page.url (TC-09, a real nav anchor). The three failures exercise the
# three routing destinations: styling -> css_agent, missing element -> html_agent
# (not-found override), navigation -> js_agent.
# Not live-tested here (deliberate): click / type (timing-fragile under the 3s
# action cap). Those stay in the mocked unit tests.
_E2E_CASES = [
    {"id": "TC-01", "component": "navbar", "description": "navbar visible",
     "action": "assert_visible", "selector": ".navbar", "expected": "", "passed": None},
    {"id": "TC-02", "component": "add-to-cart-btn", "description": "button text",
     "action": "assert_text", "selector": ".add-to-cart-btn",
     "expected": "Add to Cart", "passed": None},
    {"id": "TC-03", "component": "add-to-cart-btn", "description": "base colour ok",
     "action": "assert_css", "selector": ".add-to-cart-btn",
     "expected": "background-color=#1a73e8", "passed": None},
    {"id": "TC-04", "component": "add-to-cart-btn", "description": "hover colour ok",
     "action": "assert_hover_css", "selector": ".add-to-cart-btn",
     "expected": "background-color=#1557b0", "passed": None},
    {"id": "TC-05", "component": "add-to-cart-btn", "description": "test id attribute present",
     "action": "assert_attribute", "selector": ".add-to-cart-btn",
     "expected": "data-testid=cart-btn", "passed": None},
    {"id": "TC-06", "component": "add-to-cart-btn", "description": "wrong colour (deliberate fail)",
     "action": "assert_css", "selector": ".add-to-cart-btn",
     "expected": "background-color=#ff0000", "passed": None},
    {"id": "TC-07", "component": "ghost", "description": "missing element (deliberate fail)",
     "action": "assert_css", "selector": ".does-not-exist",
     "expected": "background-color=#000000", "passed": None},
    {"id": "TC-08", "component": "checkout-link", "description": "navigation target (deliberate fail)",
     "action": "assert_url", "selector": "body",
     "expected": "checkout", "passed": None},
    {"id": "TC-09", "component": "nav-jump",
     "description": "nav link sets the URL fragment when clicked",
     "action": "assert_url", "selector": ".nav-jump",
     "expected": "#target-section", "passed": None},
]

_e2e_rt = _SNS(state={"test_cases": _E2E_CASES, "preview_url": _E2E_URL,
                      "session_id": _E2E_SID, "modification_context": ""},
               tool_call_id="e2e-pipe-001")
_e2e_out    = run_test_suite.func(_e2e_rt).update
_e2e_cases  = _e2e_out["test_cases"]
_e2e_report = _e2e_out["test_report"]
print(_e2e_report)
print("-" * 60)

_by_id = {c["id"]: c for c in _e2e_cases}
assert _by_id["TC-01"]["passed"] is True,  "E2E-PIPE FAIL: navbar should be visible"
assert _by_id["TC-02"]["passed"] is True,  "E2E-PIPE FAIL: button text should match"
assert _by_id["TC-03"]["passed"] is True,  "E2E-PIPE FAIL: base colour should match"
assert _by_id["TC-04"]["passed"] is True,  f"E2E-PIPE FAIL: hover colour should match -- {_by_id['TC-04']['reason']}"
assert _by_id["TC-05"]["passed"] is True,  f"E2E-PIPE FAIL: attribute should be present -- {_by_id['TC-05']['reason']}"
assert _by_id["TC-06"]["passed"] is False, "E2E-PIPE FAIL: wrong colour should fail"
assert _by_id["TC-07"]["passed"] is False, "E2E-PIPE FAIL: missing element should fail"
assert _by_id["TC-08"]["passed"] is False, "E2E-PIPE FAIL: wrong URL should fail"
# TC-09 is the assert_url pipeline fix (2026-09-04): the branch now CLICKS its
# selector before reading page.url, so a real <a href="#target-section"> nav
# anchor drives the URL to the fragment. Before the fix this read the base URL
# (no click, no fragment) and could never pass -- the po0142c544 defect.
assert _by_id["TC-09"]["passed"] is True, \
    f"E2E-PIPE FAIL: assert_url should click its nav-link selector then match the fragment -- {_by_id['TC-09'].get('reason')}"

# All three agents appear in one report, each routed correctly:
assert "- css_agent | intent=modify | target_component=add-to-cart-btn" in _e2e_report, \
    f"E2E-PIPE FAIL: colour failure should route to css_agent\n{_e2e_report}"
assert "- html_agent | intent=modify | target_component=ghost" in _e2e_report, \
    f"E2E-PIPE FAIL: missing element should route to html_agent (not-found override)\n{_e2e_report}"
assert "- js_agent | intent=modify | target_component=checkout-link" in _e2e_report, \
    f"E2E-PIPE FAIL: navigation failure should route to js_agent\n{_e2e_report}"
print("PASS: E2E Test Execution pipeline -- 6 pass / 3 fail, all read-only actions run live, report routes css+html+js correctly")
print(f"[proof] assert_url clicks its selector live: TC-09 selector '.nav-jump' "
      f"(a real <a href=#target-section>) -> passed={_by_id['TC-09']['passed']}, "
      f"the page URL now carries the fragment. The old branch read page.url "
      f"without clicking, so on po0142c544 all 6 nav assert_url cases "
      f"(TC-011/013/015/017/023/025) landed on the fragment-free base URL and "
      f"failed; a real Chromium click here sets the hash and the case passes.")


# ── _sweep_geometry, live in the same browser (2026-08-31) ───────────────────
# Every assertion above resolves through query_selector, so each asks whether an
# element exists and what it says. None asks whether a click would land on it.
# On PO-08 po01e9a8b4 a grid on the wrong element squeezed six category tiles
# into a 168px column, the <li> covered one another, and Playwright refused the
# click -- while assert_text on those same tiles passed and the whole suite
# reported green on a page nobody could tap.
#
# Driven through run_test_suite, not by calling the sweep directly: the page
# lives on the Playwright worker thread inside _core, so this proves the sweep
# is WIRED IN. A sweep that works and is never called is the failure to catch.
#
# HALF 1 -- the clean fixture above must find nothing.
assert "AUTO-GEO" not in _e2e_report, (
    f"E2E-PIPE FAIL: the clean fixture produced a geometry finding. A sweep "
    f"that fires on a healthy page buys a correction round and fixes nothing.\n"
    f"{_e2e_report}")

# HALF 2 -- a fixture built to break must find both. `.stack a + a` pulls the
# second link exactly over the first, so a click at link-one's own centre lands
# on link-two; `.too-wide` is wider than any viewport this suite uses.
_GEO_SID  = "e2egeo1"
_GEO_CSS  = _E2E_ROOT / f"preview_{_GEO_SID}.css"
_GEO_FILE = _E2E_ROOT / f"preview_{_GEO_SID}.html"
# An EXTERNAL stylesheet, deliberately. An inline <style> is readable from
# document.styleSheets with or without --allow-file-access-from-files, so a
# fixture using one cannot tell Fix 0 apart from its absence. Only a LINKED
# file:// stylesheet raises SecurityError without the flag, which is how
# _sweep_dead_selectors came to report nothing on every real run for a week.
_GEO_CSS.write_text(
    '.stack a { display: block; width: 120px; height: 40px; }\n'
    '.stack a + a { margin-top: -40px; }\n'          # the second lies over the first
    '.too-wide { width: 2000px; height: 10px; }\n'   # wider than any viewport here
    '.tiles { display: grid; grid-template-columns: repeat(4, 1fr); }\n'
    # auto-fit, so check 1 sees nothing wrong: making empty tracks is what
    # auto-fit is FOR. The fault is that .card lives one level below.
    '.groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }\n'
    '.no-such-element { color: rgb(255, 0, 0); }\n', # matches nothing on the page
    encoding="utf-8")
_GEO_FILE.write_text(
    '<!DOCTYPE html>\n'
    '<html><head><meta charset="utf-8">\n'
    f'<link rel="stylesheet" href="preview_{_GEO_SID}.css"></head>\n'
    '<body>\n'
    '  <nav class="navbar">Home</nav>\n'
    '  <div class="stack"><a href="#one" id="link-one">One</a>'
    '<a href="#two" id="link-two">Two</a></div>\n'
    '  <div class="tiles"><h2>Browse</h2><ul><li>a</li><li>b</li></ul></div>\n'
    '  <div class="groups"><h3>Light</h3>'
    '<div><p class="card">1</p><p class="card">2</p></div>'
    '<div><p class="card">3</p></div>'
    '<div><p class="card">4</p></div></div>\n'
    '  <div class="too-wide"></div>\n'
    '</body></html>\n',
    encoding="utf-8")
_GEO_URL = "file:///" + str(_GEO_FILE).replace("\\", "/")
_geo_rt = _SNS(state={
    "test_cases": [{"id": "TC-G1", "component": "navbar",
                    "description": "navbar visible", "action": "assert_visible",
                    "selector": ".navbar", "expected": "", "passed": None}],
    "preview_url": _GEO_URL, "session_id": _GEO_SID,
    "modification_context": ""}, tool_call_id="e2e-geo-001")
_geo_report = run_test_suite.func(_geo_rt).update["test_report"]
print(_geo_report)
print("-" * 60)

# The authored case PASSES, so without the sweeps this report would read
# "ALL TESTS PASSED" on a page whose first link cannot be clicked, whose grid
# declares twice the columns it has items for, and whose stylesheet has a rule
# matching nothing.
assert "ALL TESTS PASSED" not in _geo_report, (
    f"E2E-PIPE FAIL: the report still claims a clean page.\n{_geo_report}")
assert "AUTO-GEO-01" in _geo_report, (
    f"E2E-PIPE FAIL: link-one is covered by link-two and the report does not say "
    f"so. The usual cause is scrollIntoView reverting to smooth behaviour, which "
    f"reads the rectangle before the scroll lands.\n{_geo_report}")
assert "link-one" in _geo_report, (
    f"E2E-PIPE FAIL: the finding does not name the covered control.\n{_geo_report}")
assert "AUTO-GEO-02" in _geo_report, (
    f"E2E-PIPE FAIL: a 2000px element did not register as horizontal "
    f"overflow.\n{_geo_report}")
# These two are ALSO the proof of Fix 0: both read document.styleSheets, which
# is unreadable from a file:// page without the launch flag.
assert "AUTO-GRID-02" in _geo_report and "0/2/1/1" in _geo_report, (
    f"E2E-PIPE FAIL: .groups lays out three wrappers and the four .card are "
    f"one level below it, 0/2/1/1 per item, and the report does not say so. "
    f"Its grid is auto-fit, so check 1 cannot see it -- only the level check "
    f"can.\n{_geo_report}")
assert "AUTO-GRID-01" in _geo_report and ".tiles" in _geo_report, (
    f"E2E-PIPE FAIL: a 4-column grid holding 2 items was not reported. If "
    f"AUTO-CSS-01 is missing too, the browser lost "
    f"--allow-file-access-from-files and BOTH stylesheet sweeps are blind.\n"
    f"{_geo_report}")
assert "AUTO-CSS-01" in _geo_report and "no-such-element" in _geo_report, (
    f"E2E-PIPE FAIL: a rule matching no element was not reported. Without "
    f"--allow-file-access-from-files, cssRules raises SecurityError, "
    f"_sweep_dead_selectors swallows it and returns [], and an empty list looks "
    f"exactly like a clean page.\n{_geo_report}")
# Each finding must name a component the CSS agent can EXTRACT. component
# becomes target_component in the work order, and the CSS modify loop calls
# extract_css_component on it -- "stylesheet" returns "No CSS blocks found" and
# spends the round's only call on nothing. The mocked cases cannot catch a wrong
# selector here: they feed the sweep a string the browser does not produce.
for _want in ("target_component=.no-such-element",   # the dead rule itself
              "target_component=#link-one",          # the COVERED control...
              "target_component=.tiles",             # grid, wrong column count
              "target_component=.groups"):           # grid, wrong level
    assert _want in _geo_report, (
        f"E2E-PIPE FAIL: {_want!r} is not among the work orders. If "
        f"'#link-two' appears instead of '#link-one', the sweep is naming the "
        f"element that DOES the covering rather than the one that is covered. "
        f"{chr(10)}{_geo_report}")

for _act in ("layout_unclickable", "layout_overflow", "grid_target",
             "css_dead_selector"):
    assert _route_agent({"action": _act}) == "css_agent", (
        f"E2E-PIPE FAIL: {_act} routes to {_route_agent({'action': _act})}, not "
        f"css_agent. Without its entry in _ACTION_TO_AGENT it falls back to "
        f"html_agent, and the HTML agent cannot fix a stylesheet.")

print(f"[proof] page-health sweeps live: one fixture whose only authored test "
      f"case PASSES yields AUTO-GEO-01 (1 of 2 controls unclickable), "
      f"AUTO-GEO-02 (overflow), AUTO-GRID-01 (.tiles: 4 columns, 2 items), "
      f"AUTO-GRID-02 (.groups: 4 cards one level below, 0/2/1/1 per item -- "
      f"its auto-fit grid is invisible to check 1) and AUTO-CSS-01 "
      f"(.no-such-element matches nothing) -- five findings the "
      f"authored suite structurally cannot produce, all routed to css_agent. "
      f"AUTO-GRID-01 and AUTO-CSS-01 are also the proof of the "
      f"--allow-file-access-from-files "
      f"flag: on PO-08 po01e9a8b4, same page and same sweep, the dead-selector "
      f"count went 0 -> 7 when the flag was added, and it had been returning 0 "
      f"on every run since 2026-08-24. Measured over the 129 preview pages: 125 "
      f"score zero on the column check, 124 of 128 on the level check, 125 on "
      f"covered controls, 126 on overflow. The level check also fires on "
      f"po018f8158, the PREVIOUS PO-08 run: this is a repeating pattern, "
      f"not one page's accident.")
print("PASS: E2E page-health sweeps -- geometry, grid targets and dead selectors "
      "all live, all routed to css_agent")

# ── HALF 3: the sweeps must read the page as DELIVERED (2026-08-31) ──────────
# SO-01 (so9e0149) spent its one correction round deleting a working CSS rule.
# The page ships <button class="add-to-cart-btn"><svg .../><span>Add to
# cart</span></button>, a case clicked it, and the script ran
#
#     addToCartButton.textContent = 'Added to cart';
#
# textContent deletes every child, so the <svg> was gone by the time the sweep
# ran and `.add-to-cart-btn svg` looked dead. On the fresh page that selector
# matches 1 element. This fixture reproduces exactly that shape.
_DIRTY_SID  = "e2edirty1"
_DIRTY_CSS  = _E2E_ROOT / f"preview_{_DIRTY_SID}.css"
_DIRTY_FILE = _E2E_ROOT / f"preview_{_DIRTY_SID}.html"
_DIRTY_CSS.write_text(
    '.navbar { color: rgb(20, 20, 20); }\n'
    '.dirty-btn { display: block; width: 160px; }\n'
    '.dirty-btn .icon { color: rgb(0, 128, 0); }\n',   # alive until the click
    encoding="utf-8")
_DIRTY_FILE.write_text(
    '<!DOCTYPE html>\n'
    '<html><head><meta charset="utf-8">\n'
    f'<link rel="stylesheet" href="preview_{_DIRTY_SID}.css"></head>\n'
    '<body>\n'
    '  <nav class="navbar">Home</nav>\n'
    '  <button class="dirty-btn" type="button">'
    '<span class="icon">+</span>Add to cart</button>\n'
    '  <script>\n'
    "  document.querySelector('.dirty-btn').addEventListener('click', function () {\n"
    "    this.textContent = 'Added to cart';\n"
    '  });\n'
    '  </script>\n'
    '</body></html>\n',
    encoding="utf-8")
_DIRTY_URL = "file:///" + str(_DIRTY_FILE).replace("\\", "/")

_dirty_rt = _SNS(state={
    "test_cases": [
        {"id": "TC-D1", "component": "dirty-btn", "description": "add to cart",
         "action": "click", "selector": ".dirty-btn", "expected": "", "passed": None},
        # covers_state puts this in phase 2 of _order_test_cases, AFTER the
        # click. Untagged it lands in phase 0 and reads the resting label --
        # which is what it did on the first run of this cell, and is exactly
        # the leak that ordering exists to prevent.
        {"id": "TC-D2", "component": "dirty-btn", "description": "label changes",
         "action": "assert_text", "selector": ".dirty-btn",
         "expected": "Added to cart", "covers_state": True, "passed": None},
    ],
    "preview_url": _DIRTY_URL, "session_id": _DIRTY_SID,
    "modification_context": ""}, tool_call_id="e2e-dirty-001")
_dirty_report = run_test_suite.func(_dirty_rt).update["test_report"]
print(_dirty_report)
print("-" * 60)

assert "AUTO-CSS-01" not in _dirty_report, (
    f"E2E-PIPE FAIL: the sweep called `.dirty-btn .icon` dead. The click "
    f"destroyed the <span> and the sweep is still reading the post-click DOM, "
    f"so run_test_suite is not reloading before it sweeps. This is the SO-01 "
    f"defect: a working rule gets deleted and the round is wasted.\n"
    f"{_dirty_report}")
assert "ALL TESTS PASSED" in _dirty_report, (
    f"E2E-PIPE FAIL: both authored cases should pass -- the click succeeds and "
    f"the label really does change.\n{_dirty_report}")

# The number. Same page, same sweep, three readings: fresh, clicked, reloaded.
# Without this the assertion above passes whether or not the reload is there,
# because a fixture that never clicks has nothing to dirty.
def _dirty_probe():
    _br = _get_browser()
    _pg = _br.new_page()
    _pg.goto(_DIRTY_URL, timeout=10000)
    _fresh = len(_sweep_dead_selectors(_pg))
    _pg.click(".dirty-btn")
    _clicked = len(_sweep_dead_selectors(_pg))
    _pg.reload(wait_until="load", timeout=10000)
    _healed = len(_sweep_dead_selectors(_pg))
    _pg.close()
    return _fresh, _clicked, _healed

_fresh, _clicked, _healed = _pw_run(_dirty_probe)
assert (_fresh, _clicked, _healed) == (0, 1, 0), (
    f"E2E-PIPE FAIL: expected 0 dead selectors fresh, 1 after the click, 0 "
    f"after the reload -- got {(_fresh, _clicked, _healed)}. If the middle "
    f"number is 0 the fixture no longer destroys the <span>, so this cell is "
    f"proving nothing.")

print(f"[proof] sweeps read the delivered page: same fixture, same sweep, "
      f"three readings -- {_fresh} dead selector(s) on load, {_clicked} after "
      f"one click destroys the button's <span class=\"icon\">, {_healed} after "
      f"reload. run_test_suite now reloads before sweeping, so its report "
      f"carries {_dirty_report.count('AUTO-CSS-01')} AUTO-CSS-01 finding(s) on "
      f"this page. Before the reload it carried 1: that is what SO-01 "
      f"(so9e0149) sent to the CSS agent, which then deleted "
      f"`.add-to-cart-btn svg`, a rule matching 1 element on the fresh page, "
      f"and the run's only correction round was spent making the page worse.")
print("PASS: E2E sweeps measure the delivered page, not the page the suite left")

_DIRTY_CSS.unlink(missing_ok=True)
_DIRTY_FILE.unlink(missing_ok=True)

_GEO_CSS.unlink(missing_ok=True)
_GEO_FILE.unlink(missing_ok=True)

# ── HALF 4: a script that throws on load must short-circuit to js_agent ───────
# The pipeline shares one page and cannot see the console. When the page's own
# script throws while loading, the DOM still renders, so read-only assertions
# can PASS and bury the crash while every handler-dependent case fails as a
# timeout -- 18 symptoms, 0 mention of the cause. run_test_suite now attaches a
# pageerror listener and, if the page threw on load, reports that one error
# routed to the JS agent instead of the symptom list.
#
# The fixture reproduces the po015df552 TDZ exactly: a top-level statement runs
# a hoisted function that reaches a `const` declared further down, so the const
# is still in its temporal dead zone when the function touches it.
_CRASH_SID  = "e2ecrash1"
_CRASH_FILE = _E2E_ROOT / f"preview_{_CRASH_SID}.html"
_CRASH_FILE.write_text(
    '<!DOCTYPE html>\n'
    '<html><head><meta charset="utf-8"></head>\n'
    '<body>\n'
    '  <nav class="navbar">Home</nav>\n'
    '  <button class="add-btn" type="button">Add to cart</button>\n'
    '  <script>\n'
    '  (function () {\n'
    '    var cart = buildCart();\n'                    # runs before the const below
    '    const helper = function () { return 1; };\n'  # TDZ target
    '    function buildCart() { return helper(); }\n'   # hoisted, reaches helper early
    '  })();\n'
    '  </script>\n'
    '</body></html>\n',
    encoding="utf-8")
_CRASH_URL = "file:///" + str(_CRASH_FILE).replace("\\", "/")

# One assertion that WOULD pass on the static DOM (the navbar renders even though
# the script died), so a report that is NOT short-circuited would read a green
# case and hide the crash.
_crash_rt = _SNS(state={
    "test_cases": [
        {"id": "TC-X1", "component": "navbar", "description": "navbar visible",
         "action": "assert_visible", "selector": ".navbar", "expected": "", "passed": None},
    ],
    "preview_url": _CRASH_URL, "session_id": _CRASH_SID,
    "modification_context": ""}, tool_call_id="e2e-crash-001")
_crash_report = run_test_suite.func(_crash_rt).update["test_report"]
print(_crash_report)
print("-" * 60)

assert "pageerror" in _crash_report, (
    f"E2E-PIPE FAIL: the page threw on load and the report does not mention it. "
    f"Either the pageerror listener is missing or goto returned before the "
    f"throw was dispatched.\n{_crash_report}")
assert "- js_agent | intent=modify | target_component=page" in _crash_report, (
    f"E2E-PIPE FAIL: a load-time crash must route to the JS agent as the whole "
    f"page.\n{_crash_report}")
assert ("initialization" in _crash_report) or ("ReferenceError" in _crash_report), (
    f"E2E-PIPE FAIL: the real error text should reach the work order, so the JS "
    f"agent fixes the cause, not a guess.\n{_crash_report}")
# The short-circuit must WIN over the passing assertion: no green line, no
# ALL TESTS PASSED, none of the per-case bookkeeping.
assert "ALL TESTS PASSED" not in _crash_report, (
    f"E2E-PIPE FAIL: a page that crashed on load must never report as clean.\n"
    f"{_crash_report}")
assert "TC-X1" not in _crash_report, (
    f"E2E-PIPE FAIL: the suite short-circuited on the crash, so the individual "
    f"cases should not appear -- their results are noise on an inert page.\n"
    f"{_crash_report}")

print(f"[proof] load-crash short-circuit live: the fixture's script throws 1 "
      f"uncaught error on load; its 1 authored assertion (navbar visible) WOULD "
      f"pass on the static DOM and hide the crash, yet the report carries 0 "
      f"per-case lines and exactly 1 js_agent work-order naming the "
      f"ReferenceError. On po015df552 the same class of crash surfaced only as "
      f"18 click timeouts routed piecemeal, and the correction round never "
      f"addressed the load error because the pipeline could not see it.")
print("PASS: E2E load-crash -- a page that throws on load short-circuits to one "
      "js_agent work-order carrying the real error")

_CRASH_FILE.unlink(missing_ok=True)
