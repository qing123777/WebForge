# Ported from fyp.ipynb cell 239 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: js_prompt_selector (@dynamic_prompt middleware)
#
# This cell sits HERE, below the prompts, and not next to the middleware it
# tests, because it compares against `_js_generation_prompt` and
# `_js_modification_prompt`. A test cell sits above every cell that follows
# it, so from up there those names do not exist yet and the cell dies on its
# first assertion. Do not move it back.
#
# These drive the REAL middleware object. The previous version of this cell
# re-implemented the selector as a local copy (_js_sel_fn) and asserted on
# that, so it could silently drift from the middleware actually bound to the
# agent - a passing test that proved nothing. @dynamic_prompt compiles the
# function into a wrap_model_call hook, so the tests go through that hook and
# read back the system message it installs.
from types import SimpleNamespace

_MODEL_SENTINEL_js = object()


class _FakeRequest_js:
    """Stand-in for ModelRequest: records the system message the hook installs."""

    def __init__(self, state):
        self.state = state
        self.system_message = None

    def override(self, system_message=None, **kwargs):
        self.system_message = system_message
        return self


def _select_js_prompt(state):
    """Run the real middleware; return (installed prompt, handler return value)."""
    req = _FakeRequest_js(state)
    seen = {}

    def _handler(request):
        seen["request"] = request
        return _MODEL_SENTINEL_js

    out = js_prompt_selector.wrap_model_call(req, _handler)
    assert seen.get("request") is req, "FAIL: middleware never called the model handler"
    return req.system_message.content, out


# Case 1 [NORMAL] generation intent selects the generation prompt
_prompt, _out = _select_js_prompt({"intent": "generate"})
print("[Case 1 · NORMAL] intent=generate installs the generation prompt")
print("  installed prompt is _js_generation_prompt:", _prompt == _js_generation_prompt)
assert _prompt == _js_generation_prompt, "FAIL: wrong prompt for generate"
assert _out is _MODEL_SENTINEL_js, "FAIL: model call was not forwarded"
print("PASS: generation prompt installed and the model call forwarded\n")

# Case 2 [NORMAL] modify intent selects the modification prompt
_prompt, _ = _select_js_prompt({"intent": "modify"})
print("[Case 2 · NORMAL] intent=modify installs the modification prompt")
print("  installed prompt is _js_modification_prompt:", _prompt == _js_modification_prompt)
assert _prompt == _js_modification_prompt, "FAIL: wrong prompt for modify"
print("PASS: modification prompt installed\n")

# Case 3 [EDGE] no intent in state falls back to generation
_prompt, _ = _select_js_prompt({})
print("[Case 3 · EDGE] missing intent falls back to generation")
print("  fell back to generation prompt:", _prompt == _js_generation_prompt)
assert _prompt == _js_generation_prompt, "FAIL: expected generation as the default"
print("PASS: safe default - a fresh run generates rather than trying to diff nothing\n")

# Case 4 [GUARD] any unrecognised intent also falls back to generation.
# Only "generate" and "modify" exist; anything else must not select the
# modification prompt, which would ask the model to diff against absent code.
for _bad in ("unknown", "MODIFY", "", "add_page"):
    _prompt, _ = _select_js_prompt({"intent": _bad})
    assert _prompt == _js_generation_prompt, f"FAIL: intent={_bad!r} did not fall back"
print("[Case 4 · GUARD] unrecognised intents never reach the modification prompt")
print("  tested:", ["unknown", "MODIFY", "", "add_page"])
print("PASS: only the exact string 'modify' selects modification mode\n")

# Case 5 [EDGE] state=None handled by the (request.state or {}) guard
_prompt, _ = _select_js_prompt(None)
print("[Case 5 · EDGE] state=None handled without raising")
print("  fell back to generation prompt:", _prompt == _js_generation_prompt)
assert _prompt == _js_generation_prompt
print("PASS: no AttributeError on a missing state\n")

# Case 6 [INVARIANT] the two prompts are genuinely different documents, so
# Cases 1-2 are distinguishing real behaviour rather than comparing a string
# to itself.
print("[Case 6 · INVARIANT] the two prompts are distinct, so the assertions above bite")
print(f"  generation {len(_js_generation_prompt)} chars,"
      f" modification {len(_js_modification_prompt)} chars")
assert _js_generation_prompt != _js_modification_prompt, "FAIL: prompts identical"
print("PASS: generation and modification prompts differ\n")

# ── New cases (2026-07-21): spec injection in generation mode ───────────────

