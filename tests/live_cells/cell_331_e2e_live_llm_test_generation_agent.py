# Ported from fyp.ipynb cell 331 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# LIVE-LLM: costs credits, run manually only
# E2E (live LLM): Test Generation agent + progress middleware.
# Run manually — this calls the REAL gpt-5.4 model (spends credits). Output follows
# the developer-agent E2E format: [E2E] diagnostic lines, an inferred store-call
# count, a Final-state line, banner headers, and PASS E2E-TG-xx. It streams the real
# agent, asserts the progress middleware fired, and checks that store_test_cases
# produced a schema-valid, spec-covering suite. TG-01 generate path.
import uuid as _uuid, re as _re, time as _time
from langchain_core.messages import HumanMessage as _HM

_TGE_KEYS    = {"id", "component", "description", "action", "selector", "expected", "passed"}
_TGE_ACTIONS = {"assert_visible", "assert_text", "assert_css", "assert_hover_css",
                "assert_attribute", "assert_url", "assert_count", "click", "type"}

# Self-contained fixture specs (do not depend on the unit-test cell above).
_TGE_QUERY = "Build a product listing page with a navbar, product cards, and an add-to-cart button."
# Fixtures are BUILT FROM the real Pydantic schemas (the cell defining class
# ComponentSpecification / LayoutSpecification / InteractionSpecification /
# DecorationSpecification). _from_model validates the raw dict against the model and
# returns the model's own dump -- the exact shape the System Design & Planning chain
# feeds downstream -- so a schema change breaks this test loudly instead of drifting.
assert all(n in globals() for n in ("ComponentSpecification", "LayoutSpecification",
           "InteractionSpecification", "DecorationSpecification")), (
    "Run the spec-schema cell (defines class ComponentSpecification / LayoutSpecification / "
    "InteractionSpecification / DecorationSpecification) BEFORE this E2E cell.")

def _from_model(_Model, _raw):
    return _Model.model_validate(_raw).model_dump()

_TGE_COMPONENTS = _from_model(ComponentSpecification, {"pages": [{"pageName": "product-listing",
    "regionComponents": {"main": [
        {"id": "navbar", "tag": "nav", "ownedBy": "HTML"},
        {"id": "product-card", "tag": "div", "ownedBy": "HTML", "className": "product-card",
         "states": [{"name": "selected"}]},
        {"id": "add-to-cart-button", "tag": "button", "ownedBy": "HTML", "className": "add-to-cart-btn",
         "states": [{"name": "disabled"}],
         "events": [{"event": "click", "flowName": "add-to-cart-flow"}]},
    ]}}]})
_TGE_LAYOUT = _from_model(LayoutSpecification, {"pages": [{"pageName": "product-listing",
    "pageType": "plp", "pageLayoutType": "single-column",
    "regions": [{"name": "main", "ownedBy": "HTML", "layoutType": "grid"}]}]})
# InteractionSpecification: a flow joins to a component by trigger.targetId (event
# origin) and stateTransitions[].componentId (state change).
_TGE_INTERACTION = _from_model(InteractionSpecification, {"pages": [{"pageName": "product-listing",
    "flows": [{"name": "add-to-cart-flow",
               "trigger": {"event": "click", "targetId": "add-to-cart-button"},
               "actions": [{"type": "addToCart", "targetId": "add-to-cart-button"}],
               "stateTransitions": [{"componentId": "add-to-cart-button",
                                     "fromState": None, "toState": "disabled"}]}]}]})
# DecorationSpecification: each ComponentDecoration joins to a component by componentId.
_TGE_DECORATION = _from_model(DecorationSpecification, {"globalTokens": {},
    "pages": [{"pageName": "product-listing", "componentDecorations": [
        {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
         "baseStyles": {"background-color": "#1a73e8", "color": "#ffffff"},
         "stateVariants": [{"stateName": "disabled", "styles": {"opacity": "0.5"}}]},
        {"componentId": "product-card", "className": "product-card",
         "baseStyles": {"border": "1px solid #dddddd"},
         "stateVariants": [{"stateName": "selected", "styles": {"border-color": "#1a73e8"}}]}]}]})
