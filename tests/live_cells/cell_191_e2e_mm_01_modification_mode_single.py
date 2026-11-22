# Ported from fyp.ipynb cell 191 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 188
# LIVE-LLM: costs credits, run manually only
# ─────────────────────────────────────────────────────────────────────────────
# E2E-MM-01  Modification mode — single component, single instance (normal case)
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-MM-01  Modification mode — single component (normal case)")
print("=" * 64)

_mm01 = _stream_html_agent(
    _session_id,
    "Add aria-label='Main navigation' to the navbar.",
    intent="modify",
    target_component="navbar",
    target_instance=1,
    run_name="HTML Agent - MM-01",
)
_html_mm01 = _mm01.get("html_code", "")

assert len(_html_mm01) > 0, \
    "E2E-MM-01 FAIL: html_code empty after modification"
assert _mm01.get("lint_passed") is True, \
    f"E2E-MM-01 FAIL: lint_passed={_mm01.get('lint_passed')}"
# Generation already emits aria-labels (navbar "Primary", the cart icon), so
# a bare substring check would pass even if the modification never applied.
# Assert the exact requested value instead.
assert re.search(r'aria-label=["\']Main navigation["\']', _html_mm01), \
    "E2E-MM-01 FAIL: aria-label='Main navigation' not present in modified HTML"
for _comp in {"product-grid", "product-card", "footer"}:
    # Naming Contract: unique components carry id=<id>, repeated ones
    # class=<className>; semantic tags (e.g. <footer>) also count as present.
    _present = (
        f'id="{_comp}"' in _html_mm01
        or re.search(rf'class="[^"]*\b{_comp}\b[^"]*"', _html_mm01)
        or f"<{_comp}" in _html_mm01
    )
    assert _present, \
        f"E2E-MM-01 FAIL: sibling {_comp} missing after navbar modification"

_disk_html_mm01 = open(_preview_path, encoding="utf-8").read()
assert _disk_html_mm01 == _html_mm01, \
    "E2E-MM-01 FAIL: file on disk does not match html_code after modification"

_e2e_passed += 1
print(f"PASS E2E-MM-01  aria-label applied  {len(_html_mm01)} chars  file updated on disk\n")

# -- No-echo proof (speed-cost ticket 03, part 1) ----------------------
# The orchestrator puts the file in state, so a modify call goes straight
# to extract. The edit landing proves nothing here: it lands the same
# whether or not the model first copied the whole file back.
_ne_tools = list(_mm01.get("tools_called", []))
_ne_store, _ne_read = _ne_tools.count("store_html_code"), _ne_tools.count("read_file")
print(f"[proof] no echo live: store_html_code called {_ne_store}x and read_file "
      f"{_ne_read}x in this modify call. Before ticket 03 every modify call "
      f"opened with 1 read_file + 1 store_html_code of the whole file "
      f"(PO-08 4fb17fbe, html: 7,626 output tokens, 64.2 s).")
assert _ne_store == 0, (
    "E2E-MM-01 FAIL: the model sent the whole file back through store_html_code "
    f"although it was already in state. tools={_ne_tools}")

# -- Fix 5/6 wiring proof (2026-08-31) --------------------------------
# The assertions above prove the EDIT landed. They cannot see whether the
# patch cap and the hunk relocation are wired, because a healthy modify
# exercises neither. Both are checked here instead, so a run that passes
# is a run where both are live in this kernel.
#
# patch_attempts is written by apply_and_lint_html on every apply, failed or
# successful. LangGraph DROPS a write to an undeclared channel silently,
# so an agent built before the field was added does not raise: the key
# simply never arrives, the cap reads 0 forever and can never fire. That
# is PO-08 po01ba89e9, which had to be killed by hand at $3.56.
if "apply_and_lint_html" in _mm01.get("tools_called", []):
    assert "patch_attempts" in _mm01, (
        "E2E-MM-01 FAIL: a diff was applied but patch_attempts never reached "
        "the caller. Either HtmlState does not declare it, or the agent was "
        "built before it was added. Restart the kernel and run every cell "
        "-- until then the patch cap cannot fire.")
    print("[proof] patch cap wired; patch_attempts after this run: "
          f"{_mm01['patch_attempts']}")
