# Ported from fyp.ipynb cell 147 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _lint_failure / _lint_refused (lint fix-loop cap)
from types import SimpleNamespace as _NSL

_rt_lint = lambda **kw: _NSL(state=kw, tool_call_id="test-lintcap")

# Case 1: first failure — attempt counted, loop continues, diagnostics preserved
c1 = _lint_failure(_rt_lint(), "Found 1 problem(s):\n  Line 3 [block-no-empty]: Empty block")
assert c1.update["lint_attempts"] == 1
assert c1.update["lint_passed"] is False
assert "lint_escalated" not in c1.update, "must not escalate on the first failure"
assert c1.update["messages"][0].content.startswith("Found 1 problem(s):"), \
    "the problem list must come first and unchanged — existing prompts key off it"
assert f"[Lint attempt 1/{_LINT_ATTEMPT_CAP}]" in c1.update["messages"][0].content
print("[Case 1] PASS: attempt 1 counted, diagnostics intact, no escalation\n")

# Case 2: the attempt that reaches the cap escalates
c2 = _lint_failure(_rt_lint(lint_attempts=_LINT_ATTEMPT_CAP - 1), "Found 2 problem(s):")
assert c2.update["lint_attempts"] == _LINT_ATTEMPT_CAP
assert c2.update["lint_escalated"] is True
assert c2.update["lint_passed"] is False, "escalation must never fake a clean lint"
_m2 = c2.update["messages"][0].content
assert _LINT_CAP_MARKER in _m2 and "save tool" in _m2 and "END your turn" in _m2
print(f"[Case 2] PASS: cap reached at attempt {_LINT_ATTEMPT_CAP}, escalation flagged\n")

# Case 3: the step just before the cap must NOT escalate (off-by-one guard)
c3 = _lint_failure(_rt_lint(lint_attempts=_LINT_ATTEMPT_CAP - 2), "Found 1 problem(s):")
assert "lint_escalated" not in c3.update
assert c3.update["lint_attempts"] == _LINT_ATTEMPT_CAP - 1
print("[Case 3] PASS: escalates on the cap, not one attempt early\n")

# Case 4: a refused call costs nothing and repeats the same instruction
c4 = _lint_refused(_rt_lint(lint_attempts=99, lint_escalated=True))
assert c4.update["lint_passed"] is False
assert "lint_attempts" not in c4.update, "a refused call must not inflate the counter"
assert _LINT_CAP_MARKER in c4.update["messages"][0].content
assert "REFUSED" in c4.update["messages"][0].content
print("[Case 4] PASS: post-cap call refused without counting\n")

# Case 5: escalation is idempotent — re-entering _lint_failure past the cap still
#   escalates rather than silently resetting or wrapping around.
c5 = _lint_failure(_rt_lint(lint_attempts=_LINT_ATTEMPT_CAP + 5), "Found 1 problem(s):")
assert c5.update["lint_escalated"] is True and c5.update["lint_passed"] is False
print("[Case 5] PASS: still escalates when called past the cap\n")

# Case 6: the whole point — a run that never lints clean terminates in a bounded
#   number of linter calls instead of climbing to GraphRecursionError.
_state, _calls = {}, 0
for _ in range(20):
    if _state.get("lint_escalated"):
        _cmd = _lint_refused(_rt_lint(**_state))
    else:
        _cmd = _lint_failure(_rt_lint(**_state), "Found 1 problem(s):")
    _calls += 1
    _state.update({k: v for k, v in _cmd.update.items() if k != "messages"})
    if _state.get("lint_escalated"):
        break
assert _state["lint_escalated"] is True
assert _calls == _LINT_ATTEMPT_CAP, f"expected {_LINT_ATTEMPT_CAP} lint runs, got {_calls}"
print(f"[Case 6] PASS: an unfixable defect stops after {_calls} lint runs, not 25 supersteps\n")

print("lint fix-loop cap: all 6 cases passed.")
