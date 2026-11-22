# Ported from fyp.ipynb cell 71 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the specification repair helpers
#
# All thirteen are pure functions, so every case here runs offline. The last
# case uses a scripted stand-in for the planner rather than the real one, so no
# model is called and nothing is spent.
_RP_CASES = 0

_LAYOUT = {"pages": [{"pageName": "plp", "pageType": "plp", "pageLayoutType": "grid",
                      "regions": [{"name": "header", "ownedBy": "HTML", "layoutType": "flex-row"},
                                  {"name": "main", "ownedBy": "HTML", "layoutType": "grid"}]}]}
_NODE = {"id": "card", "tag": "article", "ownedBy": "HTML",
         "events": [{"event": "click", "flowName": "open-product"}]}

# ── Case 1: a specification arrives in three shapes ─────────────────────────
# It may already be a checked object, a plain dict from the model, or nothing
# at all when a stage has not run yet. All three must be usable.
_obj = _coerce_layout_spec(_LAYOUT)
assert _coerce_layout_spec(_obj) is _obj, "Case 1 FAIL: an object should pass straight through"
assert _coerce_layout_spec(None).pages == [], "Case 1 FAIL: None should become an empty spec"
assert len(_coerce_layout_spec(_LAYOUT).pages) == 1, "Case 1 FAIL: a dict was not accepted"
for _fn in (_coerce_component_spec, _coerce_interaction_spec, _coerce_decoration_spec):
    _fn(None)
_RP_CASES += 1
print("PASS Case 1 - an object, a dict and nothing at all are all accepted")

# ── Case 2: an interaction spec with no page list is not an error ───────────
# The planner legitimately returns an empty object when a page has no
# interactions. Without this the whole run would fail over a page that is
# simply static.
assert _coerce_interaction_spec({}).pages == [], \
    "Case 2 FAIL: an empty interaction spec should mean no interactions, not a crash"
_RP_CASES += 1
print("PASS Case 2 - a page with no interactions is accepted, not refused")

# ── Case 3: every region the layout declares must be filled ────────────────
# A region declared in the layout and missing from the component tree means a
# whole part of the page has nothing in it. The developer agent would build
# around a hole and no linter would notice.
_full = {"pages": [{"pageName": "plp", "regionComponents": {"header": [_NODE], "main": [_NODE]}}],
         "dataSets": {"products": [{"id": "p1", "name": "Sample"}]}}
assert _validate_component_contract_for_downstream(
    _coerce_layout_spec(_LAYOUT), _coerce_component_spec(_full)) is None, \
    "Case 3 FAIL: a complete tree was reported as incomplete"

_missing = {"pages": [{"pageName": "plp", "regionComponents": {"main": [_NODE]}}]}
_msg = _validate_component_contract_for_downstream(
    _coerce_layout_spec(_LAYOUT), _coerce_component_spec(_missing))
assert _msg and "header" in _msg, f"Case 3 FAIL: the empty region was not reported: {_msg}"
_RP_CASES += 1
print("PASS Case 3 - a region left empty by the planner is named in the refusal")

# ── Case 4: a region nobody declared is also reported ──────────────────────
# The reverse mistake. Components placed in a region the layout never declared
# have nowhere to render.
_extra = {"pages": [{"pageName": "plp",
                     "regionComponents": {"header": [_NODE], "main": [_NODE], "sidebar": [_NODE]}}]}
_msg = _validate_component_contract_for_downstream(
    _coerce_layout_spec(_LAYOUT), _coerce_component_spec(_extra))
assert _msg and "sidebar" in _msg, f"Case 4 FAIL: the unknown region was not reported: {_msg}"
_RP_CASES += 1
print("PASS Case 4 - components placed in a region the layout never declared are reported")

# ── Case 5: an event with no flow name is reported ─────────────────────────
# The flow name is how a click on this component finds the behaviour that
# handles it. Without one, the JavaScript agent has an event and no instruction.
_noflow = {"pages": [{"pageName": "plp", "regionComponents": {
    "header": [_NODE],
    "main": [{"id": "btn", "tag": "button", "ownedBy": "HTML",
              "events": [{"event": "click"}]}]}}]}
_msg = _validate_component_contract_for_downstream(
    _coerce_layout_spec(_LAYOUT), _coerce_component_spec(_noflow))
assert _msg and "flowName" in _msg and "btn" in _msg, \
    f"Case 5 FAIL: the unwired event was not reported: {_msg}"
_RP_CASES += 1
print("PASS Case 5 - a click with no behaviour attached is named, with the component id")

# ── Case 6: the refusal never runs away ────────────────────────────────────
# A badly wrong specification can produce hundreds of complaints. The message
# goes into a prompt, so an unbounded list would crowd out the instruction.
_many = {"pages": [{"pageName": "plp", "regionComponents": {"header": [_NODE], "main": [
    {"id": f"n{n}", "tag": "button", "ownedBy": "HTML", "events": [{"event": "click"}]}
    for n in range(40)]}}]}
_msg = _validate_component_contract_for_downstream(
    _coerce_layout_spec(_LAYOUT), _coerce_component_spec(_many))
assert "more issue(s)" in _msg, "Case 6 FAIL: the complaint list was not capped"
assert _msg.count("\n- ") <= 26, f"Case 6 FAIL: {_msg.count(chr(10) + '- ')} lines is too many"
_RP_CASES += 1
print("PASS Case 6 - a badly wrong plan produces a capped message, not hundreds of lines")

