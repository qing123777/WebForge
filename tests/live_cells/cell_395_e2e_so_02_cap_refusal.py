# Ported from fyp.ipynb cell 395 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 392
# LIVE-LLM: costs credits, run manually only
# ══ E2E-SO-02  Cap refusal ═══════════════════════════════════════════════════
# Seeded at the cap, so this is CHEAP: the orchestrator should go straight to the
# pipeline, be refused in code, and stop. No sub-agent should run.
# The refusal itself is already unit-tested; what is under test HERE is whether
# the real model OBEYS it instead of looping — which no offline suite can show.
print("\n" + "=" * 68)
print("[E2E] SO-02  cap refusal — a 3rd correction must be refused and END")
print("=" * 68)
_so_require_so01("SO-02")
_so2 = stream_agent_run(
    secondary_orch,
    payload=_so_payload(
        "The add-to-cart button styling has been fixed. Re-run the test suite to confirm.",
        intent="modify",
        session_id=_SO_SESSION or "so-cap-probe",
        test_cases=_tc1,
        modification_context="add-to-cart-button colour corrected",
        modification_attempts=_MODIFICATION_ATTEMPT_CAP,
        # The cap keys on is_rerun = a PRIOR report existing (2026-08-29
        # refactor moved it off modification_context). Seed a non-empty
        # report so this is a genuine at-cap RE-RUN; without it the pipeline
        # reads is_rerun=False, treats the call as a fresh baseline, runs the
        # suite, and never reaches the refusal -- which is the SO-02 false
        # failure of 2026-09-01. Content is irrelevant; only non-emptiness is.
        test_report="PASSED: 9 case(s)\nFAILED: 1 case(s)\n",
    ),
    auto_add_design_schema=False, config=_so_cfg("02"))

_ord2 = _so_tools_called(_so2)
_fb2  = "\n".join(_so2["tool_feedback"])
print(f"[E2E] tool order: {' -> '.join(_ord2) or '(none)'}")
assert "REFUSED" in _fb2, f"SO-02 FAIL: the pipeline did not refuse at the cap -- {_fb2[:300]}"
# A refused call returns a message and NOTHING else, so it never writes
# modification_attempts. stream_agent_run collects state from the "updates"
# stream, which records only what nodes actually wrote and never the seeded
# payload -- so the key being ABSENT is the proof that the counter was untouched.
# If some other path did write it, it must still read 2.
_att2 = _so2["state"].get("modification_attempts")
assert _att2 is None or _att2 == 2, (
    f"SO-02 FAIL: the counter moved past the cap. Written value: {_att2!r} "
    f"(absent means no tool wrote it, which is the expected outcome).")
print(f"[E2E] counter after the refusal: "
      f"{f'never written (seeded value {_MODIFICATION_ATTEMPT_CAP} stands)' if _att2 is None else _att2}")
# and the model must STOP rather than try another route around the refusal
_after = _ord2[_ord2.index("call_test_exec_pipeline") + 1:] if "call_test_exec_pipeline" in _ord2 else []
assert not [t for t in _after if t.startswith("call_")], \
    f"SO-02 FAIL: the orchestrator kept working after REFUSED -- {_after}"
_SO_RESULTS["SO-02"] = True
print("=" * 68)
print("PASS E2E-SO-02  refused in code, counter unchanged, orchestrator stopped")
print("=" * 68)
