# Ported from fyp.ipynb cell 179 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the HTML agent is TOLD its include filenames (2026-08-30).
# REGRESSION: the prompt used to show "preview_{state.session_id}.css" and ask for
# the EXACT filenames shown. Nothing substitutes a placeholder in a plain prompt
# string, and the selector injected only the specs, so session_id never reached
# the model. It copied the placeholder, store_html_code refused ("Missing required
# include tag(s)"), and the model re-emitted the WHOLE page to fix two attributes
# -- 45s and a full page on po019a8c61, and the same opening rejection on GM-01,
# GM-02 and the earlier PO-08. These cases pin the property: the real filenames
# must reach the model, and no copyable placeholder may remain.
from types import SimpleNamespace as _inc_ns


class _IncRequest:
    """Stand-in for ModelRequest: records the system message the hook installs.

    @dynamic_prompt compiles the selector into a wrap_model_call hook, so the
    middleware object itself is not callable -- the prompt has to be read back
    from the request the hook overrides.
    """

    def __init__(self, state):
        self.state = state
        self.system_message = None

    def override(self, system_message=None, **kwargs):
        self.system_message = system_message
        return self


def _inc_prompt(state):
    req = _IncRequest(state)
    html_prompt_selector.wrap_model_call(req, lambda request: None)
    return req.system_message.content


_inc_passed = 0

_blk = _include_tags_block({"session_id": "po019a8c61"})
assert 'href="preview_po019a8c61.css"' in _blk, f"INC-1 FAIL: real css filename missing:\n{_blk}"
assert 'src="preview_po019a8c61.js"' in _blk, f"INC-1 FAIL: real js filename missing:\n{_blk}"
print("PASS INC-1 - the block carries this run's real filenames, already filled in")
_inc_passed += 1

# The whole point: the model must SEE the id. Build the prompt the way the
# middleware does and check the finished tags are in it.
_req = _inc_ns(state={"intent": "generate", "session_id": "po019a8c61",
                      "layout_specification": {}, "components_specification": {}})
_prompt = _inc_prompt(_req.state)
assert "preview_po019a8c61.css" in _prompt and "preview_po019a8c61.js" in _prompt, \
    "INC-2 FAIL: the assembled generation prompt still never names this run's files"
print("PASS INC-2 - the assembled generation prompt names the real files")
_inc_passed += 1

# No copyable placeholder may survive anywhere in the assembled prompt, except
# inside the sentence that forbids it.
_bad = "preview_{state.session_id}"
assert _bad not in _prompt, \
    f"INC-3 FAIL: a copyable placeholder filename is still in the prompt"
print("PASS INC-3 - no copyable placeholder filename remains")
_inc_passed += 1

# Degrade safely: no session_id -> no block, and no filename built from an empty id.
assert _include_tags_block({}) == "" and _include_tags_block(None) == "", \
    "INC-4 FAIL: a missing session_id must produce no block, not preview_.css"
print("PASS INC-4 - a missing session_id degrades to no block")
_inc_passed += 1

# Modify mode reads the existing file, whose tags are already correct, and its
# guard skips the include check -- so it must not grow the block.
_req_m = _inc_ns(state={"intent": "modify", "session_id": "po019a8c61"})
_prompt_m = _inc_prompt(_req_m.state)
assert "This Run's Include Tags" not in _prompt_m, \
    "INC-5 FAIL: the include-tag block leaked into modify mode"
print("PASS INC-5 - modify mode is unchanged")
_inc_passed += 1

print("=" * 64)
print(f"include-tag injection: {_inc_passed}/5 PASSED (no model calls)")
