# Ported from fyp.ipynb cell 97 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the four specification generators
#
# These generators call the planning model, so none of them is invoked here.
# What is checked instead is the wiring: which schema each chain is bound to,
# what each prompt still demands, and what a generator does when the planner
# never produces anything usable.
_GEN_CASES = 0

_GENS = [
    ("layout", layout_prompt, layout_specification_generator_chain,
     layout_specification_generator_tool, layout_specification_generator,
     LayoutSpecification),
    ("components", components_prompt, components_specification_generator_chain,
     components_specification_generator_tool, components_specification_generator,
     ComponentSpecificationDraft),
    ("interactions", interactions_prompt, interactions_specification_generator_chain,
     interactions_specification_generator_tool, interactions_specification_generator,
     InteractionSpecification),
    ("decoration", decoration_prompt, decoration_specification_generator_chain,
     decoration_specification_generator_tool, decoration_specification_generator,
     DecorationSpecification),
]

# ── Case 1: each chain is bound to the schema it claims ────────────────────
# A chain bound to the wrong schema is the worst kind of mistake here. The
# model would return something valid, it would store cleanly, and the page
# would simply be built from the wrong description.
for _name, _prompt, _chain, _tool_obj, _fn, _schema in _GENS:
    _bound = repr(_chain)
    assert _schema.__name__ in _bound, (
        f"Case 1 FAIL: the {_name} chain is not bound to {_schema.__name__}. "
        f"A chain bound to the wrong schema produces a valid-looking plan for "
        f"the wrong stage.")
_GEN_CASES += 1
print("PASS Case 1 - all four chains are bound to their own schema")

# ── Case 2: the components chain uses the DRAFT schema, on purpose ─────────
# The planner writes the tree in stages, so its first answer may leave a region
# empty. The draft allows that. The repair helpers then fill the shape, and the
# strict schema checks the result. Binding the strict schema here would reject
# a first answer that the pipeline can fix on its own.
assert "ComponentSpecificationDraft" in repr(components_specification_generator_chain), \
    "Case 2 FAIL: the components chain must accept a draft, not the final schema"
assert "ComponentSpecificationDraft" not in repr(layout_specification_generator_chain), \
    "Case 2 FAIL: only the components stage uses a draft schema"
_GEN_CASES += 1
print("PASS Case 2 - the components stage accepts a draft, so a partial first answer is fixable")

# ── Case 3: every prompt still demands what the guards enforce ────────────
# A guard downstream refuses a plan missing any of these. If the prompt stops
# asking for one, every run pays a wasted retry to be told so.
for _needle in ("ownedBy", "flowName", "componentCategory", "regionComponents"):
    assert _needle in components_prompt.template, \
        (f"Case 3 FAIL: the components prompt no longer asks for {_needle!r}, but a "
         f"guard downstream still refuses a plan without it.")
for _cat in ("product-card", "add-to-cart-button", "navbar", "footer"):
    assert _cat in components_prompt.template, \
        f"Case 3 FAIL: the category {_cat!r} is missing from the list the prompt offers"
assert "pageLayoutType" in layout_prompt.template, \
    "Case 3 FAIL: the layout prompt does not ask for pageLayoutType, which the schema requires"
_GEN_CASES += 1
print("PASS Case 3 - every prompt still asks for the fields the guards refuse a plan without")

# ── Case 4: every prompt carries the retry channel ────────────────────────
# This placeholder is how a complaint reaches the next attempt. Without it the
# three attempts are three identical guesses.
for _name, _prompt, _chain, _tool_obj, _fn, _schema in _GENS:
    assert "validation_feedback" in _prompt.template, \
        (f"Case 4 FAIL: the {_name} prompt has no validation_feedback placeholder, so "
         f"its retries would repeat the same request with no new information.")
    assert "validation_feedback" in _tool_obj.args, \
        f"Case 4 FAIL: the {_name} tool does not accept validation_feedback"
_GEN_CASES += 1
print("PASS Case 4 - all four can be told what was wrong with the previous attempt")