# ── Case 7: repair fills in the shape without inventing content ────────────
# This is the line the repair must not cross. It may add the empty region the
# planner forgot to declare. It must not put a component inside it, because
# nothing in the plan says what that component would be.
_repaired = _repair_component_spec_from_layout(_LAYOUT, _missing)
assert set(_repaired["pages"][0]["regionComponents"]) == {"header", "main"}, \
    "Case 7 FAIL: the missing region was not added"
assert _repaired["pages"][0]["regionComponents"]["header"] == [], \
    "Case 7 FAIL: the repair invented content for the missing region"
assert _repaired["pages"][0]["regionComponents"]["main"] == [_NODE], \
    "Case 7 FAIL: the repair lost content the planner did supply"
assert _repair_component_spec_from_layout(_LAYOUT, None)["pages"][0]["pageName"] == "plp", \
    "Case 7 FAIL: repairing from nothing did not produce the layout's pages"
_RP_CASES += 1
print("PASS Case 7 - repair adds the missing region empty, and never invents a component")

# ── Case 8: the scaffold and the contract describe the same layout ─────────
# The scaffold is the empty shape handed to the planner. The contract is the
# same thing written out for the prompt. They must agree, or the planner is
# told about regions the scaffold has no room for.
_scaffold = _build_component_scaffold_from_layout(_LAYOUT)
_contract = _build_component_contract_from_layout(_LAYOUT)
assert set(_scaffold["pages"][0]["regionComponents"]) == {"header", "main"}, \
    "Case 8 FAIL: the scaffold does not carry every region"
for _region in ("header", "main"):
    assert _region in _contract, f"Case 8 FAIL: '{_region}' is missing from the written contract"
assert "plp" in _contract, "Case 8 FAIL: the page name is missing from the written contract"
_RP_CASES += 1
print("PASS Case 8 - the empty shape and its written description name the same regions")

# ── Case 9: a guessed tag is always a real tag ─────────────────────────────
# When the planner names a component but not its tag, one is guessed from the
# name. A guess that produced an invented tag would be worse than no guess.
for _cid, _region, _want in (("bottomNav", "footer", "nav"),
                             ("siteHeader", "top", "header"),
                             ("searchForm", "main", "form"),
                             ("addToCartButton", "main", "button"),
                             ("productGrid", "main", "section"),
                             ("mysteryThing", "main", "section")):
    _got = _guess_component_tag(_cid, _region)
    assert _got == _want, f"Case 9 FAIL: {_cid!r} guessed {_got!r}, expected {_want!r}"
ComponentNode(**_default_component_node_for_ref("bottomNav", "footer"))
_RP_CASES += 1
print("PASS Case 9 - a guessed tag is always one the schema accepts")

# ── Case 10: the bundle check reports rather than raises ───────────────────
# This runs mid-generation. A raise here would end the run; a message can be
# handed back to the planner as feedback.
assert _bundle_validate_or_warn(stage="components", layout=_LAYOUT, component=_full) is None, \
    "Case 10 FAIL: a valid bundle produced a warning"
_warn = _bundle_validate_or_warn(stage="components", layout=_LAYOUT, component=_missing)
assert _warn and _warn.startswith("[components]"), \
    f"Case 10 FAIL: the warning is not tagged with its stage: {_warn}"
assert _bundle_validate_or_warn(stage="x", layout="not a layout") is not None, \
    "Case 10 FAIL: rubbish input raised instead of reporting"
_RP_CASES += 1
print("PASS Case 10 - an invalid bundle is reported as a message, never raised")

# ── Case 11: the retry loop stops, and passes the complaint forward ────────
# The planner is only useful on a second attempt if it is told what was wrong
# with the first. The cap of three is what keeps the loop honest: a run can end
# having failed, so a pass rate measured from it means something.
class _ScriptedTool:
    def __init__(self, results):
        self.results, self.seen = list(results), []

    def invoke(self, payload):
        self.seen.append(payload.get("validation_feedback", ""))
        return self.results.pop(0)


_tool = _ScriptedTool(["bad", "bad", "bad"])
_out, _err = _invoke_structured_with_retries(
    stage="test", structured_tool=_tool, base_payload={"q": 1},
    validate_result=lambda c: None if c == "good" else "still wrong")
# The message carries every attempt, not only the last one. Whether the model
# repeated itself or moved on is the thing worth knowing when a stage gives up,
# and the last error alone never showed it.
assert _out is None, f"Case 11 FAIL: a rejected answer was returned: {_out!r}"
assert "still wrong" in (_err or ""), f"Case 11 FAIL: the reason is missing: {_err!r}"
assert all(f"attempt {_n}:" in (_err or "") for _n in (1, 2, 3)), \
    f"Case 11 FAIL: all three attempts should be accounted for: {_err!r}"
assert len(_tool.seen) == 3, f"Case 11 FAIL: expected 3 attempts, got {len(_tool.seen)}"
# The first attempt is told nothing. The second is told BOTH what it wrote and
# what was wrong with it, so it edits rather than starting again.
assert _tool.seen[0] == "", "Case 11 FAIL: the first attempt was given feedback"
assert "still wrong" in _tool.seen[1], \
    f"Case 11 FAIL: the complaint was not fed into the retry: {_tool.seen[1][:200]}"
assert "YOUR PREVIOUS ANSWER" in _tool.seen[1] and "bad" in _tool.seen[1], \
    ("Case 11 FAIL: the retry cannot see what the previous attempt produced, so "
     "it has to rebuild from scratch and avoid a mistake it cannot look at.")

