# Ported from fyp.ipynb cell 392 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 182
# ═══════════════════════════════════════════════════════════════════════════
# E2E (live LLM): SECONDARY ORCHESTRATOR — the whole sub-workflow
#
# Run manually. This calls the REAL gpt-5.4 for the orchestrator AND for every
# sub-agent it invokes, so it is the most expensive cell in the notebook.
# RUN E2E-SO-01 ON ITS OWN FIRST — 03 and 04 reuse the page it generates.
#
#   E2E-SO-01  Generate, full path   — ordering, all three files written, suite run.
#                                     A correction loop is allowed; first-pass and
#                                     recovery are REPORTED, not asserted.
#   E2E-SO-02  Cap refusal          — a 3rd correction is REFUSED in code and the
#                                     orchestrator stops (cheap: no sub-agent runs)
#   E2E-SO-03  Correction loop      — a deliberately corrupted CSS file is detected,
#                                     routed to css_agent, fixed, attempt counted
#   E2E-SO-04  Modify + css sync    — a colour change patches the EXISTING suite
#                                     via sync_css_test_cases; Test Gen never re-runs
#   E2E-SO-05  Modify + text sync   — a label change patches assert_text the same
#                                     way, through sync_text_test_cases
#   E2E-SO-06  Modify + hover sync  — a hover-colour change patches
#                                     assert_hover_css, through sync_hover_test_cases
#
# WHY THERE IS NO SCRIPTED (offline) SECONDARY ORCHESTRATOR SUITE
# ---------------------------------------------------------------
# The developer agents earned theirs because their loops are PYTHON-driven — the
# lint retry, the coverage guard — so a scripted model still exercises real logic.
# The orchestrator has no loop of its own. Every question SO-01..04 asks is
# "does the real model follow the instructions?": does it run HTML before CSS,
# does it stop when the pipeline says REFUSED, does it sync instead of
# regenerate. Scripting the model would script exactly the behaviour under test.
# The deterministic parts are already covered elsewhere and are NOT retested here:
# the cap itself (call_test_exec_pipeline, 14 cases), the failure routing
# (_route_agent, inside the 29 run_test_suite cases), and the three sync tools
# (16 cases). What is left is model compliance, and only a live run shows it.
#
# SO-05 and SO-06 were added on 2026-08-16 because only ONE of the three sync
# tools had ever run against a real model. The other two passed their unit tests,
# which is exactly what run_eslint did for several weeks while being completely
# broken against the real binary.
# ═══════════════════════════════════════════════════════════════════════════
import uuid as _so_uuid, pathlib as _so_pl, time as _so_time
from types import SimpleNamespace as _SNS_PF
from langchain_core.messages import HumanMessage as _SO_HM

# ── Pre-flight: free wiring checks, so a typo cannot waste a paid run ────────
_assert_state_fields(
    SecondaryOrchState,
    ["session_id", "test_cases", "test_report", "modification_context",
     "modification_attempts", "intent", "components_specification"],
    "Secondary Orchestrator",
)
_SO_EXPECTED_TOOLS = {
    "call_html_agent", "call_css_agent", "call_js_agent",
    "call_test_gen_agent", "call_test_exec_pipeline",
    "sync_css_test_cases", "sync_text_test_cases", "sync_hover_test_cases",
}
_so_wired = set(_production_tool_names("secondary_orch"))
assert _so_wired == _SO_EXPECTED_TOOLS, (
    f"PRE-FLIGHT FAIL: secondary_orch tool set drifted.\n"
    f"  missing: {sorted(_SO_EXPECTED_TOOLS - _so_wired)}\n"
    f"  extra:   {sorted(_so_wired - _SO_EXPECTED_TOOLS)}")
print(f"[E2E] Pre-flight OK — {len(_so_wired)} tools wired, state schema complete")

print("[E2E] Pre-flight OK — middleware hooks run with their real signatures")

# Session-id contract smoke. The id is issued by the application layer, so the
# question is no longer "did the tool mint one" but "is a call without one
# refused". call_secondary_orchestrator is the boundary; refusing costs nothing
# because it returns before streaming anything.
assert _safe_session_id(str(_so_uuid.uuid4())), \
    "PRE-FLIGHT FAIL: a real uuid4 thread_id must be a valid session_id"