else:
    print("[proof] no diff applied this run, so the patch cap was not "
          "exercised")

# Relocation, asked of the loaded function directly. No model call, no cost.
_fx_doc  = "a" + chr(10) + "b" + chr(10) + "UNIQUE-TARGET-LINE" + chr(10) + "c" + chr(10)
_fx_want = "a" + chr(10) + "b" + chr(10) + "CHANGED" + chr(10) + "c" + chr(10)
_fx_hunk = (chr(10).join(["--- original", "+++ revised", "@@ -99,1 +99,1 @@",
                          "-UNIQUE-TARGET-LINE", "+CHANGED"]) + chr(10))
assert _apply_patch(_fx_doc, _fx_hunk) == _fx_want, (
    "E2E-MM-01 FAIL: this kernel still holds the OLD _apply_patch. A hunk with "
    "wrong line numbers fails instead of relocating by its own context, "
    "which is what every patch failure on po01ba89e9 was. Re-run the "
    "_apply_patch cell.")
print("[proof] a misnumbered hunk relocates by its context (Fix 6 live)" + chr(10))



# ─────────────────────────────────────────────────────────────────────────────
# E2E-MM-02  Modification mode — multi-instance edge case
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-MM-02  Modification mode — multi-instance edge case")
print("=" * 64)

_card_count = len(re.findall(r'class="[^"]*\bproduct-card\b[^"]*"', _html_mm01))

if _card_count < 2:
    print(f"SKIP E2E-MM-02: only {_card_count} product-card instance(s) — need ≥ 2\n")
else:
    _mm02      = _stream_html_agent(
        _session_id,
        "Add data-featured='true' to this product card.",
        intent="modify",
        target_component="product-card",
        target_instance=2,
        run_name="HTML Agent - MM-02",
    )
    _html_mm02 = _mm02.get("html_code", "")

    assert len(_html_mm02) > 0, \
        "E2E-MM-02 FAIL: html_code empty"
    assert _mm02.get("lint_passed") is True, \
        f"E2E-MM-02 FAIL: lint_passed={_mm02.get('lint_passed')}"
    _cards_after = len(re.findall(r'class="[^"]*\bproduct-card\b[^"]*"', _html_mm02))
    assert _cards_after == _card_count, \
        f"E2E-MM-02 FAIL: product-card count changed {_card_count} → {_cards_after}"

    # Modify mode, not regenerate: the merged diff tool was used and the
    # code was not re-stored past the Step 0 seed.
    _mm02_tools = _mm02.get("tools_called", [])
    assert "apply_and_lint_html" in _mm02_tools, \
        f"E2E-MM-02 FAIL: no diff applied via apply_and_lint_html. tools={_mm02_tools}"
    assert _mm02_tools.count("store_html_code") == 0, \
        f"E2E-MM-02 FAIL: re-generated instead of diffing. tools={_mm02_tools}"

    _disk_html_mm02 = open(_preview_path, encoding="utf-8").read()
    assert _disk_html_mm02 == _html_mm02, \
        "E2E-MM-02 FAIL: file on disk does not match html_code after instance-2 modification"

    _e2e_passed += 1
    print(f"PASS E2E-MM-02  instance 2 modified  {_card_count} cards preserved\n")


# ─────────────────────────────────────────────────────────────────────────────
# E2E-MM-03  Modification mode — dead end: target selector matches nothing
#
# The stale-spec scenario. Modify mode exists because specs go stale after
# hand edits, so the orchestrator will eventually pass a selector that no
# longer matches. What the agent does then is otherwise UNDEFINED behaviour.
# The two acceptable outcomes are pinned here: stop gracefully, change nothing.
# Uses the FIRST session's page, so a wrongly-written file would be detected.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-MM-03  Modification mode — dead end (selector matches nothing)")
print("=" * 64)