_tool = _ScriptedTool(["bad", "good", "never reached"])
_out, _err = _invoke_structured_with_retries(
    stage="test", structured_tool=_tool, base_payload={"q": 1},
    validate_result=lambda c: None if c == "good" else "still wrong")
assert _out == "good" and _err is None, f"Case 11 FAIL: a good result was not returned: {_out!r}"
assert len(_tool.seen) == 2, "Case 11 FAIL: it kept going after success"
_RP_CASES += 1
print("PASS Case 11 - three attempts at most, each told what was wrong with the last")

# ── Case 12: a crash inside the planner is retried, not propagated ─────────
class _ExplodingTool:
    def __init__(self):
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        raise RuntimeError("connection reset")


_boom = _ExplodingTool()
_out, _err = _invoke_structured_with_retries(
    stage="layout", structured_tool=_boom, base_payload={},
    validate_result=lambda c: None)
assert _out is None and "connection reset" in _err and "RuntimeError" in _err, \
    f"Case 12 FAIL: the cause was not carried into the message: {_err}"
assert _boom.calls == 3, f"Case 12 FAIL: expected 3 attempts, got {_boom.calls}"
_RP_CASES += 1
print("PASS Case 12 - a crash is retried three times and reported with its cause")

# ── Case 13: walking a tree reaches every depth ────────────────────────────
_deep = ComponentNode(id="a", tag="section", ownedBy="HTML", children=[
    {"id": "b", "tag": "div", "ownedBy": "HTML", "children": [
        {"id": "c", "tag": "button", "ownedBy": "HTML"}]}])
assert [n.id for n in _walk_component_nodes(_deep)] == ["a", "b", "c"], \
    "Case 13 FAIL: the walk did not reach every level"
_RP_CASES += 1
print("PASS Case 13 - the walk reaches a component nested three levels down")

# ── Case 14: the repair keeps what it was not asked to change ──────────────
# It used to return a fresh {"pages": ...}, dropping every other top-level field.
# `dataSets` never survived it, so the run's real product records were discarded
# before validation and no linter, guard or generated test could see it. E2E-SD-03
# is what finally caught it, on 2026-08-16.
_rp14_layout = {"pages": [{"pageName": "home", "pageType": "home",
                           "pageLayoutType": "single-column",
                           "regions": [{"name": "main", "layoutType": "grid",
                                        "ownedBy": "HTML"}]}]}
_rp14_candidate = {
    "pages": [{"pageName": "home", "regionComponents": {"main": []}}],
    "dataSets": {"products": [{"id": "p1", "name": "Silver Needle White Tea",
                               "price": "18.00"}]},
}
_rp14 = _repair_component_spec_from_layout(_rp14_layout, _rp14_candidate)
assert _rp14.get("dataSets") == _rp14_candidate["dataSets"], (
    f"Case 14 FAIL: the repair dropped dataSets. Got keys {sorted(_rp14)}. "
    f"Replace only `pages` and carry the rest of the payload through.")
assert [p["pageName"] for p in _rp14["pages"]] == ["home"], \
    "Case 14 FAIL: the repair stopped rebuilding pages from the layout"
_RP_CASES += 1
print("PASS Case 14 - the repair replaces pages and carries every other field through")

# ── Case 15: the scaffold gives the model a slot to fill ───────────────────
# The prompt says to start from the scaffold exactly, so a key missing here is a
# key the model never writes.
_rp15 = _build_component_scaffold_from_layout(_rp14_layout)
assert "dataSets" in _rp15 and _rp15["dataSets"] == {}, (
    f"Case 15 FAIL: the scaffold offers no dataSets slot. Keys: {sorted(_rp15)}")
assert _rp15["pages"][0]["regionComponents"] == {"main": []}, \
    "Case 15 FAIL: the scaffold stopped listing every region as an empty list"
_RP_CASES += 1
print("PASS Case 15 - the scaffold offers an empty dataSets slot beside the empty regions")

# ── Case 16: merchandise with no records is reported, not accepted ─────────
# A page declaring product cards with nothing behind them passes every other
# check, builds, lints and passes its generated tests. It just leaves the HTML
# and JavaScript agents to invent two different product lists.
_rp16_layout_obj = _coerce_layout_spec(_rp14_layout)
_rp16_card = {"id": "tea-card", "tag": "article", "ownedBy": "HTML",
              "componentCategory": "product-card", "className": "tea-card"}


def _rp16_spec(data_sets):
    return _coerce_component_spec({
        "pages": [{"pageName": "home",
                   "regionComponents": {"main": [_rp16_card]}}],
        "dataSets": data_sets})


_rp16_bad = _validate_component_contract_for_downstream(
    _rp16_layout_obj, _rp16_spec({}))
assert _rp16_bad and "dataSets is empty" in _rp16_bad, (
    f"Case 16 FAIL: a product-card with no records was accepted: {_rp16_bad!r}")
assert "product-card" in _rp16_bad, \
    "Case 16 FAIL: the complaint does not name what needs records"

_rp16_ok = _validate_component_contract_for_downstream(
    _rp16_layout_obj, _rp16_spec({"products": [{"id": "p1", "name": "Sencha"}]}))
assert _rp16_ok is None, \
    f"Case 16 FAIL: a spec WITH records was rejected: {_rp16_ok!r}"

# A NON-SELLING page with no merchandise needs no records, so it must stay
# silent. (A selling page owes records even without a labelled card: Case 20.)
_rp16_static_layout = _coerce_layout_spec({
    "pages": [{"pageName": "account", "pageType": "account",
               "pageLayoutType": "grid",
               "regions": [{"name": "main", "ownedBy": "HTML",
                            "layoutType": "flex-row"}]}]})
