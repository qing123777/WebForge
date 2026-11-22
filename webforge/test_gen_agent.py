"""test_gen_agent: the Test Generation agent: TestGenState, store_test_cases, its prompt and agent.

Lines 12301-13212 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

from webforge.css_agent import *  # noqa: F401,F403

# ==========================================================================
# Memory & State
# ==========================================================================
from typing import Annotated

def _merge_test_cases(existing, new):
    """Reducer for the Test Gen agent's `test_cases` channel.

    The agent generates the suite in BATCHES (chunked generation), calling
    store_test_cases several times. This reducer accumulates the batches and
    dedups by id: a new id is appended (order preserved), a re-sent id replaces
    its earlier version. Mirrors how add_messages accumulates chat messages.
    """
    existing = list(existing or [])
    if not new:
        return existing
    by_id, order = {}, []
    for tc in existing + list(new):
        tid = tc.get("id") if isinstance(tc, dict) else None
        if tid not in by_id:
            order.append(tid)
        by_id[tid] = tc
    return [by_id[t] for t in order]

class TestGenState(AgentState):
    user_query:                str
    layout_specification:      dict
    components_specification:  dict
    interaction_specification: dict
    decoration_specification:  dict
    test_cases:                Annotated[list, _merge_test_cases]
    session_id:                str


# ==========================================================================
# store_test_cases
# ==========================================================================
VALID_ACTIONS = {"assert_visible", "assert_text", "assert_css", "assert_hover_css",
                 "assert_attribute", "assert_url", "assert_count",
                 "click", "type"}

# A TRANSIENT / in-flight state reverts to a stable end-state on its own, so
# an assertion that pins one reads the settled value at execution time and
# fails against a correct page (PO-10 TC-056). This list is the ONE rule both
# guards read (speed-cost ticket 02): _spec_coverage_targets never makes a
# transient state a coverage target, and store_test_cases refuses any case
# tagged with one, whatever its action. Before, coverage demanded 'loading'
# while the store guard refused it only as assert_attribute, so the model
# wrote it as assert_css (PO-08 4fb17fbe TC-065), which failed on every
# correct page. The E2E-TG scan (_tge_transient_leaks) is the live twin.
_TRANSIENT_STATES = {"adding", "loading", "saving", "submitting", "sending",
                     "pending", "processing"}

def _is_transient_state(name: str) -> bool:
    """True when a state name is transient / in-flight. See _TRANSIENT_STATES."""
    return str(name or "").strip().lower() in _TRANSIENT_STATES

# assert_count's expected: a comparator and a whole number, e.g. ">=1", "=8".
# Defined by Test Execution, which interprets it (ticket 11); the validator
# below uses the same object.
from webforge.test_execution.actions import _COUNT_EXPECTED_RE  # noqa: E402

# Keys a `type` case may press after filling. Deliberately short: every one of
# these is deterministic and needs no modifier. Submitting a form is the whole
# point -- page.fill alone sets the value and fires input events, so a search box
# whose handler runs on submit was never reached by the old fixed-literal type.
VALID_KEYS = {"Enter", "Tab", "Escape", "Backspace",
              "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"}

# An action that OBSERVES the page. Everything else only changes it.
# The distinction carries the event-coverage rule below: `click` and `type`
# always report passed=True whenever the element exists and is actionable, so a
# suite made only of them proves nothing about what the page did in response.
_ASSERTING_ACTIONS = {a for a in VALID_ACTIONS if a.startswith("assert_")}

# A component's RESTING state -- the value it ships with and never leaves on
# its own -- is not a coverage target. A case tagged covers_state="default"
# asserts data-state="default" (or the resting aria value) on the page at
# LOAD, before any interaction, so it is true by construction and catches
# nothing: no CSS rule keys off the resting value (it IS the base style) and
# the JS only ever WRITES the non-resting value, never reads the resting one.
# Component coverage already forces a >=1 case per component, so the resting
# state adds no functional check on top. The states that EARN the self-test
# -- open, expanded, collapsed, disabled -- are not resting names and stay
# targets. This is a COST filter, not a correctness guard: a name that slips
# through leaves one harmless extra case, so the synonym list is generous and
# a miss costs nothing. One filter here relaxes BOTH the target count and the
# store_test_cases coverage validator, since both read this walker.
_RESTING_STATE_NAMES = {
    "default", "resting", "rest", "normal", "initial", "idle",
    "static", "base", "none", "neutral", "inactive", "unset",
}

def _is_resting_state(name: str) -> bool:
    """True when a declared state name is a resting/default synonym, so it is
    not worth a coverage target. See _RESTING_STATE_NAMES."""
    return str(name or "").strip().lower() in _RESTING_STATE_NAMES

def _spec_coverage_targets(spec):
    """Walk components_specification and return three coverage-target sets:
      components : {component_id}
      states     : {(component_id, state_name)}   from each node's `states`
      events     : {(component_id, event_name)}   from each node's `events`
    A dict is a ComponentNode when it has BOTH 'id' and 'tag' (the schema).
    Recursion handles arbitrary nesting depth."""
    comps, states, events = set(), set(), set()
    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("id"), str) and "tag" in node:
                cid = node["id"]
                comps.add(cid)
                for st in node.get("states") or []:
                    name = st.get("name") if isinstance(st, dict) else st
                    # Neither a resting state nor a transient one is a target:
                    # the first is true by construction, the second has
                    # already settled when the pipeline reads the page.
                    if (isinstance(name, str) and name and not _is_resting_state(name)
                            and not _is_transient_state(name)):
                        states.add((cid, name))
                for ev in node.get("events") or []:
                    # ComponentEvent's canonical field is `event`; older/raw specs use
                    # `name`. Read both so coverage also works against model_dump()
                    # output (a canonical dump keys events as `event`, not `name`).
                    name = (ev.get("event") or ev.get("name")) if isinstance(ev, dict) else ev
                    if isinstance(name, str) and name:
                        events.add((cid, name))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for it in node:
                walk(it)
    walk(spec)
    return comps, states, events

def _as_whole_number(value):
    """value as an int when it is a whole number (3, '3'), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None

