# Ported from fyp.ipynb cell 218 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Needs: cell 217 (it defines _p_anl).
# Unit tests: batched JS modification (2026-08-31)
# Subprocess mocked, so this runs offline. Mirror of the batched CSS suite.
_bj_passed = 0

def _bj_ok(tag, msg):
    global _bj_passed
    _bj_passed += 1
    print(f"PASS {tag} - {msg}")

# alpha and beta are referenced by the SAME handler, so both resolve to one
# paragraph. That is the overlap the guard exists for.
_BJ_JS = (
    'document.addEventListener("DOMContentLoaded", () => {\n'
    '  const a = document.querySelector(".alpha");\n'
    '  const b = document.querySelector(".beta");\n'
    '  a.addEventListener("click", () => console.log("one"));\n'
    '});\n\n'
    'document.addEventListener("DOMContentLoaded", () => {\n'
    '  const g = document.querySelector(".gamma");\n'
    '  g.addEventListener("click", () => console.log("two"));\n'
    '});\n\n'
    'document.addEventListener("DOMContentLoaded", () => {\n'
    '  const d = document.querySelector(".delta");\n'
    '  d.addEventListener("click", () => console.log("three"));\n'
    '});'
)
assert _overlapping_pair([
    (".alpha", _js_resolve_component(_BJ_JS, ".alpha", None)[1]),
    (".beta",  _js_resolve_component(_BJ_JS, ".beta",  None)[1])]) is not None, \
    "fixture: .alpha and .beta must resolve to the same paragraph"

def _bj_rt(js=_BJ_JS, **extra):
    st = {"js_code": js, "target_component": ".gamma",
          "lint_attempts": 0, "lint_escalated": False, "patch_attempts": 0}
    st.update(extra)
    return SimpleNamespace(state=st, tool_call_id="bj-1")

def _bj_diff(sel, old, new, js=_BJ_JS):
    blk = _join_blocks(_js_blocks_for_component(js, sel))
    lines = blk.splitlines()
    line = next(l for l in lines if old in l)
    ix = lines.index(line) + 1
    return (f"--- original\n+++ revised\n@@ -{ix},1 +{ix},1 @@\n"
            f"-{line}\n+{line.replace(old, new)}")

# ── extract ────────────────────────────────────────────────────────────────
_r = extract_js_component.func(_bj_rt(), components=[".gamma", ".delta"]).update
_m = _r["messages"][0].content
assert "WebForge component 1 of 2: .gamma" in _m and "WebForge component 2 of 2: .delta" in _m, _m
assert '"two"' in _m and '"three"' in _m, _m
assert _r["lint_attempts"] == 0 and _r["patch_attempts"] == 0, _r
_bj_ok("BJ-1", "two disjoint components come back in one message, separated and labelled")

_one  = extract_js_component.func(_bj_rt(), components=[".gamma"]).update["messages"][0].content
_same = extract_js_component.func(_bj_rt(), component=".gamma").update["messages"][0].content
assert _one == _same and "=====" not in _one, (_one, _same)
_bj_ok("BJ-2", "a one-entry batch returns exactly what the single call returns")

# This is the case that failed E2E-JS-MM-04 twice on 2026-08-31. The JS agent
# writes the whole page as one IIFE, so ANY two components share a paragraph.
# Refusing meant every JS batch was refused and batching never engaged.
_m = extract_js_component.func(_bj_rt(), components=[".alpha", ".beta"]).update["messages"][0].content
assert "Refusing" not in _m, _m
assert _m.count("WebForge component") == 0, (
    f"a merge leaves ONE item, and _join_components returns one item "
    f"untouched -- a separator here would break the byte-identical text "
    f"a single-component call depends on:\n{_m}")
assert ".beta" in _m, "the note must name what the block also covers"
assert "SINGLE diff for '.alpha'" in _m, _m
_bj_ok("BJ-3", "two components sharing one handler are served once, with the other named")

_m = extract_js_component.func(_bj_rt(), components=[".beta", ".alpha"]).update["messages"][0].content
assert "SINGLE diff for '.beta'" in _m, _m
_bj_ok("BJ-4", "the first named target keeps the label when a block is shared")

_m = extract_js_component.func(_bj_rt(), components=[".gamma", ".gamma", ".delta"]).update["messages"][0].content
assert "named twice" in _m and _m.count("WebForge component") == 2, _m
_bj_ok("BJ-5", "a component named twice is dropped once and the drop is reported")

