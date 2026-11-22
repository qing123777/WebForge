"""UI feedback fixes found on the 2026-11-10 PO-08 run (tools/ui_feedback.py).

    python -m pytest -q tests/test_ui_feedback.py          # offline, under 1 s
    WEBFORGE_UI_BROWSER=1 python -m pytest -q tests/test_ui_feedback.py
                                                           # + the browser loop, ~40 s

  UF-1  a developer agent that runs after Test Execution opens a "Correction
        round" block, and the round's stages are listed again under it (F3).
  UF-2  a run with no correction round gives the same rows as before.
  UF-3  the finished view keeps the round, from the steps.
  UF-4  the submit path reads nothing from the backend before its rerun (F1).
  UF-5  (browser) tools/ui_feedback.py: F1 echo < 2 s, F2 preview before the
        final reply, F3 the round row shown, on the mock with a 12 s load.
  UF-6  a backend that fails to load ends the run with an error (no spin).
  UF-7  the download zip's bytes do not change with the clock.
  UF-8  the page is shown only once html, css and js all exist.
  UF-9  an agent's own line after a test CALL does not fake a round.
  UF-10 _running_thread_id names a thread only while its run is running.
  UF-11 F1 refuses to pass when the send came after the backend loaded.
  UF-12 the mock's flags and its slow-import finder.
UF-6..9 came from the code review of the first three fixes.

stream_lit.py runs the whole app when imported, so the functions under test
are lifted out of its source with ast and run against the real contract.
"""
import ast
import os
import pathlib
import re
import subprocess
import sys
from html import escape

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI = ROOT / "stream_lit.py"
sys.path.insert(0, str(ROOT))
from webforge import contract  # noqa: E402  stdlib only

_SRC = UI.read_text(encoding="utf-8")
_TREE = ast.parse(_SRC)


def _lift(*names):
    """Exec the named top-level functions and assignments of stream_lit.py."""
    ns = {"re": re, "escape": escape, "contract": contract}
    nodes = [n for n in _TREE.body
             if (isinstance(n, ast.FunctionDef) and n.name in names)
             or (isinstance(n, ast.Assign)
                 and any(getattr(t, "id", None) in names for t in n.targets))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(UI), "exec"), ns)
    return ns


NS = _lift("_TESTS_RAN", "_RECALL", "_CORRECTION_ROW", "_STEP_TICK", "_PAR_ICON",
           "_stream_timeline", "_steps_rows_html", "_finished_timeline_html")

FIRST_PASS = [
    "[Orchestrator] Processing request...",
    "[Context Agent] Processing request...",
    "[Design Pipeline] Generating layout specification...",
    "[Secondary Orchestrator] Processing request...",
    "[Secondary Orchestrator] Calling HTML Agent...",
    "[HTML Agent] Saving HTML to filesystem...",
    "[Secondary Orchestrator] Calling CSS Agent...",
    "[JS Agent] Saving JS to filesystem...",
    "[Test Gen Agent] All test cases have been saved.",
    "[Secondary Orchestrator] Calling Test Execution Pipeline...",
    "[Test Execution Pipeline] Running Playwright test suite...",
]
# The lines production printed in the correction round of session 4fb17fbe.
ROUND = [
    "[Secondary Orchestrator] Calling HTML Agent...",
    "[HTML Agent] Reading the current page...",
    "[Secondary Orchestrator] Calling CSS Agent...",
    "[CSS Agent] Reading the current stylesheet...",
    "[Secondary Orchestrator] Calling Test Execution Pipeline...",
]


def test_uf1_correction_round_gets_its_own_block():
    rows, live, _ = NS["_stream_timeline"](FIRST_PASS + ROUND)
    labels = [r[0] for r in rows]
    i = labels.index("Correction round")
    assert rows[i][1] == "header"
    assert labels[i + 1:] == ["HTML Agent", "CSS Agent", "Test Execution Pipeline"]
    assert rows[-1] == ("Test Execution Pipeline", "now")
    assert all(s == "done" for _, s in rows[:i]), "the first pass is finished"
    html = NS["_steps_rows_html"](rows)
    assert '<div class="wf-st-round">Correction round</div>' in html
    assert html.count("<div") == html.count("</div>"), "the parallel bracket is closed"


