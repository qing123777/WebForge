"""run_test_suite: the Test Execution tool. Orders the suite, runs every case,
restores the page, runs the sweeps, builds the report."""
from __future__ import annotations

import os

from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langgraph.types import Command

from webforge import config as _wf_config
from webforge.test_execution.state import TestExecState
from webforge.test_execution.browser import _get_browser, _pw_run, PlaywrightHung
from webforge.test_execution.actions import _execute_action
from webforge.test_execution.sweeps import _sweep_evidence, run_page_sweeps
from webforge.test_execution.report import _build_report

_PREVIEW_ROOT = _wf_config.PREVIEW_DIR



# ==========================================================================
# run_test_suite
# ==========================================================================
# Actions that CHANGE the page. Everything else only observes it.
_MUTATING_ACTIONS = {"click", "type"}


def _order_test_cases(test_cases: list) -> list:
    """Order the suite so each interaction sits next to the assertion that checks
    IT, not after every other interaction. run_test_suite calls goto() once, so
    the whole suite shares one page with no reset between cases; ordering is the
    only lever.

    Three parts, stable within each so the model's own order survives:

      1. baseline           cases that must read the RESTING page (plain asserts,
                            and assert_hover_css even when tagged -- hover is a
                            live pseudo-state needing no prior click).
      2. interaction groups each click / type, immediately followed by the
                            transition assertions on its OWN component.
      3. leftover           transition assertions whose component matches no
                            interaction (a cross-component effect, e.g. a search
                            box that updates a separate result count), last.

    Why the grouping: the roast filters are single-select -- clicking one clears
    the others. Batching ALL clicks first (the old behaviour) left only the LAST
    filter active, so every earlier filter's active-state assertion failed
    (po015df552 TC-023/026/029/030). Pairing each click with its own assertion
    checks each filter while its state is still live.

    A transition pairs with the FIRST not-yet-used interaction sharing its
    `component`; a case with no `component` cannot pair and falls to leftover --
    the pre-2026-09 behaviour, so component-less suites order exactly as before.
    """
    def _is_interaction(tc):
        return isinstance(tc, dict) and tc.get("action") in _MUTATING_ACTIONS

    def _is_transition(tc):
        if not isinstance(tc, dict) or _is_interaction(tc):
            return False
        if tc.get("covers_state") and tc.get("action") != "assert_hover_css":
            return True
        if tc.get("covers_event") and str(tc.get("action") or "").startswith("assert_"):
            return True
        return False

    baseline     = [tc for tc in test_cases if not _is_interaction(tc) and not _is_transition(tc)]
    interactions = [tc for tc in test_cases if _is_interaction(tc)]
    transitions  = [tc for tc in test_cases if _is_transition(tc)]

    ordered = list(baseline)
    used    = [False] * len(transitions)
    for click in interactions:
        ordered.append(click)
        cid = click.get("component") if isinstance(click, dict) else None
        if not cid:
            continue
        for k, t in enumerate(transitions):
            if not used[k] and t.get("component") == cid:
                ordered.append(t)
                used[k] = True
    ordered.extend(t for k, t in enumerate(transitions) if not used[k])
    return ordered


# How long the suite may go WITHOUT PROGRESS before the page is declared
# unresponsive. Nothing else bounds it: set_default_timeout limits a wait for
# an element, and page.evaluate has no timeout at all, so a page whose script
# never yields holds the worker thread for ever.
#
# Progress is marked at each stage and around each case, so the limit has to
# cover the longest single lawful step, never the whole suite (a total limit
# was shorter than a lawful but badly broken run; review of a8c4f92):
#   load:  three goto attempts, 3 x 10 s + 2 x 1.5 s       = 33 s
#   case:  group reset 10 s + fill 3 s + press 3 s + 0.25 s = 16.25 s (type)
#          group reset 10 s + opener 2 s + 1.5 s + click 3 s = 16.5 s (click)
#   end:   closing reload 10 s, then each sweep marks progress itself
# 60 s is nearly twice the longest. The browser launch happens before the
# first mark and is counted from when the run starts (Playwright allows 30 s).
_STALL_LIMIT_S = 60


def _stall_limit_s() -> int:
    """Seconds run_test_suite waits with no progress.
    WEBFORGE_TESTEXEC_DEADLINE_S overrides it (a whole number of seconds)."""
    try:
        forced = int(os.environ.get("WEBFORGE_TESTEXEC_DEADLINE_S", ""))
        if forced > 0:
            return forced
    except ValueError:
        pass
    return _STALL_LIMIT_S