def _data_start_values(spec) -> dict:
    """component id -> (number, source): the number a data-bound component
    shows BEFORE any interaction, read from the components specification's own
    dataSets. The one place a count's starting value is computed (speed-cost
    ticket 01).

    Two binding shapes yield one number:
      'set.field'  the set holds exactly ONE record and that field is a whole
                   number (cartSummary.itemCount = 3).
      'set'        with format 'count': the sum of the records' 'quantity'
                   when every record has one, else the number of records.
    Anything else (a field of a many-record list, a price, a rendered list)
    is not one starting number and is left out.

    Why: on PO-08 4fb17fbe the spec started the cart at 3, TC-059 expected '1'
    after one add, the page correctly read '4', and the correction round
    hard-coded '1' into the page to make the test pass.
    """
    spec = _coerce_spec(spec or {}) or {}
    if not isinstance(spec, dict):
        return {}
    data_sets = spec.get("dataSets")
    if not isinstance(data_sets, dict):
        return {}
    out = {}

    def _start(binding):
        if not isinstance(binding, dict) or not isinstance(binding.get("source"), str):
            return None
        source = binding["source"].strip()
        name, _, field = source.partition(".")
        records = data_sets.get(name)
        if not isinstance(records, list):
            return None
        fmt = str(binding.get("format") or "").strip().lower()
        if field:
            # A whole-number price or rating is not a count.
            if fmt not in ("", "count"):
                return None
            if len(records) != 1 or not isinstance(records[0], dict):
                return None
            return _as_whole_number(records[0].get(field))
        if fmt != "count":
            return None
        qty = [_as_whole_number(r.get("quantity")) if isinstance(r, dict) else None
               for r in records]
        return sum(qty) if qty and all(q is not None for q in qty) else len(records)

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("id"), str):
                n = _start(node.get("dataBinding"))
                if n is not None:
                    out[node["id"]] = (n, node["dataBinding"]["source"].strip())
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for it in node:
                walk(it)
    walk(spec.get("pages"))
    return out

# updateData modes that only ever move a count one way. Any other mode
# (filteredCount, set, ...) can rewrite it to any number.
_COUNT_UP_MODES   = {"increment", "increase", "add"}
_COUNT_DOWN_MODES = {"decrement", "decrease", "remove", "subtract"}

def _count_directions(intx) -> dict:
    """component id -> 'up' | 'down': the way every interaction_specification
    flow moves this component's number, read from the updateData actions that
    target it. 'up' when every such action increments it, 'down' when every
    one decrements it; a component moved both ways, or by any other mode, is
    left out (no direction can be proved). The guard in store_test_cases
    reads it: after a click an only-incremented count is above its start."""
    intx = _coerce_spec(intx or {}) or {}
    if not isinstance(intx, dict):
        return {}
    modes = {}
    for page in intx.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for flow in page.get("flows") or []:
            if not isinstance(flow, dict):
                continue
            for act in flow.get("actions") or []:
                if not isinstance(act, dict) or act.get("type") != "updateData":
                    continue
                cid = act.get("targetId")
                payload = act.get("payload") if isinstance(act.get("payload"), dict) else {}
                if isinstance(cid, str) and "mode" in payload:
                    modes.setdefault(cid, set()).add(str(payload["mode"]).strip().lower())
    out = {}
    for cid, ms in modes.items():
        if ms <= _COUNT_UP_MODES:
            out[cid] = "up"
        elif ms <= _COUNT_DOWN_MODES:
            out[cid] = "down"
    return out

# A count expectation's number: exactly one whole number in the text
# ('4', 'Cart (4)'). '3 of 12' or '$54.50' is not one count and is left alone.
_ONE_NUMBER_RE = re.compile(r"^\D*(\d+)\D*$")

def _spec_selector_map(spec) -> dict:
    """component id -> the selector the Selector Contract requires:
    '.<className>' when the ComponentNode declares one, else '#<id>'.
    Same ComponentNode test as _spec_coverage_targets (has BOTH 'id' and 'tag')."""
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
    walk(spec)
    return out

def _spec_component_names(spec) -> set:
    """Every ComponentNode id anywhere in components_specification (component
    coverage target). Kept as a thin wrapper over _spec_coverage_targets so
    callers/tests that only need the component set are unaffected."""
    return _spec_coverage_targets(spec)[0]

def _decoration_styles_for(deco_spec, component):
    """(baseStyles, [(stateName, styles), ...]) for one component, from
    DecorationSpecification. Returns ({}, []) when the component is absent.

    Used by the covers_state guard: a style value that only exists inside a
    stateVariant cannot be observed on the resting page, so a case asserting it
    must be tagged so _order_test_cases runs it AFTER the transition.
    """
    spec = _coerce_spec(deco_spec or {}) or {}
    if not isinstance(spec, dict):
        return {}, []
    for page in spec.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for d in page.get("componentDecorations") or []:
            if not isinstance(d, dict):
                continue
            if component not in (d.get("componentId"), d.get("className")):
                continue
            variants = []
            for v in d.get("stateVariants") or []:
                if isinstance(v, dict) and isinstance(v.get("styles"), dict):
                    name = str(v.get("stateName") or "").strip()
                    if name:
                        variants.append((name, v["styles"]))
            return (d.get("baseStyles") or {}), variants
    return {}, []


def _state_attribute_for(state: str):
    """(attribute, active value) the State Materialization Contract requires.

    Single source of truth shared with store_html_code's guard via _ARIA_STATES,
    so the attribute Test Generation asserts and the attribute the HTML agent
    emits cannot drift apart. E2E-SO-01 is what happens when they do: the page
    shipped aria-disabled and the suite asserted data-state, so a correct page
    failed a correct-looking test and the HTML agent "fixed" it by hardcoding
    data-state="disabled" -- which made the button render greyed out forever and
    turned the test vacuous.
    """
    s = (state or "").strip()
    return (f"aria-{s}", "true") if s in _ARIA_STATES else ("data-state", s)



def _flow_produced_states(intx) -> set:
    """(componentId, toState) pairs some interaction flow PRODUCES via its
    stateTransitions -- the states a click/type can actually bring about, and so
    the only declared states the click/type-only pipeline can stage for a
    covers_state assertion. A state absent here (a header that only goes compact
    on scroll, a banner's decorative highlight) cannot be reached, so coverage
    must not demand a case for it. Structure-agnostic: finds every
    `stateTransitions` list at any depth."""
    produced = set()
    def walk(node):
        if isinstance(node, dict):
            for st in node.get("stateTransitions") or []:
                if isinstance(st, dict):
                    cid, nm = st.get("componentId"), st.get("toState")
                    if isinstance(cid, str) and isinstance(nm, str) and nm:
                        produced.add((cid, nm))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(intx)
    return produced