_rp16_static = _coerce_component_spec({
    "pages": [{"pageName": "account", "regionComponents": {"main": [
        {"id": "about", "tag": "section", "ownedBy": "HTML"}]}}]})
assert _validate_component_contract_for_downstream(
    _rp16_static_layout, _rp16_static) is None, \
    "Case 16 FAIL: a non-selling page with no merchandise was asked for records"
_RP_CASES += 1
print("PASS Case 16 - merchandise with no records is reported, and a static page is left alone")

print("=" * 64)
# ── Case 17: a slow stage can say where the time went ──────────────────────
# The layout stage passed and took 2m14s on 2026-08-16, and nothing recorded
# whether that was one slow call or three ordinary ones. Those need opposite
# fixes, so the ambiguity cost a wasted experiment before it cost anything else.
# A stage that SUCCEEDS is the important case here, because that one used to
# record nothing at all.
_TM_BEFORE = len(_SPEC_TIMINGS)
_tm_tool = _ScriptedTool(["bad", "good"])
_tm_out, _tm_err = _invoke_structured_with_retries(
    stage="timing-test", structured_tool=_tm_tool, base_payload={"q": 1},
    validate_result=lambda c: None if c == "good" else "not yet")
assert _tm_out == "good" and _tm_err is None, f"Case 17 FAIL: {_tm_out!r} {_tm_err!r}"

_tm_rows = [r for r in _SPEC_TIMINGS[_TM_BEFORE:] if r["stage"] == "timing-test"]
assert len(_tm_rows) == 2, \
    f"Case 17 FAIL: a stage that retried once recorded {len(_tm_rows)} attempt(s)"
assert [r["attempt"] for r in _tm_rows] == [1, 2], \
    "Case 17 FAIL: the attempts are not numbered in order"
assert _tm_rows[-1]["outcome"] == "accepted", \
    "Case 17 FAIL: the winning attempt is not marked accepted, so a run that "
assert all(isinstance(r["seconds"], float) and r["seconds"] >= 0 for r in _tm_rows), \
    "Case 17 FAIL: an attempt carries no duration"
_RP_CASES += 1
print("PASS Case 17 - every attempt is timed, including the one that succeeded")

# ── Case 18: what a retry is shown, in both shapes ─────────────────────
# A rejected answer is shown back so the next attempt can edit it. An answer
# that never parsed cannot be, because there is no object to edit, and pasting
# raw broken text back invites the model to copy it.
_fb = _retry_feedback({"pages": [{"pageName": "plp"}]}, "regions are missing", 1)
assert "YOUR PREVIOUS ANSWER (attempt 1)" in _fb, "Case 18 FAIL: the answer is not shown"
assert "plp" in _fb, "Case 18 FAIL: the answer's content is not in the feedback"
assert "regions are missing" in _fb, "Case 18 FAIL: the complaint is not in the feedback"
assert "Keep everything that" in _fb, \
    "Case 18 FAIL: nothing tells the model to preserve the parts that were fine"

# Nothing parsed, so only the reason goes back.
assert _retry_feedback(None, "the answer could not be parsed", 2) == \
    "the answer could not be parsed", \
    "Case 18 FAIL: an unparseable attempt should send the reason alone"

# A very large answer is cut short rather than dropped, and says so.
_big = _retry_feedback({"junk": "x" * (_RETRY_ANSWER_LIMIT + 500)}, "too big", 1)
assert "cut short here" in _big and "too big" in _big, \
    "Case 18 FAIL: an oversized answer is neither truncated nor explained"
assert len(_big) < _RETRY_ANSWER_LIMIT + 2000, \
    "Case 18 FAIL: the truncation limit is not being applied"
_RP_CASES += 1
print("PASS Case 18 - a retry sees its own answer, unless there was not one")

# ── Case 19: a timing line never reaches the Streamlit chat ───────────
# bridge.py forwards every string on the graph's custom stream straight into
# the chat, which is how the agents' own progress lines get there. A
# per-attempt timing line rode the same channel and was shown to the person
# waiting, as though the system were talking to them. It is for whoever is
# debugging a slow stage. Spy on the writer rather than trust the comment.
import io as _io19
import contextlib as _ctx19

_ST_CALLS = []
_lgc19 = None
_real_gsw19 = None
try:
    import langgraph.config as _lgc19
    _real_gsw19 = getattr(_lgc19, "get_stream_writer", None)

    def _spy_gsw19():
        _ST_CALLS.append("asked the chat stream for a writer")
        return lambda text: _ST_CALLS.append(f"wrote to the chat: {text}")

    _lgc19.get_stream_writer = _spy_gsw19
except Exception:
    _lgc19 = None

_buf19 = _io19.StringIO()
try:
    with _ctx19.redirect_stdout(_buf19):
        _spec_progress("   [timing-test] attempt 1/3 took 0.1s: accepted")
finally:
    if _lgc19 is not None and _real_gsw19 is not None:
        _lgc19.get_stream_writer = _real_gsw19

assert not _ST_CALLS, \
    ("Case 19 FAIL: the timing line went to the chat stream, so Streamlit shows "
     f"it to the user mid-conversation: {_ST_CALLS}")
assert "attempt 1/3" in _buf19.getvalue(), \
    "Case 19 FAIL: the line did not reach the console either, so it is now lost"
_RP_CASES += 1
print("PASS Case 19 - a timing line goes to the console, never to the chat")

