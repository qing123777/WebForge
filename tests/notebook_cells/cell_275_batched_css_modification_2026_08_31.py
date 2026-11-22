# Ported from fyp.ipynb cell 275 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Needs: cell 274 (it defines _p_anlc).
# Unit tests: batched CSS modification (2026-08-31)
# Subprocess mocked, so this runs offline.
#
# What is being proved: five components used to cost five extracts, five applies
# and five stylelint runs. Batching makes it one of each. The risk that buys is
# a diff written against text an earlier diff already replaced, so most of these
# cases are about which batches are REFUSED and what survives a partial failure.
_bc_passed = 0

def _bc_ok(tag, msg):
    global _bc_passed
    _bc_passed += 1
    print(f"PASS {tag} - {msg}")

# .card and .tile share ONE rule block. That is the overlap the guard exists for.
_BC_CSS = (
    '.card, .tile {\n  padding: 4px;\n}\n\n'
    '.price {\n  color: red;\n}\n\n'
    '.badge {\n  color: blue;\n}\n'
)
assert _overlapping_pair([
    (".card", _extract_css_block_spans(_BC_CSS, ".card")),
    (".tile", _extract_css_block_spans(_BC_CSS, ".tile"))]) is not None, \
    "fixture: .card and .tile must resolve to the same block"

def _bc_rt(css=_BC_CSS, **extra):
    st = {"css_code": css, "target_component": ".price",
          "lint_attempts": 0, "lint_escalated": False, "patch_attempts": 0}
    st.update(extra)
    return SimpleNamespace(state=st, tool_call_id="bc-1")

def _bc_diff(sel, old, new, css=_BC_CSS):
    blk = _join_blocks(_extract_css_blocks(css, sel))
    lines = blk.splitlines()
    line = next(l for l in lines if old in l)
    ix = lines.index(line) + 1
    return (f"--- original\n+++ revised\n@@ -{ix},1 +{ix},1 @@\n"
            f"-{line}\n+{line.replace(old, new)}")

# ── extract ────────────────────────────────────────────────────────────────
_r = extract_css_component.func(_bc_rt(), components=[".price", ".badge"]).update
_m = _r["messages"][0].content
assert "WebForge component 1 of 2: .price" in _m and "WebForge component 2 of 2: .badge" in _m, _m
assert "color: red" in _m and "color: blue" in _m, _m
assert _r["lint_attempts"] == 0 and _r["patch_attempts"] == 0, _r
_bc_ok("BC-1", "two disjoint components come back in one message, separated and labelled")

# A one-entry list must be byte-identical to the old single call: the separator
# would otherwise become context the model copies into its hunk.
_one  = extract_css_component.func(_bc_rt(), components=[".price"]).update["messages"][0].content
_same = extract_css_component.func(_bc_rt(), component=".price").update["messages"][0].content
assert _one == _same and "=====" not in _one, (_one, _same)
_bc_ok("BC-2", "a one-entry batch returns exactly what the single call returns")

# A grouped selector belongs to both components, so `.card, .tile { ... }` is
# ONE block. Two diffs against it cannot both apply, so it is served once and
# the note says which other component it covers.
_m = extract_css_component.func(_bc_rt(), components=[".card", ".tile"]).update["messages"][0].content
assert "Refusing" not in _m, _m
assert _m.count("WebForge component") == 0, (
    f"a merge leaves ONE item, and _join_components returns one item "
    f"untouched -- a separator here would break the byte-identical text "
    f"a single-component call depends on:\n{_m}")
assert ".tile" in _m, "the note must name what the block also covers"
assert "SINGLE diff for '.card'" in _m, _m
_bc_ok("BC-3", "two components sharing a grouped selector are served once, with the other named")

# The FIRST named target keeps the label, so the model can predict which name to
# pass back without re-reading the note.
_m = extract_css_component.func(_bc_rt(), components=[".tile", ".card"]).update["messages"][0].content
assert "SINGLE diff for '.tile'" in _m, _m
_bc_ok("BC-4", "the first named target keeps the label when a block is shared")

_m = extract_css_component.func(_bc_rt(), components=[".price", ".price", ".badge"]).update["messages"][0].content
assert "named twice" in _m and _m.count("WebForge component") == 2, _m
_bc_ok("BC-5", "a component named twice is dropped once and the drop is reported")