_m = extract_js_component.func(_bj_rt(), components=[".gamma", ".nope", ".delta"]).update["messages"][0].content
assert "No code found" in _m and ".nope" in _m and _m.count("WebForge component") == 2, _m
_bj_ok("BJ-6", "one stale name does not cost the whole batch")

# ── apply ──────────────────────────────────────────────────────────────────
with _p_anl("subprocess.run") as _m_:
    _m_.return_value = _M_anl(returncode=0, stdout=_ANL_CLEAN, stderr="")
    _r = apply_and_lint_js.func(runtime=_bj_rt(), diffs=[
        {"component": ".gamma", "diff_output": _bj_diff(".gamma", '"two"', '"TWO"')},
        {"component": ".delta", "diff_output": _bj_diff(".delta", '"three"', '"THREE"')},
    ]).update
    _n_lint = _m_.call_count
_m = _r["messages"][0].content
assert "Applied 2 of 2 diff(s) in one call." in _m, _m
assert '"TWO"' in _r["js_code"] and '"THREE"' in _r["js_code"], _r["js_code"]
assert _r["patch_attempts"] == 0 and _r["lint_passed"] is True, _r
assert _n_lint == 1, f"expected 1 linter run for the batch, got {_n_lint}"
_bj_ok("BJ-7", "two diffs land in one call and ESLint runs exactly once")

_stale = ("--- original\n+++ revised\n@@ -1,1 +1,1 @@\n"
          '-  THIS LINE IS NOT IN THE SCRIPT;\n+  const x = 1;\n')
with _p_anl("subprocess.run") as _m_:
    _m_.return_value = _M_anl(returncode=0, stdout=_ANL_CLEAN, stderr="")
    _r = apply_and_lint_js.func(runtime=_bj_rt(), diffs=[
        {"component": ".gamma", "diff_output": _bj_diff(".gamma", '"two"', '"TWO"')},
        {"component": ".delta", "diff_output": _stale},
    ]).update
_m = _r["messages"][0].content
assert "Applied 1 of 2 diff(s) in one call." in _m and "FAILED" in _m and ".delta" in _m, _m
assert '"TWO"' in _r["js_code"], "the diff that applied must be KEPT"
assert _r["patch_attempts"] == 1, _r
assert "Current block for '.delta'" in _m, _m
_bj_ok("BJ-8", "a failed diff keeps the ones that landed, is named, and counts once")

_r = apply_and_lint_js.func(runtime=_bj_rt(), diffs=[
    {"component": ".delta", "diff_output": _stale}]).update
assert "js_code" not in _r, "nothing applied, so nothing may be committed"
assert _r["patch_attempts"] == 1, _r
_bj_ok("BJ-9", "a batch where nothing applies commits nothing and counts an attempt")

with _p_anl("subprocess.run") as _m_:
    _m_.return_value = _M_anl(returncode=0, stdout=_ANL_CLEAN, stderr="")
    _r = apply_and_lint_js.func(_bj_diff(".gamma", '"two"', '"TWO"'), _bj_rt()).update
assert "Diff applied." in _r["messages"][0].content and '"TWO"' in _r["js_code"]
_bj_ok("BJ-10", "the single-diff call still behaves exactly as before")

# A single-component ask inside a batched call returns the WHOLE batch. This is
# the case E2E-JS-MM-04 caught live: the JS agent extracted twice.
_r = extract_js_component.func(
    _bj_rt(target_components=[".gamma", ".delta"]), component=".gamma").update
_m = _r["messages"][0].content
assert "WebForge component 1 of 2: .gamma" in _m and ".delta" in _m, _m
assert "You asked for ONE component" in _m and "Do NOT call this tool again" in _m, _m
assert "apply_and_lint_js" in _m, _m
_bj_ok("BJ-11", "asking for one component in a batched call returns all of them")

_m = extract_js_component.func(
    _bj_rt(target_components=[".gamma"]), component=".gamma").update["messages"][0].content
assert "=====" not in _m and '"two"' in _m and '"three"' not in _m, _m
_bj_ok("BJ-12", "a one-target call is not upgraded and returns the bare block")

print("=" * 64)
print(f"batched JS modification: {_bj_passed}/12 PASSED (no model calls)")