@tool
def store_test_cases(test_cases: list, runtime: ToolRuntime[TestGenState]) -> Command:
    """
    Store a BATCH of generated test cases into agent state.

    Generation is CHUNKED: call this as many times as needed (one batch per
    page/region). Batches ACCUMULATE — the test_cases state field has a
    dedup-by-id reducer, so a new id is appended and a re-sent id replaces its
    earlier version. Keep calling until the returned message says "SUITE COMPLETE".

    Each item must be a dict with the 7 required keys:
      id, component, description, action, selector, expected, passed.
    component MUST be a node's exact id from components_specification, and
    selector MUST follow the Selector Contract: '.<className>' when that node
    declares a className, else '#<id>'. Both are enforced here, not just asked
    for -- a batch that breaks either is REJECTED and nothing is saved.
    Optional keys:
      viewport     : "<width>x<height>" in px (responsive cases only)
      covers_state : a declared state name this case exercises (drives state coverage)
      covers_event : a declared event name this case exercises (drives event coverage)
      input        : the text a `type` case fills in. Without it the pipeline
                     fills a fixed literal that matches no product, so a search
                     or filter case cannot distinguish a working page from a
                     dead one.
      press        : a key a `type` case presses after filling, e.g. "Enter".
                     Use it whenever the behaviour under test runs on submit.
    Valid action values: assert_visible, assert_text, assert_css, assert_hover_css,
      assert_attribute, assert_url, assert_count, click, type.
    For assert_css / assert_hover_css: expected is pipe-separated 'property=value'
      pairs, e.g. "background-color=#1a73e8|color=#ffffff".
    For assert_attribute: expected is 'attribute=value' (value may be empty for a
      presence-only check, e.g. 'disabled=').
    For assert_url: expected is a substring the current page URL must contain.
    For assert_count: expected is a comparator and a whole number, e.g. '>=1',
      '=8', '<4'. It counts how many elements the selector matches. Tag it
      covers_event (or covers_state) when the count is meant to change after a
      click, so it runs AFTER the interaction rather than against the resting page.

    Coverage is checked over the ACCUMULATED suite (not just this batch): every
    component in components_specification, every declared state (via covers_state),
    and every declared event (via covers_event) must have >= 1 case. An event
    additionally needs an ASSERTION on the same component -- a lone click or type
    case reports success whenever the element exists, so it cannot show that the
    page reacted. A batch with a
    schema/format error is REJECTED (nothing saved) — fix and resend it. A
    well-formed but coverage-incomplete batch IS saved, and the message lists what
    is still uncovered so the next batch can fill the gaps.
    """
    def _reject(msg):
        return Command(update={"messages": [ToolMessage(
            content=msg, tool_call_id=runtime.tool_call_id)]})

    if not isinstance(test_cases, list):
        return _reject(f"test_cases must be a list. Received: {type(test_cases).__name__}")

    required_keys = {"id", "component", "description", "action", "selector", "expected", "passed"}
    for i, tc in enumerate(test_cases):
        if not isinstance(tc, dict):
            return _reject(f"Test case at index {i} must be a dict. Got: {type(tc).__name__}")
        missing = required_keys - set(tc.keys())
        if missing:
            return _reject(f"Test case at index {i} missing required keys: {sorted(missing)}")
        if tc["action"] not in VALID_ACTIONS:
            return _reject(f"Test case at index {i} has invalid action: '{tc['action']}'."
                           f" Must be one of: {sorted(VALID_ACTIONS)}")
        if tc["action"] in ("assert_css", "assert_hover_css"):
            for pair in tc["expected"].split("|"):
                if "=" not in pair:
                    return _reject(
                        f"Test case {tc['id']}: {tc['action']} expected must be pipe-separated "
                        f"'property=value' pairs (e.g. 'background-color=#fff|color=#000'). "
                        f"Got: '{tc['expected']}'")
        if tc["action"] == "assert_count":
            if not _COUNT_EXPECTED_RE.match(str(tc["expected"]).strip()):
                return _reject(
                    f"Test case {tc['id']}: assert_count expected must be a comparator "
                    f"and a whole number, e.g. '>=1', '=8', '<4'. Got: '{tc['expected']}'")
        if tc["action"] == "assert_attribute" and "=" not in tc["expected"]:
            return _reject(
                f"Test case {tc['id']}: assert_attribute expected must be 'attribute=value' "
                f"(value may be empty for presence-only, e.g. 'disabled='). Got: '{tc['expected']}'")
        vp = str(tc.get("viewport") or "")
        if vp:
            _parts = vp.lower().split("x")
            if len(_parts) != 2 or not all(p.strip().isdigit() for p in _parts):
                return _reject(
                    f"Test case {tc['id']}: viewport must be '<width>x<height>' in pixels "
                    f"(e.g. '375x812'). Got: '{vp}'")
        for _tag in ("covers_state", "covers_event"):
            if tc.get(_tag) is not None and not isinstance(tc.get(_tag), str):
                _kind = "state" if _tag == "covers_state" else "event"
                return _reject(
                    f"Test case {tc['id']}: {_tag} must be a string naming a declared {_kind}. "
                    f"Got: {type(tc[_tag]).__name__}")
        for _k in ("input", "press"):
            if tc.get(_k) is not None and not isinstance(tc.get(_k), str):
                return _reject(
                    f"Test case {tc['id']}: {_k} must be a string. "
                    f"Got: {type(tc[_k]).__name__}")
        if (tc.get("input") or tc.get("press")) and tc["action"] != "type":
            return _reject(
                f"Test case {tc['id']}: 'input' and 'press' apply only to a 'type' "
                f"action. Got action='{tc['action']}'. Drop them, or change the action.")
        _press = str(tc.get("press") or "").strip()
        if _press and _press not in VALID_KEYS:
            return _reject(
                f"Test case {tc['id']}: press must be one of {sorted(VALID_KEYS)}. "
                f"Got: '{_press}'")
        # This system builds ONE page; a nav click SCROLLS to a section, it
        # never loads a new document, so the URL only ever gains a '#<id>'
        # fragment. An assert_url expecting a label word ('shop') or the page
        # name can therefore never pass -- PO-06 shipped a dozen of exactly
        # those on 2026-08-23. The fragment is the guarantee the model cannot
        # guess its way around.
        if tc["action"] == "assert_url":
            _url_exp = str(tc.get("expected") or "").strip()
            if not _url_exp.startswith("#"):
                return _reject(
                    f"Test case {tc['id']}: assert_url in this single-page build "
                    f"must expect a URL fragment that begins with '#' -- the id of "
                    f"the section the click scrolls to, e.g. '#product-listing', "
                    f"taken from the layout region id the link targets. The "
                    f"whole-page URL never contains a label word or the page name. "
                    f"Got: '{_url_exp}'")
            # The fragment only appears AFTER the link is clicked, and the
            # pipeline clicks this case's own selector before reading the
            # URL. An assert_url with no selector would click nothing, so
            # the URL would keep its fragment-free opening value and the
            # case could never pass -- the other half of the po0142c544 dead
            # assert_url cases.
            _url_sel = str(tc.get("selector") or "").strip()
            if not _url_sel:
                return _reject(
                    f"Test case {tc['id']}: assert_url must name, in its "
                    f"selector, the nav link or CTA to click -- the pipeline "
                    f"clicks the selector, then checks the URL gained the "
                    f"'#<id>' fragment. Give the link's selector (e.g. "
                    f"'#hdr_listing_link'), not an empty selector.")

    # Coerce the spec BEFORE the contract pass -- both the Selector Contract check
    # and the coverage check need it, and a bad spec must reject without saving.
    spec = _coerce_spec(runtime.state.get("components_specification") or {})
    if spec is None:
        return _reject(
            "[INTERNAL] components_specification is a string that is not valid JSON, "
            "so the coverage check cannot run. This is a pipeline configuration error, "
            "not a defect in the test suite. Report it in your final message and stop.")

    # ── Naming + Selector Contract (Python-enforced since 2026-08-08) ─────────
    # Both were PROMPT-ONLY before. Nothing downstream catches a breach either:
    # a wrong selector makes the pipeline report "not found", _route_agent
    # OVERRIDES that to html_agent, and a developer agent is sent to fix a page
    # that was never broken -- spending one of only TWO correction attempts.
    # The mapping is derived from the same component tree the coverage targets
    # come from, so the guard costs one extra walk. Skipped when there is no
    # components_specification to check against (the degenerate-spec path).
    sel_map = _spec_selector_map(spec)
    if sel_map:
        for i, tc in enumerate(test_cases):
            comp = tc["component"]
            if comp not in sel_map:
                return _reject(
                    f"Test case {tc['id']}: component '{comp}' is not in "
                    f"components_specification. 'component' must be a node's EXACT id. "
                    f"Known ids: {sorted(sel_map)}")
            want = sel_map[comp]
            if tc["selector"] != want:
                return _reject(
                    f"Test case {tc['id']}: Selector Contract violation for '{comp}'. "
                    f"selector must be '{want}' ('.className' when the node declares one, "
                    f"else '#id'). Got: '{tc['selector']}'")

    # ── Transient-state assertions are unreadable, so reject them (2026-09-05) ─
    # An in-flight value (adding, loading, saving, ...) reverts on its own, so
    # by the time the pipeline reads the attribute the value has already
    # settled to the stable end-state. Asserting it fails against a correct
    # page -- a timing false failure, not a page bug (PO-10 TC-056). The prompt
    # already asks for the stable end-state; this is the Python backstop for
    # when the model still emits one.
    #
    # Two ways in, both refused. A case TAGGED with a transient covers_state is
    # refused whatever its action (ticket 02): the tag is the claim that the
    # case observes the in-flight moment, and no action can. Checking only
    # assert_attribute let PO-08 4fb17fbe TC-065 through as assert_css. An
    # UNTAGGED assert_attribute whose value is transient is refused too.
    for tc in test_cases:
        _tst = str(tc.get("covers_state") or "").strip()
        if _is_transient_state(_tst):
            return _reject(
                f"Test case {tc['id']}: covers_state='{_tst}' is a TRANSIENT / "
                f"in-flight state that reverts on its own, so no action can "
                f"observe it: by the time the pipeline reads the page it has "
                f"settled, and the case fails against a correct page whatever "
                f"its action ({tc['action']}). It is not a coverage target. "
                f"Assert the STABLE end-state the interaction settles into "
                f"instead (e.g. 'added', 'saved', 'done', 'sent'), tagged with "
                f"that state, or drop this case.")
        if tc["action"] != "assert_attribute":
            continue
        _tval = tc["expected"].split("=", 1)[-1].strip().lower()
        if _tval in _TRANSIENT_STATES:
            return _reject(
                f"Test case {tc['id']}: '{_tval}' is a TRANSIENT / in-flight "
                f"state that reverts on its own, so the pipeline reads the "
                f"settled value and the assertion fails against a correct page. "
                f"Assert the STABLE end-state instead (e.g. 'added', 'saved', "
                f"'done', 'sent'). Got: '{tc['expected']}'.")

    # ── State Materialization Contract for assertions (2026-08-09) ───────────
    # Both guards come straight out of E2E-SO-01. See _state_attribute_for.
    for tc in test_cases:
        st = str(tc.get("covers_state") or "").strip()

        # B. A tagged assert_attribute must name the attribute the contract picks
        #    for that state, asserting its ACTIVE value -- the case runs after the
        #    transition, so the resting value would be wrong by construction.
        if tc["action"] == "assert_attribute" and st and st not in _PSEUDO_STATES:
            _attr, _ = tc["expected"].partition("=")[0], None
            _got_attr = tc["expected"].split("=", 1)[0].strip()
            _got_val  = tc["expected"].split("=", 1)[1].strip()
            _want_attr, _want_val = _state_attribute_for(st)
            if _got_attr != _want_attr or _got_val.lower() != _want_val.lower():
                return _reject(
                    f"Test case {tc['id']}: State Materialization Contract violation. "
                    f"covers_state='{st}', so the assertion must be "
                    f"'{_want_attr}={_want_val}' -- that is the attribute the HTML "
                    f"agent emits for this state and the one the JS agent toggles. "
                    f"Got: '{tc['expected']}'. Asserting any other attribute fails "
                    f"against a correct page.")

        # A. A style value that exists ONLY inside a stateVariant is invisible on
        #    the resting page. _order_test_cases puts an untagged case in phase 0,
        #    before any click, so it can never pass.
        if tc["action"] == "assert_css":
            _base, _variants = _decoration_styles_for(
                runtime.state.get("decoration_specification"), tc["component"])
            for _pair in tc["expected"].split("|"):
                _p, _, _v = _pair.partition("=")
                _p, _v = _p.strip().lower(), _v.strip().lower()
                # The tagged state's own variant carries this value: the case
                # is correctly tagged, whatever other variant shares the value.
                # Checked first, because the loop below would otherwise refuse
                # it on a sibling variant (e.g. 'loading' and 'added' both
                # white), and for a transient sibling no tag could satisfy it.
                if any(_sname == st
                       and str(_styles.get(_p, "")).strip().lower() == _v
                       for _sname, _styles in _variants):
                    continue
                for _sname, _styles in _variants:
                    if _sname in _PSEUDO_STATES:
                        continue          # hover/focus belong to assert_hover_css
                    _sv = str(_styles.get(_p, "")).strip().lower()
                    if not _sv or _sv != _v:
                        continue
                    if str(_base.get(_p, "")).strip().lower() == _v:
                        continue          # same at rest, so not state-derived
                    if st == _sname:
                        continue          # correctly tagged
                    if _is_transient_state(_sname):
                        # Tagging it would only meet the transient refusal
                        # above, so never advise the tag (ticket 02).
                        return _reject(
                            f"Test case {tc['id']}: '{_p}={_v}' is the "
                            f"'{_sname}' stateVariant value for "
                            f"'{tc['component']}', and '{_sname}' is a "
                            f"TRANSIENT / in-flight state that reverts on its "
                            f"own, so no case can observe it. Assert the "
                            f"STABLE end-state the interaction settles into "
                            f"instead, or the resting value "
                            f"'{_base.get(_p, '(unset)')}' untagged.")
                    return _reject(
                        f"Test case {tc['id']}: '{_p}={_v}' is the '{_sname}' "
                        f"stateVariant value for '{tc['component']}', not its "
                        f"resting value. Tag this case covers_state='{_sname}' so "
                        f"it runs AFTER the transition, or assert the resting "
                        f"value '{_base.get(_p, '(unset)')}' instead. Untagged, it "
                        f"runs against the resting page and cannot pass.")

    # A count starts from the spec's own data (speed-cost ticket 01). PO-08
    # 4fb17fbe TC-059 expected '1' after one add on a cart the spec started at
    # 3, and the correction round hard-coded '1' into a correct page.
    #
    # Only a PROVABLE error is refused. An untagged case runs on the resting
    # page, before any click, so it reads the start. After a click the exact
    # number is not provable: a group reset reloads the page but keeps its
    # localStorage, so an earlier group's add can still be in the cart, and a
    # filter can rewrite a results count to anything. What is provable is the
    # direction, when every flow moves the count one way (_count_directions):
    # an only-incremented count is above its start, an only-decremented one
    # below it. Anything else after a click is left to the model.
    _starts = _data_start_values(spec)
    _ways = _count_directions(runtime.state.get("interaction_specification"))
    for tc in test_cases:
        if tc["action"] != "assert_text" or tc["component"] not in _starts:
            continue
        _m = _ONE_NUMBER_RE.match(str(tc["expected"]))
        if not _m:
            continue
        _got = int(_m.group(1))
        _n0, _src = _starts[tc["component"]]
        _after = bool(tc.get("covers_event") or tc.get("covers_state"))
        _way = _ways.get(tc["component"])
        _base = (f"Test case {tc['id']}: '{tc['component']}' starts at {_n0}, read "
                 f"from the components specification (dataSets {_src}), and "
                 f"expected '{tc['expected']}' ignores that starting data. ")
        if not _after:
            if _got != _n0:
                return _reject(
                    _base + f"This case is not tagged covers_event / covers_state, "
                    f"so it runs on the resting page, before any click: expect "
                    f"{_n0}. To check the number after a click, tag it with the "
                    f"event.")
        elif _way == "up" and _got <= _n0:
            return _reject(
                _base + f"Every flow in the interaction specification increments "
                f"it, so after an add it is more than {_n0}: expect {_n0 + 1} "
                f"for one add.")
        elif _way == "down" and _got >= _n0:
            return _reject(
                _base + f"Every flow in the interaction specification decrements "
                f"it, so after a remove it is less than {_n0}: expect {_n0 - 1} "
                f"for one remove.")

    # Accumulated suite = what is already in state + this batch (dedup by id).
    accumulated = _merge_test_cases(runtime.state.get("test_cases", []), test_cases)
    saved, total = len(test_cases), len(accumulated)
    save_update = {"test_cases": test_cases}   # the reducer appends this batch

    # Coverage over the ACCUMULATED suite against the enriched spec target.
    comp_targets, state_targets, event_targets = _spec_coverage_targets(spec)

    if comp_targets:
        covered_comps  = {tc["component"] for tc in accumulated}
        covered_states = {(tc["component"], tc["covers_state"])
                          for tc in accumulated if tc.get("covers_state")}
        # An event is covered only when the accumulated suite ALSO asserts
        # something about the same component. Before this rule a single
        # `click` tagged covers_event closed the gap and the tool reported
        # SUITE COMPLETE, even though the click branch cannot fail on a button
        # that does nothing. The trigger and the outcome are now both required.
        asserted_comps = {tc["component"] for tc in accumulated
                          if tc["action"] in _ASSERTING_ACTIONS}
        covered_events = {(tc["component"], tc["covers_event"])
                          for tc in accumulated if tc.get("covers_event")
                          and tc["component"] in asserted_comps}
        miss_comps  = comp_targets  - covered_comps
        miss_states = state_targets - covered_states
        # A state no interaction flow PRODUCES cannot be staged by the click/type-only
        # pipeline (a header that only goes compact on scroll, a banner's decorative
        # highlight): demanding a covers_state case for it is a guard the model cannot
        # satisfy -- it loops, or ships a case that fails on every run. When the run
        # provides an interaction spec, keep only the states some flow can produce; with
        # none (older unit fixtures) the demand is unchanged.
        _intx_raw = runtime.state.get("interaction_specification") or {}
        if isinstance(_intx_raw, str):
            try: _intx_raw = json.loads(_intx_raw)
            except Exception: _intx_raw = {}
        if isinstance(_intx_raw, dict) and _intx_raw:
            _producible = _flow_produced_states(_intx_raw)
            miss_states = {(c, st) for (c, st) in miss_states if (c, st) in _producible}
        miss_events = event_targets - covered_events
        if miss_comps or miss_states or miss_events:
            parts = [f"Saved {saved} test case(s) (suite now {total}). Coverage INCOMPLETE — keep going:"]
            if miss_comps:
                parts.append(f"  components with no test: {sorted(miss_comps)}")
            if miss_states:
                parts.append("  states not yet covered (add a case tagged covers_state): "
                             + str(sorted(f"{c}:{s}" for c, s in miss_states)))
            if miss_events:
                parts.append("  events not yet covered (add a case tagged covers_event): "
                             + str(sorted(f"{c}:{e}" for c, e in miss_events)))
                _triggered = {(tc["component"], tc["covers_event"])
                              for tc in accumulated if tc.get("covers_event")}
                _no_assert = sorted(f"{c}:{e}" for c, e in (miss_events & _triggered))
                if _no_assert:
                    parts.append(
                        "  of those, these already have a click/type case but NO "
                        f"assertion on the same component: {_no_assert}. A click "
                        "passes whenever the element exists, so on its own it "
                        "proves nothing happened. Add an assertion case for the "
                        "same component -- assert_text on what the click changed, "
                        "or assert_attribute on the state it set.")
            parts.append("Send another store_test_cases batch covering the items above. "
                         "Earlier batches are retained — do NOT resend them.")
            save_update["messages"] = [ToolMessage(
                content="\n".join(parts), tool_call_id=runtime.tool_call_id)]
            return Command(update=save_update)
        done = (f"Saved {saved} test case(s) (suite now {total}). SUITE COMPLETE — every component, "
                f"state, and event in the spec is covered. Stop calling store_test_cases.")
    else:
        done = (f"Saved {saved} test case(s) (suite now {total}). No components_specification to "
                f"check coverage against — SUITE COMPLETE. Stop calling store_test_cases.")

    save_update["messages"] = [ToolMessage(content=done, tool_call_id=runtime.tool_call_id)]
    return Command(update=save_update)


