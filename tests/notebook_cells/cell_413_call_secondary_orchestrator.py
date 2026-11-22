# Ported from fyp.ipynb cell 413 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: call_secondary_orchestrator
#
# The guard is the whole point of deleting generate_session_id: the id is issued
# by the application layer, so a call that arrives without one must STOP rather
# than mint a replacement and write an orphan page. Only the refusal paths are
# exercised offline -- the accept path streams the real Secondary Orchestrator
# and therefore the real LLM, so it is covered by E2E-SO-01 instead.
#
# EVERY case that invokes the tool must sit inside the get_stream_writer patch
# below. The tool's first statement is `writer = get_stream_writer()`, and the
# real one raises "Called get_config outside of a runnable context" when there
# is no graph around it. A case appended after the `finally` fails there instead
# of testing anything -- which is exactly what happened on 2026-08-10.
from types import SimpleNamespace as _SN_CSO
import uuid as _cso_uuid

_cso_events = []


class _CSOWriter:
    def __call__(self, x):
        _cso_events.append(x)


def _rt_cso(sid):
    return _SN_CSO(state={"session_id": sid, "working_memory": WorkingMemory()},
                   tool_call_id="cso-1")


_cso_sid   = "utest_" + _cso_uuid.uuid4().hex[:8]
_cso_files = [_PREVIEW_ROOT / f"preview_{_cso_sid}.{_e}" for _e in ("html", "css", "js")]