# Case 7 [NORMAL] generation + specs in state -> specs appended to the prompt.
# Before this change NOTHING surfaced state to the model; the model could only
# learn spec ids/classNames/states from coverage-guard rejections.
_spec7 = {"pages": [{"rootComponents": [{"id": "spec-probe-7", "tag": "nav"}]}]}
_prompt, _ = _select_js_prompt({"intent": "generate", "components_specification": _spec7})
assert _prompt.startswith(_js_generation_prompt), "FAIL: base prompt must stay the head"
assert "Binding specifications" in _prompt and '"spec-probe-7"' in _prompt, \
    "FAIL: spec content not injected"
print("[Case 7 · NORMAL] generation mode appends the specs to the base prompt")
print("  injected block found:", '"spec-probe-7"' in _prompt)
print("PASS: specs reach the model's context in generation mode\n")

# Case 8 [GUARD] modify mode never injects - the stored spec may be stale
# relative to the hand-edited page.
_prompt, _ = _select_js_prompt({"intent": "modify", "components_specification": _spec7})
assert _prompt == _js_modification_prompt, "FAIL: modify mode must not inject specs"
print("[Case 8 · GUARD] modify mode installs the bare modification prompt")
print("PASS: stale-spec injection impossible in modify mode\n")

# Case 9 [EDGE] a JSON-string spec renders verbatim; an empty "{}" spec is
# skipped so the base prompt stays byte-identical.
_prompt, _ = _select_js_prompt({"intent": "generate",
                             "components_specification": '{"pages": ["string-probe-9"]}'})
assert "string-probe-9" in _prompt and _prompt.startswith(_js_generation_prompt)
_prompt, _ = _select_js_prompt({"intent": "generate", "components_specification": "{}"})
assert _prompt == _js_generation_prompt, "FAIL: empty spec must leave the prompt unchanged"
print("[Case 9 · EDGE] string specs render verbatim, empty specs are skipped")
print("PASS: string and empty specs handled\n")

# Case 10 [GUARD] the no-image and don't-rebuild-grid constraints reach BOTH
# modes (they live in the shared base). PO-08 po0113ce72 shipped fabricated <img>
# photos and a JS-rebuilt grid; store_js_code now hard-refuses the <img>, and the
# prompt tells the model up front so it does not waste a retry finding out.
for _jp in (_js_generation_prompt, _js_modification_prompt):
    assert "NEVER create an <img> element" in _jp, \
        "Case 10 FAIL: the no-image rule is missing from a JS prompt"
    assert "NEVER rebuild the product grid from a data array" in _jp, \
        "Case 10 FAIL: the don't-rebuild-grid rule is missing from a JS prompt"
print("[Case 10] no-image and don't-rebuild-grid constraints reach both modes")
print("PASS: JS constraints present in generation and modification prompts\n")

# Case 11 [NORMAL] the real generated HTML is fed into generate mode so the JS
# agent binds to the ACTUAL DOM (ids, classNames, data-* tokens, shipped state
# attributes), not the spec's guessed names -- the token-vs-label filter bug that
# shipped an empty catalog on po01d91aaf (2026-09-03). Modify mode must NOT get it
# (same stale-page reason as the specs). A missing page -> empty block. Twin of
# the CSS Case 18.
_sid11 = "__jsctxtest__"
_html11 = "<main><select id='filter'><option value='all'>All</option></select></main>"
_p11 = _PREVIEW_ROOT / f"preview_{_sid11}.html"
try:
    _p11.write_text(_html11, encoding="utf-8")
    assert _html11 in _js_html_context_block({"session_id": _sid11}), \
        "FAIL: the HTML context block does not carry the page HTML"
    _prompt11, _ = _select_js_prompt({"intent": "generate", "session_id": _sid11})
    assert _html11 in _prompt11, "FAIL: generate prompt did not receive the real HTML"
    assert "authoritative for the DOM" in _prompt11
    _prompt11m, _ = _select_js_prompt({"intent": "modify", "session_id": _sid11})
    assert _html11 not in _prompt11m, "FAIL: the HTML leaked into modify mode"
finally:
    try:
        _p11.unlink()
    except OSError:
        pass
assert _js_html_context_block({"session_id": "__nope__"}) == "", \
    "FAIL: a missing page must yield an empty block, not raise or inject"
print("[Case 11 - NORMAL] the real HTML reaches generate mode and not modify mode\n")

# Case 12 [GUARD] the declaration-order (TDZ) rule reaches GENERATE mode. PO-08
# po015df552 (2026-09-04) shipped a script whose top-level
# `let cart = loadCartState()` ran before the `const keepElementAutomationReady`
# it reached through buildCartFromDom, a load-time ReferenceError that killed
# every handler. The rule lives in the generation prompt, where a whole file is
# authored; modify mode edits an already-ordered file.
assert "Cannot access X before initialization" in _js_generation_prompt, \
    "Case 12 FAIL: the generation prompt lost the declaration-order (TDZ) rule"