_html_latest = _html_mm02 if _card_count >= 2 else _html_mm01
_disk_before = open(_preview_path, encoding="utf-8").read()

_mm03 = _stream_html_agent(
    _session_id,
    "Change the checkout form's title to 'Secure Checkout'.",
    intent="modify",
    target_component="#checkout-form",        # deliberately absent from the page
    target_instance=1,
    run_name="HTML Agent - MM-03",
)

_disk_after = open(_preview_path, encoding="utf-8").read()
_mm03_tools = _mm03.get("tools_called", [])

# 1. terminated gracefully — reaching this line means no recursion blow-up
# 2. the file on disk is byte-identical
assert _disk_after == _disk_before, \
    "E2E-MM-03 FAIL: the file changed despite the target not existing"
# 3. html_code in state unchanged (absent from updates == never touched, and
#    the prompt's Step 0 seed re-stores the same content, so equality holds)
assert _mm03.get("html_code", _html_latest) == _html_latest, \
    "E2E-MM-03 FAIL: html_code was altered on a dead-end modification"
# 4. trajectory: extract was attempted, but no diff applied and nothing saved
#    (store_html_code IS allowed once — the prompt's Step 0 seed)
assert "extract_component" in _mm03_tools, \
    f"E2E-MM-03 FAIL: extract never attempted. tools={_mm03_tools}"
assert "apply_and_lint_html" not in _mm03_tools, \
    f"E2E-MM-03 FAIL: a diff was applied to a nonexistent target. tools={_mm03_tools}"
assert "save_html_file" not in _mm03_tools, \
    f"E2E-MM-03 FAIL: saved despite a dead-end modification. tools={_mm03_tools}"
# 5. bounded: a dead end must not become a thrash loop
assert len(_mm03_tools) <= 10, \
    f"E2E-MM-03 FAIL: {len(_mm03_tools)} tool calls on a dead end — thrashing. tools={_mm03_tools}"
_e2e_passed += 1
print(f"PASS E2E-MM-03  dead end handled: disk byte-identical, state untouched, "
      f"{len(_mm03_tools)} tool calls, no diff, no save\n")


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
# -----------------------------------------------------------------------------
# E2E-MM-04  Modification mode - BATCH: two components in one agent session
#
# The local proof for A (2026-08-31). CSS and JS have had this case since
# 2026-08-02; HTML could not, because extract_component and apply_and_lint_html
# took no arguments and a batched session had no way to name its second target.
#
# What this catches that PO-08 cannot catch cheaply: PO-08 costs ~$2.7 and
# fifteen minutes. This is two model calls. Run it BEFORE the full system run.
# -----------------------------------------------------------------------------
print("=" * 64)
print("E2E-MM-04  Modification mode - batch (two components, one session)")
print("=" * 64)

_html_batch_targets = ["#navbar", "#footer"]
if not os.path.exists(_preview_path):
    print("SKIP E2E-MM-04: generation produced no HTML file to modify\n")