_TGE_COMP_IDS      = {"navbar", "product-card", "add-to-cart-button"}
# C1: a declared state no interaction flow PRODUCES cannot be materialised by the
# click/type-only pipeline, so asserting a data-state for it is a permanent false
# failure. The store_test_cases guard drops such a state from its coverage demand
# when an interaction spec is present; mirror the SAME rule here so this harness
# checks the contract the agent was actually told to satisfy, not the old
# "every declared state" one. product-card `selected` has no producing flow in
# this fixture (only add-to-cart-flow -> disabled), so it drops from REQUIRED.
def _tge_flow_produced(_intx):
    _out = set()
    for _pg in (_intx or {}).get("pages") or []:
        for _fl in _pg.get("flows") or []:
            for _st in _fl.get("stateTransitions") or []:
                if _st.get("componentId") and _st.get("toState"):
                    _out.add((_st["componentId"], _st["toState"]))
    return _out
_TGE_DECLARED_STATES = {("product-card", "selected"), ("add-to-cart-button", "disabled")}
_TGE_PRODUCIBLE      = _tge_flow_produced(_TGE_INTERACTION)
# required = declared AND reachable, never transient (the guard refuses those, ticket 02)
_TGE_STATE_TARGETS   = {(_c, _s) for (_c, _s) in _TGE_DECLARED_STATES & _TGE_PRODUCIBLE
                        if not _is_transient_state(_s)}
_TGE_EVENT_TARGETS = {("add-to-cart-button", "click")}

def _tge_cfg(tag, run_name=None):
    cfg = {"configurable": {"thread_id": f"tge-{tag}-{_uuid.uuid4().hex[:6]}"}}
    if run_name:
        cfg["run_name"] = run_name   # names the run in LangSmith
    return cfg

def _tge_progress(events):
    """Flatten the custom progress stream to one searchable string."""
    parts = []
    for e in events:
        if isinstance(e, str):
            parts.append(e)
        elif isinstance(e, dict) and e.get("type") == "log":
            parts.append(str(e.get("text", "")))
    return "\n".join(parts)

def _tge_saved_count(feedback):
    for msg in feedback:
        m = _re.search(r"(\d+) test case", msg, _re.I)
        if m:
            return int(m.group(1))
    return None

_TGE_RESTING = {"default", "idle", "closed", "collapsed", "inactive"}
def _tge_resting_leaks(cases):
    """Rule B: a case asserting a RESTING state (default/idle/closed) must NOT be
    tagged covers_state. The tag pushes it to phase 2 (after all clicks), where the
    resting value is already gone, so it fails for no real defect (po015df552 TC-003,
    TC-055). Returns the offending (id, expected, covers_state) tuples."""
    out = []
    for tc in cases:
        if tc.get("action") != "assert_attribute" or not tc.get("covers_state"):
            continue
        _val = str(tc.get("expected", "")).split("=", 1)[-1].strip().lower()
        if _val in _TGE_RESTING:
            out.append((tc["id"], tc.get("expected"), tc.get("covers_state")))
    return out

_TGE_TRANSIENT = _TRANSIENT_STATES   # the one list, from webforge.test_gen_agent (ticket 02)
def _tge_transient_leaks(cases):
    """A TRANSIENT / in-flight state (adding, loading, saving...) reverts to a stable
    end-state on its own, so an assertion racing to catch it is timing-dependent and
    fails once the state has settled (po015df552 TC-057, `adding`). Flags any case
    TAGGED with a transient covers_state, whatever its action (PO-08 4fb17fbe TC-065
    was an assert_css), and any assert_attribute whose expected VALUE is a transient
    word. Returns the offending (id, expected) tuples."""
    out = []
    for tc in cases:
        _val = str(tc.get("expected", "")).split("=", 1)[-1]
        if _is_transient_state(tc.get("covers_state")) or (
                tc.get("action") == "assert_attribute" and _is_transient_state(_val)):
            out.append((tc["id"], tc.get("expected")))
    return out

