# Ported from fyp.ipynb cell 387 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: one call per developer agent per round (2026-08-31).
# Placed AFTER call_test_exec_pipeline and _secondary_orch_system_prompt, not
# next to call_html_agent: a test cell sits ABOVE everything defined below it,
# so naming a later tool raises NameError on a straight top-to-bottom run.
# Same reason extract_component's cross-tool check lives in store_html_diff's
# cell rather than its own.
# modification_attempts caps the number of ROUNDS at 2. Nothing capped the
# number of calls INSIDE a round, so PO-08 po018f8158 made 12 developer-agent
# calls across its 2 rounds:
#
#   round 1   HTML x5   CSS x1   JS x1
#   round 2   HTML x3   CSS x1   JS x1
#
# The five HTML sessions cost 324,425 input tokens and returned 7,417 output
# tokens, 5,822 of which were reasoning. With this cap and the batching added
# in the same session, the ceiling is 3 agents x 2 rounds = 6 calls.
from types import SimpleNamespace as _RcNS
from unittest.mock import MagicMock as _RcMock

_rc_passed = 0


def _rc(label, cond):
    global _rc_passed
    assert cond, f"FAIL {label}"
    _rc_passed += 1
    print(f"PASS {label}")


def _rc_call(tool, agent_name, state, **kw):
    """Call one call_*_agent tool with its sub-agent mocked.

    Returns (command, was_streamed). was_streamed is the point of the whole
    cap: a refused call must not reach the sub-agent, or it saves nothing.
    """
    global get_stream_writer
    _orig_gsw = get_stream_writer
    _mock = _RcMock()
    _mock.stream.return_value = iter(())
    _real = globals()[agent_name]
    try:
        globals()[agent_name] = _mock
        get_stream_writer = lambda: (lambda d: None)
        st = {"session_id": "rc01"}
        st.update(state)
        cmd = tool.func(_RcNS(state=st, tool_call_id="rc-tc"), "fix it", **kw)
    finally:
        globals()[agent_name] = _real
        get_stream_writer = _orig_gsw
    return cmd, _mock.stream.called


_TRIPLE = ((call_html_agent, "html_agent", "html_round_calls", "HTML"),
           (call_css_agent, "css_agent", "css_round_calls", "CSS"),
           (call_js_agent, "js_agent", "js_round_calls", "JS"))

# ── the cap itself, on all three ───────────────────────────────────────────
for _tool, _name, _field, _label in _TRIPLE:
    _cmd, _streamed = _rc_call(_tool, _name, {_field: 0}, intent="modify",
                               target_component=".a")
    _rc(f"RC-1 {_label}: the FIRST modify call runs and records the call",
        _streamed and _cmd.update.get(_field) == 1)

    _cmd, _streamed = _rc_call(_tool, _name, {_field: _ROUND_CALL_CAP},
                               intent="modify", target_component=".a")
    _msg = _cmd.update["messages"][0].content
    _rc(f"RC-2 {_label}: a SECOND call in the same round is refused, unspent",
        not _streamed and "[ROUND CAP]" in _msg)

    # A guard the model cannot satisfy is a wall. The refusal has to name both
    # ways out: batch the rest into one call, or open the next round.
    _rc(f"RC-3 {_label}: the refusal says how to batch AND how to open a round",
        "target_components" in _msg and "call_test_exec_pipeline" in _msg)

    # Generation calls each agent exactly once by construction, so capping it
    # could only ever break a working path.
    _cmd, _streamed = _rc_call(_tool, _name, {_field: _ROUND_CALL_CAP})
    _rc(f"RC-4 {_label}: generation is exempt from the round cap", _streamed)

# ── the counters cannot collide ────────────────────────────────────────────
# css and js are called in ONE assistant message during a correction round, so
# both Commands land in ONE LangGraph superstep. Two writes to a shared key is
# InvalidUpdateError, which is what killed SO-01 on 2026-08-09. A reducer would
# be the wrong fix: it would turn a loud crash into a silently lost count.
_written = []
for _tool, _name, _field, _label in _TRIPLE:
    _cmd, _ = _rc_call(_tool, _name, {_field: 0}, intent="modify",
                       target_component=".a")
    _written.append({k for k in _cmd.update if k.endswith("_round_calls")})
_rc("RC-5  each tool writes ONLY its own counter, so parallel calls cannot "
    "collide",
    _written == [{"html_round_calls"}, {"css_round_calls"}, {"js_round_calls"}])

# ── a test run is the round boundary, so it clears all three ───────────────
_rt_real = run_test_suite
_gsw_real = get_stream_writer
try:
    run_test_suite = _RcMock()
    run_test_suite.func.return_value = _RcNS(update={"test_report": "PASSED: x"})
    get_stream_writer = lambda: (lambda d: None)
    _cmd = call_test_exec_pipeline.func(_RcNS(
        state={"session_id": "rc01", "test_cases": [{"id": "t1"}],
               "html_round_calls": 1, "css_round_calls": 1, "js_round_calls": 1},
        tool_call_id="rc-pipe"))
finally:
    run_test_suite = _rt_real
    get_stream_writer = _gsw_real
_rc("RC-6  a test run resets every per-round counter, opening the next round",
    _cmd.update.get("html_round_calls") == 0
    and _cmd.update.get("css_round_calls") == 0
    and _cmd.update.get("js_round_calls") == 0)

# ── the prompt asks for what the guard requires ────────────────────────────
# The components generator was refused three identical times on 2026-08-31 for
# obeying one prompt rule that another rule forbade. A cap whose prompt still
# said "call html_agent once per component" would be the same trap.
# The prompt is a plain string in this notebook, not a PromptTemplate, so a
# straight `in` test is meaningful here. (On a PromptTemplate it would be
# an assertion that can never fail -- Pydantic defines __iter__.)
_sop = _secondary_orch_system_prompt
_rc("RC-7  the prompt no longer tells HTML to run once PER COMPONENT",
    "once per component (no batch support)" not in _sop)
_rc("RC-8  and it states the one-call-per-round budget the guard enforces",
    "ONE call per round" in _sop)

# 4 cases per developer agent x 3 agents = 12, plus the collision check,
# the pipeline reset and the two prompt checks = 16.
_RC_TOTAL = 4 * 3 + 4
assert _rc_passed == _RC_TOTAL, f"expected {_RC_TOTAL}, counted {_rc_passed}"
print(f"round call cap: {_rc_passed}/{_RC_TOTAL} PASSED (no model calls)")
