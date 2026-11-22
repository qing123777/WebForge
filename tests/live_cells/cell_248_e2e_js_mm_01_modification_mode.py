# Ported from fyp.ipynb cell 248 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# LIVE-LLM: costs credits, run manually only
# ─────────────────────────────────────────────────────────────────────────────
# E2E-JS-MM-01  Modification mode — targeted change, wiring intact
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-JS-MM-01  Modification mode — single component")
print("=" * 64)

if not os.path.exists(_js_path):
    print("SKIP E2E-JS-MM-01: generation did not produce a JS file to modify\n")
else:
    _js_mm01 = _stream_js_agent(
        _js_session_id,
        "Also update the mini-cart's data-count attribute whenever the counter "
        "changes.",
        intent="modify",
        target_component="#mini-cart",   # Selector Contract: #id (no className)
        target_instance=1,
        interaction_specification=_JS_INTERACTION_SPEC,
        components_specification=_JS_COMPONENTS_SPEC,
        run_name="JS Agent - MM-01",
    )
    _js_modified = _js_mm01.get("js_code", "")

    assert len(_js_modified) > 0, \
        "E2E-JS-MM-01 FAIL: js_code empty after modification"
    assert _js_mm01.get("lint_passed") is True, \
        f"E2E-JS-MM-01 FAIL: lint_passed={_js_mm01.get('lint_passed')}"
    assert _js_modified != _js_generated, \
        "E2E-JS-MM-01 FAIL: JS unchanged — the modification never applied"

    # No collateral damage: the original wiring must survive the edit.
    for _ref in _JS_EXPECTED_REFS:
        assert _ref in _js_modified, \
            f"E2E-JS-MM-01 FAIL: reference to {_ref!r} lost during modification"

    _js_disk_mm01 = open(_js_path, encoding="utf-8").read()
    assert _js_disk_mm01 == _js_modified, \
        "E2E-JS-MM-01 FAIL: file on disk does not match js_code after modification"

    _js_e2e_passed += 1
    print(f"PASS E2E-JS-MM-01  change applied  {len(_js_modified)} chars  "
          f"wiring preserved  file updated")
    print(f"[soft] literal 'data-count' present: "
          f"{'data-count' in _js_modified}\n")

    # -- No-echo proof (speed-cost ticket 03, part 1) ----------------------
    # The orchestrator puts the file in state, so a modify call goes straight
    # to extract. The edit landing proves nothing here: it lands the same
    # whether or not the model first copied the whole file back.
    _ne_tools = list(_js_mm01.get("tools_called", []))
    _ne_store, _ne_read = _ne_tools.count("store_js_code"), _ne_tools.count("read_file")
    print(f"[proof] no echo live: store_js_code called {_ne_store}x and read_file "
          f"{_ne_read}x in this modify call. Before ticket 03 every modify call "
          f"opened with 1 read_file + 1 store_js_code of the whole file "
          f"(PO-08 4fb17fbe, js: 6,327 output tokens, 55.1 s).")
    assert _ne_store == 0, (
        "E2E-JS-MM-01 FAIL: the model sent the whole file back through store_js_code "
        f"although it was already in state. tools={_ne_tools}")

    # -- Fix 5/6 wiring proof (2026-08-31) --------------------------------
    # The assertions above prove the EDIT landed. They cannot see whether the
    # patch cap and the hunk relocation are wired, because a healthy modify
    # exercises neither. Both are checked here instead, so a run that passes
    # is a run where both are live in this kernel.
    #
    # patch_attempts is written by apply_and_lint_js on every apply, failed or
    # successful. LangGraph DROPS a write to an undeclared channel silently,
    # so an agent built before the field was added does not raise: the key
    # simply never arrives, the cap reads 0 forever and can never fire. That
    # is PO-08 po01ba89e9, which had to be killed by hand at $3.56.
    if "apply_and_lint_js" in _js_mm01.get("tools_called", []):
        assert "patch_attempts" in _js_mm01, (
            "E2E-JS-MM-01 FAIL: a diff was applied but patch_attempts never reached "
            "the caller. Either JsState does not declare it, or the agent was "
            "built before it was added. Restart the kernel and run every cell "
            "-- until then the patch cap cannot fire.")
        print("[proof] patch cap wired; patch_attempts after this run: "
              f"{_js_mm01['patch_attempts']}")
    else:
        print("[proof] no diff applied this run, so the patch cap was not "
              "exercised")

    # Relocation, asked of the loaded function directly. No model call, no cost.
    _fx_doc  = "a" + chr(10) + "b" + chr(10) + "UNIQUE-TARGET-LINE" + chr(10) + "c" + chr(10)
    _fx_want = "a" + chr(10) + "b" + chr(10) + "CHANGED" + chr(10) + "c" + chr(10)
    _fx_hunk = (chr(10).join(["--- original", "+++ revised", "@@ -99,1 +99,1 @@",
                              "-UNIQUE-TARGET-LINE", "+CHANGED"]) + chr(10))
    assert _apply_patch(_fx_doc, _fx_hunk) == _fx_want, (
        "E2E-JS-MM-01 FAIL: this kernel still holds the OLD _apply_patch. A hunk with "
        "wrong line numbers fails instead of relocating by its own context, "
        "which is what every patch failure on po01ba89e9 was. Re-run the "
        "_apply_patch cell.")
    print("[proof] a misnumbered hunk relocates by its context (Fix 6 live)" + chr(10))