# ── Contract checks (Priority 1) ──────────────────────────────────────────────
# The coverage asserts above prove the suite is COMPLETE. They do not prove it is
# USABLE. Two contracts decide that, and neither is enforced by store_test_cases:
#
#   Selector Contract  '.className' when the spec node declares one, else '#id'.
#       A wrong selector makes the pipeline report "not found", which _route_agent
#       overrides to html_agent -- so a developer agent is sent to fix a page that
#       was never broken, burning one of only TWO correction attempts.
#   Decoration values  an assert_css expectation must match the value the CSS agent
#       was actually told to write. A wrong value is a permanent false failure that
#       the correction loop can never resolve.
#
# Both live only in the prompt, so only a real-LLM run can catch a breach.

def _tge_spec_selectors(components_spec):
    """component id -> the selector the Selector Contract requires."""
    out = {}
    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("id"), str) and "tag" in node:
                _cls = node.get("className")
                out[node["id"]] = f".{_cls}" if _cls else f"#{node['id']}"
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for it in node:
                walk(it)
    walk(components_spec)
    return out


def _tge_spec_styles(decoration_spec):
    """component id -> {css property: {allowed values}} from baseStyles AND every
    stateVariant. A property can legitimately hold different values in different
    states (border-color base vs selected), so values are collected as a set."""
    out = {}
    for _pg in (decoration_spec or {}).get("pages") or []:
        for _dec in _pg.get("componentDecorations") or []:
            _cid = _dec.get("componentId")
            if not _cid:
                continue
            _bucket = out.setdefault(_cid, {})
            _blocks = [_dec.get("baseStyles") or {}]
            _blocks += [(_sv.get("styles") or {}) for _sv in _dec.get("stateVariants") or []]
            for _blk in _blocks:
                for _prop, _val in _blk.items():
                    _bucket.setdefault(str(_prop).strip().lower(), set()).add(
                        str(_val).strip().lower())
    return out


def _tge_check_contracts(tag, cases, components_spec, decoration_spec):
    """Hard-assert the Selector Contract and the decoration values. Returns the
    number of assert_css pairs that referenced a property the spec never declares --
    reported as ADVISORY, not failed, since a case may legitimately check something
    outside the decoration spec (a layout-driven property, a global token)."""
    _sel   = _tge_spec_selectors(components_spec)
    _style = _tge_spec_styles(decoration_spec)
    _unknown, _badsel, _badcss, _offspec = [], [], [], []
    for tc in cases:
        _cid = tc["component"]
        if _cid not in _sel:
            _unknown.append((tc["id"], _cid))
            continue
        if tc["selector"] != _sel[_cid]:
            _badsel.append((tc["id"], _cid, tc["selector"], _sel[_cid]))
        if _style and tc["action"] in ("assert_css", "assert_hover_css"):
            for _pair in str(tc["expected"]).split("|"):
                _prop, _, _val = _pair.partition("=")
                _prop, _val = _prop.strip().lower(), _val.strip().lower()
                _allowed = _style.get(_cid, {}).get(_prop)
                if not _allowed:
                    _offspec.append((tc["id"], _cid, _prop))
                elif _val not in _allowed:
                    _badcss.append((tc["id"], _cid, _prop, _val, sorted(_allowed)))
    assert not _unknown, (
        f"{tag} FAIL: Naming Contract -- test case(s) name a component that is not in "
        f"components_specification: {_unknown}")
    assert not _badsel, (
        f"{tag} FAIL: Selector Contract -- (case, component, got, expected): {_badsel}")
    assert not _badcss, (
        f"{tag} FAIL: assert_css expectation does not match the decoration spec "
        f"-- (case, component, property, got, allowed): {_badcss}")
    print(f"[E2E] Contracts - Selector Contract OK on {len(cases)} case(s)"
          + (f"; decoration values OK" if _style else "; no decoration spec, CSS values not checked"))
    if _offspec:
        print(f"[E2E] ADVISORY - {len(_offspec)} assert_css pair(s) check a property the "
              f"decoration spec does not declare: {_offspec[:5]}")
    return len(_offspec)


