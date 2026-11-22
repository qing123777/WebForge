# Ported from fyp.ipynb cell 338 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: _ensure_reachable (Fix B) opens a closed disclosure so a click case
# can reach a control a real user only sees after opening the drawer. po2r117e13f
# emitted mini-cart clicks ("click #mini-cart-qty-increment", "#mini-cart-checkout"
# ...) with no step to open the cart first, so on the shipped page the drawer was
# hidden and every one timed out -- a phantom failure unrelated to whether the
# button works. Runs on a CONTROLLED fixture (page.set_content), and, like every
# other browser test here, does all Playwright work on the worker thread via
# _pw_run (a main-thread new_page would bind the browser to the wrong thread and
# break the _pw_run tests that follow).
_B_FIXTURE = """<!doctype html><html><head><style>
  #drawer[hidden]{display:none}
  #drawer{position:fixed;inset:0;background:#fff}
</style></head><body>
  <a href="#cart-wrap" id="opener">Open cart</a>
  <button id="visible-btn">Visible</button>
  <section id="cart-wrap">
    <aside hidden id="drawer" data-component="mini-cart">
      <button id="inside-btn">Increase</button>
    </aside>
  </section>
  <button hidden id="lonely-btn">no opener points here</button>
  <script>
    document.getElementById('opener').addEventListener('click', function(e){
      e.preventDefault();
      document.getElementById('drawer').hidden = false;
    });
  </script>
</body></html>"""

def _b_core():
    page = _get_browser().new_page()
    page.set_default_timeout(1500)   # keep the fail-open negatives fast
    def _click(sel):
        return _execute_action(page, {"action": "click", "selector": sel,
                                      "expected": "triggered"}, "sess")
    obs = {}
    try:
        # 1) target inside a hidden drawer -> B opens it, click lands
        page.set_content(_B_FIXTURE)
        obs["r1"] = _click("#inside-btn"); obs["v1"] = page.locator("#drawer").first.is_visible()
        # 2) already-visible target -> B is a NO-OP (must not click the opener)
        page.set_content(_B_FIXTURE)
        obs["r2"] = _click("#visible-btn"); obs["v2"] = page.locator("#drawer").first.is_visible()
        # 3) hidden target with NO findable opener -> B fails OPEN (no magic open)
        page.set_content(_B_FIXTURE)
        obs["r3"] = _click("#lonely-btn")
        # 4) drawer ALREADY open -> B must NOT re-click a toggle opener and CLOSE it
        page.set_content(_B_FIXTURE)
        page.evaluate("document.getElementById('drawer').hidden = false")
        obs["r4"] = _click("#inside-btn"); obs["v4"] = page.locator("#drawer").first.is_visible()
        # 5) kill switch: WEBFORGE_AUTO_OPEN=0 disables B, hidden target fails again
        page.set_content(_B_FIXTURE)
        _prev = os.environ.get("WEBFORGE_AUTO_OPEN"); os.environ["WEBFORGE_AUTO_OPEN"] = "0"
        try:
            obs["r5"] = _click("#inside-btn")
        finally:
            if _prev is None: os.environ.pop("WEBFORGE_AUTO_OPEN", None)
            else: os.environ["WEBFORGE_AUTO_OPEN"] = _prev
    finally:
        page.close()
    return obs

# Ticket 05: this cell failed now and then on a cold Chromium start (seen on
# the Windows PC, not reproduced on Linux), and the cause was invisible: the
# opener's timeout was swallowed inside _ensure_reachable. It now returns that
# error, and this spy puts it in the failure message.
_b_reach_errors = []
_b_real_reach = _ensure_reachable


def _b_reach_spy(page, selector):
    err = _b_real_reach(page, selector)
    if err is not None:
        _b_reach_errors.append(f"{selector}: {type(err).__name__}: {err}")
    return err


_ensure_reachable = _b_reach_spy
try:
    _bo = _pw_run(_b_core)
finally:
    _ensure_reachable = _b_real_reach
assert _bo["r1"]["passed"] is True and _bo["v1"], (
    f"B FAIL(1): auto-open did not reach #inside-btn: {_bo['r1']}; "
    f"_ensure_reachable said: {_b_reach_errors}")
assert _bo["r2"]["passed"] is True and _bo["v2"] is False, f"B FAIL(2): B opened the drawer for a visible target: {_bo['r2']}"
assert _bo["r3"]["passed"] is False, f"B FAIL(3): no-opener target must stay unreachable: {_bo['r3']}"
assert _bo["r4"]["passed"] is True and _bo["v4"], (
    f"B FAIL(4): B toggled an already-open drawer shut: {_bo['r4']}; "
    f"_ensure_reachable said: {_b_reach_errors}")
assert _bo["r5"]["passed"] is False, f"B FAIL(5): gate off should NOT auto-open: {_bo['r5']}"
print("PASS: _ensure_reachable (Fix B) 5/5 -- opens a hidden drawer to reach a click target, "
      "no-ops on a visible target, fails open with no opener, never toggles an open drawer shut, "
      "and honours WEBFORGE_AUTO_OPEN=0.")