# ── Case 5: each stage reads what the stage before produced ───────────────
# The chain runs layout, then components, then interactions, then decoration.
# A stage that stopped reading its predecessor would plan in isolation.
assert "design_schema" in layout_prompt.template
assert "layout_specification" in components_prompt.template
assert "components_specification" in interactions_prompt.template
assert "components_specification" in decoration_prompt.template
_GEN_CASES += 1
print("PASS Case 5 - each stage is given the output of the stage before it")

# ── Case 6: a failed generator stores nothing ─────────────────────────────
# This is the one behaviour worth testing without the model. When the planner
# never produces anything usable, the generator must leave the field empty and
# say so. Storing a half-built specification would let the next stage plan on
# top of it.
class _Runtime:
    def __init__(self, state):
        self.state, self.tool_call_id = state, "test-call"


_saved = _invoke_structured_with_retries
try:
    def _always_fails(**kwargs):
        return None, "[%s] planner never returned a usable result" % kwargs["stage"]

    _invoke_structured_with_retries = _always_fails
    for _name, _prompt, _chain, _tool_obj, _fn, _schema in _GENS:
        _cmd = _fn.func(_Runtime({"input_query": "build a shop"}))
        _keys = set(_cmd.update)
        assert _keys == {"messages"}, \
            (f"Case 6 FAIL: the {_name} generator wrote {_keys - {'messages'}} after failing. "
             f"A half-built specification would be planned on top of by the next stage.")
        assert "FAILED" in _cmd.update["messages"][0].content, \
            f"Case 6 FAIL: the {_name} failure was not reported in the message"
finally:
    _invoke_structured_with_retries = _saved
_GEN_CASES += 1
print("PASS Case 6 - a generator that fails stores nothing and says so")

# ── Case 7: the layout generator refuses a plan with more than one page ────
# The rule used to live only in the planning agent's system prompt, and the
# planning agent does not write the page list. This chain does, and its own
# prompt is the whole instruction set the writing model sees. The check below
# drives the real generator against a stand-in chain that keeps returning two
# pages, and proves three things: nothing is stored, the failure is reported,
# and the reason names the page count rather than something vague.
class _TwoPageTool:
    """Stands in for the structured chain. Always answers with two pages."""

    def __init__(self):
        self.calls = 0
        self.feedback = []

    def invoke(self, payload):
        self.calls += 1
        self.feedback.append(payload.get("validation_feedback", ""))
        return {"pages": [
            {"pageName": "ListingPage", "pageType": "plp", "pageLayoutType": "grid",
             "responsive": True, "regions": [{"name": "grid", "ownedBy": "HTML",
                                              "layoutType": "grid"}]},
            {"pageName": "CartPage", "pageType": "cart", "pageLayoutType": "flex-column",
             "responsive": True, "regions": [{"name": "items", "ownedBy": "HTML",
                                              "layoutType": "flex-column"}]},
        ]}


_two = _TwoPageTool()
_lg_real = layout_specification_generator_tool
globals()["layout_specification_generator_tool"] = _two
try:
    _rt_lg = SimpleNamespace(state={"input_query": "build a shop and a cart page",
                                    "design_schema": {}},
                             tool_call_id="lg-1")
    _cmd = layout_specification_generator.func(_rt_lg)
finally:
    globals()["layout_specification_generator_tool"] = _lg_real

assert "layout_specification" not in _cmd.update, (
    "Case 7 FAIL: a two-page layout was STORED. Everything downstream would "
    "then plan against two pages and the run would die at the orchestrator.")
_msg = _cmd.update["messages"][0].content
assert "EXACTLY ONE" in _msg and "got 2" in _msg, \
    f"Case 7 FAIL: the reason does not name the page count: {_msg[:200]}"
assert _two.calls == 3, \
    f"Case 7 FAIL: expected 3 attempts before giving up, got {_two.calls}"
assert "EXACTLY ONE" in (_two.feedback[1] or ""), \
    "Case 7 FAIL: the second attempt was not told why the first was rejected"
assert "EXACTLY ONE page" in layout_prompt.template, \
    "Case 7 FAIL: the prompt no longer states the limit, so the model is only " \
    "corrected by retry instead of being told up front"
