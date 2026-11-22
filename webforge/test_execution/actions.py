"""Run one structured test case (the 9-action vocabulary) against a page."""
from __future__ import annotations

import os
import re

from webforge.test_execution.css_values import _css_pair_mismatches

# assert_count's expected: a comparator and a whole number, e.g. ">=1", "=8".
# This is the only assertion in the vocabulary that can observe an OUTCOME
# rather than a property. Every other one compares a string, a computed style,
# an attribute or a URL against a value that must already be known when the
# suite is written, so "a cart line appeared", "the grid shrank" and "a second
# thumbnail exists" had no way to be expressed at all.
# Test Execution reads it here; Test Generation imports it to validate a case
# (ticket 11 moved it from test_gen_agent, so this package needs no agent code).
_COUNT_EXPECTED_RE = re.compile(r"^(>=|<=|>|<|=)\s*(\d+)$")

def _settle_transitions(page, selector: str, timeout_ms: int = 900) -> None:
    """Block until the element's animated styles stop moving.

    A computed style read mid-transition returns a blended colour that appears
    nowhere in the stylesheet and exists for a couple of hundred milliseconds.
    That makes the assertion TIMING-DEPENDENT, which is worse than a plain
    failure: the same page can pass and fail on consecutive runs, and Metric 3
    of the evaluation campaign measures exactly that stability.

    Sampling until two consecutive reads agree needs no knowledge of which
    properties are transitioned or how long they take, so it also covers
    animations and delayed transitions. Bounded, and never raises -- a page that
    animates forever must fall through to the assertion rather than hang the
    suite.
    """
    js = """(sel) => {
        const el = document.querySelector(sel);
        if (!el) return "";
        const cs = getComputedStyle(el);
        return [cs.backgroundColor, cs.color, cs.borderColor, cs.opacity,
                cs.transform, cs.width, cs.height].join("|");
    }"""
    try:
        previous, waited = None, 0
        while waited <= timeout_ms:
            current = page.evaluate(js, selector)
            if current == previous:
                return
            previous = current
            page.wait_for_timeout(60)
            waited += 60
    except Exception:
        return          # never let a settle check fail the run on its own


# ── Auto-open a closed disclosure so a click case can reach its target ─────────
# A test case is a single action. store_test_cases emits "click #mini-cart-close"
# with no step that first opens the cart drawer, so on the shipped page the drawer
# is hidden and the click times out -- a phantom failure that has nothing to do
# with whether the button works (po2r117e13f: 6 mini-cart clicks failed this way).
# Before a CLICK, if the target is not visible because it sits inside a hidden
# drawer/panel, open that panel by clicking its opener (the control whose
# aria-controls, or whose href fragment, points at a box that CONTAINS the
# target). This runs ONLY on the click path -- an assertion that reads the
# resting page never calls it -- so it can only ever do what the click case
# already intends. It fails OPEN: a visible target, or no findable opener, and it
# does nothing, leaving the caller's own click (and its timeout) to decide, byte
# for byte as before. WEBFORGE_AUTO_OPEN=0 disables it.
_FIND_OPENER_JS = r"""
(selector) => {
  const target = document.querySelector(selector);
  if (!target) return null;
  const hidden = (el) => {
    if (!el || el.nodeType !== 1) return false;
    if (el.hasAttribute('hidden')) return true;
    if (el.getAttribute('aria-hidden') === 'true') return true;
    const cs = getComputedStyle(el);
    return cs.display === 'none' || cs.visibility === 'hidden';
  };
  let node = target, hiddenAnc = null;
  while (node) { if (hidden(node)) hiddenAnc = node; node = node.parentElement; }
  if (!hiddenAnc) return null;                    // target is not inside a closed box
  const idSel = (el) => el.id ? ('#' + CSS.escape(el.id)) : null;
  const points_at = (id) => {
    const box = id && document.getElementById(id);
    return box && box !== target && (box === hiddenAnc || box.contains(target));
  };
  for (const o of document.querySelectorAll('[aria-controls]')) {
    for (const id of (o.getAttribute('aria-controls') || '').split(/\s+/)) {
      if (points_at(id) && o.offsetParent !== null) { const s = idSel(o); if (s) return s; }
    }
  }
  for (const a of document.querySelectorAll('a[href^="#"]')) {
    const id = decodeURIComponent((a.getAttribute('href') || '').slice(1));
    if (points_at(id) && a.offsetParent !== null) { const s = idSel(a); if (s) return s; }
  }
  return null;
}
"""

def _ensure_reachable(page, selector):
    """Open the drawer/panel a click target hides inside; no-op otherwise.

    Fails open: it never raises. When the opener click or the wait for the
    target times out, it returns that exception (None otherwise), so a caller
    or a test can say what timed out. The click path ignores the return value,
    so its behaviour is unchanged."""
    if os.environ.get("WEBFORGE_AUTO_OPEN", "1") == "0":
        return
    try:
        loc = page.locator(selector).first
        if loc.count() == 0 or loc.is_visible():
            return
    except Exception:
        return
    try:
        opener = page.evaluate(_FIND_OPENER_JS, selector)
    except Exception:
        opener = None
    if not opener:
        return
    try:
        page.click(opener, timeout=2000)
        page.locator(selector).first.wait_for(state="visible", timeout=1500)
    except Exception as exc:
        return exc
    return None


