# Ported from fyp.ipynb cell 397 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 392
# LIVE-LLM: costs credits, run manually only
# ══ E2E-SO-03  Correction loop ═══════════════════════════════════════════════
# The bug is introduced BY THIS TEST, which is what makes the scenario
# deterministic — waiting for a natural failure is not a test. A wrong colour is
# unambiguous: assert_css fails, and _route_agent sends it to css_agent.
if not (_SO_SESSION and _tc1):
    print("\n[E2E] SO-03 SKIPPED — run E2E-SO-01 first: it generates the page "
          "these scenarios act on and the suite they reuse.")
else:
    print("\n" + "=" * 68)
    print("[E2E] SO-03  correction loop — corrupt the CSS, expect detect/route/fix")
    print("=" * 68)
    _css_path = _SO_PREVIEW / f"preview_{_SO_SESSION}.css"
    _css_before = _css_path.read_text(encoding="utf-8")
    _WRONG = "#c0392b"
    assert _SO_BTN_BG in _css_before.lower() or _SO_BTN_BG.upper() in _css_before, \
        (f"SO-03 SETUP FAIL: {_SO_BTN_BG} is not in the generated CSS, so there is "
         f"nothing to corrupt. The CSS agent may have written the colour in another "
         f"notation -- inspect {_css_path} and pick a different target.")
    _css_path.write_text(
        _css_before.replace(_SO_BTN_BG, _WRONG).replace(_SO_BTN_BG.upper(), _WRONG),
        encoding="utf-8")
    print(f"[E2E] corrupted {_SO_BTN_BG} -> {_WRONG} in preview_{_SO_SESSION}.css")

    _so3 = stream_agent_run(
        secondary_orch,
        payload=_so_payload(
            "Re-run the test suite for this page and fix anything that fails.",
            intent="modify", session_id=_SO_SESSION, test_cases=_tc1,
        ),
        auto_add_design_schema=False, config=_so_cfg("03"))

    _ord3 = _so_tools_called(_so3)
    _fb3  = "\n".join(_so3["tool_feedback"])
    _rp3  = _so3["state"].get("test_report") or ""
    print(f"[E2E] tool order: {' -> '.join(_ord3)}")

    assert "FAILED" in _fb3, "SO-03 FAIL: the corrupted colour was never detected"
    assert "css_agent" in _fb3, \
        "SO-03 FAIL: the failure was not routed to css_agent -- check _route_agent"
    assert "call_css_agent" in _ord3, \
        f"SO-03 FAIL: the orchestrator did not act on the routing -- {_ord3}"
    _att3 = _so3["state"].get("modification_attempts", 0)
    assert 1 <= _att3 <= _MODIFICATION_ATTEMPT_CAP, f"SO-03 FAIL: attempts out of bounds: {_att3}"
    # Recovery is a MEASUREMENT, not an invariant -- a capped loop is allowed to
    # end still failing, which is exactly why the pass rate is an honest number.
    _recovered = "ALL TESTS PASSED" in _rp3
    print(f"[E2E] recovered within the cap: {_recovered}  (attempts used: {_att3}/{_MODIFICATION_ATTEMPT_CAP})")
    if not _recovered:
        _css_path.write_text(_css_before, encoding="utf-8")
        print("[E2E] CSS restored by hand so SO-04 starts from a clean page")
    # -- C proof: this is the case that actually enters a correction round -----
    # SO-03 corrupts a colour on purpose, so assert_css fails and the loop runs.
    # Without this the cap has no live evidence at all: SO-01 passes first time
    # and exercises none of it.
    _shape3 = _so_round_shape(_ord3)
    _so_assert_round_cap(_shape3, "SO-03")
    assert _shape3, (
        "SO-03 FAIL: no correction round was detected, so the forced failure "
        f"never reached the loop. tool order was {_ord3}")
    print(f"[proof] round cap live: {len(_shape3)} correction round(s), calls "
          f"per agent per round = {_shape3}. Every agent is capped at "
          f"{_ROUND_CALL_CAP} per round; PO-08 po018f8158 ran html 5x then 3x "
          f"across its two rounds, 12 developer calls in total.")

    _SO_RESULTS["SO-03"] = True
    print("=" * 68)
    print(f"PASS E2E-SO-03  detected, routed to css_agent, fix attempted, "
          f"{_att3} attempt(s) counted")
    print("=" * 68)
