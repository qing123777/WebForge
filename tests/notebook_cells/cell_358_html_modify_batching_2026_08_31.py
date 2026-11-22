# Ported from fyp.ipynb cell 358 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Needs: cell 178 (it defines _select_prompt).
# Unit tests: HTML modify batching (2026-08-31).
# CSS and JS have taken a target_components list since 2026-08-02; HTML could
# not, and the reason was structural rather than an oversight. extract_component
# and apply_and_lint_html took NO arguments -- both read target_component from
# state -- so a batched session had no way to name its second component.
#
# What that cost, measured on PO-08 po018f8158: the orchestrator made 8 separate
# call_html_agent sessions across 2 correction rounds, each re-sending the whole
# page. 442,689 input and 21,928 output tokens, of which 10,542 were reasoning.
# CSS fixed the same number of components in 3 sessions.
#
# Deliberately NOT marked LIVE-LLM: html_agent is mocked here, nothing calls a
# model, and these have to run on every offline sweep. (The call_css_agent
# equivalents ARE marked live and therefore never run in the sweep, which is a
# separate thing to fix.)
from types import SimpleNamespace as _BaNS
from unittest.mock import MagicMock as _BaMock

_ba_passed = 0


def _ba(label, cond):
    global _ba_passed
    assert cond, f"FAIL {label}"
    _ba_passed += 1
    print(f"PASS {label}")


def _run_cha(chunks=(), query="fix these", session_id="ba01", **kw):
    """Mirror of _run_cca, for the HTML tool. A plain DICT state, because that
    is what LangGraph passes -- a SimpleNamespace here once hid a production
    AttributeError."""
    global html_agent, get_stream_writer
    _orig, _orig_gsw = html_agent, get_stream_writer
    _mock = _BaMock()
    _mock.stream.return_value = iter(chunks)
    try:
        html_agent = _mock
        get_stream_writer = lambda: (lambda d: None)
        rt = _BaNS(state={"session_id": session_id}, tool_call_id="ba-tc")
        call_html_agent.func(rt, query, **kw)
    finally:
        html_agent, get_stream_writer = _orig, _orig_gsw
    # config is passed as a KEYWORD by _stream_dev_agent, not positionally.
    _ca = _mock.stream.call_args
    _cfg = _ca.kwargs.get("config") or (_ca.args[1] if len(_ca.args) > 1 else {})
    return _ca.args[0], _cfg


# ── the orchestrator hands over a batch ────────────────────────────────────
_p, _cfg = _run_cha(intent="modify", target_components=[".a", ".b", ".c"])
_ba("BA-1  target_components is forwarded, and target_component is its head",
    _p["target_components"] == [".a", ".b", ".c"] and _p["target_component"] == ".a")

_p, _ = _run_cha(intent="modify", target_component=".only")
_ba("BA-2  a lone target_component still becomes a one-item list",
    _p["target_components"] == [".only"] and _p["target_component"] == ".only")

_many = [f".c{i}" for i in range(_MODIFY_BATCH_CAP + 4)]
_p, _ = _run_cha(intent="modify", target_components=_many)
_ba(f"BA-3  the batch is capped at _MODIFY_BATCH_CAP ({_MODIFY_BATCH_CAP})",
    _p["target_components"] == _many[:_MODIFY_BATCH_CAP])

_p, _ = _run_cha()
_ba("BA-4  generate mode yields an empty target_components list",
    _p["target_components"] == [])

# The step budget has to grow with the batch. Keeping the one-component budget
# is how run po019a8c61 died: the limit was hit, and the raise nobody caught
# destroyed a finished run.
_p6, _cfg6 = _run_cha(intent="modify", target_components=_many)
_p1, _cfg1 = _run_cha(intent="modify", target_component=".one")
_ba("BA-5  recursion_limit is sized to the batch, not to one component",
    _cfg6["recursion_limit"] == _dev_agent_recursion_limit(_MODIFY_BATCH_CAP)
    and _cfg6["recursion_limit"] > _cfg1["recursion_limit"])

# ── the tools can be told WHICH component ──────────────────────────────────
_BA_HTML = ('<html><body><div class="alpha"><p>A</p></div>'
            '<div class="beta"><span>B</span></div></body></html>')


def _ba_rt(**extra):
    st = {"html_code": _BA_HTML, "target_component": ".alpha",
          "target_instance": 1, "intent": "modify"}
    st.update(extra)
    return _BaNS(state=st, tool_call_id="ba-x")