# ==========================================================================
# System Prompt
# ==========================================================================
_test_gen_system_prompt = """
You are a specialized Test Generation Agent for a B2C e-commerce web application. Generate a comprehensive structured test suite from the provided specifications.

Your ONLY output is `store_test_cases` tool calls. Never write a text response or explain your reasoning.

## Context
You receive:
- `user_query`: original user requirement
- `layout_specification`: page structure and component placement
- `components_specification`: component tree; each node has a stable `id`, `tag`, optional `className`, and optional `states` / `events`
- `interaction_specification`: triggers, actions, and state transitions
- `decoration_specification`: base styles, state variants, and responsive breakpoints

The HTML agent renders `className` as the class attribute when present; otherwise it renders the node `id` as the id attribute. Declared states materialize as `aria-*` / `data-state` attributes.

## Output and chunking
Generate the suite in BATCHES and call `store_test_cases` repeatedly. A page or region per batch is a good rhythm. Saved batches accumulate through deduplication by test-case id, so never resend a batch already saved.

After every call, read the returned message:
- `"Coverage INCOMPLETE"`: send ONE additional batch covering only the listed missing components, states, and events.
- `"SUITE COMPLETE"`: stop immediately.
- Schema/format error: that batch was not saved; fix and resend it.

Continue until `"SUITE COMPLETE"`.

## Test-case schema
Every case has these 7 required keys and may use the 5 optional keys shown below:
{
  "id":           "TC-001",
  "component":    "<ComponentNode id from components_specification>",
  "description":  "<what is being verified>",
  "action":       "<assert_visible | assert_text | assert_css | assert_hover_css | assert_attribute | assert_url | assert_count | click | type>",
  "selector":     "<'.<className>' if the node defines className, else '#<id>'>",
  "expected":     "<expected result after the action>",
  "passed":       null,
  "viewport":     "<OPTIONAL: '<width>x<height>' in px, e.g. '375x812' — responsive checks only>",
  "covers_state": "<OPTIONAL: declared state exercised by this case>",
  "covers_event": "<OPTIONAL: declared event exercised by this case>",
  "input":        "<OPTIONAL, `type` only: exact text to fill>",
  "press":        "<OPTIONAL, `type` only: Enter | Tab | Escape | Backspace | ArrowUp | ArrowDown | ArrowLeft | ArrowRight>"
}
VALID action values ONLY: assert_visible, assert_text, assert_css, assert_hover_css, assert_attribute, assert_url, assert_count, click, type.
`passed` is ALWAYS `null`.

## Selector Contract
For every component:
- `component` = the node's EXACT `id` from `components_specification`
- `selector` = `'.<className>'` if that node sets `className`, otherwise `'#<id>'`

Never invent component names, ids, or classes not present in the specification.

## JOIN-BY-KEY analysis
Associate data by stable component id, never by free-form similarity.
For component id `X` with optional className `C`:
- Components: read `X`'s own `states[]` and `events[]`.
- Selector: `.C` if className exists, otherwise `#X`.
- Decoration: in `decoration_specification.pages[].componentDecorations[]`, use only the entry whose `componentId == X`. Use `baseStyles` for `assert_css` and `stateVariants[]` for state styling / `assert_hover_css`.
- Interaction: in `interaction_specification.pages[].flows[]`, use flows whose `trigger.targetId == X`. From their `stateTransitions[]`, use entries whose `componentId == X` to obtain the expected `toState`.
- Layout: locate `X` by id/name in `layout_specification` to determine its page and region.

Ignore entries that do not belong to `X`. This key join prevents one component's style or state from being attached to another.

## Coverage requirements
Cover:
- every component
- every state an `interaction_specification` flow produces (its `stateTransitions[].toState`); a state no flow produces is not required, per Grounded state assertions
- every declared event
- every trigger in `interaction_specification`

When the run supplies NO `interaction_specification` at all, no producing flow is knowable; fall back to covering every declared state (tag each with `covers_state`), which is what the coverage guard still requires in that case.

A declared state counts only when a case has `covers_state="<state>"`.
A declared event counts only when a case has `covers_event="<event>"`.
An untagged case does not satisfy state/event coverage.

## Events require trigger + outcome
Every event needs BOTH:
1. a trigger case such as `click` or `type`, tagged with `covers_event`
2. an assertion on the SAME component demonstrating the resulting observable effect

A lone `click` / `type` proves only that the element exists and can be acted on.
Use a grounded `assert_text`, `assert_attribute`, `assert_count`, or other supported assertion for the outcome. Never invent an effect that is absent from the specifications.
If no spec-defined observable DOM change exists, do not fabricate one. Test the grounded trigger and only use assertions that can be derived from the supplied specifications.

## LIVE-VALUE rule
When an event changes a numeric live value such as:
- cart item count
- subtotal
- order total
- result count

assert THAT value's own element after the interaction. The test must fail if the number remains unchanged.
Use `assert_text` on the displayed value or `assert_count` on the elements that directly represent it; do not merely verify that some related element exists.

## `type` rules
Every `type` case must include `input`.
Use real text from the specifications, such as an actual product name for search or an actual category for filtering.
Add `press: "Enter"` when the behavior runs on submit rather than on each keystroke.
Target the actual `<input>` or `<textarea>`, never its form, label, wrapper, or submit button.
Pair every `type` case with a post-interaction assertion proving the page reacted.

## `assert_count` rules
`assert_count` is the only count-based outcome check.
Set `expected` to a comparator plus integer, e.g.:
- `">=1"`
- `"=8"`
- `"<4"`

Examples:
- cart line exists after Add to cart: `">=1"`, tagged `covers_event`
- filtered grid shrank: `"<8"`, tagged `covers_event`
- eight product cards exist at rest: `"=8"`, untagged

If the count is only true AFTER an interaction, tag the case with `covers_event` or `covers_state`. An untagged count executes against the resting page.

## Grounded state assertions
Derive state-transition assertions from `interaction_specification.stateTransitions` plus the State Materialization Contract:
A declared state materializes as:
- `aria-<state>`
- or `data-state` containing the state name

For `assert_attribute`, use `attribute=value`; `disabled=` means presence-only.
Never invent an unspecified transition or DOM effect.
A component's RESTING/default state (data-state=default, an aria-* of false, or a value like idle/closed/collapsed) is a BASELINE fact, not a transition. Assert it WITHOUT covers_state so it runs before any interaction and reads the page as delivered. Tag covers_state ONLY on the state an interaction PRODUCES (active, added, open, expanded, selected). Tagging a resting-state assertion as covers_state pushes it after the clicks, where the resting value is already gone, and it then fails for no real defect.
A TRANSIENT / in-flight state -- adding, loading, saving, submitting, sending, pending, processing -- exists only for the moment an action is running and reverts to a stable end-state on its own. An assertion racing to catch it is timing-dependent: by the time the pipeline reads the attribute the state has usually already settled, so the case fails with no real defect (po015df552 TC-057, `adding`). Assert only the STABLE end-state the interaction settles into (added, saved, sent, done, or the resting default). Never assert a transient state, and never tag one with covers_state.
A declared state that NO flow produces is not a coverage target and usually cannot be staged: if it is a hover or focus visual, check it with `assert_hover_css` against its `stateVariant`; if it is a load condition specific elements already show (a sold-out card, a disabled button), assert it WITHOUT `covers_state` and target that element by its `id`, not a shared `className`; if only scrolling or a timer produces it, emit no case -- the pipeline cannot reach it.
If a component is created dynamically by JavaScript, such as a toast, modal, or dropdown, reach it through the interaction that creates it. Do NOT `assert_visible` for it on initial page load.

## CSS and responsive assertions
Use `decoration_specification.baseStyles` for `assert_css`.
For `assert_css`, set `expected` to pipe-separated `property=value` pairs, e.g.:
`background-color=#1a73e8|color=#ffffff`
Copy each value VERBATIM from the decoration spec. Never compute or convert it: if the spec says `1.2rem`, write `1.2rem`, not the `19.2px` you calculated. The pipeline resolves relative units, `var()` tokens, transforms, and re-serialised shorthands (box-shadow, background, font, transition) to the browser's computed form before comparing, so an invented absolute value only produces a false failure the correction loop can never win.
Use `stateVariants` for hover/focus/state styling, including `assert_hover_css`.
Use optional `viewport` only for responsive checks.

## Navigation / `assert_url`
Emit ONE `assert_url` case per navigation link or CTA. Do NOT emit a separate `click` case for that URL check.
The pipeline automatically clicks the case's `selector` before reading the URL.
Therefore:
- `selector` must be the nav link / CTA itself using the Selector Contract
- selector must be non-empty
- `expected` must be the exact `#<section-id>` href target, e.g. `#product-listing`

This build is ONE page only. Navigation only adds a `#fragment`; it never loads another document.
Never use a label such as `"shop"` or the page name as `expected`. Any non-`#` expected value is invalid.

## Automatic execution order
Write all required trigger and assertion cases; do not manually manage their list order.
The pipeline automatically reorders the suite so all `click` / `type` actions run before cases tagged `covers_state`. Cases that must inspect the resting page run before those interactions.

## Generation categories
For each page/region, generate relevant cases for:
- Structural: `assert_visible`
- Content: `assert_text`
- Interactive: `click` / `type` plus grounded outcome assertions
- Style: `assert_css`
- Responsive: `assert_visible` / `assert_css` with `viewport`
- State variants: `assert_hover_css`
- State transitions: trigger plus `assert_attribute`, tagging declared event/state coverage
- Navigation: `assert_url`

## Edge cases
If all four specifications are empty dicts:
- derive at least 3 generic structural test cases from `user_query`
- call `store_test_cases`
- continue processing tool responses until `"SUITE COMPLETE"`

If `user_query` is empty:
- generate tests from the specifications alone as normal

In all cases, keep calling `store_test_cases` until it returns `"SUITE COMPLETE"`. Never resend a saved batch.
"""


