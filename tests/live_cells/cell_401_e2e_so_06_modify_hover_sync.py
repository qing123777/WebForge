# Ported from fyp.ipynb cell 401 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 392
# LIVE-LLM: costs credits, run manually only
# ══ E2E-SO-06  Modify + HOVER sync ═══════════════════════════════════════════
# The third sync tool, and the one with the least margin for error. A hover style
# only exists while the pointer is on the element, so the assertion that checks
# it is assert_hover_css, and rebasing it wrongly produces a test that can never
# pass and can never be diagnosed from a screenshot.
#
# The fixture declares a hover stateVariant precisely so SO-01's suite contains a
# case here. If it does not, the scenario skips rather than passing vacuously.
if not (_SO_SESSION and _tc1):
    print("\n[E2E] SO-06 SKIPPED — run E2E-SO-01 first: it generates the page "
          "these scenarios act on and the suite they reuse.")
else:
    print("\n" + "=" * 68)
    print("[E2E] SO-06  modify hover — suite rebased via sync_hover_test_cases")
    print("=" * 68)
    _NEW_HOVER = "#0b5394"

    _hov_before = [t for t in _tc1
                   if t.get("action") == "assert_hover_css"
                   and t.get("component") == "add-to-cart-button"]
    print(f"[E2E] {len(_hov_before)} assert_hover_css case(s) before the change: "
          f"{[t.get('expected') for t in _hov_before]}")
    if not _hov_before:
        print("[E2E] SO-06 SKIPPED — SO-01's suite has no assert_hover_css case on "
              "the button, so there is nothing for the hover sync to rebase. The "
              "fixture DOES declare a hover variant, so if this keeps happening the "
              "real finding is that Test Generation is not deriving hover cases "
              "from stateVariants, which is a defect worth reporting on its own.")
    else:
        _so6 = stream_agent_run(
            secondary_orch,
            payload=_so_payload(
                f"Change the add-to-cart button's HOVER background colour to {_NEW_HOVER}. "
                f"Leave its resting colour alone.",
                intent="modify", session_id=_SO_SESSION, test_cases=_tc1,
                target_component="add-to-cart-button",
            ),
            auto_add_design_schema=False, config=_so_cfg("06"))

        _ord6 = _so_tools_called(_so6)
        print(f"[E2E] tool order: {' -> '.join(_ord6)}")
        assert "call_css_agent" in _ord6, \
            f"SO-06 FAIL: a hover style is CSS, so the CSS agent had to run -- {_ord6}"
        assert "sync_hover_test_cases" in _ord6, \
            (f"SO-06 FAIL: hover expectations were not rebased. sync_css_test_cases "
             f"does NOT touch assert_hover_css cases, so the hover assertion still "
             f"expects the old colour -- {_ord6}")
        assert "call_test_gen_agent" not in _ord6, \
            f"SO-06 FAIL: the suite was REGENERATED instead of patched -- {_ord6}"
        assert _so_first(_ord6, "sync_hover_test_cases") < _so_first(_ord6, "call_test_exec_pipeline"), \
            f"SO-06 FAIL: the suite must be rebased BEFORE it is re-run -- {_ord6}"

        _tc6 = _merge_test_cases(_tc1, _so6["state"].get("test_cases") or [])
        _hov_after = [t for t in _tc6
                      if t.get("action") == "assert_hover_css"
                      and t.get("component") == "add-to-cart-button"]
        assert _hov_after, "SO-06 FAIL: the assert_hover_css cases vanished"

        # What the PAGE says, printed before the assertions read the suite.
        # Three separate faults produce the same failed assertion below: the CSS
        # agent never changed the stylesheet, the sync read the specification
        # instead of the page, or the colour is there in another notation and a
        # substring test misses it. Each one has cost a paid run to tell apart.
        _live6 = _live_hover_styles(
            _read_preview_source(_SO_SESSION, "css"), "add-to-cart-button",
            _so6["state"].get("decoration_specification") or {},
            {"background-color"})
        print(f"[E2E] the stylesheet's hover background is now : "
              f"{_live6.get('background-color') or 'NOT FOUND in any :hover block'}")
        print(f"[E2E] the suite's hover expectation is now     : "
              f"{[t.get('expected') for t in _hov_after]}")
        print(f"[E2E] the scenario asked for                   : {_NEW_HOVER}")

        _stale6 = [t for t in _hov_after
                   if _SO_BTN_HOVER.lower() in (t.get("expected") or "").lower()]
        assert not _stale6, (
            f"SO-06 FAIL: {len(_stale6)} hover case(s) still expect the OLD colour "
            f"{_SO_BTN_HOVER}: {[t['id'] for t in _stale6]}")
        _fresh6 = [t for t in _hov_after
                   if _NEW_HOVER.lower() in (t.get("expected") or "").lower()]
        assert len(_fresh6) == len(_hov_after), (
            f"SO-06 FAIL: only {len(_fresh6)} of {len(_hov_after)} hover case(s) carry "
            f"the requested colour {_NEW_HOVER}")

        # The resting colour must be untouched. A hover sync that also rewrote the
        # base assertion would look like a pass here and break SO-04's guarantee.
        _base6 = [t for t in _tc6 if t.get("action") == "assert_css"
                  and t.get("component") == "add-to-cart-button"]
        _damaged = [t for t in _base6
                    if _NEW_HOVER.lower() in (t.get("expected") or "").lower()]
        assert not _damaged, (
            f"SO-06 FAIL: the hover sync leaked into {len(_damaged)} RESTING "
            f"assert_css case(s): {[t['id'] for t in _damaged]}")

        assert len(_tc6) == len(_tc1), \
            f"SO-06 FAIL: the suite changed size ({len(_tc1)} -> {len(_tc6)})"

        print(f"[E2E] all {len(_hov_after)} hover assertion(s) expect {_NEW_HOVER}, "
              f"and {len(_base6)} resting assertion(s) were left alone")
        _SO_RESULTS["SO-06"] = True
        print("=" * 68)
        print("PASS E2E-SO-06  hover modified, hover suite rebased, resting suite intact")
        print("=" * 68)