# ── Case 20: a selling page owes records even when the model forgot to
# label its cards. E2E-SD-03 shipped an empty tea shop because every card's
# category came back null, so Case 16's category test stayed silent. The
# page type is the backstop the model cannot leave off.
_rp20_home = _coerce_layout_spec({
    "pages": [{"pageName": "home", "pageType": "home", "pageLayoutType": "grid",
               "regions": [{"name": "main", "ownedBy": "HTML",
                            "layoutType": "flex-row"}]}]})
_rp20_unlabelled = _coerce_component_spec({
    "pages": [{"pageName": "home", "regionComponents": {"main": [
        {"id": "tea-card", "tag": "article", "ownedBy": "HTML"}]}}]})
_rp20_bad = _validate_component_contract_for_downstream(_rp20_home, _rp20_unlabelled)
assert _rp20_bad and "selling page" in _rp20_bad, (
    f"Case 20 FAIL: a home page with empty dataSets was accepted: {_rp20_bad!r}")
_rp20_ok = _validate_component_contract_for_downstream(
    _rp20_home, _coerce_component_spec({
        "pages": [{"pageName": "home", "regionComponents": {"main": [
            {"id": "tea-card", "tag": "article", "ownedBy": "HTML"}]}}],
        "dataSets": {"products": [{"id": "t1", "name": "Sencha"}]}}))
assert _rp20_ok is None, \
    f"Case 20 FAIL: a home page WITH records was rejected: {_rp20_ok!r}"
_RP_CASES += 1
print("PASS Case 20 - a selling page with empty dataSets is rejected even with no labelled card")

# -- Case 21: a search-bar must expose its input as an addressable child, or a
# type test has nothing to fill (Playwright fill needs a real input). PO-06's
# search bar was one opaque form node, so the type case targeted the form.
_rp21_layout = _coerce_layout_spec({
    "pages": [{"pageName": "account", "pageType": "account", "pageLayoutType": "grid",
               "regions": [{"name": "main", "ownedBy": "HTML",
                            "layoutType": "flex-row"}]}]})
_rp21_no_input = _coerce_component_spec({
    "pages": [{"pageName": "account", "regionComponents": {"main": [
        {"id": "site-search", "tag": "form", "ownedBy": "HTML",
         "componentCategory": "search-bar"}]}}]})
_rp21_bad = _validate_component_contract_for_downstream(_rp21_layout, _rp21_no_input)
assert _rp21_bad and "no <input>" in _rp21_bad, (
    f"Case 21 FAIL: a search-bar with no input field was accepted: {_rp21_bad!r}")
_rp21_ok = _validate_component_contract_for_downstream(
    _rp21_layout, _coerce_component_spec({
        "pages": [{"pageName": "account", "regionComponents": {"main": [
            {"id": "site-search", "tag": "form", "ownedBy": "HTML",
             "componentCategory": "search-bar", "children": [
                 {"id": "site-search-input", "tag": "input", "ownedBy": "HTML"}]}]}}]}))
assert _rp21_ok is None, \
    f"Case 21 FAIL: a search-bar WITH an input child was rejected: {_rp21_ok!r}"
_RP_CASES += 1
print("PASS Case 21 - a search-bar without an addressable input field is rejected")

# -- Case 22: a quantity-selector must expose a control that can change the
# amount, or it ships as a static number. PO-10 po07cdf97e's mini-cart quantity
# was a bare <span> with events:[], so nothing wired a stepper and Test
# Generation had no event to cover. The +/- controls live as CHILDREN of the
# selector (the search-bar/input contract, one category over); a sibling remove
# button is not inside it and does not count. Both fixtures carry dataSets so the
# ONLY difference under test is the stepper controls.
_rp22_layout = _coerce_layout_spec({
    "pages": [{"pageName": "cart", "pageType": "home", "pageLayoutType": "grid",
               "regions": [{"name": "cart-drawer", "ownedBy": "JavaScript",
                            "layoutType": "flex-row"}]}]})
_rp22_bare = _coerce_component_spec({
    "pages": [{"pageName": "cart", "regionComponents": {"cart-drawer": [
        {"id": "mini-cart-item", "tag": "article", "ownedBy": "JavaScript",
         "componentCategory": "cart-item", "children": [
            {"id": "mini-cart-quantity", "tag": "span", "ownedBy": "JavaScript",
             "componentCategory": "quantity-selector"},
            {"id": "mini-cart-remove", "tag": "button", "ownedBy": "JavaScript",
             "events": [{"event": "onClick", "flowName": "removeCartItem"}]}]}]}}],
    "dataSets": {"cartItems": [{"id": "c1", "name": "Item"}]}})
_rp22_bad = _validate_component_contract_for_downstream(_rp22_layout, _rp22_bare)
assert _rp22_bad and "quantity-selector" in _rp22_bad and "change the amount" in _rp22_bad, (
    f"Case 22 FAIL: a quantity-selector with no control was accepted: {_rp22_bad!r}")