def _hang_report(deadline_s: int, progress: dict, total: int) -> str:
    """The report for a run abandoned at its deadline. Same shape as the
    load-failure and pageerror short-circuits: one FAILED line carrying the
    cause, one work order. The fix is the script's, so it goes to the JS agent."""
    tc = progress.get("case") or {}
    if tc:
        where = (f"It was running {tc.get('id', '?')} [{tc.get('action', '?')}] "
                 f"on {tc.get('selector') or 'the page'}, after "
                 f"{progress.get('done', 0)} of {total} case(s) had finished.")
    else:
        where = f"It stopped {progress.get('stage', 'before the first case')}."
    # The JS agent's modify extract finds code by this name, and `page`
    # matches nothing in a script, so name the component that was being
    # exercised when the page stopped; that is where the loop usually lives.
    target = str(tc.get("component") or "").strip() or "page"
    cause = ("a script on the page runs without end, most often an observer or "
             "event handler that changes the very thing it watches (a "
             "MutationObserver on `style` or `class` whose callback sets `style` "
             "or `class`)")
    return (
        f"FAILED: page-unresponsive [hang] -- the page stopped answering and the "
        f"test run was abandoned after {deadline_s} s without progress. {where} No case result "
        f"from this run can be trusted. Usual cause: {cause}."
        "\n\nAction required:\n"
        f"- js_agent | intent=modify | target_component={target}"
        f" | reason=the page stops responding during the tests: {cause}. "
        "Remove the loop; do not force an element's state from an observer."
    )