def _tge_profile(tag, cases, feedback, elapsed):
    """Cost & Latency Profile input. The evaluation campaign has no Test Generation
    numbers yet, and these two runs are already being paid for."""
    print(f"[E2E] Profile {tag} - {len(cases)} case(s) over {len(feedback)} batch(es) "
          f"in {elapsed:.1f}s ({elapsed / max(len(cases), 1):.2f}s per case)")


# ══════════════════════════════════════════════════════════════════════════════
# END-TO-END TEST GENERATION AGENT TESTS  (no mocking — real LLM)
#   E2E-TG-01  Generation — progress fired, schema valid, component+state+event
#                           coverage complete (SUITE COMPLETE), Selector Contract
#                           and decoration values honoured
#   E2E-TG-02  Large spec — chunked generation at scale, same invariants
#   E2E-TG-03  Degenerate spec — empty components_specification: the no-spec
#                           coverage branch must return SUITE COMPLETE and the run
#                           must TERMINATE rather than spin toward recursion_limit
# ══════════════════════════════════════════════════════════════════════════════
_e2e_tg_passed = 0

# ── E2E-TG-01: generate path — full specs ──────────────────────────────────────
print("=" * 64)
print("[E2E] TG-01  intent=generate  (full specs)")
print("=" * 64)
_t0 = _time.perf_counter()
_tg1 = stream_agent_run(
    test_gen_agent,
    payload={
        "messages":                  [_HM(content=_TGE_QUERY)],
        "user_query":                _TGE_QUERY,
        "layout_specification":      _TGE_LAYOUT,
        "components_specification":  _TGE_COMPONENTS,
        "interaction_specification": _TGE_INTERACTION,
        "decoration_specification":  _TGE_DECORATION,
        "test_cases":                [],
        "session_id":                "tge-01",
    },
    auto_add_design_schema=False,
    config=_tge_cfg("01", run_name="Test Gen Agent - TG-01"),
)
_el1 = _time.perf_counter() - _t0

_p1 = _tge_progress(_tg1["custom_events"])
assert "Processing request"    in _p1, f"TG-01 FAIL: before_agent progress missing\n{_p1}"
assert "Generating test suite" in _p1, f"TG-01 FAIL: before_model generate progress missing\n{_p1}"
assert "Storing test cases"    in _p1, f"TG-01 FAIL: tool progress (store_test_cases) missing\n{_p1}"

_cnt1   = _tge_saved_count(_tg1["tool_feedback"])
_calls1 = len(_tg1["tool_feedback"])   # each store_test_cases call returns one ToolMessage
assert _cnt1 and _cnt1 > 0, f"TG-01 FAIL: store_test_cases not called / 0 cases -- {_tg1['tool_feedback']}"
print(f"[E2E] store_test_cases calls: {_calls1} (inferred from tool feedback)")

