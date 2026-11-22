# Ported from fyp.ipynb cell 415 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: ask_user and its two guards
# Offline. The tool touches no model and no disk, so every branch is reachable
# here, and the live case only has to prove the orchestrator reaches for it.
_au_passed = 0


def _au_ok(case, description):
    global _au_passed
    _au_passed += 1
    print(f"  PASS  {case}  {description}")


class _AURuntime:
    """Only the two attributes the tool reads."""

    def __init__(self, state=None):
        self.state = state or {}
        self.tool_call_id = "au-call-1"


def _au_call(state=None, **kw):
    kw.setdefault("question", "Which page, and what look?")
    kw.setdefault("options", [
        {"field": "type", "value": "home", "label": "Home",
         "help": "A storefront: hero, categories, featured products."},
        {"field": "style", "value": "minimal_premium"},
    ])
    return ask_user.func(runtime=_AURuntime(state), **kw)


def _au_text(cmd):
    return cmd.update["messages"][0].content


# AU-1  A good call records the question and spends the gate.
_c = _au_call()
assert _c.update["clarifier_used"] is True, "AU-1 FAIL: the gate was not spent"
_pq = _c.update["pending_question"]
assert _pq["question"] == "Which page, and what look?", "AU-1 FAIL: question lost"
assert len(_pq["options"]) == 2, "AU-1 FAIL: an option was dropped"
assert _pq["allow_free_text"] is True, \
    "AU-1 FAIL: the free-text box is not optional, the gate has to stay open"
_au_ok("AU-1", "a renderable question is recorded and the gate is spent")

# AU-2  Every option carries what the panel needs, including a label the model
# did not bother to write. Rendering must never fall back to a raw schema word.
assert _pq["options"][1]["label"] == "Minimal premium", \
    "AU-2 FAIL: a missing label was not filled in from the value"
assert set(_pq["options"][0]) == {"field", "value", "label", "help"}, \
    "AU-2 FAIL: an option has a shape the panel cannot rely on"
_au_ok("AU-2", "every option carries field, value, label and help")

# AU-3  THE LOAD-BEARING GUARD. A value outside the schema must never reach the
# panel, because the user would pick something that cannot be built.
_c = _au_call(options=[
    {"field": "style", "value": "super_fancy"},
    {"field": "style", "value": "catalog_heavy"},
])
assert "pending_question" not in _c.update, \
    "AU-3 FAIL: an illegal value was recorded for the panel to render"
assert "clarifier_used" not in _c.update, \
    "AU-3 FAIL: a refused call spent the gate, so the model cannot try again"
assert "super_fancy" in _au_text(_c) and "catalog_heavy" in _au_text(_c), \
    "AU-3 FAIL: the refusal does not name the bad value and the legal ones"
_au_ok("AU-3", "an illegal value for a closed field is refused, gate not spent")

# AU-4  A field the user does not choose is equally unrenderable.
_c = _au_call(options=[{"field": "colour", "value": "blue"},
                       {"field": "colour", "value": "red"}])
assert "pending_question" not in _c.update, "AU-4 FAIL: unknown field accepted"
assert "commerce_type" in _au_text(_c), \
    "AU-4 FAIL: the refusal does not say which fields are choosable"
_au_ok("AU-4", "an option naming a field the user cannot choose is refused")

# AU-5  Free text is the whole reason the model writes the options. An option
# with no field is not value-checked, so sections and features can be offered.
_c = _au_call(options=[
    {"value": "hero + featured products", "help": "A short front page."},
    {"value": "hero + categories + reviews", "help": "More to browse."},
])
assert _c.update["pending_question"]["options"][0]["field"] == "", \
    "AU-5 FAIL: a free-text option was rejected or given a field"
_au_ok("AU-5", "an option with no field passes through unchecked")

# AU-6  One option is not a choice.
for _n, _opts in ((1, [{"value": "home", "field": "type"}]), (0, [])):
    _c = _au_call(options=_opts)
    assert "pending_question" not in _c.update, \
        f"AU-6 FAIL: {_n} option(s) was accepted as a question"
_au_ok("AU-6", "fewer than two options is refused")

# AU-7  An empty question is a control with no prompt above it.
_c = _au_call(question="   ")
assert "pending_question" not in _c.update, "AU-7 FAIL: empty question accepted"
_au_ok("AU-7", "an empty question is refused")

# AU-8  THE OTHER LOAD-BEARING GUARD. Ask once, enforced here rather than only
# instructed in the prompt.
_c = _au_call(state={"clarifier_used": True})
assert "pending_question" not in _c.update, "AU-8 FAIL: a second question was recorded"
assert "already asked" in _au_text(_c), \
    "AU-8 FAIL: the refusal does not say why, so the model cannot recover"
assert "defaults" in _au_text(_c), \
    "AU-8 FAIL: the refusal does not say what to do instead, so it may stall"
_au_ok("AU-8", "a second call on the same thread is refused, with the way out")

# AU-9  Every refusal must be recognisable by the ERROR HANDLING rule in the
# prompt, which keys on the REFUSED prefix and nothing else.
for _bad in ({"question": ""}, {"options": []},
             {"options": [{"field": "style", "value": "nope"},
                          {"field": "style", "value": "nope2"}]}):
    _c = _au_call(**_bad)
    assert _au_text(_c).startswith("REFUSED: "), \
        f"AU-9 FAIL: a refusal for {_bad} is not marked REFUSED"
    assert set(_c.update) == {"messages"}, \
        f"AU-9 FAIL: a refusal for {_bad} wrote state as well as a message"
_au_ok("AU-9", "every refusal is prefixed REFUSED and writes no state")

# AU-10  The guard list is generated, not typed. If a field is ever added to the
# choice schema, this catches a hand-written copy left behind here.
assert set(_CLOSED_CHOICE_FIELDS) == set(user_choice_options()), \
    "AU-10 FAIL: the closed-field list has drifted from the choice schema"
for _f in _CLOSED_CHOICE_FIELDS:
    assert _legal_choice_values(_f), f"AU-10 FAIL: {_f} offers no values"
_au_ok("AU-10", "the closed-field list is generated from the choice schema")

print("=" * 76)
print(f"ask_user: {_au_passed}/10 PASSED  "
      f"(closed fields: {', '.join(_CLOSED_CHOICE_FIELDS)})")
print("NOT wired into create_agent yet. The prompt rule and the PO-01 rewrite")
print("land together in the next change, so nothing live behaves differently.")
print("=" * 76)
