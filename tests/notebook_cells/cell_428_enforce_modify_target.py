# Ported from fyp.ipynb cell 428 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: enforce_modify_target
# Every branch is reachable offline, which is the point: the guarantee is proved
# here rather than inferred from a paid run.
_emt_passed = 0


def _emt_ok(case, description):
    global _emt_passed
    _emt_passed += 1
    print(f"  PASS  {case}  {description}")


class _EMTRequest:
    def __init__(self, tool_call, state):
        self.tool_call = tool_call
        self.state = state

    def override(self, **kw):
        clone = _EMTRequest(self.tool_call, self.state)
        for k, v in kw.items():
            setattr(clone, k, v)
        return clone


def _emt_human(text):
    return {"role": "user", "content": text}


_EMT_MARKER = ("[intent=modify | target_component=add-to-cart-button "
               "| target_instance=2] make this button dark green")


def _emt_run(args, state=None, name="call_secondary_orchestrator"):
    """Return the args the tool would actually receive."""
    seen = {}

    def handler(req):
        seen["args"] = dict((req.tool_call or {}).get("args") or {})
        seen["name"] = (req.tool_call or {}).get("name")
        return "tool-result"

    state = state if state is not None else {"messages": [_emt_human(_EMT_MARKER)]}
    out = _enforce_modify_target(
        _EMTRequest({"name": name, "args": args, "id": "c1"}, state), handler)
    assert out == "tool-result", "the middleware must return the handler's result"
    return seen["args"]


# EMT-1  THE POINT. A paraphrased component name never reaches the tool.
_a = _emt_run({"intent": "modify", "target_component": "the add to cart button",
               "target_instance": 2})
assert _a["target_component"] == "add-to-cart-button", \
    f"EMT-1 FAIL: a paraphrase reached the tool: {_a['target_component']!r}"
_emt_ok("EMT-1", "a paraphrased target_component is replaced by the marker's")

# EMT-2  The instance is the other half, and it is the one that silently edits a
# different card on a page with eight of them.
_a = _emt_run({"intent": "modify", "target_component": "add-to-cart-button",
               "target_instance": 1})
assert _a["target_instance"] == 2, \
    f"EMT-2 FAIL: the wrong instance survived: {_a['target_instance']!r}"
_emt_ok("EMT-2", "a wrong target_instance is replaced by the marker's")

# EMT-3  intent is forced too, so a modify cannot be dispatched as a generate.
_a = _emt_run({"intent": "generate", "target_component": "add-to-cart-button",
               "target_instance": 2})
assert _a["intent"] == "modify", f"EMT-3 FAIL: intent stayed {_a['intent']!r}"
_emt_ok("EMT-3", "intent is forced to modify when a marker is present")

# EMT-4  The marker is text, so its instance is a string. The tool takes an int.
_a = _emt_run({"intent": "modify", "target_component": "x", "target_instance": "2"})
assert _a["target_instance"] == 2 and isinstance(_a["target_instance"], int), \
    f"EMT-4 FAIL: instance not normalised to int: {_a['target_instance']!r}"
_emt_ok("EMT-4", "the instance is normalised from marker text to an int")

# EMT-5  Missing arguments are filled in, not just corrected.
_a = _emt_run({})
assert _a == {"intent": "modify", "target_component": "add-to-cart-button",
              "target_instance": 2}, f"EMT-5 FAIL: {_a}"
_emt_ok("EMT-5", "arguments the model omitted entirely are supplied")

# EMT-6  A correct call is left exactly as it is. This middleware must be
# invisible when the model gets it right, which is most of the time.
_good = {"intent": "modify", "target_component": "add-to-cart-button",
         "target_instance": 2, "user_request": "make it dark green"}
_a = _emt_run(dict(_good))
assert _a == _good, f"EMT-6 FAIL: a correct call was altered: {_a}"
_emt_ok("EMT-6", "a correct call passes through untouched, extra args included")

# EMT-7  Everything the model said that is NOT the target survives. The marker
# owns three fields and nothing else.
_a = _emt_run({"intent": "modify", "target_component": "wrong",
               "target_instance": 9, "user_request": "make it dark green"})
assert _a["user_request"] == "make it dark green", \
    "EMT-7 FAIL: the instruction was lost while correcting the target"
_emt_ok("EMT-7", "the user's instruction is preserved while the target is corrected")

# EMT-8  A generation run has no marker to be faithful to.
_a = _emt_run({"intent": "generate", "target_component": "", "target_instance": 1},
              state={"messages": [_emt_human("Generate an umbrella shop.")]})
assert _a["intent"] == "generate", \
    f"EMT-8 FAIL: a generate run was rewritten as a modify: {_a}"
_emt_ok("EMT-8", "a request with no marker is left alone")

# EMT-9  PO-07 seeds the state instead of sending a marker. Both routes resolve.
_a = _emt_run({"intent": "modify", "target_component": "guessed", "target_instance": 5},
              state={"messages": [_emt_human("make this button green")],
                     "intent": "modify", "target_component": "hero-cta",
                     "target_instance": 3})
assert _a["target_component"] == "hero-cta" and _a["target_instance"] == 3, \
    f"EMT-9 FAIL: a seeded modify was not enforced: {_a}"
_emt_ok("EMT-9", "a seeded modify is enforced with no marker in the text")

# EMT-10  Only the dispatch tool is touched. Correcting anything else would be
# this middleware reaching outside what it knows.
_a = _emt_run({"intent": "generate"}, name="update_input")
assert _a == {"intent": "generate"}, f"EMT-10 FAIL: another tool was rewritten: {_a}"
_emt_ok("EMT-10", "a call to any other tool is untouched")

# EMT-11  A marker with an unreadable instance means the first one, which is
# what a component appearing once produces.
_a = _emt_run({}, state={"messages": [_emt_human(
    "[intent=modify | target_component=navbar | target_instance=] recolour it")]})
assert _a["target_instance"] == 1 and _a["target_component"] == "navbar", \
    f"EMT-11 FAIL: {_a}"
_emt_ok("EMT-11", "an unreadable instance falls back to the first")

print("=" * 76)
print(f"enforce_modify_target: {_emt_passed}/11 PASSED")
print("Forces the ARGUMENTS, never the call. The model can still answer in")
print("words, which is how a structural modify is declined. See PO-04.")
print("=" * 76)