_tc1 = _tg1["state"].get("test_cases")
if isinstance(_tc1, list) and _tc1:
    for k, tc in enumerate(_tc1):
        assert isinstance(tc, dict) and not (_TGE_KEYS - set(tc)), f"TG-01 FAIL: TC[{k}] bad keys: {tc}"
        assert tc["passed"] is None, f"TG-01 FAIL: TC[{k}] passed should be None"
        assert tc["action"] in _TGE_ACTIONS, f"TG-01 FAIL: TC[{k}] invalid action {tc['action']!r}"
    _covered_comps  = {tc["component"] for tc in _tc1}
    _covered_states = {(tc["component"], tc.get("covers_state")) for tc in _tc1 if tc.get("covers_state")}
    _covered_events = {(tc["component"], tc.get("covers_event")) for tc in _tc1 if tc.get("covers_event")}
    assert _TGE_COMP_IDS <= _covered_comps, \
        f"TG-01 FAIL: components not all covered -- missing {_TGE_COMP_IDS - _covered_comps}"
    print(f"[proof] C1 reachable-state coverage TG-01: {len(_TGE_DECLARED_STATES)} declared "
          f"state(s), {len(_TGE_STATE_TARGETS)} reachable by a flow and therefore REQUIRED "
          f"({sorted(_TGE_STATE_TARGETS)}); dropped as unreachable "
          f"{sorted(_TGE_DECLARED_STATES - _TGE_STATE_TARGETS)} -- no flow produces it, so a "
          f"data-state assertion on it would fail on every run. Before C1 the harness demanded "
          f"all {len(_TGE_DECLARED_STATES)}, and this suite false-failed on the unreachable one.")
    _dropped = _TGE_DECLARED_STATES - _TGE_STATE_TARGETS
    _untagged_seen = {(tc["component"], str(tc.get("expected","")).split("=",1)[-1].strip())
                      for tc in _tc1 if not tc.get("covers_state")}
    for _c, _s in sorted(_dropped):
        if (_c, _s) in _untagged_seen:
            print(f"[E2E] ADVISORY - unreachable state {_c}:{_s} was still asserted WITHOUT "
                  f"covers_state (a baseline read), which is allowed and preferred.")
    assert _TGE_STATE_TARGETS <= _covered_states, \
        f"TG-01 FAIL: declared states not covered via covers_state -- missing {_TGE_STATE_TARGETS - _covered_states}"
    assert _TGE_EVENT_TARGETS <= _covered_events, \
        f"TG-01 FAIL: declared events not covered via covers_event -- missing {_TGE_EVENT_TARGETS - _covered_events}"
    assert "SUITE COMPLETE" in "\n".join(_tg1["tool_feedback"]), \
        "TG-01 FAIL: store_test_cases never reported SUITE COMPLETE"
    _leaks1 = _tge_resting_leaks(_tc1)
    assert not _leaks1, (
        f"TG-01 FAIL: Rule B -- resting-state assertion(s) tagged covers_state, which "
        f"pushes them after the clicks where the resting value is gone: {_leaks1}")
    _tleaks1 = _tge_transient_leaks(_tc1)
    assert not _tleaks1, (
        f"TG-01 FAIL: transient-state assertion(s) -- a value like 'adding'/'loading' that "
        f"reverts on its own, so the read is timing-dependent and fails for no real defect: {_tleaks1}")
    print(f"[proof] transient-state hygiene TG-01: {len([t for t in _tc1 if t.get('action')=='assert_attribute'])} "
          f"assert_attribute case(s), 0 assert a transient/in-flight value (adding, loading, saving...) -- "
          f"the class that shipped po015df552 TC-057 as a false failure; every state assertion targets a "
          f"stable end-state the read can catch.")
    _tge_check_contracts("TG-01", _tc1, _TGE_COMPONENTS, _TGE_DECORATION)
    _css_cases1 = [tc for tc in _tc1 if tc["action"] in ("assert_css", "assert_hover_css")]
    print(f"[proof] assert_css hygiene TG-01: {len(_css_cases1)} assert_css case(s), every "
          f"value matched the decoration spec VERBATIM -- _tge_check_contracts above hard-fails "
          f"on a computed value the spec never declares (an 18px written for a 1.2rem token, the "
          f"po015df552 assert_css false-failure class), so reaching this line proves 0 such values.")
    _tge_profile("TG-01", _tc1, _tg1["tool_feedback"], _el1)
    print(f"[E2E] Final state - test_cases={len(_tc1)}, coverage=complete (component+state+event)")
    _e2e_tg_passed += 1
    print("=" * 64)
    print(f"PASS E2E-TG-01  {len(_tc1)} cases, component+state+event covered (SUITE COMPLETE)")
    print("=" * 64)
