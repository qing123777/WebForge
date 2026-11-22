"""Test Execution gives up on a page that stops answering.

    pytest tests/test_testexec_deadline.py   (or python tests/test_testexec_deadline.py)

Offline, no model calls; drives a real headless browser.

On the 2026-11-11 PO-08 run (session 7141dce4) the correction round's JS fix
added a MutationObserver that watched `style` and whose callback set `style`.
The page span, the next Playwright call never returned, and run_test_suite
waited on it until the run was stopped by hand nine minutes later (the test
browser had used 428 CPU-seconds by then). Nothing in the pipeline had a
deadline of its own: `page.set_default_timeout` bounds a wait for an element,
not a renderer that never answers.

  TD-1  the limit is time WITHOUT PROGRESS, 60 s whatever the suite's size,
        and WEBFORGE_TESTEXEC_DEADLINE_S overrides it.
  TD-5  a slow page that keeps making progress runs past the limit and is
        reported as failures, not as a hang.
  TD-2  a page whose script loops: run_test_suite returns at the deadline with
        a report that says the page hung, names the case that was running, and
        routes the fix to the JS agent.
  TD-3  the hung browser is gone afterwards, not left spinning.
  TD-4  the next run, on a healthy page, works: the browser was replaced.
"""
import pathlib
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

import webforge.test_execution.browser as browser  # noqa: E402
import webforge.test_execution.suite as suite  # noqa: E402

_SPIN = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>spin</title></head>
<body><button id="go" class="go" type="button">Go</button><div id="box" class="box">x</div>
<script>
document.getElementById('go').addEventListener('click', function () {
  var box = document.getElementById('box');
  new MutationObserver(function () { box.style.opacity = String(Math.random()); })
    .observe(box, {attributes: true, attributeFilter: ['style']});
  box.style.opacity = '0.5';
});
</script></body></html>"""

_OK = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>ok</title></head>
<body><button id="go" class="go" type="button">Go</button><div id="box" class="box">x</div>
</body></html>"""

_CASES = [
    {"id": "TC-001", "action": "assert_visible", "selector": ".box", "expected": "",
     "component": "box"},
    {"id": "TC-002", "action": "click", "selector": ".go", "expected": "", "component": "go"},
    {"id": "TC-003", "action": "assert_text", "selector": ".box", "expected": "x",
     "component": "go", "covers_event": "click"},
]


def _run(tmp_path, html, sid, give_up_s=90):
    """run_test_suite on `html`, in a daemon thread, so that code WITHOUT a
    working limit fails this test after `give_up_s` instead of hanging the
    whole pytest session."""
    import threading
    box = {}

    def go():
        try:
            box["out"] = _run_inline(tmp_path, html, sid)
        except BaseException as e:   # noqa: BLE001  report it in the main thread
            box["err"] = e

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(give_up_s)
    assert not t.is_alive(), f"run_test_suite did not return within {give_up_s} s"
    if "err" in box:
        raise box["err"]
    return box["out"]


def _run_inline(tmp_path, html, sid):
    (tmp_path / f"preview_{sid}.html").write_text(html, encoding="utf-8")
    old_root = suite._PREVIEW_ROOT
    suite._PREVIEW_ROOT = tmp_path
    try:
        rt = SimpleNamespace(
            state={"test_cases": [dict(c) for c in _CASES],
                   "preview_url": (tmp_path / f"preview_{sid}.html").as_uri(),
                   "session_id": sid, "modification_context": ""},
            tool_call_id="td")
        t0 = time.time()
        out = suite.run_test_suite.func(rt).update
        return out, time.time() - t0
    finally:
        suite._PREVIEW_ROOT = old_root


def test_the_limit_is_time_without_progress_not_total_time(monkeypatch):
    """TD-1 (review of a8c4f92). A total deadline of 60 s + 5 s a case was
    shorter than a lawful but badly broken run: a click whose opener fails
    takes 6.5 s, a hover on a hidden element 11 s, a group reset up to 10 s,
    so 64 such cases could need about 400-680 s against 380 s and be reported
    as a hang that does not exist. The limit is now the time since the last
    sign of progress, and does not depend on the suite's size."""
    monkeypatch.delenv("WEBFORGE_TESTEXEC_DEADLINE_S", raising=False)
    assert suite._stall_limit_s() == 60
    monkeypatch.setenv("WEBFORGE_TESTEXEC_DEADLINE_S", "7")
    assert suite._stall_limit_s() == 7
    monkeypatch.setenv("WEBFORGE_TESTEXEC_DEADLINE_S", "not a number")
    assert suite._stall_limit_s() == 60