# ==========================================================================
# System Prompt
# ==========================================================================
# Test Gen Agent uses a single static system prompt (_test_gen_system_prompt).
# No dynamic routing needed — update mode has been eliminated.
# The agent is invoked once per session during generation only.


# ==========================================================================
# Streaming progress
# ==========================================================================
@before_agent
def test_gen_agent_progress(state, runtime):
    get_stream_writer()("   [Test Gen Agent] Processing request...")
    return None


def _tg_remaining(state):
    """Count coverage targets still open (components + states + events).

    Reuses the same spec walker and covers-tag logic the store_test_cases
    validator uses, so the progress label agrees with the tool's own verdict.
    Returns 0 when there is no spec (nothing to complete)."""
    spec = _coerce_spec((state or {}).get("components_specification") or {})
    if not spec:
        return 0
    comps, states, events = _spec_coverage_targets(spec)
    tcs   = (state or {}).get("test_cases", []) or []
    cov_c = {t.get("component") for t in tcs}
    cov_s = {(t.get("component"), t.get("covers_state")) for t in tcs if t.get("covers_state")}
    cov_e = {(t.get("component"), t.get("covers_event")) for t in tcs if t.get("covers_event")}
    return len(comps - cov_c) + len(states - cov_s) + len(events - cov_e)