assert _safe_session_id("../../x") == "", \
    "PRE-FLIGHT FAIL: _safe_session_id lets a traversing id through"
print("[E2E] Pre-flight OK — session_id validator accepts uuid4, rejects traversal\n")


# ── Fixture: ONE small page. Deliberately small — every extra component costs a
# real generation round in three agents plus a bigger test suite. ─────────────
# Fixtures are BUILT FROM the real Pydantic schemas, so a schema change breaks this
# cell loudly instead of drifting. Defined locally rather than borrowed from the
# Test Gen E2E cell, so this cell can be run on its own.
assert all(n in globals() for n in ("ComponentSpecification", "LayoutSpecification",
           "InteractionSpecification", "DecorationSpecification")), (
    "Run the spec-schema cell BEFORE this E2E cell.")

def _so_from_model(_Model, _raw):
    return _Model.model_validate(_raw).model_dump()

_SO_QUERY = ("Build a product listing page with a navigation bar, one product card, "
             "and an add-to-cart button.")
_SO_COMPONENTS = _so_from_model(ComponentSpecification, {"pages": [{"pageName": "product-listing",
    "regionComponents": {"main": [
        {"id": "navbar", "tag": "nav", "ownedBy": "HTML",
         "componentCategory": "navbar"},
        {"id": "product-card", "tag": "article", "ownedBy": "HTML",
         "className": "product-card", "componentCategory": "product-card"},
        {"id": "add-to-cart-button", "tag": "button", "ownedBy": "HTML",
         "className": "add-to-cart-btn", "componentCategory": "add-to-cart-button",
         "states": [{"name": "disabled"}],
         "events": [{"event": "click", "flowName": "add-to-cart-flow"}]},
    ]}}]})
_SO_LAYOUT = _so_from_model(LayoutSpecification, {"pages": [{"pageName": "product-listing",
    "pageType": "plp", "pageLayoutType": "single-column",
    "regions": [{"name": "main", "ownedBy": "HTML", "layoutType": "grid"}]}]})
_SO_INTERACTION = _so_from_model(InteractionSpecification, {"pages": [{"pageName": "product-listing",
    "flows": [{"name": "add-to-cart-flow",
               "trigger": {"event": "click", "targetId": "add-to-cart-button"},
               "actions": [{"type": "addToCart", "targetId": "add-to-cart-button"}],
               "stateTransitions": [{"componentId": "add-to-cart-button",
                                     "fromState": None, "toState": "disabled"}]}]}]})
_SO_BTN_BG    = "#1a73e8"
# A hover variant, so the generated suite contains an assert_hover_css case for
# SO-06 to rebase. Without one there is nothing for the hover sync to patch and
# the scenario would pass while testing nothing.
_SO_BTN_HOVER = "#1557b0"
_SO_DECORATION = _so_from_model(DecorationSpecification, {"globalTokens": {},
    "pages": [{"pageName": "product-listing", "componentDecorations": [
        {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
         "baseStyles": {"background-color": _SO_BTN_BG, "color": "#ffffff"},
         "stateVariants": [{"stateName": "disabled", "styles": {"opacity": "0.5"}},
                           {"stateName": "hover",
                            "styles": {"background-color": _SO_BTN_HOVER}}]},
        {"componentId": "product-card", "className": "product-card",
         "baseStyles": {"border": "1px solid #dddddd"}, "stateVariants": []}]}]})

_SO_PREVIEW = _so_pl.Path.cwd() / "static" / "preview"


def _so_payload(query, **over):
    """Base payload. Overrides let a scenario seed modification state."""
    p = {
        "messages":                  [_SO_HM(content=query)],
        # The harness stands in for the Streamlit layer, which owns the id.
        # Overridable: SO-02/03/04 pass SO-01's id to reuse its page.
        "session_id":                f"so{_so_uuid.uuid4().hex[:6]}",
        "user_query":                query,
        "layout_specification":      _SO_LAYOUT,
        "components_specification":  _SO_COMPONENTS,
        "interaction_specification": _SO_INTERACTION,
        "decoration_specification":  _SO_DECORATION,
        "test_cases":                [],
        "test_report":               "",
        "modification_context":      "",
        "modification_attempts":     0,
        "intent":                    "generate",
    }
    p.update(over)
    return p