else:
    _before4 = open(_preview_path, encoding="utf-8").read()
    _mm04 = _stream_html_agent(
        _session_id,
        "Make two separate changes. First, add aria-label=\"Primary\" to the "
        "navbar element. Second, add aria-label=\"Site footer\" to the footer "
        "element.",
        intent="modify",
        target_components=_html_batch_targets,
        run_name="HTML Agent - MM-04",
    )
    _mod4       = _mm04.get("html_code", "")
    _mm04_names = _mm04.get("tools_called", [])
    _mm04_full  = _mm04.get("tool_calls_full", [])

    assert _mm04.get("lint_passed") is True, \
        f"E2E-MM-04 FAIL: lint_passed={_mm04.get('lint_passed')}"
    assert _mod4 and _mod4 != _before4, \
        "E2E-MM-04 FAIL: HTML unchanged - the batch never applied"

    # BATCH PROOF 1 - ONE extract_component call carrying the WHOLE list, and one
    # apply_and_lint_html call carrying one diff per component. Read from the ARGUMENTS, not
    # from a call count: a count cannot tell "twice on the same target" from
    # "once on each", and after 2026-08-31 the point IS that the count is 1.
    _ex_calls = [_tc for _tc in _mm04_full if _tc["name"] == "extract_component"]
    _ap_calls = [_tc for _tc in _mm04_full if _tc["name"] == "apply_and_lint_html"]
    assert len(_ex_calls) == 1, (
        f"E2E-MM-04 FAIL: extract_component was called {len(_ex_calls)}x, expected 1. "
        f"One call takes the whole list. More than one means the prompt is still "
        f"looping per component; zero means it never extracted. (A batch is also "
        f"refused when two targets overlap, but these two are disjoint.)")
    _ex_args = [str(_a) for _a in (_ex_calls[0]["args"].get("components") or [])]
    _ex_bare = {_a.lstrip("#.").strip() for _a in _ex_args}
    for _t in _html_batch_targets:
        assert _t.lstrip("#.").strip() in _ex_bare, (
            f"E2E-MM-04 FAIL: {_t} was not in the extracted batch. "
            f"components={_ex_args}")
    assert len(_ap_calls) >= 1, f"E2E-MM-04 FAIL: nothing was applied."
    _ap_named = [str(_d.get("component", "")) for _c in _ap_calls
                 for _d in (_c["args"].get("diffs") or [])]
    _ap_bare = {_a.lstrip("#.").strip() for _a in _ap_named}
    assert _ap_named, (
        f"E2E-MM-04 FAIL: the apply was not batched -- `diffs` was empty, "
        f"or the model used the single-diff argument instead.")
    # NOT "every target is named". When two targets share one block the
    # extract merges them and asks for a SINGLE diff, so only the keeper
    # appears here -- and that is the correct, cheaper outcome. Demanding
    # both names would fail a batch that worked.
    _named_ok = [_t for _t in _html_batch_targets
                 if _t.lstrip("#.").strip() in _ap_bare]
    assert _named_ok, (
        f"E2E-MM-04 FAIL: no requested target was named in any diff. "
        f"named={_ap_named}, wanted={_html_batch_targets}")
    _merged = len(_html_batch_targets) - len(_named_ok)

    # BATCH PROOF 2 - saved ONCE at the end, not once per component. A per-
    # component save is the old one-call-per-component shape wearing a batch's
    # clothes, and it costs the same.
    _saves = _mm04_names.count("save_html_file")
    assert _saves == 1, \
        (f"E2E-MM-04 FAIL: save_html_file called {_saves}x, expected exactly 1 "
         f"- a batch saves once at the end. tools={_mm04_names}")

    # No collateral damage: the second edit must not undo the first.
    assert 'aria-label="Primary"' in _mod4 and 'aria-label="Site footer"' in _mod4, \
        "E2E-MM-04 FAIL: one edit of the batch was lost"
    assert open(_preview_path, encoding="utf-8").read() == _mod4, \
        "E2E-MM-04 FAIL: disk != state after the batch"

    _e2e_passed += 1
    print(f"PASS E2E-MM-04  batch of {len(_html_batch_targets)} applied  "
          f"both extracted  saved once  both edits intact  disk == state\n")

    # -- the numbers, beside the numbers they replaced ----------------------
    print(f"[proof] one-pass modify live: {len(_html_batch_targets)} component(s) fixed "
          f"with {len(_ex_calls)} extract_component call and {len(_ap_calls)} "
          f"apply_and_lint_html call(s), {_merged} merged, {_mm04_names.count('save_html_file')} save, "
          f"{len(_mm04_names)} tool calls in the whole session. One at a time "
          f"INSIDE the session was {2 * len(_html_batch_targets)} calls and "
          f"{len(_html_batch_targets)} html-validate runs; one component per SESSION was 8 "
          f"sessions on PO-08 po018f8158, 442,689 input tokens for HTML alone.")
    print(f"[proof] the batch named itself explicitly: extract components="
          f"{_ex_args}, apply diffs for {_ap_named}")


print("(MM-02 auto-skips itself when the generated HTML has < 2 product-cards)")
print(f"E2E HTML Agent: {_e2e_passed} PASSED")