else:
    print(f"[E2E] Final state - test_cases delta not captured; count via feedback={_cnt1}")
    _e2e_tg_passed += 1
    print("=" * 64)
    print(f"PASS E2E-TG-01  {_cnt1} case(s) saved (state delta not captured)")
    print("=" * 64)

# ── E2E-TG-02: large spec — exercises chunked generation at scale ──────────────
# A bigger multi-region spec (11 components, 5 states, 5 events). With this many
# targets the model typically generates in SEVERAL store_test_cases batches (the
# accumulation + gap-report loop). We HARD-assert the invariants that must hold
# regardless of batch count (full component+state+event coverage, SUITE COMPLETE,
# valid schema) and REPORT the batch count — >1 confirms live chunking. Note:
# chunking cannot be forced deterministically on a live model, so the batch count
# is reported, not asserted; the reducer/accumulation mechanics are proven in the
# offline unit tests (cell 275, T5 + reducer).
print("\n" + "=" * 64)
print("[E2E] TG-02  intent=generate  (large spec — exercises chunked generation)")
print("=" * 64)
_TG2_QUERY = ("Build a full product listing page with a search bar, filter panel, sort bar, "
              "a product grid of cards each with add-to-cart and wishlist buttons, a cart "
              "sidebar, a checkout button, and a footer.")
_TG2_COMPONENTS = _from_model(ComponentSpecification, {"pages": [{"pageName": "plp", "regionComponents": {"main": [
    {"id": "navbar",             "tag": "nav", "ownedBy": "HTML"},
    {"id": "search-bar",         "tag": "input", "ownedBy": "HTML",   "className": "search-bar",   "events": [{"event": "input"}]},
    {"id": "filter-panel",       "tag": "aside", "ownedBy": "HTML",   "className": "filter-panel", "states": [{"name": "expanded"}]},
    {"id": "sort-bar",           "tag": "div", "ownedBy": "HTML",     "className": "sort-bar",     "events": [{"event": "change"}]},
    {"id": "product-grid",       "tag": "section", "ownedBy": "HTML"},
    {"id": "product-card",       "tag": "article", "ownedBy": "HTML", "className": "product-card", "states": [{"name": "selected"}]},
    {"id": "add-to-cart-button", "tag": "button", "ownedBy": "HTML",  "className": "add-to-cart-btn",
     "states": [{"name": "disabled"}], "events": [{"event": "click"}]},
    {"id": "wishlist-button",    "tag": "button", "ownedBy": "HTML",  "className": "wishlist-btn",
     "states": [{"name": "active"}],   "events": [{"event": "click"}]},
    {"id": "cart-sidebar",       "tag": "aside", "ownedBy": "HTML",   "className": "cart-sidebar", "states": [{"name": "open"}]},
    {"id": "checkout-button",    "tag": "button", "ownedBy": "HTML",  "className": "checkout-btn", "events": [{"event": "click"}]},
    {"id": "footer",             "tag": "footer", "ownedBy": "HTML"},
]}}]})
_TG2_COMP_IDS      = {"navbar", "search-bar", "filter-panel", "sort-bar", "product-grid",
                      "product-card", "add-to-cart-button", "wishlist-button", "cart-sidebar",
                      "checkout-button", "footer"}
_TG2_STATE_TARGETS = {("filter-panel", "expanded"), ("product-card", "selected"),
                      ("add-to-cart-button", "disabled"), ("wishlist-button", "active"),
                      ("cart-sidebar", "open")}