def _so_cfg(tag):
    return {"configurable": {"thread_id": f"so-{tag}-{_so_uuid.uuid4().hex[:6]}"},
            "run_name": f"Secondary Orchestrator - SO-{tag}"}


# The wrap_tool_call middleware writes one line per orchestrator tool, so the
# progress stream is an ORDERED trace of which tool ran when. That is the only
# place the ordering constraints (HTML before CSS/JS, TestExec last) are visible.
_SO_TRACE = {
    "Calling HTML Agent":                       "call_html_agent",
    "Calling CSS Agent":                        "call_css_agent",
    "Calling JS Agent":                         "call_js_agent",
    "Calling Test Generation Agent":            "call_test_gen_agent",
    "Calling Test Execution Pipeline":          "call_test_exec_pipeline",
    "Updating style test expectations":         "sync_css_test_cases",
    "Updating hover-style test expectations":   "sync_hover_test_cases",
    "Updating text test expectations":          "sync_text_test_cases",
}


def _so_tools_called(run):
    """Ordered list of orchestrator tool names, read off the progress stream."""
    order = []
    for e in run["custom_events"]:
        text = e if isinstance(e, str) else (e.get("text", "") if isinstance(e, dict) else "")
        for needle, name in _SO_TRACE.items():
            if needle in str(text):
                order.append(name)
                break
    return order


def _so_first(order, name):
    return order.index(name) if name in order else -1


# Scenario outcomes live in a dict rather than a counter, so re-running a single
# scenario cell overwrites its own entry instead of double-counting.
_SO_RESULTS = {}
_SO_SESSION = None      # set by SO-01, reused by SO-02, SO-03 and SO-04
_tc1        = []        # the suite SO-01 produces, reused by the others


def _so_require_so01(tag):
    """SO-02..04 reuse the page and the test suite SO-01 produces."""
    if not _SO_SESSION or not _tc1:
        raise RuntimeError(
            f"{tag} needs E2E-SO-01 to have run first: it generates the page these "
            f"scenarios act on and the test suite they reuse.")