@before_model
def test_gen_before_model_progress(state, runtime):
    # Chunked generation makes several model turns. Label the FIRST generate
    # turn, and each later turn that still has coverage gaps ("Generating more
    # ..."). Stay SILENT once coverage is complete — the wrap-up turn does no
    # more generation, and a guessed label there promises work that never comes
    # (the same lesson the developer-agent progress hooks learned live).
    writer     = get_stream_writer()
    test_cases = (state or {}).get("test_cases", [])
    if not test_cases:
        writer("   [Test Gen Agent] Generating test suite...")
    else:
        _left = _tg_remaining(state)
        if _left:
            writer(f"   [Test Gen Agent] Generating more test cases "
                   f"({len(test_cases)} written, {_left} target(s) left)...")
    return None


@wrap_tool_call
def test_gen_tool_progress(request, handler):
    writer = get_stream_writer()
    tool_name = ""
    try:
        tool_name = (request.tool_call or {}).get("name") or ""
    except Exception:
        tool_name = ""
    if tool_name == "store_test_cases":
        writer("   [Test Gen Agent] Storing test cases...")
    result = handler(request)
    if tool_name == "store_test_cases":
        # The tool's own message is written FOR THE MODEL: saved counts, the exact
        # missing targets, and the instruction to stop. That is far too detailed
        # for a progress stream, so only the finished signal is surfaced here.
        # Mid-run progress is already narrated by test_gen_before_model_progress
        # ("Generating more test cases (N written, M target(s) left)...").
        try:
            content = ""
            if hasattr(result, "update") and isinstance(result.update, dict):
                _msgs = result.update.get("messages") or []
                if _msgs:
                    content = getattr(_msgs[-1], "content", "") or ""
            elif hasattr(result, "content"):
                content = result.content or ""
            if "SUITE COMPLETE" in content:
                writer("   [Test Gen Agent] All test cases have been saved.")
        except Exception:
            pass
    return result