_cso_real_writer = globals().get("get_stream_writer")
globals()["get_stream_writer"] = lambda: _CSOWriter()
try:
    print("[Case 1 · EDGE] A missing session_id is REFUSED, and no sub-graph runs.")
    _r = call_secondary_orchestrator.func(_rt_cso(""), query="build a page")
    assert set(_r.update.keys()) == {"messages"}, f"FAIL: extra state written: {_r.update.keys()}"
    _m = _r.update["messages"][0]
    assert "REFUSED" in _m.content, f"FAIL: not a refusal: {_m.content[:80]}"
    assert _m.tool_call_id == "cso-1", "FAIL: tool_call_id not echoed"
    print("   ", _m.content[:96])
    print("PASS: empty id refused with a ToolMessage, nothing generated\n")

    print("[Case 2 · MALICIOUS] A traversing id is REFUSED, not sanitised silently.")
    for _bad in ("../../etc", "a/b", "x" * 65, None):
        _rb = call_secondary_orchestrator.func(_rt_cso(_bad), query="q")
        assert "REFUSED" in _rb.update["messages"][0].content, f"FAIL: {_bad!r} accepted"
    print("PASS: traversal, separator, over-length and None all refused\n")

    print("[Case 3 · NORMAL] The indent the tool opened is closed on the refusal path.")
    # writer({'indent': +1}) runs before the guard. Without the matching -1 the
    # Streamlit progress pane stays indented for the rest of the run.
    _cso_events.clear()
    call_secondary_orchestrator.func(_rt_cso(""), query="q")
    _deltas = [e.get("delta") for e in _cso_events if isinstance(e, dict) and "delta" in e]
    assert sum(_deltas) == 0, f"FAIL: indent left open, deltas={_deltas}"
    print(f"indent deltas {_deltas} sum to 0")
    print("PASS: refusal path restores the indent level\n")

    # ── Outcome reporting (added 2026-08-10) ────────────────────────────────
    # The SO-01 defect one layer up: the tool read test_report to decide whether
    # to fire the memory hooks, then discarded it and always said "completed."
    print("[Case 4 · GUARD] The outcome message is built from what actually happened.")
    _PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        _m = _secondary_outcome(_cso_sid, {"test_report": "ALL TESTS PASSED — no action required."})
        assert "NO artefacts" in _m and "FAILED build" in _m, _m
        print("     no files ->", _m[:78])

        for _f in _cso_files:
            _f.write_text("/* x */", encoding="utf-8")

        _m = _secondary_outcome(_cso_sid, {
            "test_report": "PASSED: TC-001\n\nALL TESTS PASSED — no action required.",
            "modification_attempts": 0})
        assert "ALL TESTS PASSED" in _m and "first pass" in _m, _m
        print("     passing  ->", _m[:78])

        _m = _secondary_outcome(_cso_sid, {
            "test_report": ("PASSED: TC-001\n"
                            "FAILED: TC-007 [assert_attribute] — expected aria-disabled=true, got false\n"
                            "\nAction required:\n- js_agent | intent=modify | ..."),
            "modification_attempts": 2})
        assert "ENDED WITH FAILING TESTS" in _m and "Do NOT report" in _m, _m
        assert "TC-007" in _m, "FAIL: the failing case is not named"
        assert "2 correction round" in _m, _m
        print("     failing  ->", _m.splitlines()[0][:78])

        _m = _secondary_outcome(_cso_sid, {"test_report": ""})
        assert "UNVERIFIED" in _m, _m
        print("     no report->", _m[:78])
    finally:
        for _f in _cso_files:
            if _f.exists():
                _f.unlink()
    print("PASS: passing, failing, unverified and no-artefact runs read differently\n")

    # ── Single-document contract (added 2026-08-10) ─────────────────────────
    # Stated where the cause is visible. store_html_code would reject an N-page
    # run too, but only after the HTML agent had generated it, and with a
    # per-component coverage message that names the symptom instead.
    print("[Case 5 · GUARD] A multi-page layout_specification is refused at the boundary.")
    assert _layout_page_count({"pages": [{"name": "home"}, {"name": "cart"}]}) == 2
    assert _layout_page_count({"pages": [{"name": "home"}]}) == 1
    assert _layout_page_count('{"pages": [{"n": 1}, {"n": 2}]}') == 2, "JSON-string spec not coerced"
    assert _layout_page_count("not json") == 0 and _layout_page_count(None) == 0

    _cso_wm = WorkingMemory(layout_specification={"pages": [{"name": "home"}, {"name": "cart"}]})
    _cso_events.clear()
    _r = call_secondary_orchestrator.func(
        _SN_CSO(state={"session_id": "utestmp", "working_memory": _cso_wm},
                tool_call_id="cso-2"),
        query="build a shop")
    _m = _r.update["messages"][0].content
    assert set(_r.update.keys()) == {"messages"}, f"FAIL: extra state written: {_r.update.keys()}"
    assert "REFUSED" in _m and "2 pages" in _m, _m
    assert "anchor" in _m, "FAIL: the refusal must name the supported alternative"
    _deltas = [e.get("delta") for e in _cso_events if isinstance(e, dict) and "delta" in e]
    assert sum(_deltas) == 0, f"FAIL: indent left open on the multi-page path, {_deltas}"
    print("   ", _m[:96])
    print("PASS: refused before the HTML agent generated anything, indent balanced\n")

    # ── No-specs generate guard (added 2026-08-22) ──────────────────────────
    # The model skipped context engineering and planning and called this tool
    # directly, so working_memory held only the empty specs reset_before wrote.
    # A build from them invents a page from the query alone. Refuse, and name
    # the two skipped steps. Modify is exempt by construction (intent check),
    # and that is an accept path, so it is covered by the live SO suite.
    print("[Case 6 · GUARD] A generate build with no specifications is refused.")
    _cso_events.clear()
    _r = call_secondary_orchestrator.func(
        _SN_CSO(state={"session_id": "utestns", "working_memory": WorkingMemory()},
                tool_call_id="cso-3"),
        query="build an umbrella shop", intent="generate")
    _m = _r.update["messages"][0].content
    assert set(_r.update.keys()) == {"messages"}, f"FAIL: extra state written: {_r.update.keys()}"
    assert "REFUSED" in _m and "no specifications" in _m, _m
    assert "call_system_design_planning_agent" in _m, "FAIL: refusal must name the skipped step"
    _deltas = [e.get("delta") for e in _cso_events if isinstance(e, dict) and "delta" in e]
    assert sum(_deltas) == 0, f"FAIL: indent left open on the no-specs path, {_deltas}"
    print("   ", _m[:96])
    print("PASS: generate refused when planning was skipped, indent balanced\n")
    # ── Test cases persist beside the page (2026-09-15) ─────────────────────
    # 13b71045: every user modify ran Playwright on an EMPTY suite and ended
    # "(no report produced)", because this tool seeded test_cases=[] and the
    # primary's _reset_before wipes working_memory each turn. The suite now
    # lives in tests_<sid>.json. The sub-graph is MOCKED: it yields the same
    # ("updates", {...}) chunks the real stream does, so the seed, the
    # reducer-fold and the write-back are exercised without a model call.
    from unittest.mock import MagicMock as _CsoMock
    print("[Case 7 · NORMAL] The suite a run produced is written beside the page, and a modify reads it back.")
    _cso_tsid = "utest_tc_" + _cso_uuid.uuid4().hex[:6]
    _cso_tpath = _test_cases_path(_cso_tsid)
    _cso_page = _PREVIEW_ROOT / f"preview_{_cso_tsid}.html"
    assert _load_test_cases_file(_cso_tsid) == [], "no file -> empty suite"
    _cso_tpath.write_text("not json", encoding="utf-8")
    assert _load_test_cases_file(_cso_tsid) == [], "bad json -> empty suite, no raise"
    _cso_tpath.unlink()

    def _run_cso_mocked(chunks, **kw):
        global secondary_orch
        _orig = secondary_orch
        _m = _CsoMock()
        _m.stream.return_value = iter(chunks)
        try:
            secondary_orch = _m
            _r = call_secondary_orchestrator.func(
                _SN_CSO(state={"session_id": _cso_tsid,
                               "working_memory": WorkingMemory(
                                   layout_specification={"pages": [{"name": "home"}]})},
                        tool_call_id="cso-7"), **kw)
        finally:
            secondary_orch = _orig
        return _r, _m.stream.call_args.args[0]

    try:
        _cso_page.write_text("<html></html>", encoding="utf-8")
        # generation: two Test Gen batches + a sync delta -> ONE merged file
        _r, _p = _run_cso_mocked([
            ("updates", {"tools": {"test_cases": [{"id": "TC-1", "x": 1}, {"id": "TC-2", "x": 2}]}}),
            ("updates", {"tools": {"test_cases": [{"id": "TC-3", "x": 3}]}}),
            ("updates", {"tools": {"test_cases": [{"id": "TC-2", "x": 22}]}}),
        ], query="build a shop", intent="generate")
        assert _p["test_cases"] == [], "generation must start with an empty suite"
        _saved = _load_test_cases_file(_cso_tsid)
        assert [t["id"] for t in _saved] == ["TC-1", "TC-2", "TC-3"], _saved
        assert _saved[1]["x"] == 22, "a re-sent id must replace, not duplicate (reducer fold)"
        assert "3 test case(s) kept" in _r.update["messages"][0].content
        # modify: the file seeds the payload; a sync delta is folded and written back
        _r, _p = _run_cso_mocked([
            ("updates", {"tools": {"test_cases": [{"id": "TC-1", "x": 11}]}}),
        ], query="change a word", intent="modify", target_component=".card")
        assert [t["id"] for t in _p["test_cases"]] == ["TC-1", "TC-2", "TC-3"], \
            "modify must be seeded with the stored suite"
        assert _load_test_cases_file(_cso_tsid)[0]["x"] == 11, "sync delta folded and written back"
        # a modify that touches no case leaves the file as it was
        _r, _p = _run_cso_mocked([], query="change a word", intent="modify", target_component=".card")
        assert len(_load_test_cases_file(_cso_tsid)) == 3
        print("PASS: generate writes the merged suite, modify reads it back and folds sync deltas\n")
    finally:
        for _f in (_cso_tpath, _cso_page):
            if _f.exists():
                _f.unlink()
finally:
    if _cso_real_writer is not None:
        globals()["get_stream_writer"] = _cso_real_writer

print("All 7 cases passed -- call_secondary_orchestrator "
      "(session_id guard, indent, outcome reporting, single-document "
      "contract, no-specs generate guard).")