# ── Diagnostics helper, shared by the per-scenario diagnostic cells ──────────
# Costs nothing and calls no agent: it only reads what a run left in the kernel.
# Run a diagnostic cell as often as you like, including long after the scenario,
# to inspect a run you have already paid for.
def _so_diagnose(run, order, label="SO-01"):
    _exec = order.count("call_test_exec_pipeline")
    _st   = run["state"]
    _rep  = _st.get("test_report") or ""
    print("=" * 68)
    print(f"  {label} diagnostics")
    print("=" * 68)
    print("tool order      :", " -> ".join(order) or "(none captured)")
    print(f"pipeline runs   : {_exec}")
    # Absent means no tool wrote it this run, which is NOT the same as zero:
    # a refused call writes nothing, so the seeded value still stands.
    _att = _st.get("modification_attempts")
    print(f"corrections     : "
          f"{'not written this run' if _att is None else f'{_att} / cap 2'}")
    print(f"first-pass      : {_exec == 1}")
    print(f"ended passing   : {'ALL TESTS PASSED' in _rep}")
    # Only what this run WROTE. A generate run writes the whole suite; a
    # sync-only run writes just the cases it patched.
    print(f"test cases      : {len(_st.get('test_cases') or [])} written this run")
    print(f"session_id      : "
          f"{_st.get('session_id') or '(supplied by the caller, never rewritten)'}")

    # Batching: everything after the FIRST pipeline run is correction work.
    if "call_test_exec_pipeline" in order:
        _after = order[order.index("call_test_exec_pipeline") + 1:]
        _fixes = [t for t in _after if t.startswith("call_") and t.endswith("_agent")]
        print(f"correction calls: {_fixes or '(none)'}")
        # Batching is a PER-ROUND rule: one call per agent between two pipeline
        # runs. Counting across the whole correction phase flagged an agent that
        # legitimately worked in round 1 and again in round 2, so SO-01 reported
        # a defect that was not there (2026-08-09).
        _round, _rounds = [], []
        for _t in _after:
            if _t == "call_test_exec_pipeline":
                _rounds.append(_round)
                _round = []
            elif _t.startswith("call_") and _t.endswith("_agent"):
                _round.append(_t)
        _rounds.append(_round)
        for _n, _r in enumerate(_rounds, 1):
            if not _r:
                continue
            _dupes = sorted({t for t in _r if _r.count(t) > 1})
            _flag = f"  NOT BATCHED: {_dupes}" if _dupes else ""
            print(f"  round {_n}: {_r}{_flag}")
        if any(sorted({t for t in _r if _r.count(t) > 1}) for _r in _rounds):
            print("  NOTE  the prompt asks for ONE batched call per agent per round "
                  "(target_components=[...], all three agents, max 12).")

    # The work orders the pipeline produced -- who was blamed, and for what.
    _actions = [l.strip() for l in _rep.splitlines()
                if "|" in l and ("_agent" in l or "[infra]" in l)]
    if _actions:
        print(f"\nwork orders ({len(_actions)}):")
        for _a in _actions[:12]:
            print("   ", _a[:110])
    # The report line alone was not enough to explain TC-007 (a data-state
    # assertion that failed on a page which HAD the attribute), so print the
    # failing cases as stored: selector and expected value included.
    _by_id = {t.get("id"): t for t in (_st.get("test_cases") or []) if isinstance(t, dict)}
    _failed = [l.strip() for l in _rep.splitlines() if l.strip().startswith("FAILED")]
    if _failed:
        print(f"\nfailures ({len(_failed)}), first 8:")
        for _f in _failed[:8]:
            _tid = _f.split()[1] if len(_f.split()) > 1 else ""
            _tc  = _by_id.get(_tid.rstrip(":"))
            if _tc:
                print(f"      case {_tid} selector={_tc.get('selector')!r} "
                      f"expected={_tc.get('expected')!r} "
                      f"covers_state={_tc.get('covers_state')!r}")
            print("   ", _f[:110])
    print("=" * 68)

# ── Parallel-stream viewer: one column per agent ─────────────────────────────
# The orchestrator runs CSS, JS and Test Generation in PARALLEL, so their
# progress lines arrive interleaved in one flat stream and are painful to read.
# Every line already carries its own "[X Agent]" prefix, written by each agent's
# middleware, so the stream can be split after the fact with no change to the
# agents themselves.
#
# This renders a FINISHED run. Live side-by-side output is not possible in a
# notebook, whose cell output is a single linear stream -- and it is not needed,
# because the point is inspection after the fact.
import html as _cols_html
import textwrap as _cols_wrap

_COLUMN_ORDER = ["HTML Agent", "CSS Agent", "JS Agent", "Test Gen Agent"]


def _split_agent_streams(run):
    """Bucket a run's custom progress events by the agent that emitted them.

    Returns {label: [line, ...]}. Anything with no recognised prefix, including
    the orchestrator's own lines, goes to 'Secondary Orchestrator'.
    """
    buckets, order = {}, []
    for ev in (run.get("custom_events") or []):
        if isinstance(ev, dict):
            if ev.get("type") in ("indent",):      # layout control, not content
                continue
            text = str(ev.get("text", "") or "")
        else:
            text = str(ev)
        if not text.strip():
            continue
        stripped = text.strip()
        label = "Secondary Orchestrator"
        if stripped.startswith("["):
            end = stripped.find("]")
            if end > 1:
                label = stripped[1:end].strip()
                stripped = stripped[end + 1:].strip()
        if label not in buckets:
            buckets[label] = []
            order.append(label)
        buckets[label].append(stripped)
    ranked = [l for l in _COLUMN_ORDER if l in buckets]
    ranked += [l for l in order if l not in ranked]
    return {l: buckets[l] for l in ranked}