def test_a_slow_page_that_keeps_moving_is_not_a_hang(tmp_path, monkeypatch):
    """TD-5 (review of a8c4f92). Every case here waits its full 3 s for an
    element that is not there: about 15 s in all, past an 8 s limit, with
    progress after every case. Under the old total deadline this was a hang."""
    pytest.importorskip("playwright")
    _run(tmp_path, _OK, "warm2")
    monkeypatch.setenv("WEBFORGE_TESTEXEC_DEADLINE_S", "8")
    slow = [{"id": f"TC-1{k}", "action": "type", "selector": f".missing-{k}",
             "expected": "x", "component": f"missing-{k}"} for k in range(5)]
    (tmp_path / "preview_slow.html").write_text(_OK, encoding="utf-8")
    old_root = suite._PREVIEW_ROOT
    suite._PREVIEW_ROOT = tmp_path
    try:
        rt = SimpleNamespace(state={"test_cases": slow,
                                    "preview_url": (tmp_path / "preview_slow.html").as_uri(),
                                    "session_id": "slow", "modification_context": ""},
                             tool_call_id="td5")
        t0 = time.time()
        out = suite.run_test_suite.func(rt).update
        took = time.time() - t0
    finally:
        suite._PREVIEW_ROOT = old_root
    print(f"\n[proof] slow page: {len(slow)} cases took {took:.1f} s against an 8 s "
          f"limit and were reported as failures, not as a hang. The total deadline "
          f"it replaces would have cut this run at 8 s.")
    assert took > 8, took
    assert "page-unresponsive" not in out["test_report"], out["test_report"]
    assert len(out["test_cases"]) == len(slow)


def test_a_spinning_page_ends_the_run_with_a_report(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    psutil = pytest.importorskip("psutil")
    # A healthy run first: it launches the browser, so the 8 s below measure the
    # page and not a cold Chromium start, and it shows the deadline costs a
    # healthy page nothing.
    out0, took0 = _run(tmp_path, _OK, "warm")
    assert "page-unresponsive" not in out0["test_report"], out0["test_report"]
    monkeypatch.setenv("WEBFORGE_TESTEXEC_DEADLINE_S", "8")

    out, took = _run(tmp_path, _SPIN, "spin")
    report = out["test_report"]
    print(f"\n[proof] spinning page: run_test_suite returned after {took:.1f} s "
          f"(deadline 8 s). On PO-08 7141dce4 the same fault was still running "
          f"after 540 s and never returned.")
    assert took < 8 + 15, took                                   # TD-2: it came back
    assert "page-unresponsive" in report and "[hang]" in report, report
    assert "8 s" in report, report
    assert "TC-00" in report, report                             # the case in flight
    import webforge.secondary_orchestrator as so
    assert so._routed_agents_from_report(report) == {"js"}, report
    assert "MutationObserver" in report, report                  # the usual cause, named

    # TD-3: nothing of the hung browser is left running under this process.
    end = time.time() + 10
    left = browser._playwright_children()
    while left and time.time() < end:
        time.sleep(0.5)
        left = browser._playwright_children()
    assert not left, [(p.pid, p.name()) for p in left]
    assert psutil is not None
    # ... and no Playwright worker thread is left either. An abandoned one
    # busy-loops on the dead connection and starves every other thread.
    import threading
    spinning = [t.name for t in threading.enumerate() if t.name.startswith("playwright")]
    assert not spinning, spinning

    # TD-4: a healthy page right after it runs clean on a fresh browser, at the
    # real limit: a cold browser start must not race the 8 s used above.
    monkeypatch.delenv("WEBFORGE_TESTEXEC_DEADLINE_S")
    out2, took2 = _run(tmp_path, _OK, "ok")
    by_id = {c["id"]: c for c in out2["test_cases"]}
    assert by_id["TC-001"]["passed"] and by_id["TC-002"]["passed"], out2["test_report"]
    assert "page-unresponsive" not in out2["test_report"]


def test_the_hang_work_order_names_a_component_the_js_agent_can_find():
    """TD-6 (review of a8c4f92). `target_component=page` matched nothing in
    the JS agent's modify extract (it searches the script for that name), so
    the agent got a miss and had to guess. The work order now names the
    component of the case that was running, falling back to page."""
    running = {"case": {"id": "TC-047", "action": "click", "selector": ".mini-cart-close",
                        "component": "mini-cart-close"}, "done": 46}
    report = suite._hang_report(60, running, 64)
    action = report.split("Action required:")[1]
    assert "target_component=mini-cart-close" in action, action
    idle = suite._hang_report(60, {"case": None, "stage": "while the page was loading"}, 64)
    assert "target_component=page" in idle.split("Action required:")[1]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