_rp22_ok = _validate_component_contract_for_downstream(
    _rp22_layout, _coerce_component_spec({
        "pages": [{"pageName": "cart", "regionComponents": {"cart-drawer": [
            {"id": "mini-cart-item", "tag": "article", "ownedBy": "JavaScript",
             "componentCategory": "cart-item", "children": [
                {"id": "mini-cart-quantity", "tag": "div", "ownedBy": "JavaScript",
                 "componentCategory": "quantity-selector", "children": [
                    {"id": "qty-decrement", "tag": "button", "ownedBy": "JavaScript",
                     "events": [{"event": "onClick", "flowName": "decreaseCartItem"}]},
                    {"id": "qty-value", "tag": "span", "ownedBy": "JavaScript"},
                    {"id": "qty-increment", "tag": "button", "ownedBy": "JavaScript",
                     "events": [{"event": "onClick", "flowName": "increaseCartItem"}]}]},
                {"id": "mini-cart-remove", "tag": "button", "ownedBy": "JavaScript",
                 "events": [{"event": "onClick", "flowName": "removeCartItem"}]}]}]}}],
        "dataSets": {"cartItems": [{"id": "c1", "name": "Item"}]}}))
assert _rp22_ok is None, \
    f"Case 22 FAIL: a quantity-selector WITH +/- control children was rejected: {_rp22_ok!r}"
_RP_CASES += 1
print("PASS Case 22 - a quantity-selector with no control that changes the amount is rejected")

# -- Case 23: a mini-cart drawer opens over the page and must be closable. PO-10
# po07cdf97e's mini-cart opened and nothing ever closed it -- the shopper was
# trapped. A remove or checkout button is not a close control. The close button
# lives as a CHILD. Keyed on the mini-cart category, so a toggle-only navbar is
# never touched.
_rp23_layout = _coerce_layout_spec({
    "pages": [{"pageName": "cart", "pageType": "account", "pageLayoutType": "grid",
               "regions": [{"name": "cart-drawer", "ownedBy": "JavaScript",
                            "layoutType": "flex-row"}]}]})
_rp23_noclose = _coerce_component_spec({
    "pages": [{"pageName": "cart", "regionComponents": {"cart-drawer": [
        {"id": "mini-cart-panel", "tag": "aside", "ownedBy": "JavaScript",
         "componentCategory": "mini-cart",
         "states": [{"name": "closed"}, {"name": "open"}],
         "children": [
            {"id": "cart-checkout-link", "tag": "a", "ownedBy": "JavaScript",
             "events": [{"event": "onClick", "flowName": "openCheckoutPanel"}]}]}]}}]})
_rp23_bad = _validate_component_contract_for_downstream(_rp23_layout, _rp23_noclose)
assert _rp23_bad and "no control to close it" in _rp23_bad, (
    f"Case 23 FAIL: a mini-cart with no close control was accepted: {_rp23_bad!r}")
_rp23_ok = _validate_component_contract_for_downstream(
    _rp23_layout, _coerce_component_spec({
        "pages": [{"pageName": "cart", "regionComponents": {"cart-drawer": [
            {"id": "mini-cart-panel", "tag": "aside", "ownedBy": "JavaScript",
             "componentCategory": "mini-cart",
             "states": [{"name": "closed"}, {"name": "open"}],
             "children": [
                {"id": "mini-cart-close", "tag": "button", "ownedBy": "JavaScript",
                 "events": [{"event": "onClick", "flowName": "closeMiniCart"}]},
                {"id": "cart-checkout-link", "tag": "a", "ownedBy": "JavaScript",
                 "events": [{"event": "onClick", "flowName": "openCheckoutPanel"}]}]}]}}]}))
assert _rp23_ok is None, \
    f"Case 23 FAIL: a mini-cart WITH a close button child was rejected: {_rp23_ok!r}"
_RP_CASES += 1
print("PASS Case 23 - a mini-cart with no control to close it is rejected")
print(f"[proof] mini-cart close contract: PO-10-shape mini-cart (only remove/checkout "
      f"children) -> {'1 violation' if _rp23_bad else '0'} (names it + asks for a close button "
      f"child); the same drawer WITH a close button child -> "
      f"{'0' if _rp23_ok is None else 'still flagged'}. Before this guard the drawer opened and "
      f"never closed, and Test Generation had no close event to cover. Keyed on the mini-cart "
      f"category, so a toggle-only navbar/accordion (expanded/collapsed) is never flagged.")
print(f"[proof] quantity-selector contract: PO-10-shape bare selector -> "
      f"{'1 violation' if _rp22_bad else '0 violations'} (names it + tells the model to add +/- "
      f"button children); the same tree WITH a decrement/increment child pair -> "
      f"{'0' if _rp22_ok is None else 'still flagged'} violations. Before this guard a "
      f"quantity-selector with events:[] passed every check, so the cart shipped a static "
      f"number and Test Generation wrote no increment/decrement test (all 39 PO-10 failures "
      f"were unrelated camelCase false failures).")

# -- Case 24: the last-resort fill gives every EMPTY html region a valid node,
# and leaves the rest alone. A product-ish region gets a product-grid bound to
# products; a plain region gets a CSS container; a JS-owned region stays empty;
# a region the model already planned is untouched. This is the deterministic
# floor under PO-10 po2r1707798, which dropped the product listing 3/3.
_fe_layout = _coerce_layout_spec({"pages": [{"pageName": "home", "pageType": "home",
    "pageLayoutType": "grid", "regions": [
        {"name": "product-listing", "ownedBy": "HTML", "layoutType": "flex-row"},
        {"name": "about", "ownedBy": "HTML", "layoutType": "flex-row"},
        {"name": "hero", "ownedBy": "HTML", "layoutType": "flex-row"},
        {"name": "cart-drawer", "ownedBy": "JavaScript", "layoutType": "flex-row"}]}]})