_m = extract_css_component.func(_bc_rt(), components=[".price", ".nope", ".badge"]).update["messages"][0].content
assert "No blocks found" in _m and ".nope" in _m and _m.count("WebForge component") == 2, _m
_bc_ok("BC-6", "one stale name does not cost the whole batch")

# ── apply ──────────────────────────────────────────────────────────────────
with _p_anlc("subprocess.run") as _m_:
    _m_.return_value = _M_anlc(returncode=0, stdout=_ANLC_CLEAN, stderr="")
    _r = apply_and_lint_css.func(runtime=_bc_rt(), diffs=[
        {"component": ".price", "diff_output": _bc_diff(".price", "color: red", "color: green")},
        {"component": ".badge", "diff_output": _bc_diff(".badge", "color: blue", "color: teal")},
    ]).update
    _n_lint = _m_.call_count
_m = _r["messages"][0].content
assert "Applied 2 of 2 diff(s) in one call." in _m, _m
assert "color: green" in _r["css_code"] and "color: teal" in _r["css_code"], _r["css_code"]
assert _r["patch_attempts"] == 0 and _r["lint_passed"] is True, _r
# ONE stylelint subprocess for two components. That is the round trip saved.
assert _n_lint == 1, f"expected 1 linter run for the batch, got {_n_lint}"
_bc_ok("BC-7", "two diffs land in one call and stylelint runs exactly once")

# PARTIAL COMMIT: all-or-nothing would discard a good fix because a later diff
# miscounted its line numbers, and the model would rewrite both.
_stale = ("--- original\n+++ revised\n@@ -1,1 +1,1 @@\n"
          "-  color: THIS IS NOT IN THE FILE;\n+  color: teal;\n")
with _p_anlc("subprocess.run") as _m_:
    _m_.return_value = _M_anlc(returncode=0, stdout=_ANLC_CLEAN, stderr="")
    _r = apply_and_lint_css.func(runtime=_bc_rt(), diffs=[
        {"component": ".price", "diff_output": _bc_diff(".price", "color: red", "color: green")},
        {"component": ".badge", "diff_output": _stale},
    ]).update
_m = _r["messages"][0].content
assert "Applied 1 of 2 diff(s) in one call." in _m and "FAILED" in _m and ".badge" in _m, _m
assert "color: green" in _r["css_code"], "the diff that applied must be KEPT"
assert _r["patch_attempts"] == 1, _r
assert "Current block for '.badge'" in _m, _m
_bc_ok("BC-8", "a failed diff keeps the ones that landed, is named, and counts once")

_r = apply_and_lint_css.func(runtime=_bc_rt(), diffs=[
    {"component": ".badge", "diff_output": _stale}]).update
assert "css_code" not in _r, "nothing applied, so nothing may be committed"
assert _r["patch_attempts"] == 1, _r
_bc_ok("BC-9", "a batch where nothing applies commits nothing and counts an attempt")

with _p_anlc("subprocess.run") as _m_:
    _m_.return_value = _M_anlc(returncode=0, stdout=_ANLC_CLEAN, stderr="")
    _r = apply_and_lint_css.func(
        _bc_diff(".price", "color: red", "color: green"), _bc_rt()).update
assert "Diff applied." in _r["messages"][0].content and "color: green" in _r["css_code"]
_bc_ok("BC-10", "the single-diff call still behaves exactly as before")

# A single-component ask inside a batched call returns the WHOLE batch.
_r = extract_css_component.func(
    _bc_rt(target_components=[".price", ".badge"]), component=".price").update
_m = _r["messages"][0].content
assert "WebForge component 1 of 2: .price" in _m and ".badge" in _m, _m
assert "You asked for ONE component" in _m and "Do NOT call this tool again" in _m, _m
assert "apply_and_lint_css" in _m, _m
_bc_ok("BC-11", "asking for one component in a batched call returns all of them")

_m = extract_css_component.func(
    _bc_rt(target_components=[".price"]), component=".price").update["messages"][0].content
assert "=====" not in _m and "color: red" in _m and "color: blue" not in _m, _m
_bc_ok("BC-12", "a one-target call is not upgraded and returns the bare block")

print("=" * 64)
print(f"batched CSS modification: {_bc_passed}/12 PASSED (no model calls)")
