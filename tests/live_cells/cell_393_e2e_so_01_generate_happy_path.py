# Ported from fyp.ipynb cell 393 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 392
# LIVE-LLM: costs credits, run manually only
# ══ E2E-SO-01  Generate happy path ═══════════════════════════════════════════
print("=" * 68)
print("[E2E] SO-01  generate — full sub-workflow, ordering, artefacts, cap accounting")
print("=" * 68)
_t0  = _so_time.perf_counter()
# Hold the payload: the session id is now an INPUT, so the id under test is
# the one sent in, not one read back out of the final state.
_so1_payload = _so_payload(_SO_QUERY)
_so1 = stream_agent_run(secondary_orch, payload=_so1_payload,
                        auto_add_design_schema=False, config=_so_cfg("01"))
_el1 = _so_time.perf_counter() - _t0

_ord1 = _so_tools_called(_so1)
print(f"[E2E] tool order: {' -> '.join(_ord1)}")

# Ordering constraints from the system prompt, each enforced as its own assert so
# a failure names WHICH rule broke.
for _t in ("call_html_agent", "call_css_agent",
           "call_js_agent", "call_test_gen_agent", "call_test_exec_pipeline"):
    assert _t in _ord1, f"SO-01 FAIL: {_t} was never called -- order was {_ord1}"
assert _so_first(_ord1, "call_html_agent") == 0, (
    f"SO-01 FAIL: call_html_agent must come first now that the session id is "
    f"an input rather than a tool call -- {_ord1}")
_html_at = _so_first(_ord1, "call_html_agent")
for _t in ("call_css_agent", "call_js_agent"):
    assert _html_at < _so_first(_ord1, _t), \
        f"SO-01 FAIL: HTML must finish before {_t} (both read the generated HTML) -- {_ord1}"
assert _ord1[-1] == "call_test_exec_pipeline", \
    f"SO-01 FAIL: the test run must come last -- {_ord1}"

# The id the CALLER issued. Nothing in the graph writes session_id any more,
# so it is absent from the captured state and that is correct. The three
# files existing under this exact name is the real proof it travelled intact
# from the payload, through the orchestrator, into all three developer agents.
_SO_SESSION = _so1_payload["session_id"]
for _ext in ("html", "css", "js"):
    _f = _SO_PREVIEW / f"preview_{_SO_SESSION}.{_ext}"
    assert _f.exists() and _f.stat().st_size > 0, f"SO-01 FAIL: {_f} missing or empty"
print(f"[E2E] artefacts: preview_{_SO_SESSION}.{{html,css,js}} all written "
      f"-- the caller-issued session id reached every developer agent unchanged")

_tc1 = _so1["state"].get("test_cases") or []
_rp1 = _so1["state"].get("test_report") or ""
assert _tc1, "SO-01 FAIL: no test_cases in final state"
assert _rp1, "SO-01 FAIL: no test_report in final state"
# A correction loop here is legitimate behaviour, not a failure. SO-01 asks
# whether the WORKFLOW completed, not whether the model got the page right first
# time. Asserting modification_attempts == 0 would quietly demand the second, and
# would contradict the evaluation argument that a capped loop may end still
# failing -- the same reason SO-03 reports recovery instead of asserting it.
_exec_calls = _ord1.count("call_test_exec_pipeline")
_att1       = _so1["state"].get("modification_attempts", 0)
assert _att1 <= _MODIFICATION_ATTEMPT_CAP, f"SO-01 FAIL: the cap was breached -- modification_attempts={_att1}"
# The invariant that holds whether or not corrections happened: the BASELINE run
# carries an empty modification_context and is never counted, so the counter
# equals the number of pipeline calls after the first, saturating at the cap
# (a call refused at the cap returns before incrementing).
assert _att1 == min(_exec_calls - 1, _MODIFICATION_ATTEMPT_CAP), (
    f"SO-01 FAIL: {_exec_calls} pipeline run(s) but modification_attempts={_att1}; "
    f"expected {min(_exec_calls - 1, _MODIFICATION_ATTEMPT_CAP)}. Either the baseline run was counted or a "
    f"correction was not.")
_pass1  = "ALL TESTS PASSED" in _rp1
_first1 = _exec_calls == 1
print(f"[E2E] Profile SO-01 - {len(_ord1)} tool call(s), {len(_tc1)} test case(s), "
      f"{_el1:.0f}s")
print(f"[E2E] Outcome SO-01 - pipeline runs: {_exec_calls} | corrections: {_att1}/{_MODIFICATION_ATTEMPT_CAP} "
      f"| first-pass: {_first1} | ended passing: {_pass1}")
if not _pass1:
    print("[E2E] NOTE - the run ended with tests still failing inside the cap. That is a "
          "permitted outcome and a residual-failure data point, not a workflow defect.")
# -- C proof: one call per developer agent per correction round -------------
# SO-01 is the happy path and normally passes first time, so this usually
# reports NO correction rounds. That is the honest reading and it is why the
# same proof also runs in SO-03, which forces a failure and therefore actually
# exercises the cap.
_shape1 = _so_round_shape(_ord1)
_so_assert_round_cap(_shape1, "SO-01")
_shape1_txt = str(_shape1) if _shape1 else (
    "none -- the page passed first time, so the cap was NOT exercised here. "
    "SO-03 is the case that forces a correction round")
print(f"[proof] round cap live: {len(_shape1)} correction round(s), calls per "
      f"agent per round = {_shape1_txt}. PO-08 po018f8158 ran html 5x then 3x "
      f"across its two rounds, 12 developer calls in total; the ceiling is now "
      f"3 agents x {_MODIFICATION_ATTEMPT_CAP} correction round(s) = "
      f"{3 * _MODIFICATION_ATTEMPT_CAP}.")

_SO_RESULTS["SO-01"] = True
print("=" * 68)
print(f"PASS E2E-SO-01  ordering held, 3 files written, {len(_tc1)} cases run, "
      f"{_exec_calls} pipeline run(s), {_att1}/{_MODIFICATION_ATTEMPT_CAP} corrections counted")
print("=" * 68)