_fe_model = _repair_component_spec_from_layout(_fe_layout, {"pages": [{"pageName": "home",
    "regionComponents": {"hero": [{"id": "hero-x", "tag": "section", "ownedBy": "HTML",
        "className": "hero-x"}]}}],
    "dataSets": {"products": [{"id": "p1", "name": "Widget", "price": "$9"}]}})
_fe_filled, _fe_n = _fill_empty_html_regions(_fe_layout, _fe_model)
_fe_rc = _fe_filled["pages"][0]["regionComponents"]
assert _fe_n == 2, f"Case 24 FAIL: expected 2 fills (product-listing, about), got {_fe_n}"
assert _fe_rc["product-listing"][0]["componentCategory"] == "product-grid", "listing not a grid"
assert _fe_rc["product-listing"][0]["children"][0]["dataBinding"] == {"source": "products"}, \
    "the fallback product-card is not bound to products"
assert _fe_rc["about"][0]["ownedBy"] == "CSS", "a plain region should get a CSS container"
assert _fe_rc["hero"][0]["id"] == "hero-x", "an already-planned region must be untouched"
assert not _fe_rc.get("cart-drawer"), "a JS-owned region must stay empty"
assert _validate_component_contract_for_downstream(
    _fe_layout, _coerce_component_spec(_fe_filled)) is None, "filled spec must pass the guard"
_RP_CASES += 1
print("PASS Case 24 - empty HTML regions filled, JS/planned regions untouched")

# -- Case 25: the on_give_up hook rescues a run whose model exhausted its
# attempts leaving an HTML region empty. Without the hook the loop still fails
# (the wall); with it the loop returns a filled, valid spec.
_lr_layout = _coerce_layout_spec({"pages": [{"pageName": "home", "pageType": "home",
    "pageLayoutType": "grid", "regions": [
        {"name": "product-listing", "ownedBy": "HTML", "layoutType": "flex-row"},
        {"name": "footer", "ownedBy": "HTML", "layoutType": "flex-row"}]}]})
_lr_stub = {"pages": [{"pageName": "home", "regionComponents": {}}],
            "dataSets": {"products": [{"id": "p1", "name": "Widget", "price": "$9"}]}}
class _LRTool:
    def invoke(self, payload, config=None):
        return json.loads(json.dumps(_lr_stub))
def _lr_validate(cand):
    return _validate_component_contract_for_downstream(
        _lr_layout, _coerce_component_spec(_repair_component_spec_from_layout(_lr_layout, cand)))
def _lr_give_up(last_candidate, last_error):
    _rep = _repair_component_spec_from_layout(_lr_layout, last_candidate)
    _fl, _nn = _fill_empty_html_regions(_lr_layout, _rep)
    if not _nn:
        return None
    _obj = _coerce_component_spec(_fl)
    if _validate_component_contract_for_downstream(_lr_layout, _obj) is None:
        return _obj.model_dump()
    return None
_lr_fail, _lr_e1 = _invoke_structured_with_retries(
    stage="components-selftest", structured_tool=_LRTool(), base_payload={},
    validate_result=_lr_validate, max_attempts=3)
assert _lr_fail is None and _lr_e1, "Case 25 FAIL: without on_give_up the wall must still fail"
_lr_ok, _lr_e2 = _invoke_structured_with_retries(
    stage="components-selftest", structured_tool=_LRTool(), base_payload={},
    validate_result=_lr_validate, max_attempts=3, on_give_up=_lr_give_up)
assert _lr_e2 is None and _lr_ok is not None, f"Case 25 FAIL: on_give_up should rescue: {_lr_e2!r}"
_lr_rc = _lr_ok["pages"][0]["regionComponents"]
assert _lr_rc.get("product-listing") and _lr_rc.get("footer"), "rescued spec missing regions"
_RP_CASES += 1
print("PASS Case 25 - on_give_up fills empty HTML regions after all retries fail")
print(f"[proof] never-abort backstop: a model that drops 2 HTML regions on all 3 "
      f"attempts -> WITHOUT on_give_up the loop returns None (the PO-10 po2r1707798 "
      f"abort); WITH it the loop returns a valid spec, product-listing filled as a "
      f"product-grid bound to products. 3 model attempts either way; 0 extra model "
      f"calls in the rescue (it is pure Python).")

# -- Case 26: re-injecting the REPAIRED answer on retry lets the model fill a
# region it dropped. Same model, same 3-attempt budget: without re-injection the
# feedback shows the model its own answer with the dropped key GONE, so it never
# re-adds it (the PO-10 po2r1707798 wall); with it, the feedback carries the
# empty key and the model fills it on attempt 2 -- BEFORE the Case 25 backstop.
_ri_layout = _coerce_layout_spec({"pages": [{"pageName": "home", "pageType": "home",
    "pageLayoutType": "grid", "regions": [
        {"name": "product-listing", "ownedBy": "HTML", "layoutType": "flex-row"},
        {"name": "hero", "ownedBy": "HTML", "layoutType": "flex-row"}]}]})
_ri_hero = {"id": "hero-x", "tag": "section", "ownedBy": "HTML", "className": "hero-x"}
_ri_grid = {"id": "pl-grid", "tag": "section", "ownedBy": "HTML",
            "componentCategory": "product-grid", "className": "pl-grid",
            "dataBinding": {"source": "products"},
            "children": [{"id": "pl-card", "tag": "article", "ownedBy": "HTML",
                          "componentCategory": "product-card", "className": "pl-card",
                          "dataBinding": {"source": "products"}}]}
_ri_incomplete = {"pages": [{"pageName": "home", "regionComponents": {"hero": [_ri_hero]}}],
                  "dataSets": {"products": [{"id": "p1", "name": "Widget", "price": "$9"}]}}
