# Ported from fyp.ipynb cell 274 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: apply_and_lint_css (subprocess mocked — offline)
# Mirror of the apply_and_lint_js suite: merges store_css_diff + run_stylelint
# into one call, handing the current block back on any failure (no re-extract).
from types import SimpleNamespace
from unittest.mock import patch as _p_anlc, MagicMock as _M_anlc

_ANLC_CSS = (
    '[data-component="add-to-cart-btn"] {\n'
    '  background-color: blue;\n'
    '  color: white;\n'
    '}\n\n'
    '[data-component="navbar"] {\n'
    '  background: #1a73e8;\n'
    '}'
)
_ANLC_BLK   = _join_blocks(_extract_css_blocks(_ANLC_CSS, "add-to-cart-btn"))
_ANLC_LINES = _ANLC_BLK.splitlines()
_ANLC_OLD   = next(l for l in _ANLC_LINES if "background-color: blue" in l)
_ANLC_NEW   = _ANLC_OLD.replace("blue", "#e05c5c")
_ANLC_IX    = _ANLC_LINES.index(_ANLC_OLD) + 1
_ANLC_DIFF  = (f"--- original\n+++ revised\n@@ -{_ANLC_IX},1 +{_ANLC_IX},1 @@\n"
               f"-{_ANLC_OLD}\n+{_ANLC_NEW}")

_ANLC_CLEAN = '[{"source":"x.css","warnings":[],"parseErrors":[]}]'
_ANLC_ERRJ  = ('[{"source":"x.css","warnings":['
               '{"line":2,"column":3,"rule":"unit-no-unknown","text":"Unexpected unknown unit"}],'
               '"parseErrors":[]}]')

_mk_anlc = lambda **st: SimpleNamespace(state=st, tool_call_id="anlc-1")

# Case 1 [NORMAL] valid diff + clean lint: applied AND linted in one call
with _p_anlc("subprocess.run") as _m:
    _m.return_value = _M_anlc(returncode=0, stdout=_ANLC_CLEAN, stderr="")
    r1 = apply_and_lint_css.func(_ANLC_DIFF, _mk_anlc(css_code=_ANLC_CSS, target_component="add-to-cart-btn"))
assert r1.update["lint_passed"] is True
assert "#e05c5c" in r1.update["css_code"] and "background-color: blue" not in r1.update["css_code"]
assert 'data-component="navbar"' in r1.update["css_code"], "untargeted block must survive"
_c1 = r1.update["messages"][0].content
assert "Diff applied." in _c1 and "No issues found." in _c1
print("[Case 1 · NORMAL] apply + clean lint in one call: css updated, verdict attached.")
print(_c1)
print("PASS\n")

# Case 2 [GUARD] bad diff: patch fails, css_code untouched, current block returned
_BAD_ANLC = ("--- original\n+++ revised\n@@ -2,1 +2,1 @@\n"
             "-  background-color: WRONG;\n"
             "+  background-color: red;")
r2 = apply_and_lint_css.func(_BAD_ANLC, _mk_anlc(css_code=_ANLC_CSS, target_component="add-to-cart-btn"))
assert "css_code" not in r2.update, "a failed patch must not mutate css_code"
_c2 = r2.update["messages"][0].content
assert "Patch failed" in _c2 and "background-color: blue" in _c2, "current block must be handed back"
print("[Case 2 · GUARD] bad diff: state unchanged, current block returned (no re-extract).")
print("PASS\n")

# Case 3 [NORMAL] valid diff + lint problem: applied, problems reported, NEW block returned
with _p_anlc("subprocess.run") as _m:
    _m.return_value = _M_anlc(returncode=2, stdout=_ANLC_ERRJ, stderr="")
    r3 = apply_and_lint_css.func(_ANLC_DIFF, _mk_anlc(css_code=_ANLC_CSS, target_component="add-to-cart-btn"))
assert r3.update["lint_passed"] is False
assert "#e05c5c" in r3.update["css_code"], "the diff still applies before linting"
_c3 = r3.update["messages"][0].content
assert "Diff applied." in _c3 and "Found 1 problem(s):" in _c3
assert "Current block AFTER this patch" in _c3 and "#e05c5c" in _c3
print("[Case 3 · NORMAL] apply succeeds but lint fails: problems + post-patch block returned.")
print("PASS\n")

# Case 4 [EDGE] empty css_code
r4 = apply_and_lint_css.func(_ANLC_DIFF, _mk_anlc(css_code="", target_component="add-to-cart-btn"))
assert "css_code" not in r4.update and "empty" in r4.update["messages"][0].content.lower()
print("[Case 4 · EDGE] empty css_code handled gracefully.")
print("PASS\n")

# Case 5 [EDGE] component not found
r5 = apply_and_lint_css.func(_ANLC_DIFF, _mk_anlc(css_code=_ANLC_CSS, target_component="footer"))
assert "css_code" not in r5.update and "no css block found" in r5.update["messages"][0].content.lower()
print("[Case 5 · EDGE] unknown component reported, not crashed.")
print("PASS\n")

# Case 6 [GUARD] lint cap already reached: apply happens, lint refuses, no block re-offered
with _p_anlc("subprocess.run") as _m:
    _m.return_value = _M_anlc(returncode=0, stdout=_ANLC_CLEAN, stderr="")
    r6 = apply_and_lint_css.func(_ANLC_DIFF, _mk_anlc(
        css_code=_ANLC_CSS, target_component="add-to-cart-btn", lint_escalated=True))
_c6 = r6.update["messages"][0].content
assert "[LINT CAP REACHED]" in _c6, "escalation must refuse further linting"
assert "Current block AFTER this patch" not in _c6, "the cap message must stop the loop, not invite a re-diff"
print("[Case 6 · GUARD] with the cap already reached, lint is refused and the loop is told to stop.")
print("PASS\n")

# Case 7 [NORMAL] explicit component= parameter (batch-ready) overrides empty state target
with _p_anlc("subprocess.run") as _m:
    _m.return_value = _M_anlc(returncode=0, stdout=_ANLC_CLEAN, stderr="")
    r7 = apply_and_lint_css.func(_ANLC_DIFF, _mk_anlc(css_code=_ANLC_CSS, target_component=""),
                                 component="add-to-cart-btn")
assert r7.update["lint_passed"] is True and "#e05c5c" in r7.update["css_code"]
print("[Case 7 · NORMAL] explicit component= parameter resolves the block (enables batching).")
print("PASS\n")

# Case 8 [GUARD] an empty call is refused, not applied (13b71045: diffs=[] was "applied")
for _empty_kw in ({"diffs": []}, {"diffs": None}):
    r8 = apply_and_lint_css.func("", _mk_anlc(css_code=_ANLC_CSS), **_empty_kw)
    assert "No diff supplied" in r8.update["messages"][0].content, r8.update["messages"][0].content
    assert "css_code" not in r8.update and "lint_passed" not in r8.update, "empty call must change nothing"
print("[Case 8 · GUARD] diffs=[] with a blank diff_output is refused; nothing applied, nothing linted.")
print("PASS\n")

print("All 8 apply_and_lint_css cases passed.")