_TG2_EVENT_TARGETS = {("search-bar", "input"), ("sort-bar", "change"),
                      ("add-to-cart-button", "click"), ("wishlist-button", "click"),
                      ("checkout-button", "click")}

_t0 = _time.perf_counter()
_tg2 = stream_agent_run(
    test_gen_agent,
    payload={
        "messages":                  [_HM(content=_TG2_QUERY)],
        "user_query":                _TG2_QUERY,
        "layout_specification":      {},
        "components_specification":  _TG2_COMPONENTS,
        "interaction_specification": {},
        "decoration_specification":  {},
        "test_cases":                [],
        "session_id":                "tge-02",
    },
    auto_add_design_schema=False,
    config=_tge_cfg("02", run_name="Test Gen Agent - TG-02"),
)
_el2 = _time.perf_counter() - _t0

_p2 = _tge_progress(_tg2["custom_events"])
assert "Processing request"    in _p2, f"TG-02 FAIL: before_agent progress missing\n{_p2}"
assert "Generating test suite" in _p2, f"TG-02 FAIL: before_model generate progress missing\n{_p2}"
assert "Storing test cases"    in _p2, f"TG-02 FAIL: tool progress missing\n{_p2}"

_calls2 = len(_tg2["tool_feedback"])
print(f"[E2E] store_test_cases calls: {_calls2}"
      + ("  (chunked — multiple batches accumulated)" if _calls2 > 1 else "  (single batch)"))

_tc2 = _tg2["state"].get("test_cases")
assert isinstance(_tc2, list) and _tc2, f"TG-02 FAIL: no test_cases captured -- {_tg2['tool_feedback']}"
for k, tc in enumerate(_tc2):
    assert isinstance(tc, dict) and not (_TGE_KEYS - set(tc)), f"TG-02 FAIL: TC[{k}] bad keys: {tc}"
    assert tc["action"] in _TGE_ACTIONS, f"TG-02 FAIL: TC[{k}] invalid action {tc['action']!r}"
_cov_c = {tc["component"] for tc in _tc2}
_cov_s = {(tc["component"], tc.get("covers_state")) for tc in _tc2 if tc.get("covers_state")}
_cov_e = {(tc["component"], tc.get("covers_event")) for tc in _tc2 if tc.get("covers_event")}
assert _TG2_COMP_IDS      <= _cov_c, f"TG-02 FAIL: components not all covered -- missing {_TG2_COMP_IDS - _cov_c}"
assert _TG2_STATE_TARGETS <= _cov_s, f"TG-02 FAIL: states not covered -- missing {_TG2_STATE_TARGETS - _cov_s}"
assert _TG2_EVENT_TARGETS <= _cov_e, f"TG-02 FAIL: events not covered -- missing {_TG2_EVENT_TARGETS - _cov_e}"
assert "SUITE COMPLETE" in "\n".join(_tg2["tool_feedback"]), "TG-02 FAIL: never reached SUITE COMPLETE"
# TG-02 passes no decoration spec, so only the Selector Contract is checkable here.
_leaks2 = _tge_resting_leaks(_tc2)
assert not _leaks2, (
    f"TG-02 FAIL: Rule B -- resting-state assertion(s) tagged covers_state: {_leaks2}")
_tleaks2 = _tge_transient_leaks(_tc2)
assert not _tleaks2, (
    f"TG-02 FAIL: transient-state assertion(s) that revert on their own (timing-dependent): {_tleaks2}")
_tge_check_contracts("TG-02", _tc2, _TG2_COMPONENTS, {})
_tge_profile("TG-02", _tc2, _tg2["tool_feedback"], _el2)
print(f"[E2E] Final state - test_cases={len(_tc2)}, coverage=complete (11 comp / 5 state / 5 event)")
_e2e_tg_passed += 1
print("=" * 64)
print(f"PASS E2E-TG-02  {len(_tc2)} cases over {_calls2} batch(es), full coverage (SUITE COMPLETE)")
print("=" * 64)