def show_agent_columns(run, width=34, only_parallel=True):
    """Print one column per agent for a finished run.

    only_parallel keeps just the three agents the orchestrator fans out to, which
    is the case worth untangling. Pass False to include HTML and the orchestrator.
    """
    buckets = _split_agent_streams(run)
    if only_parallel:
        keep = {"CSS Agent", "JS Agent", "Test Gen Agent"}
        buckets = {k: v for k, v in buckets.items() if k in keep} or buckets
    if not buckets:
        print("No progress events captured for this run.")
        return

    labels = list(buckets)
    cols   = [[] for _ in labels]
    for n, label in enumerate(labels):
        for line in buckets[label]:
            cols[n].extend(_cols_wrap.wrap(line, width) or [""])

    try:                                    # rich output when a notebook is hosting us
        from IPython.display import HTML, display
        cells_html = []
        for label, body in zip(labels, cols):
            rows = "".join(f"<div>{_cols_html.escape(l)}</div>" for l in body) or "<div>—</div>"
            cells_html.append(
                "<div style='flex:1;min-width:0;padding:0 10px;"
                "border-left:1px solid rgba(128,128,128,.35)'>"
                f"<div style='font-weight:600;padding-bottom:6px'>{_cols_html.escape(label)}"
                f" <span style='opacity:.6;font-weight:400'>({len(buckets[label])})</span></div>"
                f"<div style='font-family:ui-monospace,Consolas,monospace;font-size:12px;"
                f"line-height:1.45;white-space:pre-wrap'>{rows}</div></div>")
        display(HTML("<div style='display:flex;align-items:flex-start;gap:0'>"
                     + "".join(cells_html) + "</div>"))
        return
    except Exception:
        pass

    header = " | ".join(f"{l[:width]:<{width}}" for l in labels)
    print(header)
    print("-" * len(header))
    for row in range(max(len(c) for c in cols)):
        print(" | ".join(f"{(c[row] if row < len(c) else ''):<{width}}" for c in cols))


print("[E2E] Setup ready — run E2E-SO-01 next, on its own.")

# Ticket 18: the notebook checked here that secondary_orch was not built
# before a tool's cell was re-run (assert_secondary_orch_is_current). Ticket 06
# deleted that guard: the package is imported once per process, so every agent
# is built from the tool objects that run. Nothing can be stale here.


_SO_DEV_TOOLS = ("call_html_agent", "call_css_agent", "call_js_agent")


def _so_round_shape(order):
    """Developer-agent calls per CORRECTION round, from a tool order.

    A test run is the round boundary, so splitting on call_test_exec_pipeline
    gives the rounds: element 0 is generation, every later one is a correction
    round. The pipeline is normally the LAST tool of the run, and the split then
    leaves an empty tail that is not a round at all -- counting it is what made
    SO-01 report "1 correction round" for a run that passed first time and made
    no corrections. Dropped explicitly, and only when it is empty.

    Returns [{"html": n, "css": n, "js": n}, ...], one entry per correction
    round, so an empty list means the page passed first time and the cap was
    never exercised.
    """
    rounds, cur = [], []
    for t in order:
        if t == "call_test_exec_pipeline":
            rounds.append(cur)
            cur = []
        else:
            cur.append(t)
    rounds.append(cur)
    if rounds and not rounds[-1]:
        rounds.pop()
    return [{a.replace("call_", "").replace("_agent", ""): r.count(a)
             for a in _SO_DEV_TOOLS} for r in rounds[1:]]


def _so_assert_round_cap(shape, case_id):
    """Every developer agent obeyed _ROUND_CALL_CAP in every correction round."""
    for i, r in enumerate(shape, 1):
        for agent, n in r.items():
            assert n <= _ROUND_CALL_CAP, (
                f"{case_id} FAIL: {agent} ran {n}x in correction round {i}; the "
                f"cap is {_ROUND_CALL_CAP}. Either the counter is being dropped "
                f"(SecondaryOrchState does not declare it) or the orchestrator "
                f"was built before the cap existed -- re-run its create_agent "
                f"cell.")