assert "declared BEFORE the first" in _js_generation_prompt, \
    "Case 12 FAIL: the TDZ rule ordering instruction is missing"
print("[Case 12 - GUARD] the declaration-order (TDZ) rule is present in generate mode")
print("PASS: JS generation prompt carries the TDZ ordering rule\n")

# Case 13 [GUARD] the preserve-ids-on-re-render rule reaches BOTH modes. It lives
# in the shared base, not the generation prompt: on po015df552 renderCart() rebuilt
# the quantity <option>s with text only, wiping #cart-qty-option-1..4 (TC-073..076),
# and the pipeline routes that _sweep_dropped_shipped_id finding to js_agent in
# MODIFY mode -- so the rule the fixing agent reads must be in the modify prompt too.
for _jp in (_js_generation_prompt, _js_modification_prompt):
    assert "carry over the id and every machine attribute" in _jp, \
        "Case 13 FAIL: the preserve-ids-on-re-render rule is missing from a JS prompt"
print("[Case 13 - GUARD] the preserve-ids-on-re-render rule is present in both JS modes")
print("PASS: a re-render that rebuilds shipped rows must carry their ids in both modes\n")

# -- Cases 14-16: the shared-data block (Task 1, 2026-09-07). The JS agent kept
# reading product data from the DOM and getting bounced by the Shared Data
# Contract guard into a FULL file rewrite (po1r1f1fb3d, po2r1053187). The block
# hands it the run's records as a finished const, built from the SAME
# _dataset_records the guard reads, so the first store passes.
_sdb_comp = {"dataSets": {
    "products": [{"id": "p-x1", "name": "Aurora X1 Headphones", "salePrice": "$89"}],
    "cartItems": [{"id": "ci-x1", "name": "Aurora X1 Headphones", "quantity": 1}]}}
_sdb_rw = {"pages": [{"flows": [{"actions": [{"type": "addToCart", "targetId": "add"}]}]}]}
_sdb_ro = {"pages": [{"flows": [{"actions": [{"type": "toggleVisibility"}]}]}]}

_sdb_block = _js_shared_data_block({"intent": "generate",
    "components_specification": _sdb_comp, "interaction_specification": _sdb_rw})
assert "const DATA_RECORDS" in _sdb_block, "Case 14 FAIL: data block not injected on a rewriting run"
_recs = _dataset_records(_sdb_comp)
_absent_with = [f"{k}:'{n}'" for k, rid, n in _recs if rid not in _sdb_block and n not in _sdb_block]
_absent_without = [f"{k}:'{n}'" for k, rid, n in _recs if rid not in "" and n not in ""]
assert _absent_with == [], f"Case 14 FAIL: block still misses records {_absent_with}"
assert len(_absent_without) == len(_recs), "Case 14 FAIL: empty code should miss all records"
print("PASS Case 14 - the injected data block carries every record the guard checks")
print(f"[proof] shared-data block: {len(_recs)} record(s) in dataSets. An empty/invented "
      f"script misses all {len(_absent_without)} -> Shared Data Contract REJECT -> full JS "
      f"rewrite (po1r1f1fb3d and po2r1053187 each lost one). With the injected const the "
      f"guard finds {len(_absent_with)} missing, so the first store passes and that rewrite "
      f"is skipped. This is the model-authored path; nothing here changes the guard itself.")

_sdb_ro_block = _js_shared_data_block({"intent": "generate",
    "components_specification": _sdb_comp, "interaction_specification": _sdb_ro})
assert _sdb_ro_block == "", "Case 15 FAIL: block injected with no content-rewriting action (dead const)"
assert not _js_rewrites_data(_sdb_ro) and _js_rewrites_data(_sdb_rw), "Case 15 FAIL: rewrite detector wrong"
print("PASS Case 15 - no data block when no interaction rewrites content (no dead const)")

_sdb_str_block = _js_shared_data_block({"intent": "generate",
    "components_specification": json.dumps(_sdb_comp),
    "interaction_specification": json.dumps(_sdb_rw)})
assert "const DATA_RECORDS" in _sdb_str_block, "Case 16 FAIL: block must build when specs arrive as JSON strings"
print("PASS Case 16 - the block is built even when specs arrive as JSON strings")

print("All 16 cases passed - js_prompt_selector (real middleware object, spec injection).")