@tool
def run_test_suite(runtime: ToolRuntime[TestExecState]) -> Command:
    """
    Execute all test cases against the preview page sequentially using Playwright.
    Reads test_cases, preview_url, session_id, and modification_context from state.
    Stores updated test_cases (passed=True/False) and test_report back to state.
    Call this once — it handles execution, result recording, and report generation.

    All Playwright work runs on the dedicated worker thread (see _pw_run), so the
    sync API is safe to call even inside a running asyncio loop (e.g. a Jupyter
    kernel or an async host).
    """
    test_cases           = runtime.state.get("test_cases", [])
    preview_url          = runtime.state.get("preview_url", "")
    session_id           = runtime.state.get("session_id", "")
    modification_context = runtime.state.get("modification_context", "")

    if not test_cases:
        return Command(update={"messages": [ToolMessage(
            content="No test cases found in state. Cannot run test suite.",
            tool_call_id=runtime.tool_call_id
        )]})

    # Execution order is decided here, not by the order the model happened to
    # write the batches in. See _order_test_cases.
    test_cases = _order_test_cases(test_cases)

    # Written by the worker thread, read by this one only after a hang, to say
    # where the run stopped.
    _progress = {"case": None, "done": 0, "stage": "while the page was loading",
                 "t": 0.0}

    def _tick():
        import time
        _progress["t"] = time.monotonic()

    def _core():
        browser = _get_browser()
        page    = browser.new_page()
        # A script that throws while the page loads leaves the DOM standing
        # but every event handler unbound: the cart drawer never closes, no
        # button responds, and the whole interaction suite fails as click
        # timeouts. The pipeline cannot see the console, so that one uncaught
        # error never reaches the correction loop -- it reads 18 symptoms
        # instead of 1 cause. Capture load-time errors for the short-circuit below.
        _page_errors: list = []
        page.on("pageerror", lambda exc: _page_errors.append(str(exc)))
        # Cap how long click/type wait for a missing element (Playwright default
        # is 30s per action — a page missing 5 interactive elements would burn
        # 2.5 min of dead waiting). Assertions never wait, and goto keeps its own
        # explicit 10s budget, so only the auto-waiting actions are affected.
        page.set_default_timeout(3000)

        # Retry transient load hiccups (file still mid-write, momentary lock) so
        # only genuine load failures enter the correction loop and consume a
        # modification attempt. 3 attempts total, short pause between.
        _load_error = None
        _tick()
        for _attempt in range(3):
            try:
                page.goto(preview_url, timeout=10000)
                _load_error = None
                break
            except Exception as _e_load:
                _load_error = _e_load
                if _attempt < 2:
                    import time
                    time.sleep(1.5)

        if _load_error is not None:
            e = _load_error
            page.close()
            report = (
                "\n".join(f"FAILED: {tc['id']} [page_load] — page failed to load: {e}"
                           for tc in test_cases)
                + "\n\nAction required:\n"
                  "- html_agent | intent=modify | target_component=page"
                  " | reason=preview page failed to load"
            )
            return {"test_report": report}

        # goto succeeded, so the HTML and CSS rendered -- but if the page's
        # own script threw as the load event fired, the page is inert: no
        # handler ran and every interaction case is about to fail as a
        # timeout. Report the 18 symptoms and the JS agent chases selectors;
        # the one fact it needs is the uncaught error. Short-circuit exactly
        # as a failed goto does, but route to the JS agent with the real
        # message.
        #   po015df552, 2026-09-04: `let cart = loadCartState()` ran before
        #   the `const keepElementAutomationReady` it reached through
        #   buildCartFromDom, a TDZ ReferenceError ESLint's static pass
        #   cannot see (the reference is lexically after the declaration)
        #   and the pipeline reported only as 18 click timeouts.
        if _page_errors:
            _crash = _page_errors[0]
            page.close()
            report = (
                f"FAILED: page-load-script [pageerror] -- the page threw an "
                f"uncaught error while loading, so no interaction works: {_crash}"
                + "\n\nAction required:\n"
                  "- js_agent | intent=modify | target_component=page"
                  f" | reason=uncaught JavaScript error on load: {_crash}"
            )
            return {"test_report": report}

        # Viewport handling: a case may carry an optional "viewport" ("375x812")
        # for responsive checks. The browser is resized only when the target size
        # changes; cases without the key run at the default desktop size.
        _DEFAULT_VP = (1280, 720)
        _current_vp = None
        results = []
        # A case either mutates the page (click/type) or only reads it (assert_*).
        # _order_test_cases already lays the suite out as independent groups: each
        # click is followed only by the assertions on its OWN component. But every
        # group used to run on the SAME page with no reset, so a group that opened
        # the cart drawer (or applied a filter) left that state ON, and the next
        # group's clicks were intercepted by the open overlay or found their target
        # hidden -- one real interaction became dozens of phantom 'intercepts
        # pointer events' / 'element is not visible' failures (po2r117e13f: ~330 of
        # ~346 work orders). Reloading the shipped page at each new group boundary
        # makes execution match the independence the ordering already assumes. The
        # reset fires ONLY on a mutating action, and only when a previous group
        # already dirtied the page -- so a click and its paired assertions are never
        # split, and a clean suite pays nothing. WEBFORGE_CASE_RESET=0 disables it.
        _reset_between_groups = os.environ.get("WEBFORGE_CASE_RESET", "1") != "0"
        _dirty = False
        for tc in test_cases:
            _is_mutating = tc.get("action") in _MUTATING_ACTIONS
            if _is_mutating and _dirty and _reset_between_groups:
                try:
                    page.reload(wait_until="load", timeout=10000)
                except Exception:
                    pass
                _dirty = False
            try:
                _w, _h  = (int(p) for p in str(tc.get("viewport") or "").lower().split("x"))
                _target = (_w, _h)
            except Exception:
                _target = _DEFAULT_VP
            if _target != _current_vp:
                page.set_viewport_size({"width": _target[0], "height": _target[1]})
                _current_vp = _target
            _progress["case"] = tc
            _tick()
            results.append({**tc, **_execute_action(page, tc, session_id)})
            _progress["done"] += 1
            _tick()
            if _is_mutating:
                _dirty = True
        _progress["case"]  = None
        _progress["stage"] = "after the last case, while the page was restored and swept"
        _tick()

        # Restore the page before measuring it. The sweeps ask whether the
        # DELIVERED page is sound, so they must read it as it ships, not as
        # the suite left it. Two things dirty it:
        #
        #   * the cases just clicked and typed on it. On SO-01 (so9e0149,
        #     2026-08-31) a case clicked add-to-cart and the script ran
        #     `addToCartButton.textContent = 'Added to cart'` -- textContent
        #     deletes every child, the button's <svg> included. The sweep
        #     then called `.add-to-cart-btn svg` dead (on the fresh page it
        #     matches 1 element), the CSS agent deleted a working rule, and
        #     the run's only correction round was spent making it worse.
        #   * a case carrying "viewport" leaves the browser at that size, so
        #     one mobile case at the end of the list would have AUTO-GEO-02
        #     measure overflow against 375px while its message says 1280.
        #
        # wait_until="load" is also the barrier _sweep_resources wanted: the
        # load event fires after subresources settle, which is a real signal,
        # where "the suite took a while" was a proxy for one.
        #
        # Given up deliberately: a fault that exists only after interaction --
        # an opened accordion that overflows, a modal covering a button. That
        # belongs to the authored suite, which can click and then assert.
        #
        # Fails OPEN. A sweep of a dirtied page is worth more than no sweep.
        if _current_vp != _DEFAULT_VP:
            page.set_viewport_size({"width":  _DEFAULT_VP[0],
                                    "height": _DEFAULT_VP[1]})
            _current_vp = _DEFAULT_VP
        try:
            page.reload(wait_until="load", timeout=10000)
        except Exception:
            pass
        # Measured BEFORE the sweeps, on the same restored page, so the line
        # describes exactly what they were looking at.
        # The static HTML as delivered (before any script ran), for the
        # dropped-id sweep. Read from disk, not the live DOM, which is post-JS.
        try:
            _html_source = (_PREVIEW_ROOT / f"preview_{session_id}.html").read_text(encoding="utf-8")
        except Exception:
            _html_source = ""
        _tick()
        evidence = _sweep_evidence(page)
        auto = run_page_sweeps(page, _html_source, tick=_tick)
        page.close()

        report = _build_report(results, modification_context, auto, evidence)
        # `auto` deliberately does not join test_cases -- see _sweep_resources.
        return {"test_cases": results, "test_report": report}

    _deadline = _stall_limit_s()
    try:
        _out = _pw_run(_core, timeout=_deadline, heartbeat=lambda: _progress["t"])
    except PlaywrightHung:
        _out = {"test_report": _hang_report(_deadline, _progress, len(test_cases))}

    update = dict(_out)
    update["messages"] = [ToolMessage(content=_out["test_report"],
                                      tool_call_id=runtime.tool_call_id)]
    return Command(update=update)


# Every name this module defines or imports, for the package's __init__ and
# from there for webforge.test_exec, which re-exports it into the load order.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