_ri_complete = {"pages": [{"pageName": "home", "regionComponents":
                    {"hero": [_ri_hero], "product-listing": [_ri_grid]}}],
                "dataSets": {"products": [{"id": "p1", "name": "Widget", "price": "$9"}]}}
class _RITool:
    def __init__(self): self.attempts = 0
    def invoke(self, payload, config=None):
        self.attempts += 1
        fb = payload.get("validation_feedback") or ""
        # the model only re-adds the region when it can SEE the empty key in
        # its own prior answer (the double-quoted JSON key, never the prose).
        if '"product-listing"' in fb:
            return json.loads(json.dumps(_ri_complete))
        return json.loads(json.dumps(_ri_incomplete))
def _ri_validate(cand):
    return _validate_component_contract_for_downstream(
        _ri_layout, _coerce_component_spec(_repair_component_spec_from_layout(_ri_layout, cand)))
_ri_t1 = _RITool()
_ri_a1, _ri_e1 = _invoke_structured_with_retries(stage="ri-selftest",
    structured_tool=_ri_t1, base_payload={}, validate_result=_ri_validate, max_attempts=3)
assert _ri_a1 is None and _ri_e1, "Case 26 FAIL: without re-injection the model cannot see the dropped key"
_ri_t2 = _RITool()
_ri_a2, _ri_e2 = _invoke_structured_with_retries(stage="ri-selftest",
    structured_tool=_ri_t2, base_payload={}, validate_result=_ri_validate, max_attempts=3,
    normalize=lambda c: _repair_component_spec_from_layout(_ri_layout, c))
assert _ri_e2 is None and _ri_a2 is not None, f"Case 26 FAIL: re-injection should converge: {_ri_e2!r}"
assert _ri_t2.attempts == 2, f"Case 26 FAIL: expected convergence on attempt 2, took {_ri_t2.attempts}"
_RP_CASES += 1
print("PASS Case 26 - re-injecting the repaired answer lets the model fill a dropped region")
print(f"[proof] retry re-injection: same model, same 3-attempt budget. WITHOUT it the model "
      f"sees its own answer with the product-listing key gone and never re-adds it "
      f"({_ri_t1.attempts} attempts, failed). WITH it the feedback carries 'product-listing': [] "
      f"and the model fills it on attempt {_ri_t2.attempts}. Model-authored path; the Case 25 "
      f"Python backstop only fires if even this fails.")

# -- Case 27 (REGRESSION, po2r12253d9): the model tags BOTH the open button and
# the drawer componentCategory='mini-cart'. The close-control check must fire only
# on the drawer (a container), never on the <button> trigger -- flagging the button
# bounced a correct spec into a 3/3 components thrash and shipped a broken cart.
_rp27_layout = _coerce_layout_spec({"pages": [{"pageName": "home", "pageType": "account",
    "pageLayoutType": "grid", "regions": [{"name": "header", "ownedBy": "HTML",
        "layoutType": "flex-row"}]}]})
_rp27_ok = _validate_component_contract_for_downstream(_rp27_layout, _coerce_component_spec({
    "pages": [{"pageName": "home", "regionComponents": {"header": [
        {"id": "header-mini-cart-toggle", "tag": "button", "ownedBy": "HTML",
         "componentCategory": "mini-cart",
         "events": [{"event": "onClick", "flowName": "openMiniCart"}],
         "children": [{"id": "mini-cart-count", "tag": "span", "ownedBy": "HTML"}]},
        {"id": "mini-cart-drawer", "tag": "aside", "ownedBy": "HTML",
         "componentCategory": "mini-cart",
         "children": [
            {"id": "mini-cart-close", "tag": "button", "ownedBy": "HTML",
             "events": [{"event": "onClick", "flowName": "closeMiniCart"}]},
            {"id": "mini-cart-items", "tag": "ul", "ownedBy": "HTML"}]}]}}]}))
assert _rp27_ok is None, \
    f"Case 27 FAIL: a mini-cart TOGGLE button was wrongly flagged for no close control: {_rp27_ok!r}"
# and the drawer alone, with NO close, is still correctly flagged
_rp27_bad = _validate_component_contract_for_downstream(_rp27_layout, _coerce_component_spec({
    "pages": [{"pageName": "home", "regionComponents": {"header": [
        {"id": "mini-cart-drawer", "tag": "aside", "ownedBy": "HTML",
         "componentCategory": "mini-cart",
         "children": [{"id": "mini-cart-checkout", "tag": "a", "ownedBy": "HTML",
             "events": [{"event": "onClick", "flowName": "goCheckout"}]}]}]}}]}))
assert _rp27_bad and "no control to close it" in _rp27_bad, \
    f"Case 27 FAIL: a real drawer with no close control must still be flagged: {_rp27_bad!r}"
_RP_CASES += 1
print("PASS Case 27 - a mini-cart TOGGLE button is exempt; a drawer with no close is still flagged")
print(f"[proof] mini-cart-close false positive fixed: the po2r12253d9 shape (a <button> toggle "
      f"+ an <aside> drawer that HAS a close) -> {'0 violations' if _rp27_ok is None else 'STILL FLAGGED'}; "
      f"a drawer with only a checkout link -> {'flagged' if _rp27_bad else '0'}. Before this the button "
      f"was flagged and components thrashed 3/3 (safety net shipped a cart with no quantity controls).")

print(f"Specification repair helpers: {_RP_CASES}/27 cases PASSED")
print("=" * 64)