# ── E2E-TG-03: degenerate spec — empty components_specification ───────────────
# Exercises the branch no other test reaches, live or offline:
#
#     if comp_targets:   ...gap report...
#     else:              "No components_specification to check coverage against
#                         — SUITE COMPLETE. Stop calling store_test_cases."
#
# With no components the pre-join middleware also returns an EMPTY sheet, so the
# model works from the user query alone. The thing being tested is TERMINATION:
# the loop is bounded only by recursion_limit = 50, and nothing in the code catches
# a GraphRecursionError, so a run that cannot satisfy coverage would crash rather
# than degrade. A tiny payload keeps the cost of proving this low.
print("\n" + "=" * 64)
print("[E2E] TG-03  degenerate spec  (empty components_specification)")
print("=" * 64)
_TG3_QUERY = "Build a simple landing page with a heading and a sign-up button."

_t0  = _time.perf_counter()
_tg3 = stream_agent_run(
    test_gen_agent,
    payload={
        "messages":                  [_HM(content=_TG3_QUERY)],
        "user_query":                _TG3_QUERY,
        "layout_specification":      {},
        "components_specification":  {},
        "interaction_specification": {},
        "decoration_specification":  {},
        "test_cases":                [],
        "session_id":                "tge-03",
    },
    auto_add_design_schema=False,
    config=_tge_cfg("03", run_name="Test Gen Agent - TG-03"),
)
_el3 = _time.perf_counter() - _t0

_p3 = _tge_progress(_tg3["custom_events"])
assert "Processing request" in _p3, f"TG-03 FAIL: before_agent progress missing\n{_p3}"

_fb3    = "\n".join(_tg3["tool_feedback"])
_calls3 = len(_tg3["tool_feedback"])
assert _calls3 >= 1, "TG-03 FAIL: store_test_cases was never called with no spec to work from"
assert "SUITE COMPLETE" in _fb3, f"TG-03 FAIL: never reported SUITE COMPLETE -- {_fb3[:300]}"
assert "No components_specification" in _fb3, (
    "TG-03 FAIL: the no-spec coverage branch did not fire -- the run went through the "
    f"normal gap-report path instead: {_fb3[:300]}")
# Termination: with no coverage target the FIRST valid batch must close the suite.
# A few extra calls are tolerated (a schema retry), a spin is not.
assert _calls3 <= 3, (
    f"TG-03 FAIL: {_calls3} store_test_cases calls with nothing to cover -- the agent is "
    f"spinning toward recursion_limit=50 instead of stopping")

_tc3 = _tg3["state"].get("test_cases")
if isinstance(_tc3, list) and _tc3:
    for k, tc in enumerate(_tc3):
        assert isinstance(tc, dict) and not (_TGE_KEYS - set(tc)), f"TG-03 FAIL: TC[{k}] bad keys: {tc}"
        assert tc["action"] in _TGE_ACTIONS, f"TG-03 FAIL: TC[{k}] invalid action {tc['action']!r}"
    _tge_profile("TG-03", _tc3, _tg3["tool_feedback"], _el3)
    print(f"[E2E] Final state - test_cases={len(_tc3)}, no-spec branch fired, terminated in {_calls3} call(s)")
else:
    print(f"[E2E] Final state - state delta not captured; terminated in {_calls3} call(s) in {_el3:.1f}s")
_e2e_tg_passed += 1
print("=" * 64)
print(f"PASS E2E-TG-03  no-spec branch reported SUITE COMPLETE and the run terminated "
      f"({_calls3} call(s), no recursion-limit spin)")
print("=" * 64)

print("\n" + "=" * 64)
print(f"  Test Generation agent live E2E: {_e2e_tg_passed}/3 PASSED  "
      f"(TG-01 generate, TG-02 large-spec/chunked, TG-03 degenerate spec)")
print("=" * 64)