_r = extract_component.func(_ba_rt(), component=".beta")
_ba("BA-6  extract_component(component=) selects that element, not state's",
    "<span>" in _r.update["messages"][0].content
    and "<p>" not in _r.update["messages"][0].content)

_r = extract_component.func(_ba_rt())
_ba("BA-7  with no argument it still falls back to state (old callers safe)",
    "<p>" in _r.update["messages"][0].content)

# A batch shares one session, so the lint and patch budgets have to restart at
# each component. Without this the first of six spends the whole allowance.
_r = extract_component.func(_ba_rt(lint_attempts=3, patch_attempts=3),
                            component=".beta")
_ba("BA-8  a successful extract records the component and resets both budgets",
    _r.update.get("last_extracted_component") == ".beta"
    and _r.update.get("lint_attempts") == 0
    and _r.update.get("patch_attempts") == 0)

# The silent-corruption case, and the reason last_extracted_* exists at all. A
# model that names the component on extract and forgets it on apply must patch
# the element it extracted -- NOT quietly patch the batch's first component and
# report success. Python guarantees it; the prompt only asks.
_r = apply_and_lint_html.func(
    "--- original\n+++ revised\n@@ -1,1 +1,1 @@\n-<nonexistent>\n+<nope>\n",
    _ba_rt(last_extracted_component=".beta", last_extracted_instance=1))
_m = _r.update["messages"][0].content
_ba("BA-9  a forgotten component= falls back to what was EXTRACTED, not state",
    "<span>" in _m and "<p>A</p>" not in _m)

# ── the prompt agrees with the tools ───────────────────────────────────────
# The tools take the whole list in one call. If the prompt still said "one at a
# time" the batch arguments would sit there unused, which is the same class of
# failure as a guard the model cannot satisfy: the code and the instructions
# would disagree, and only the instructions reach the model.
_ba("BA-10 the modify prompt asks for the whole batch in ONE extract and ONE apply",
    "Extract EVERY Target in ONE Call" in _html_modification_prompt
    and "ONE extract_component call and ONE apply_and_lint_html call"
        in _html_modification_prompt
    and "ONCE PER COMPONENT" not in _html_modification_prompt)
_ba("BA-11 it saves once at the end, not once per component",
    "once, at the very end" in _html_modification_prompt)

# Through the REAL middleware, via the shim the html_prompt_selector tests
# already use: a hand-called function would not prove the prompt the agent
# actually receives.
_sel, _ = _select_prompt({"intent": "modify",
                         "target_components": [".a", ".b"]})
_ba("BA-12 the modify prompt actually SHOWS the list to the model",
    "Components to fix in THIS call" in _sel and ".b" in _sel)

# ── a click-to-select target survives a model that forgets to pass it ──────
# 13b71045 (2026-09-15): state held '.featured-product-card', the SO model
# passed target_component='' and the agent got nothing. The tool now takes
# the target from state whenever a modify call names none.
def _run_cha_state(state_extra, **kw):
    global html_agent, get_stream_writer
    _orig, _orig_gsw = html_agent, get_stream_writer
    _mock = _BaMock()
    _mock.stream.return_value = iter(())
    try:
        html_agent = _mock
        get_stream_writer = lambda: (lambda d: None)
        rt = _BaNS(state={"session_id": "ba01", **state_extra}, tool_call_id="ba-tc")
        call_html_agent.func(rt, "change Aurora to Alpha", **kw)
    finally:
        html_agent, get_stream_writer = _orig, _orig_gsw
    return _mock.stream.call_args.args[0]


_p = _run_cha_state({"target_component": ".featured-product-card",
                     "target_instance": 2}, intent="modify", target_component="")
_ba("BA-13 an empty modify target falls back to state's target AND instance",
    _p["target_components"] == [".featured-product-card"]
    and _p["target_component"] == ".featured-product-card"
    and _p["target_instance"] == 2)

_p = _run_cha_state({"target_component": ".featured-product-card",
                     "target_instance": 2},
                    intent="modify", target_components=[".a", ".b"], target_instance=1)
_ba("BA-14 a routed batch is NOT overridden by state's click target",
    _p["target_components"] == [".a", ".b"] and _p["target_instance"] == 1)

_p = _run_cha_state({"target_component": ".featured-product-card"},
                    intent="generate")
_ba("BA-15 generate mode ignores a stale target in state",
    _p["target_components"] == [] and _p["target_component"] == "")

_BA_TOTAL = 15
assert _ba_passed == _BA_TOTAL, f"expected {_BA_TOTAL}, counted {_ba_passed}"
print(f"HTML modify batching: {_ba_passed}/{_BA_TOTAL} PASSED (no model calls)")