def _execute_action(page, tc: dict, session_id: str) -> dict:
    """Run one test case action via Playwright. Returns {passed, reason}."""
    action, selector, expected = tc["action"], tc["selector"], tc["expected"]
    try:
        if action == "assert_visible":
            passed = page.query_selector(selector) is not None
            reason = "" if passed else f"'{selector}' not found in DOM"

        elif action == "assert_text":
            el = page.query_selector(selector)
            if el is None:
                return {"passed": False, "reason": f"'{selector}' not found"}
            text   = el.inner_text()
            passed = expected.lower() in text.lower()
            reason = "" if passed else f"expected '{expected}', got '{text[:80]}'"

        elif action == "assert_css":
            el = page.query_selector(selector)
            if el is None:
                return {"passed": False, "reason": f"'{selector}' not found"}
            # assert_css measures the RESTING style. A preceding click leaves the
            # pointer on the element, so :hover is still applied and its
            # transition is still running. Park the mouse, then wait for the
            # computed values to stop moving.
            page.mouse.move(0, 0)
            _settle_transitions(page, selector)
            mismatches = _css_pair_mismatches(page, selector, expected)
            passed = not mismatches
            reason = "; ".join(mismatches)

        elif action == "assert_hover_css":
            el = page.query_selector(selector)
            if el is None:
                return {"passed": False, "reason": f"'{selector}' not found"}
            # Real mouse hover so the browser applies :hover for real. The
            # element's existence is already confirmed above, so give the hover a
            # generous timeout: it is not waiting on a missing element, it is
            # absorbing the real-mouse subsystem's cold-start cost (~2-3s on the
            # first hover of a fresh headless browser), which overruns the 3s
            # default action cap and spuriously fails an otherwise-correct page.
            page.hover(selector, timeout=10000)  # browser applies :hover for real
            # The hover transition runs in the same 200ms window, so the hover
            # value needs settling just as much as the resting one does.
            _settle_transitions(page, selector)
            mismatches = _css_pair_mismatches(page, selector, expected)
            page.mouse.move(0, 0)  # un-hover: keep the parked mouse from leaking
                                   # the :hover state into a later assert_css on the
                                   # same element (found via live E2E 2026-08-02)
            passed = not mismatches
            reason = "; ".join(mismatches)

        elif action == "assert_attribute":
            el = page.query_selector(selector)
            if el is None:
                return {"passed": False, "reason": f"'{selector}' not found"}
            attr, _, want = expected.partition("=")
            attr, want = attr.strip(), want.strip()
            actual = el.get_attribute(attr)
            # empty value means presence-only check (e.g. "disabled=")
            passed = actual is not None and (want in actual if want else True)
            reason = "" if passed else (
                f"{attr}: expected '{want or '<present>'}', got "
                f"{'<missing>' if actual is None else repr(actual)}"
            )

        elif action == "assert_url":
            # A nav link only changes the URL when it is CLICKED: the shared
            # page opens once with no fragment, so reading page.url without
            # clicking first can never see the "#<id>" the link adds. The
            # link to click is the case's own selector (e.g.
            # "#hdr_listing_link"); store_test_cases requires it. Clicking
            # here keeps the case atomic and order-free, instead of relying
            # on a separate click case landing first -- the pipeline reorders
            # cases, so it cannot guarantee that order.
            if selector:
                _ensure_reachable(page, selector)
                page.click(selector)
                page.mouse.move(0, 0)
            current = page.url
            passed = expected in current
            reason = "" if passed else (
                f"expected URL to contain '{expected}', got '{current}'"
            )

        elif action == "assert_count":
            # The one assertion that observes an OUTCOME. Counting matched
            # elements is how "a cart line appeared" and "the grid shrank" become
            # checkable at all -- every other assertion compares a value that had
            # to be known when the suite was written.
            _m = _COUNT_EXPECTED_RE.match(str(expected).strip())
            if _m is None:
                return {"passed": False,
                        "reason": f"malformed assert_count expected: '{expected}'"}
            _op, _want = _m.group(1), int(_m.group(2))
            _actual = len(page.query_selector_all(selector))
            passed = {">=": _actual >= _want, "<=": _actual <= _want,
                      ">":  _actual >  _want, "<":  _actual <  _want,
                      "=":  _actual == _want}[_op]
            reason = "" if passed else (
                f"expected '{selector}' to match {_op}{_want} element(s), "
                f"matched {_actual}"
            )

        elif action == "click":
            _ensure_reachable(page, selector)
            page.click(selector)
            # Park the mouse for the same reason assert_hover_css already does:
            # the pointer would otherwise sit on the element and leak :hover into
            # every later assertion about it. A state-covering case clicks first
            # and asserts second, so this is precisely the sequence that broke.
            page.mouse.move(0, 0)
            passed, reason = True, ""

        elif action == "type":
            # The value under test comes from the case. It used to be the fixed
            # literal "test input", which matches no product name and no price,
            # so a search box that filters correctly and one that does nothing
            # produced an identical page and every assertion after it was
            # vacuous. The literal survives only as the fallback for an untyped
            # case, where the point really is just "this field accepts text".
            page.fill(selector, tc.get("input") or "test input")
            _key = str(tc.get("press") or "").strip()
            if _key:
                # page.fill sets the value and fires input events. It never
                # submits, so a handler bound to submit was previously
                # unreachable from the suite.
                page.press(selector, _key)
                page.wait_for_timeout(250)   # let the handler run before the
                                             # next case observes the page
            passed, reason = True, ""

        else:
            return {"passed": False, "reason": f"Unknown action: '{action}'"}

    except Exception as e:
        return {"passed": False, "reason": str(e)}

    return {"passed": passed, "reason": reason}


# Every name this module defines or imports, for the package's __init__ and
# from there for webforge.test_exec, which re-exports it into the load order.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
