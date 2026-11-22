# Ported from fyp.ipynb cell 217 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: apply_and_lint_js (subprocess mocked — offline)
# apply_and_lint_js merges store_js_diff + run_eslint into one call, and hands
# the current block back on any failure so the model never re-extracts.
from types import SimpleNamespace
from unittest.mock import patch as _p_anl, MagicMock as _M_anl

_ANL_JS = (
    'document.addEventListener("DOMContentLoaded", () => {\n'
    '  const btn = document.querySelector(\'[data-component="add-to-cart-btn"]\');\n'
    '  btn.addEventListener("click", () => console.log("old message"));\n'
    '});\n\n'
    'document.addEventListener("DOMContentLoaded", () => {\n'
    '  const nav = document.querySelector(\'[data-component="navbar"]\');\n'
    '  nav.addEventListener("click", () => {});\n'
    '});'
)
_ANL_BLK   = _join_blocks(_js_blocks_for_component(_ANL_JS, "add-to-cart-btn"))
_ANL_LINES = _ANL_BLK.splitlines()
_ANL_OLD   = next(l for l in _ANL_LINES if "old message" in l)
_ANL_NEW   = _ANL_OLD.replace("old message", "new message")
_ANL_IX    = _ANL_LINES.index(_ANL_OLD) + 1
_ANL_DIFF  = (f"--- original\n+++ revised\n@@ -{_ANL_IX},1 +{_ANL_IX},1 @@\n"
              f"-{_ANL_OLD}\n+{_ANL_NEW}")

_ANL_CLEAN = '[{"filePath":"x.js","messages":[],"errorCount":0,"warningCount":0}]'
_ANL_ERRJ  = ('[{"filePath":"x.js","messages":['
              '{"ruleId":"no-undef","severity":2,"message":"foo is not defined","line":1,"column":1}],'
              '"errorCount":1,"warningCount":0}]')

_mk_anl = lambda **st: SimpleNamespace(state=st, tool_call_id="anl-1")

# Case 1 [NORMAL] valid diff + clean lint: applied AND linted in one call
with _p_anl("subprocess.run") as _m:
    _m.return_value = _M_anl(returncode=0, stdout=_ANL_CLEAN, stderr="")
    r1 = apply_and_lint_js.func(_ANL_DIFF, _mk_anl(js_code=_ANL_JS, target_component="add-to-cart-btn"))
assert r1.update["lint_passed"] is True
assert "new message" in r1.update["js_code"] and "old message" not in r1.update["js_code"]
assert "navbar" in r1.update["js_code"], "untargeted block must survive"
_c1 = r1.update["messages"][0].content
assert "Diff applied." in _c1 and "No issues found." in _c1
print("[Case 1 · NORMAL] apply + clean lint in one call: js updated, verdict attached.")
print(_c1)
print("PASS\n")

# Case 2 [GUARD] bad diff: patch fails, js_code untouched, current block returned
_BAD_ANL = ("--- original\n+++ revised\n@@ -1,1 +1,1 @@\n"
            "-  btn.addEventListener('click', () => console.log('WRONG'));\n"
            "+  btn.addEventListener('click', () => console.log('x'));")
r2 = apply_and_lint_js.func(_BAD_ANL, _mk_anl(js_code=_ANL_JS, target_component="add-to-cart-btn"))
assert "js_code" not in r2.update, "a failed patch must not mutate js_code"
_c2 = r2.update["messages"][0].content
assert "Patch failed" in _c2 and "old message" in _c2, "current block must be handed back"
print("[Case 2 · GUARD] bad diff: state unchanged, current block returned (no re-extract).")
print("PASS\n")

# Case 3 [NORMAL] valid diff + lint ERROR: applied, errors reported, NEW block returned
with _p_anl("subprocess.run") as _m:
    _m.return_value = _M_anl(returncode=1, stdout=_ANL_ERRJ, stderr="")
    r3 = apply_and_lint_js.func(_ANL_DIFF, _mk_anl(js_code=_ANL_JS, target_component="add-to-cart-btn"))
assert r3.update["lint_passed"] is False
assert "new message" in r3.update["js_code"], "the diff still applies before linting"
_c3 = r3.update["messages"][0].content
assert "Diff applied." in _c3 and "Found 1 error(s):" in _c3
assert "Current block AFTER this patch" in _c3 and "new message" in _c3
print("[Case 3 · NORMAL] apply succeeds but lint fails: errors + post-patch block returned.")
print("PASS\n")

# Case 4 [EDGE] empty js_code
r4 = apply_and_lint_js.func(_ANL_DIFF, _mk_anl(js_code="", target_component="add-to-cart-btn"))
assert "js_code" not in r4.update and "empty" in r4.update["messages"][0].content.lower()
print("[Case 4 · EDGE] empty js_code handled gracefully.")
print("PASS\n")

# Case 5 [EDGE] component not found
r5 = apply_and_lint_js.func(_ANL_DIFF, _mk_anl(js_code=_ANL_JS, target_component="footer"))
assert "js_code" not in r5.update and "no js block found" in r5.update["messages"][0].content.lower()
print("[Case 5 · EDGE] unknown component reported, not crashed.")
print("PASS\n")

# Case 6 [GUARD] lint cap already reached: apply happens, lint refuses, no block re-offered
with _p_anl("subprocess.run") as _m:
    _m.return_value = _M_anl(returncode=0, stdout=_ANL_CLEAN, stderr="")
    r6 = apply_and_lint_js.func(_ANL_DIFF, _mk_anl(
        js_code=_ANL_JS, target_component="add-to-cart-btn", lint_escalated=True))
_c6 = r6.update["messages"][0].content
assert "[LINT CAP REACHED]" in _c6, "escalation must refuse further linting"
assert "Current block AFTER this patch" not in _c6, "the cap message must stop the loop, not invite a re-diff"
print("[Case 6 · GUARD] with the cap already reached, lint is refused and the loop is told to stop.")
print("PASS\n")

# Case 7 [NORMAL] explicit component= parameter (batch-ready) overrides empty state target
with _p_anl("subprocess.run") as _m:
    _m.return_value = _M_anl(returncode=0, stdout=_ANL_CLEAN, stderr="")
    r7 = apply_and_lint_js.func(_ANL_DIFF, _mk_anl(js_code=_ANL_JS, target_component=""),
                                component="add-to-cart-btn")
assert r7.update["lint_passed"] is True and "new message" in r7.update["js_code"]
print("[Case 7 · NORMAL] explicit component= parameter resolves the block (enables batching).")
print("PASS\n")

# Case 8 [GUARD] an empty call is refused, not applied (13b71045: diffs=[] was "applied")
for _empty_kw in ({"diffs": []}, {"diffs": None}):
    r8 = apply_and_lint_js.func("", _mk_anl(js_code=_ANL_JS), **_empty_kw)
    assert "No diff supplied" in r8.update["messages"][0].content, r8.update["messages"][0].content
    assert "js_code" not in r8.update and "lint_passed" not in r8.update, "empty call must change nothing"
print("[Case 8 · GUARD] diffs=[] with a blank diff_output is refused; nothing applied, nothing linted.")
print("PASS\n")

print("All 8 apply_and_lint_js cases passed.")
