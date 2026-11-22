# Ported from fyp.ipynb cell 305 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# LIVE-LLM: costs credits, run manually only
# ─────────────────────────────────────────────────────────────────────────────
# E2E-CSS-MM-01  Modification mode — targeted change, siblings intact
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-CSS-MM-01  Modification mode — single component")
print("=" * 64)

if not os.path.exists(_css_path):
    print("SKIP E2E-CSS-MM-01: generation did not produce a CSS file to modify\n")
else:
    _css_mm01 = _stream_css_agent(
        _css_session_id,
        "Change the add-to-cart button background colour to #0b5cd5.",
        intent="modify",
        target_component=".add-to-cart-btn",   # Selector Contract: .className
        target_instance=1,
        decoration_specification=_CSS_DECORATION_SPEC,
        run_name="CSS Agent - MM-01",
    )
    _css_modified = _css_mm01.get("css_code", "")

    assert len(_css_modified) > 0, \
        "E2E-CSS-MM-01 FAIL: css_code empty after modification"
    assert _css_mm01.get("lint_passed") is True, \
        f"E2E-CSS-MM-01 FAIL: lint_passed={_css_mm01.get('lint_passed')}"
    assert _css_modified != _css_generated, \
        "E2E-CSS-MM-01 FAIL: CSS unchanged — the modification never applied"

    # No collateral damage: every previously-styled component still has a rule.
    for _cn in _EXPECTED_CLASSNAMES:
        assert re.search(rf"\.{re.escape(_cn)}\b", _css_modified), \
            f"E2E-CSS-MM-01 FAIL: rule for .{_cn} lost during modification"

    _css_disk_mm01 = open(_css_path, encoding="utf-8").read()
    assert _css_disk_mm01 == _css_modified, \
        "E2E-CSS-MM-01 FAIL: file on disk does not match css_code after modification"

    _css_e2e_passed += 1
    print(f"PASS E2E-CSS-MM-01  change applied  {len(_css_modified)} chars  "
          f"all {len(_EXPECTED_CLASSNAMES)} rules preserved  file updated")
    # Soft: the exact literal may be normalised (rgb(), uppercase hex, ...)
    print(f"[soft] literal '#0b5cd5' present   : "
          f"{'#0b5cd5' in _css_modified.lower()}\n")

    # -- No-echo proof (speed-cost ticket 03, part 1) ----------------------
    # The orchestrator puts the file in state, so a modify call goes straight
    # to extract. The edit landing proves nothing here: it lands the same
    # whether or not the model first copied the whole file back.
    _ne_tools = list(_css_mm01.get("tools_called", []))
    _ne_store, _ne_read = _ne_tools.count("store_css_code"), _ne_tools.count("read_file")
    print(f"[proof] no echo live: store_css_code called {_ne_store}x and read_file "
          f"{_ne_read}x in this modify call. Before ticket 03 every modify call "
          f"opened with 1 read_file + 1 store_css_code of the whole file "
          f"(PO-08 4fb17fbe, css: 8,461 output tokens, 70.5 s).")
    assert _ne_store == 0, (
        "E2E-CSS-MM-01 FAIL: the model sent the whole file back through store_css_code "
        f"although it was already in state. tools={_ne_tools}")

    # -- Fix 5/6 wiring proof (2026-08-31) --------------------------------
    # The assertions above prove the EDIT landed. They cannot see whether the
    # patch cap and the hunk relocation are wired, because a healthy modify
    # exercises neither. Both are checked here instead, so a run that passes
    # is a run where both are live in this kernel.
    #
    # patch_attempts is written by apply_and_lint_css on every apply, failed or
    # successful. LangGraph DROPS a write to an undeclared channel silently,
    # so an agent built before the field was added does not raise: the key
    # simply never arrives, the cap reads 0 forever and can never fire. That
    # is PO-08 po01ba89e9, which had to be killed by hand at $3.56.
    if "apply_and_lint_css" in _css_mm01.get("tools_called", []):
        assert "patch_attempts" in _css_mm01, (
            "E2E-CSS-MM-01 FAIL: a diff was applied but patch_attempts never reached "
            "the caller. Either CssState does not declare it, or the agent was "
            "built before it was added. Restart the kernel and run every cell "
            "-- until then the patch cap cannot fire.")
        print("[proof] patch cap wired; patch_attempts after this run: "
              f"{_css_mm01['patch_attempts']}")
    else:
        print("[proof] no diff applied this run, so the patch cap was not "
              "exercised")

    # Relocation, asked of the loaded function directly. No model call, no cost.
    _fx_doc  = "a" + chr(10) + "b" + chr(10) + "UNIQUE-TARGET-LINE" + chr(10) + "c" + chr(10)
    _fx_want = "a" + chr(10) + "b" + chr(10) + "CHANGED" + chr(10) + "c" + chr(10)
    _fx_hunk = (chr(10).join(["--- original", "+++ revised", "@@ -99,1 +99,1 @@",
                              "-UNIQUE-TARGET-LINE", "+CHANGED"]) + chr(10))
    assert _apply_patch(_fx_doc, _fx_hunk) == _fx_want, (
        "E2E-CSS-MM-01 FAIL: this kernel still holds the OLD _apply_patch. A hunk with "
        "wrong line numbers fails instead of relocating by its own context, "
        "which is what every patch failure on po01ba89e9 was. Re-run the "
        "_apply_patch cell.")
    print("[proof] a misnumbered hunk relocates by its context (Fix 6 live)" + chr(10))



