# Ported from fyp.ipynb cell 399 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 392
# LIVE-LLM: costs credits, run manually only
# ══ E2E-SO-04  Modify + css sync ═════════════════════════════════════════════════
# The user-select path. The suite must be PATCHED, never regenerated: the specs
# go stale the moment a page is hand-edited, so re-running Test Generation would
# rebuild tests from a spec that no longer describes the page.
if not (_SO_SESSION and _tc1):
    print("\n[E2E] SO-04 SKIPPED — run E2E-SO-01 first: it generates the page "
          "these scenarios act on and the suite they reuse.")
else:
    print("\n" + "=" * 68)
    print("[E2E] SO-04  modify — style change must SYNC the suite, not regenerate")
    print("=" * 68)
    _NEW_BG = "#d93025"
    _so4 = stream_agent_run(
        secondary_orch,
        payload=_so_payload(
            f"Change the add-to-cart button's background colour to {_NEW_BG}.",
            intent="modify", session_id=_SO_SESSION, test_cases=_tc1,
            target_component="add-to-cart-button",
        ),
        auto_add_design_schema=False, config=_so_cfg("04"))

    _ord4 = _so_tools_called(_so4)
    print(f"[E2E] tool order: {' -> '.join(_ord4)}")
    assert "call_css_agent" in _ord4, f"SO-04 FAIL: the CSS agent never ran -- {_ord4}"
    assert "sync_css_test_cases" in _ord4, \
        (f"SO-04 FAIL: assert_css expectations were not rebased, so the suite still "
         f"expects the OLD colour and will fail forever -- {_ord4}")
    assert "call_test_gen_agent" not in _ord4, \
        (f"SO-04 FAIL: the suite was REGENERATED. A modify run must patch the existing "
         f"suite -- the specs are stale once the page is hand-edited -- {_ord4}")
    assert "call_test_exec_pipeline" in _ord4, f"SO-04 FAIL: tests never re-ran -- {_ord4}"
    assert _so_first(_ord4, "sync_css_test_cases") < _so_first(_ord4, "call_test_exec_pipeline"), \
        f"SO-04 FAIL: the suite must be rebased BEFORE it is re-run -- {_ord4}"

    # A sync tool returns only the cases it CHANGED, and stream_agent_run records
    # only what a run wrote, so the captured value is the delta. Merge it back
    # over the suite SO-01 produced to see the patched suite as state holds it.
    _delta4 = _so4["state"].get("test_cases") or []
    _tc4    = _merge_test_cases(_tc1, _delta4)
    _syn    = [t for t in _tc4 if t.get("action") == "assert_css"
               and t.get("component") == "add-to-cart-button"]
    print(f"[E2E] sync patched {len(_delta4)} case(s); the suite holds "
          f"{len(_syn)} assert_css case(s) on the button, {len(_tc4)} in total")

    # The OUTCOME, not just the shape of the run. Until 2026-08-11 this scenario
    # asserted only that call_css_agent and sync_css_test_cases had been CALLED,
    # so it PASSED while sync rebased every expectation back to the PRE-change
    # colour, the suite failed twice, and the correction cap was exhausted. A
    # scenario about keeping the suite in step with the page has to check that
    # it IS in step with the page.
    assert _syn, "SO-04 FAIL: no assert_css case on the button to rebase"
    _stale4 = [t for t in _syn
               if _SO_BTN_BG.lower() in (t.get("expected") or "").lower()]
    assert not _stale4, (
        f"SO-04 FAIL: {len(_stale4)} of {len(_syn)} assert_css case(s) still expect "
        f"the OLD colour {_SO_BTN_BG} after sync -- the suite was rebased onto the "
        f"stale specification instead of onto the page: {[t['id'] for t in _stale4]}")
    _fresh4 = [t for t in _syn
               if _NEW_BG.lower() in (t.get("expected") or "").lower()]
    assert len(_fresh4) == len(_syn), (
        f"SO-04 FAIL: only {len(_fresh4)} of {len(_syn)} assert_css case(s) carry "
        f"the requested colour {_NEW_BG}; sync patched some of them but not all")
    print(f"[E2E] all {len(_syn)} button assertion(s) expect {_NEW_BG}, none expect "
          f"{_SO_BTN_BG}")

    assert len(_tc4) == len(_tc1), \
        (f"SO-04 FAIL: the suite changed size ({len(_tc1)} -> {len(_tc4)}). A sync "
         f"must PATCH existing cases, never add or drop any.")
    _SO_RESULTS["SO-04"] = True
    print("=" * 68)
    print("PASS E2E-SO-04  css modified, suite rebased via sync, Test Gen never re-ran")
    print("=" * 68)