def _build_component_join_sheet(state):
    """Return a per-component join sheet, or '' when there are no components."""
    comp_spec = _coerce_spec((state or {}).get("components_specification") or {}) or {}
    inter     = _coerce_spec((state or {}).get("interaction_specification") or {}) or {}
    decor     = _coerce_spec((state or {}).get("decoration_specification") or {}) or {}
    layout    = _coerce_spec((state or {}).get("layout_specification") or {}) or {}

    nodes = []  # (page, region, node)
    for page in comp_spec.get("pages", []) or []:
        pg = page.get("pageName", "")
        for region, comps in (page.get("regionComponents") or {}).items():
            def walk(n):
                if isinstance(n, dict) and isinstance(n.get("id"), str) and "tag" in n:
                    nodes.append((pg, region, n))
                    for ch in n.get("children") or []:
                        walk(ch)
            for c in comps or []:
                walk(c)
    if not nodes:
        return ""

    dec_by_id = {}
    for page in decor.get("pages", []) or []:
        for d in page.get("componentDecorations") or []:
            if isinstance(d, dict) and d.get("componentId"):
                dec_by_id[d["componentId"]] = d

    flows_by_id = {}
    for page in inter.get("pages", []) or []:
        for f in page.get("flows") or []:
            if not isinstance(f, dict):
                continue
            ids = set()
            if (f.get("trigger") or {}).get("targetId"):
                ids.add(f["trigger"]["targetId"])
            for tr in f.get("stateTransitions") or []:
                if isinstance(tr, dict) and tr.get("componentId"):
                    ids.add(tr["componentId"])
            for cid in ids:
                flows_by_id.setdefault(cid, []).append(f)

    def _ev(ev): return (ev.get("event") or ev.get("name")) if isinstance(ev, dict) else ev
    def _st(st): return st.get("name") if isinstance(st, dict) else st

    starts = _data_start_values(comp_spec)
    directions = _count_directions(inter)

    lines = []
    for pg, region, n in nodes:
        cid = n["id"]
        cls = n.get("className")
        sel = f".{cls}" if cls else f"#{cid}"
        states = [s for s in (_st(s) for s in n.get("states") or []) if s]
        events = [e for e in (_ev(e) for e in n.get("events") or []) if e]
        lines.append(f"- {cid}  (selector {sel}, tag {n.get('tag','')}, page {pg}/{region})")
        if states:
            lines.append(f"    states: {', '.join(states)}")
        if events:
            lines.append(f"    events: {', '.join(events)}")
        if cid in starts:
            n0, src = starts[cid]
            seg = (f"    starts at: {n0} (dataSets {src}): the page shows {n0} "
                   f"before any click")
            way = directions.get(cid)
            if way == "up":
                seg += f"; after an add it is more than {n0} (one add: {n0 + 1})"
            elif way == "down":
                seg += f"; after a remove it is less than {n0} (one remove: {n0 - 1})"
            lines.append(seg)
        d = dec_by_id.get(cid)
        if d:
            base = d.get("baseStyles") or {}
            if base:
                lines.append("    styles(base): " + ", ".join(f"{k}={v}" for k, v in base.items()))
            for sv in d.get("stateVariants") or []:
                if isinstance(sv, dict) and sv.get("stateName"):
                    sty = ", ".join(f"{k}={v}" for k, v in (sv.get("styles") or {}).items())
                    lines.append(f"    styles(state {sv['stateName']}): {sty}")
        for f in flows_by_id.get(cid, []):
            ev = (f.get("trigger") or {}).get("event", "")
            trs = [f"{t.get('fromState') or '*'}->{t.get('toState')}"
                   for t in (f.get("stateTransitions") or [])
                   if isinstance(t, dict) and t.get("componentId") == cid and t.get("toState")]
            seg = f"    interaction: flow '{f.get('name','')}' on {ev}"
            if trs:
                seg += "; state change " + ", ".join(trs) + " (materialize as aria-<toState>/data-state)"
            lines.append(seg)

    return (
        "\n\n## Pre-joined component sheet for THIS run (authoritative)\n"
        "Each component's styling, behavior, and location are already matched to it by id. "
        "Use this instead of scanning the raw specs. Cover every component, state, and event listed.\n\n"
        + "\n".join(lines)
    )


@dynamic_prompt
def test_gen_prompt_selector(request) -> str:
    """Static test-gen prompt + the pre-joined component sheet for this run."""
    state = getattr(request, "state", None) or {}
    return _test_gen_system_prompt + _build_component_join_sheet(state)


# ==========================================================================
# Agent
# ==========================================================================
# Parallel tool calls stay ENABLED here, unlike the three developer agents.
# store_test_cases writes only `messages` and `test_cases`, and both carry a
# reducer -- _merge_test_cases was written for exactly this, accumulating the
# batches of chunked generation and deduping by id. Forcing one batch per turn
# would add turns to the most token-heavy agent and prevent nothing.
_test_gen_model = ChatOpenAI(model="gpt-5.4",
    reasoning=_reasoning_for("test_gen"),
    timeout=120,
    max_retries=2,
    parallel_tool_calls=True)

test_gen_agent = create_agent(
    model=_test_gen_model,
    tools=[store_test_cases],
    middleware=[
        test_gen_prompt_selector,
        test_gen_agent_progress,
        test_gen_before_model_progress,
        test_gen_tool_progress,
    ],
    state_schema=TestGenState,
)


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