# ─────────────────────────────────────────────────────────────────────────────
# E2E-CSS-MM-02  Modification mode — multi-block edge case
#
# product-card has BOTH a base rule and a `:hover` rule, so its styling spans
# more than one block. Editing it exercises the multi-block diff path
# (extract_css_component returns base + :hover together; store_css_diff splices
# non-contiguous blocks) while every other component's rule must survive.
# Auto-skips if generation wrote product-card in a single block.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-CSS-MM-02  Modification mode — multi-block edge case")
print("=" * 64)

_pc_blocks = len(re.findall(r"\.product-card\b", _css_gen2))
if not os.path.exists(_css_path2) or _pc_blocks < 2:
    print(f"SKIP E2E-CSS-MM-02: .product-card written in {_pc_blocks} block(s) — "
          f"need >= 2 for the multi-block path\n")
else:
    _css_mm02 = _stream_css_agent(
        _css_session_id2,
        "Increase the product card corner radius to 12px.",
        intent="modify",
        target_component=".product-card",
        target_instance=1,
        decoration_specification=_CSS_DECORATION_SPEC2,
        run_name="CSS Agent - MM-02",
    )
    _css_mod2   = _css_mm02.get("css_code", "")
    _mm02_tools = _css_mm02.get("tools_called", [])

    assert _css_mm02.get("lint_passed") is True, \
        f"E2E-CSS-MM-02 FAIL: lint_passed={_css_mm02.get('lint_passed')}"
    assert _css_mod2 and _css_mod2 != _css_gen2, \
        "E2E-CSS-MM-02 FAIL: CSS unchanged — the modification never applied"
    # Base + :hover for product-card both survive; other rules intact.
    assert len(re.findall(r"\.product-card\b", _css_mod2)) >= 2, \
        "E2E-CSS-MM-02 FAIL: a product-card block was lost during the edit"
    for _cn in ("site-navbar", "add-to-cart-btn"):
        assert re.search(rf"\.{re.escape(_cn)}\b", _css_mod2), \
            f"E2E-CSS-MM-02 FAIL: rule for .{_cn} lost during the product-card edit"
    # Modify mode, not regenerate: a diff was applied, code not re-stored.
    assert "apply_and_lint_css" in _mm02_tools, \
        f"E2E-CSS-MM-02 FAIL: no diff applied. tools={_mm02_tools}"
    assert _mm02_tools.count("store_css_code") == 0, \
        f"E2E-CSS-MM-02 FAIL: re-generated instead of diffing. tools={_mm02_tools}"
    assert open(_css_path2, encoding="utf-8").read() == _css_mod2, \
        "E2E-CSS-MM-02 FAIL: disk != state after modification"

    _css_e2e_passed += 1
    print(f"PASS E2E-CSS-MM-02  product-card edited across {_pc_blocks} blocks  "
          f"other rules intact  disk == state\n")


# ─────────────────────────────────────────────────────────────────────────────
# E2E-CSS-MM-03  Modification mode — dead end: target selector matches nothing
#
# The stale-spec scenario: the orchestrator passes a selector the page no
# longer has. Acceptable behaviour is pinned here — stop gracefully, change
# nothing on disk, apply no diff, save no file. Uses the FIRST session's file.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-CSS-MM-03  Modification mode — dead end (selector matches nothing)")
print("=" * 64)

if not os.path.exists(_css_path):
    print("SKIP E2E-CSS-MM-03: no first-session CSS file to modify\n")
else:
    _css_before = open(_css_path, encoding="utf-8").read()
    _css_mm03 = _stream_css_agent(
        _css_session_id,
        "Give the wishlist drawer a subtle drop shadow.",
        intent="modify",
        target_component=".wishlist-drawer",   # deliberately absent from the page
        target_instance=1,
        decoration_specification=_CSS_DECORATION_SPEC,
        run_name="CSS Agent - MM-03",
    )
    _css_after  = open(_css_path, encoding="utf-8").read()
    _mm03_tools = _css_mm03.get("tools_called", [])

    assert _css_after == _css_before, \
        "E2E-CSS-MM-03 FAIL: the file changed despite the target not existing"
    assert "apply_and_lint_css" not in _mm03_tools, \
        f"E2E-CSS-MM-03 FAIL: a diff was applied to a nonexistent target. tools={_mm03_tools}"
    assert "save_css_file" not in _mm03_tools, \
        f"E2E-CSS-MM-03 FAIL: saved despite a dead-end modification. tools={_mm03_tools}"
    assert len(_mm03_tools) <= 10, \
        f"E2E-CSS-MM-03 FAIL: {len(_mm03_tools)} tool calls on a dead end — thrashing. tools={_mm03_tools}"

    _css_e2e_passed += 1
    print(f"PASS E2E-CSS-MM-03  dead end handled: file byte-identical, "
          f"{len(_mm03_tools)} tool calls, no diff, no save\n")