# ─────────────────────────────────────────────────────────────────────────────
# E2E-JS-MM-02  Modification mode — multi-block edge case
#
# mini-cart is touched by BOTH flows, so its wiring is spread across more than
# one place in the script. Editing it exercises the multi-block diff path
# (extract_js_component returns every referencing block; store_js_diff splices
# non-contiguous spans) while the two button flows must survive untouched.
# Auto-skips if generation happened to wire mini-cart in a single place.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-JS-MM-02  Modification mode — multi-block edge case")
print("=" * 64)

_mc_refs = _js_gen2.count("mini-cart")
if not os.path.exists(_js_path2) or _mc_refs < 2:
    print(f"SKIP E2E-JS-MM-02: mini-cart referenced {_mc_refs} time(s) — "
          f"need >= 2 for the multi-block path\n")
else:
    _js_mm02 = _stream_js_agent(
        _js_session_id2,
        "Change the mini-cart so it displays its count as 'N items' instead "
        "of just the number.",
        intent="modify",
        target_component="#mini-cart",   # Selector Contract: #id (no className)
        target_instance=1,
        interaction_specification=_JS_INTERACTION_SPEC2,
        components_specification=_JS_COMPONENTS_SPEC2,
        run_name="JS Agent - MM-02",
    )
    _js_mod2    = _js_mm02.get("js_code", "")
    _mm02_tools = _js_mm02.get("tools_called", [])

    assert _js_mm02.get("lint_passed") is True, \
        f"E2E-JS-MM-02 FAIL: lint_passed={_js_mm02.get('lint_passed')}"
    assert _js_mod2 and _js_mod2 != _js_gen2, \
        "E2E-JS-MM-02 FAIL: JS unchanged — the modification never applied"
    # No collateral damage: both button flows must survive the mini-cart edit.
    for _ref in ("add-to-cart-btn", "clear-cart-btn"):
        assert _ref in _js_mod2, \
            f"E2E-JS-MM-02 FAIL: flow control {_ref!r} lost during the mini-cart edit"
    # Modify mode, not regenerate: a diff was applied and code was not re-stored
    # past the Step 0 seed.
    assert "apply_and_lint_js" in _mm02_tools, \
        f"E2E-JS-MM-02 FAIL: no diff applied. tools={_mm02_tools}"
    assert _mm02_tools.count("store_js_code") == 0, \
        f"E2E-JS-MM-02 FAIL: re-generated instead of diffing. tools={_mm02_tools}"
    assert open(_js_path2, encoding="utf-8").read() == _js_mod2, \
        "E2E-JS-MM-02 FAIL: disk != state after modification"

    _js_e2e_passed += 1
    print(f"PASS E2E-JS-MM-02  mini-cart edited across {_mc_refs} refs  "
          f"both flows intact  disk == state\n")


# ─────────────────────────────────────────────────────────────────────────────
# E2E-JS-MM-03  Modification mode — dead end: target selector matches nothing
#
# The stale-spec scenario: the orchestrator passes a selector that no longer
# matches the page. Acceptable behaviour is pinned here — stop gracefully,
# change nothing on disk, apply no diff, save no file. Uses the FIRST session's
# script so a wrongly-written file would be caught.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-JS-MM-03  Modification mode — dead end (selector matches nothing)")
print("=" * 64)

if not os.path.exists(_js_path):
    print("SKIP E2E-JS-MM-03: no first-session JS file to modify\n")
else:
    _js_before = open(_js_path, encoding="utf-8").read()
    _js_mm03 = _stream_js_agent(
        _js_session_id,
        "Wire the wishlist drawer's close button to hide the drawer.",
        intent="modify",
        target_component="#wishlist-drawer",   # deliberately absent from the page
        target_instance=1,
        interaction_specification=_JS_INTERACTION_SPEC,
        components_specification=_JS_COMPONENTS_SPEC,
        run_name="JS Agent - MM-03",
    )
    _js_after   = open(_js_path, encoding="utf-8").read()
    _mm03_tools = _js_mm03.get("tools_called", [])

    # 1. terminated gracefully (reaching here means no recursion blow-up)
    # 2. the file on disk is byte-identical
    assert _js_after == _js_before, \
        "E2E-JS-MM-03 FAIL: the file changed despite the target not existing"
    # 3. trajectory: no diff applied, nothing saved (store_js_code IS allowed
    #    once — the prompt's Step 0 seed)
    assert "apply_and_lint_js" not in _mm03_tools, \
        f"E2E-JS-MM-03 FAIL: a diff was applied to a nonexistent target. tools={_mm03_tools}"
    assert "save_js_file" not in _mm03_tools, \
        f"E2E-JS-MM-03 FAIL: saved despite a dead-end modification. tools={_mm03_tools}"
    # 4. bounded: a dead end must not become a thrash loop
    assert len(_mm03_tools) <= 10, \
        f"E2E-JS-MM-03 FAIL: {len(_mm03_tools)} tool calls on a dead end — thrashing. tools={_mm03_tools}"

    _js_e2e_passed += 1
    print(f"PASS E2E-JS-MM-03  dead end handled: file byte-identical, "
          f"{len(_mm03_tools)} tool calls, no diff, no save\n")