_GEN_CASES += 1
print("PASS Case 7 - a multi-page layout is rejected, retried with the reason, "
      "and never stored")

# ── Case 8: the layout prompt names the schema's fields, and only those ─────
# It asked for `componentRefs` in its opening instruction and forbade the same
# field twenty lines later. Region has never had that field. The model's first
# instruction was therefore impossible, and this is the slowest of the four
# stages.
#
# Checked both ways. A field the schema does not have must not appear, or the
# model wastes its thinking reconciling it. A field the schema requires must
# appear, or the model leaves it out and the stage spends all three attempts.
_lp = layout_prompt.template

# Only camelCase tokens are examined. Every field name in these schemas is
# camelCase, and no ordinary English word is, so "which components go inside
# them" stays prose while "componentRefs" is read as the field it looks like.
import re as _lp_re

_lp_known = set(Page.model_fields) | set(Region.model_fields)
_lp_named = set(_lp_re.findall(r"\b[a-z]+[A-Z]\w*", _lp))
_lp_ghost = sorted(_lp_named - _lp_known)
assert not _lp_ghost, (
    f"Case 8 FAIL: the layout prompt asks for {_lp_ghost}, which neither Page "
    f"nor Region has. The model cannot supply it, and trying costs it time on "
    f"the slowest of the four stages.")

for _cls in (Page, Region):
    _missing = [f for f, info in _cls.model_fields.items()
                if info.is_required() and f not in _lp]
    assert not _missing, (
        f"Case 8 FAIL: {_cls.__name__} requires {_missing}, and the layout "
        f"prompt never names it. The model will leave it out on all three "
        f"attempts and the stage will fail.")

print("PASS Case 8 - the layout prompt names every required field and no invented one")
_GEN_CASES += 1

# ── Case 9: a prompt that lists a schema's values lists all of them ─────────
# Both lists had fallen behind by two values, and both times the missing pair
# was what a checkout needs. advanceStep and submitOrder were added to
# ActionType, and checkout-steps and order-confirmation to ComponentCategory,
# on 2026-08-15. The prompts still named eleven of thirteen and twenty-six of
# twenty-eight the next day. A prompt saying "MUST be one of" then omitting a
# value makes that value unreachable, and nothing reports it.
#
# Both lists are now generated from the schema. This case is what keeps a third
# hand-written list from appearing.
import typing as _lv_t

for _lit, _prompt, _where in ((ActionType, interactions_prompt.template, "interactions"),
                              (ComponentCategory, components_prompt.template, "components")):
    _unnamed = [v for v in _lv_t.get_args(_lit) if v not in _prompt]
    assert not _unnamed, (
        f"Case 9 FAIL: the {_where} prompt never names {_unnamed}, so the model "
        f"cannot use a value the schema accepts. Generate the list with "
        f"literal_values() rather than writing it out.")

print("PASS Case 9 - both prompts name every value their schema accepts")
_GEN_CASES += 1

# ── Case 10 (section-skeleton check RETIRED 2026-09-03) ──────
# The uniform seven-section skeleton (INPUTS / OUTCOME / VERIFICATION /
# CONSTRAINTS / ITERATION POLICY / ERROR HANDLING / OUTPUT, in order) was
# dropped by user decision during the lean-prompt campaign: GPT-5.4 may
# reorganize each generator prompt into whatever structure reads best, so the
# fixed headings are no longer a contract. The dataSets-location check below
# stays, because a misfiled key still stops the answer parsing.

# The components stage kept filing the records inside a page, and a misfiled key
# stops the answer parsing. The prompt has to say WHERE they go, not only what
# they are. The old one described the field at length and never said that.
assert "beside pages" in components_prompt.template, \
    "Case 10 FAIL: the components prompt never says where dataSets goes"
print("PASS Case 10 - dataSets location stated (section-skeleton check retired)")
_GEN_CASES += 1


print("=" * 64)
print(f"Specification generators: {_GEN_CASES}/10 cases PASSED")




print("=" * 64)