def test_uf9_agent_lines_after_a_test_call_do_not_fake_a_round():
    """Review finding: the Secondary Orchestrator runs tools in parallel, so a
    batch can print "Calling Test Execution Pipeline..." while the CSS agent is
    still working. Its later "[CSS Agent] Linting..." line is not a second
    pass. Only an orchestrator "Calling X Agent" line after the tests really
    ran ("Running Playwright test suite") opens a round."""
    batch = FIRST_PASS[:6] + [
        "[Secondary Orchestrator] Calling Test Execution Pipeline...",
        "[CSS Agent] Linting CSS code with Stylelint...",
        "[CSS Agent] Saving CSS to filesystem...",
        "[Test Execution Pipeline] Running Playwright test suite...",
    ]
    rows, _, _ = NS["_stream_timeline"](batch)
    assert "Correction round" not in [r[0] for r in rows], rows
    # A test CALL that never ran (refused) is not a test run either.
    refused = FIRST_PASS[:6] + [
        "[Secondary Orchestrator] Calling Test Execution Pipeline...",
        "[Secondary Orchestrator] Calling JS Agent...",
    ]
    rows, _, _ = NS["_stream_timeline"](refused)
    assert "Correction round" not in [r[0] for r in rows], rows


def test_uf2_no_round_means_the_old_rows():
    rows, _, _ = NS["_stream_timeline"](FIRST_PASS)
    assert [r[0] for r in rows] == [l for l in contract.STAGE_ORDER]
    assert rows[-1] == ("Test Execution Pipeline", "now")
    assert "wf-st-round" not in NS["_steps_rows_html"](rows)


def test_uf3_finished_view_keeps_the_round():
    times = [{"label": "Primary Orchestrator", "at": 0.0}]
    html = NS["_finished_timeline_html"](times, FIRST_PASS + ROUND)
    assert "Correction round" in html and "wf-st-now" not in html
    assert NS["_finished_timeline_html"]([], FIRST_PASS + ROUND) == "", \
        "a run that recorded no stages still shows no timeline"


def test_uf4_submit_path_reads_nothing_from_the_backend():
    """_start_background_run runs in the submit handler, before the rerun that
    shows the user's message. A backend import there waits for the warm-up
    (~26 s cold), so the message stayed invisible. Only the worker may."""
    fn = next(n for n in _TREE.body
              if isinstance(n, ast.FunctionDef) and n.name == "_start_background_run")
    worker = next(n for n in ast.walk(fn)
                  if isinstance(n, ast.FunctionDef) and n.name == "worker")
    inside_worker = {id(n) for n in ast.walk(worker)}
    outside = [n for n in ast.walk(fn) if id(n) not in inside_worker
               and isinstance(n, ast.Call)
               and ((isinstance(n.func, ast.Name) and n.func.id == "_get_label_llm")
                    or (isinstance(n.func, ast.Attribute)
                        and getattr(n.func.value, "id", None) == "bridge"))]
    assert not outside, [ast.unparse(n) for n in outside]


def _worker_fn():
    fn = next(n for n in _TREE.body
              if isinstance(n, ast.FunctionDef) and n.name == "_start_background_run")
    return next(n for n in ast.walk(fn)
                if isinstance(n, ast.FunctionDef) and n.name == "worker")


def test_uf6_a_backend_that_fails_to_load_ends_the_run_with_an_error():
    """The worker loads the backend (label model, stream). If that raises (no
    .env, a bad key), the except clause must see it and set status "error";
    outside the try the thread dies and the run spins forever."""
    worker = _worker_fn()
    tries = [n for n in worker.body if isinstance(n, ast.Try)]
    assert tries, "worker has no top-level try"
    in_try = {id(n) for t in tries for stmt in t.body for n in ast.walk(stmt)}
    calls = [n for n in ast.walk(worker) if isinstance(n, ast.Call)
             and (getattr(n.func, "id", None) == "_get_label_llm"
                  or getattr(n.func, "attr", None) == "stream_message")]
    assert calls, "worker no longer loads the backend; update this test"
    outside = [ast.unparse(n)[:60] for n in calls if id(n) not in in_try]
    assert not outside, f"backend calls outside the worker's try: {outside}"


def _preview_ns(tmp_path):
    ns = _lift("_normalize_preview_session_id", "_preview_complete", "_build_preview_zip")
    import time as _time
    ns.update(_PREVIEW_DIR=tmp_path, Path=pathlib.Path, time=_time)
    return ns


