# Ported from fyp.ipynb cell 400 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 392
# LIVE-LLM: costs credits, run manually only
# ══ E2E-SO-05  Modify + TEXT sync ════════════════════════════════════════════
# The same contract SO-04 checks for styles, applied to visible text. A label
# change lives in the markup, so the HTML agent makes it, and every assert_text
# case that quoted the old label is now wrong. sync_text_test_cases rebases them.
#
# Why it needs its own live case: sync_text_test_cases has unit tests and has
# never run against a real model. The failure it guards against is silent. The
# page is correct, the suite expects the old words, the tests fail, and the
# correction loop spends both attempts "fixing" a page that was never broken.
if not (_SO_SESSION and _tc1):
    print("\n[E2E] SO-05 SKIPPED — run E2E-SO-01 first: it generates the page "
          "these scenarios act on and the suite they reuse.")
else:
    print("\n" + "=" * 68)
    print("[E2E] SO-05  modify text — suite rebased via sync_text_test_cases")
    print("=" * 68)
    _NEW_LABEL = "Add to bag"

    # What the suite expected BEFORE the change. Read from the suite rather than
    # assumed, because the label was written by the HTML agent in SO-01 and this
    # cell has no way to know what it chose.
    _txt_before = [t for t in _tc1
                   if t.get("action") == "assert_text"
                   and t.get("component") == "add-to-cart-button"]
    print(f"[E2E] {len(_txt_before)} assert_text case(s) on the button before the change: "
          f"{[t.get('expected') for t in _txt_before]}")
    if not _txt_before:
        print("[E2E] SO-05 SKIPPED — SO-01's suite has no assert_text case on the "
              "button, so there is nothing for the text sync to rebase. Re-run "
              "SO-01: Test Generation decides what to assert, and it varies.")
    else:
        _so5 = stream_agent_run(
            secondary_orch,
            payload=_so_payload(
                f'Change the add-to-cart button\'s visible text to "{_NEW_LABEL}".',
                intent="modify", session_id=_SO_SESSION, test_cases=_tc1,
                target_component="add-to-cart-button",
            ),
            auto_add_design_schema=False, config=_so_cfg("05"))

        _ord5 = _so_tools_called(_so5)
        print(f"[E2E] tool order: {' -> '.join(_ord5)}")
        assert "call_html_agent" in _ord5, \
            f"SO-05 FAIL: visible text lives in the markup, so the HTML agent had to run -- {_ord5}"
        assert "sync_text_test_cases" in _ord5, \
            (f"SO-05 FAIL: assert_text expectations were not rebased, so the suite "
             f"still quotes the OLD label and will fail forever -- {_ord5}")
        assert "call_test_gen_agent" not in _ord5, \
            (f"SO-05 FAIL: the suite was REGENERATED. A modify run must patch the "
             f"existing suite -- the specs are stale once the page is edited -- {_ord5}")
        assert _so_first(_ord5, "sync_text_test_cases") < _so_first(_ord5, "call_test_exec_pipeline"), \
            f"SO-05 FAIL: the suite must be rebased BEFORE it is re-run -- {_ord5}"

        _tc5 = _merge_test_cases(_tc1, _so5["state"].get("test_cases") or [])
        _txt_after = [t for t in _tc5
                      if t.get("action") == "assert_text"
                      and t.get("component") == "add-to-cart-button"]
        assert _txt_after, "SO-05 FAIL: the assert_text cases vanished from the suite"

        _stale5 = [t for t in _txt_after
                   if _NEW_LABEL.lower() not in (t.get("expected") or "").lower()]
        assert not _stale5, (
            f"SO-05 FAIL: {len(_stale5)} of {len(_txt_after)} assert_text case(s) do "
            f"not expect {_NEW_LABEL!r} after sync. The page says one thing and the "
            f"suite expects another: "
            f"{[(t['id'], t.get('expected')) for t in _stale5]}")
        assert len(_tc5) == len(_tc1), \
            (f"SO-05 FAIL: the suite changed size ({len(_tc1)} -> {len(_tc5)}). A sync "
             f"must PATCH existing cases, never add or drop any.")

        print(f"[E2E] all {len(_txt_after)} button text assertion(s) now expect "
              f"{_NEW_LABEL!r}")
        _SO_RESULTS["SO-05"] = True
        print("=" * 68)
        print("PASS E2E-SO-05  text modified, suite rebased via sync, Test Gen never re-ran")
        print("=" * 68)
