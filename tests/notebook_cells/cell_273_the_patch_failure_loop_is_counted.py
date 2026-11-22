# Ported from fyp.ipynb cell 273 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the patch-failure loop is counted and capped (2026-08-30).
# REGRESSION for PO-08 po01ba89e9. A LINT failure has always been counted and
# capped; a PATCH failure -- the diff did not apply -- handed the block back and
# counted NOTHING. Only recursion_limit ever stopped it, and raising that for
# batched correction removed the accidental brake: the run spun until it was
# killed by hand at 2,185,845 tokens and $3.56. The failures were the
# line-numbered diff miscounting ("Hunk at original line 16 does not match
# current content at line 16").
from tests.package_source import package_cells, package_notebook  # Ticket 05: the package source, not the frozen notebook
_pc_passed = 0


class _PcRt:
    def __init__(self, attempts=0):
        self.state = {"patch_attempts": attempts}
        self.tool_call_id = "pc-1"


# Below the cap: counted, and the message says which attempt this is so the
# model can see it is running out of room.
_r1 = _patch_failure(_PcRt(0), "Patch failed: Hunk at original line 16 ...")
assert _r1.update["patch_attempts"] == 1, _r1.update
_m1 = _r1.update["messages"][0].content
assert "Patch failed" in _m1 and f"[Patch attempt 1/{_PATCH_ATTEMPT_CAP}]" in _m1, _m1
assert "[PATCH CAP REACHED]" not in _m1, "PC-1 FAIL: capped on the first failure"
print("PASS PC-1 - a failed patch is counted and the attempt is shown")
_pc_passed += 1

# At the cap: stop. The message must forbid another diff AND say what to do
# instead, or a batch would stall on one component.
_r3 = _patch_failure(_PcRt(_PATCH_ATTEMPT_CAP - 1), "Patch failed: Hunk at original line 16 ...")
assert _r3.update["patch_attempts"] == _PATCH_ATTEMPT_CAP, _r3.update
_m3 = _r3.update["messages"][0].content
assert "[PATCH CAP REACHED]" in _m3, _m3
assert "Do NOT write another diff" in _m3, "PC-2 FAIL: the cap does not stop the loop"
assert "move to the next one" in _m3 and "save" in _m3, \
    "PC-2 FAIL: the cap does not say what to do instead, so a batch would stall"
print("PASS PC-2 - at the cap the loop is stopped and given a next action")
_pc_passed += 1

# The cap is _PATCH_ATTEMPT_CAP failures IN A ROW on one component, not that
# many scattered anywhere in a batch --
# so every apply tool must clear the counter when a patch lands. Without this a
# six-component batch would stop after three scattered failures.
# inspect.getsource cannot see a function defined in a notebook cell, so read
# the notebook file the way the PS-6 schema regression already does.
import ast as _pc_ast, json as _pc_json, pathlib as _pc_path
_pc_cells = package_cells()
_pc_src = ["".join(c["source"]) for c in _pc_cells if c["cell_type"] == "code"]
def _pc_function(name):
    return next((_pc_ast.get_source_segment(t, n) for t in _pc_src
                 for n in _pc_ast.parse(t).body
                 if isinstance(n, _pc_ast.FunctionDef) and n.name == name), "")


for _label in ("css", "js", "html"):
    # Ticket 05: a module holds many functions, so only this one's source is
    # checked, as its own notebook cell was.
    _code = _pc_function("apply_and_lint_%s" % _label)
    assert _code, "PC-3 FAIL: apply_and_lint_%s not found in the notebook" % _label
    # Ticket 09: the CSS and JS tools hand their body to the engine's one
    # apply-and-lint core, so that is the source checked for them.
    if _label in ("css", "js"):
        assert "return loop_apply_and_lint(" in _code, _label
        _code = _pc_function("loop_apply_and_lint")
        assert _code, "PC-3 FAIL: loop_apply_and_lint not found in webforge/dev_agent.py"
    assert "_patch_failure(runtime" in _code, (
        "PC-3 FAIL: %s still returns an uncounted patch failure" % _label)
    assert 'upd["patch_attempts"] = 0' in _code, (
        "PC-3 FAIL: %s never resets the counter, so the cap counts across "
        "components" % _label)
print("PASS PC-3 - all three apply tools count a failure and reset on success")
_pc_passed += 1

# The counter must be a DECLARED channel on every schema that writes it.
# LangGraph drops a write to an undeclared channel silently, which would make
# the cap read 0 forever and never fire -- the exact class of bug this project
# has been burned by before.
for _schema, _name in ((HtmlState, "HtmlState"), (CssState, "CssState"),
                       (JsState, "JsState")):
    assert "patch_attempts" in getattr(_schema, "__annotations__", {}), \
        "PC-4 FAIL: %s does not declare patch_attempts, so the count is dropped" % _name
print("PASS PC-4 - patch_attempts is a declared channel on all three schemas")
_pc_passed += 1

# It must NOT share the lint budget: one component's diff trouble would
# otherwise escalate the run and leave the rest of the batch unlinted.
assert "lint_attempts" not in _r3.update and "lint_escalated" not in _r3.update, \
    "PC-5 FAIL: a patch failure is spending the lint budget"
print("PASS PC-5 - the patch cap is separate from the lint cap")
_pc_passed += 1

print("=" * 64)
print("patch-failure cap: %d/5 PASSED (no model calls)" % _pc_passed)