def test_uf7_download_zip_bytes_do_not_change_with_the_clock(tmp_path, monkeypatch):
    """The preview panel re-renders every 2 s during a run and rebuilds the
    download zip each time. A zip stamped with the current time differs on
    every tick, so the download button re-registered a new file each time."""
    import time as _time
    ns = _preview_ns(tmp_path)
    for ext, body in (("html", "<p>hi</p>"), ("css", "p{}"), ("js", "1;")):
        (tmp_path / f"preview_s1.{ext}").write_text(body, encoding="utf-8")
    monkeypatch.setattr(_time, "time", lambda: 1_700_000_000.0)
    a = ns["_build_preview_zip"]("s1")
    monkeypatch.setattr(_time, "time", lambda: 1_700_000_100.0)
    b = ns["_build_preview_zip"]("s1")
    assert a and a == b


def test_uf8_preview_complete_needs_all_three_files(tmp_path):
    ns = _preview_ns(tmp_path)
    (tmp_path / "preview_s1.html").write_text("x", encoding="utf-8")
    assert not ns["_preview_complete"]("s1"), "only the HTML: not shown mid-run"
    (tmp_path / "preview_s1.css").write_text("x", encoding="utf-8")
    assert not ns["_preview_complete"]("s1")
    (tmp_path / "preview_s1.js").write_text("x", encoding="utf-8")
    assert ns["_preview_complete"]("s1")
    assert ns["_preview_complete"]("preview_s1.html"), "takes the file name form too"
    assert not ns["_preview_complete"](None) and not ns["_preview_complete"]("")


def test_uf10_running_thread_id_only_while_running():
    import types
    ns = _lift("_running_thread_id")
    runs = {"r1": {"status": "running", "thread_id": "t1"},
            "r2": {"status": "complete", "thread_id": "t2"}}
    ns["_get_run_snapshot"] = lambda rid: runs.get(rid)
    for rid, want in (("r1", "t1"), ("r2", None), (None, None)):
        ns["st"] = types.SimpleNamespace(session_state={"active_run_id": rid})
        assert ns["_running_thread_id"]() == want, rid


def test_uf11_f1_refuses_to_pass_when_sent_after_the_load():
    sys.path.insert(0, str(ROOT / "tools"))
    import ui_feedback
    fast = {"echo_s": 0.3, "preview_s": 9.0, "round_s": 8.0, "final_s": 10.0}
    late =ui_feedback.verdicts({**fast, "sent_after_open_s": 14.0}, load_s=12)[0]
    assert ui_feedback.verdicts({**fast, "sent_after_open_s": 2.0}, load_s=12)[0][1]
    assert not late[1] and "INVALID" in late[2]
    slow = ui_feedback.verdicts({**fast, "echo_s": 17.2, "sent_after_open_s": 2.0},
                                load_s=12)[0]
    assert not slow[1]


def test_uf12_mock_flags_and_slow_import(monkeypatch):
    """The mock's opt-in flags, and the finder that makes `import
    webforge.entry` slow the way the real backend is."""
    sys.path.insert(0, str(ROOT / "tools"))
    import mock_backend as mb
    for v, want in (("", False), ("0", False), ("1", True), ("yes", True)):
        monkeypatch.setenv("WEBFORGE_MOCK_CORRECTION", v)
        assert mb._flag("WEBFORGE_MOCK_CORRECTION") is want
    for v, want in (("", 0.0), ("bad", 0.0), ("-3", 0.0), ("2.5", 2.5)):
        monkeypatch.setenv("WEBFORGE_MOCK_LOAD_S", v)
        assert mb._load_seconds() == want
    f = mb._SlowEntryFinder(0.0)
    assert f.find_spec("webforge.contract") is None, "only webforge.entry is slowed"
    spec = f.find_spec(mb.ENTRY)
    assert spec is not None and spec.loader is f


@pytest.mark.skipif(not os.environ.get("WEBFORGE_UI_BROWSER"),
                    reason="browser loop: set WEBFORGE_UI_BROWSER=1")
def test_uf5_browser_feedback_loop():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "ui_feedback.py")],
                       cwd=str(ROOT / "tools"), capture_output=True, text=True,
                       encoding="utf-8", timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
