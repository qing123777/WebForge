# Ported from fyp.ipynb cell 178 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: html_prompt_selector (@dynamic_prompt middleware)
#
# This cell sits HERE, below the prompts, and not next to the middleware it
# tests, because it compares against `_html_generation_prompt` and
# `_html_modification_prompt`. A test cell sits above every cell that follows
# it, so from up there those names do not exist yet and the cell dies on its
# first assertion. Do not move it back.
#
# These drive the REAL middleware object. The previous version of this cell
# re-implemented the selector as a local copy, which could silently drift from
# the middleware actually bound to the agent - a passing test that proved
# nothing. @dynamic_prompt compiles the function into a wrap_model_call hook,
# so the tests go through that hook and read back the system message it sets.
from types import SimpleNamespace

_MODEL_SENTINEL = object()


class _FakeRequest:
    """Stand-in for ModelRequest: records the system message the hook installs."""

    def __init__(self, state):
        self.state = state
        self.system_message = None

    def override(self, system_message=None, **kwargs):
        self.system_message = system_message
        return self


def _select_prompt(state):
    """Run the real middleware; return (installed prompt, handler return value)."""
    req = _FakeRequest(state)
    seen = {}

    def _handler(request):
        seen["request"] = request
        return _MODEL_SENTINEL

    out = html_prompt_selector.wrap_model_call(req, _handler)
    assert seen.get("request") is req, "FAIL: middleware never called the model handler"
    return req.system_message.content, out


# The selector APPENDS blocks to a base prompt (the specifications, the icon
# catalogue), so these cases assert "starts with the right base" rather
# than "==". They used to compare by equality, which held only while every
# appended block happened to be empty: adding the image catalogue in M2 broke
# all three at once. `startswith` states what the case actually means -- which
# base was selected -- and the appended content is checked on its own below.

# Case 1 [NORMAL] generation intent selects the generation prompt
_prompt, _out = _select_prompt({"intent": "generate"})
print("[Case 1 - NORMAL] intent=generate installs the generation prompt")
print("  installed prompt starts with _html_generation_prompt:",
      _prompt.startswith(_html_generation_prompt))
assert _prompt.startswith(_html_generation_prompt), "FAIL: wrong prompt for generate"
assert not _prompt.startswith(_html_modification_prompt), "FAIL: modify base selected"
assert _out is _MODEL_SENTINEL, "FAIL: model call was not forwarded"
print("PASS: generation prompt installed and the model call forwarded\n")

# Case 2 [NORMAL] modify intent selects the modification prompt
_prompt, _ = _select_prompt({"intent": "modify"})
print("[Case 2 - NORMAL] intent=modify installs the modification prompt")
print("  installed prompt starts with _html_modification_prompt:",
      _prompt.startswith(_html_modification_prompt))
assert _prompt.startswith(_html_modification_prompt), "FAIL: wrong prompt for modify"
print("PASS: modification prompt installed\n")

# Case 3 [EDGE] no intent in state falls back to generation
_prompt, _ = _select_prompt({})
print("[Case 3 - EDGE] missing intent falls back to generation")
print("  fell back to generation prompt:", _prompt.startswith(_html_generation_prompt))
assert _prompt.startswith(_html_generation_prompt), "FAIL: expected generation as the default"
print("PASS: safe default - a fresh run generates rather than trying to diff nothing\n")

# Case 4 [GUARD] any unrecognised intent also falls back to generation.
# Only "generate" and "modify" exist; anything else must not select the
# modification prompt, which would ask the model to diff against absent code.
for _bad in ("unknown", "GENERATE", "", "add_page"):
    _prompt, _ = _select_prompt({"intent": _bad})
    assert _prompt.startswith(_html_generation_prompt), \
        f"FAIL: intent={_bad!r} did not fall back"
print("[Case 4 - GUARD] unrecognised intents never reach the modification prompt")
print("  tested:", ["unknown", "GENERATE", "", "add_page"])
print("PASS: only the exact string 'modify' selects modification mode\n")

# Case 5 [EDGE] state=None handled by the (request.state or {}) guard
_prompt, _ = _select_prompt(None)
print("[Case 5 - EDGE] state=None handled without raising")
print("  fell back to generation prompt:", _prompt.startswith(_html_generation_prompt))
assert _prompt.startswith(_html_generation_prompt)
print("PASS: no AttributeError on a missing state\n")

# Case 6 [INVARIANT] the two prompts are genuinely different documents, so
# Cases 1-2 are distinguishing real behaviour rather than comparing a string
# to itself.
print("[Case 6 - INVARIANT] the two prompts are distinct, so the assertions above bite")
print(f"  generation {len(_html_generation_prompt)} chars,"
      f" modification {len(_html_modification_prompt)} chars")
assert _html_generation_prompt != _html_modification_prompt, "FAIL: prompts identical"
print("PASS: generation and modification prompts differ\n")

# ── New cases (2026-07-21): spec injection in generation mode ───────────────

# Case 7 [NORMAL] generation + specs in state -> specs appended to the prompt.
# Before this change NOTHING surfaced state to the model; the model could only
# learn spec ids/classNames/states from coverage-guard rejections.
_spec7 = {"pages": [{"rootComponents": [{"id": "spec-probe-7", "tag": "nav"}]}]}
_prompt, _ = _select_prompt({"intent": "generate", "components_specification": _spec7})
assert _prompt.startswith(_html_generation_prompt), "FAIL: base prompt must stay the head"
assert "Binding specifications" in _prompt and '"spec-probe-7"' in _prompt, \
    "FAIL: spec content not injected"
print("[Case 7 - NORMAL] generation mode appends the specs to the base prompt")
print("  injected block found:", '"spec-probe-7"' in _prompt)
print("PASS: specs reach the model's context in generation mode\n")

# Case 8 [GUARD] modify mode never injects - the stored spec may be stale
# relative to the hand-edited page.
_prompt, _ = _select_prompt({"intent": "modify", "components_specification": _spec7})
assert _prompt.startswith(_html_modification_prompt), "FAIL: wrong base prompt"
assert "## Binding specifications for THIS run" not in _prompt, \
    "FAIL: modify mode must not inject specs"
assert '"spec-probe-7"' not in _prompt, \
    "FAIL: spec CONTENT leaked into the modification prompt"
# The exact claim: modification base + the two catalogues, and nothing else.
# Checking for the word "components_specification" would be wrong -- the prompt
# TEXT names it ten times, because the instructions tell the agent to read the
# specification. A term appearing is not the same as content being injected.
assert _prompt == (_html_modification_prompt + _icon_catalogue_block()), \
    "FAIL: something other than the icon catalogue was appended in modify mode"
print("[Case 8 - GUARD] modify mode installs the bare modification prompt")
print("PASS: stale-spec injection impossible in modify mode\n")

# Case 9 [EDGE] a JSON-string spec renders verbatim; an empty "{}" spec is
# skipped so the base prompt stays byte-identical.
_prompt, _ = _select_prompt({"intent": "generate",
                             "components_specification": '{"pages": ["string-probe-9"]}'})
assert "string-probe-9" in _prompt and _prompt.startswith(_html_generation_prompt)
_prompt, _ = _select_prompt({"intent": "generate", "components_specification": "{}"})
assert _prompt == (_html_generation_prompt + _icon_catalogue_block()), \
    "FAIL: an empty spec must add nothing beyond the icon catalogue"
print("[Case 9 - EDGE] string specs render verbatim, empty specs are skipped")
print("PASS: string and empty specs handled\n")

print("All 9 cases passed - html_prompt_selector (real middleware object, spec injection).")


# Unit tests: _targets_block (modify-mode component listing appendix)
assert _targets_block({}) == "", "empty state must yield no block"
assert _targets_block({"target_component": ""}) == "", "blank target must yield no block"
_one = _targets_block({"target_component": "#mini-cart"})
assert "## Components to fix in THIS call" in _one and "1. #mini-cart" in _one, \
    "single target must fall back to a one-item listing"
_many = _targets_block({"target_components": [".a", ".b", ".c"]})
assert "1. .a" in _many and "2. .b" in _many and "3. .c" in _many, \
    "explicit list must be numbered in order"
# explicit list wins over target_component; empty entries filtered out
_mix = _targets_block({"target_components": [".x", ""], "target_component": "#y"})
assert "1. .x" in _mix and "#y" not in _mix and "2." not in _mix, \
    "list must win over target_component and drop empties"
# the resolved session file names reach the model (13b71045: it sent the
# literal placeholder preview_{session_id}.html to read_file)
_sid = _targets_block({"session_id": "abc-123", "target_component": "#y"})
assert ("preview_abc-123.html" in _sid and "preview_abc-123.css" in _sid
        and "preview_abc-123.js" in _sid and "1. #y" in _sid), _sid
assert _sid.find("This run's files") < _sid.find("Components to fix"), "files first"
assert _targets_block({"session_id": "  "}) == "", "blank session_id adds nothing"
print("PASS _targets_block: empty, single-fallback, multi, list-wins/filter, session files named")

# ── Lucide icon catalogue (M4) ───────────────────────────────────────────────
# The geometry is COPIED from the lucide-static package, never generated, so the
# thing worth testing is that the copy is intact. A wrong curve command renders
# as a scribble that html-validate, the coverage guard and assert_visible all
# accept -- there is no downstream check that would catch it.
import xml.etree.ElementTree as _ic_ET
import re as _ic_re

_IC_PATH_CHARS = set("MmLlHhVvCcSsQqTtAaZz0123456789 .,-+eE")

for _name, (_purpose, _inner) in sorted(_LUCIDE_ICONS.items()):
    # 1. the markup is well-formed XML once wrapped
    try:
        _ic_ET.fromstring("<svg>%s</svg>" % _inner)
    except _ic_ET.ParseError as _e:
        raise AssertionError("icon %r is not well-formed XML: %s" % (_name, _e))
    # 2. every path is syntactically a path: starts with a moveto, uses only
    #    legal command letters and number characters
    _ds = _ic_re.findall(r'\bd="([^"]+)"', _inner)
    assert _ds or "<circle" in _inner or "<rect" in _inner, \
        "icon %r has no drawable geometry" % _name
    for _d in _ds:
        assert _d[0] in "Mm", "icon %r: path does not start with a moveto: %r" % (_name, _d[:20])
        _stray = set(_d) - _IC_PATH_CHARS
        assert not _stray, "icon %r: illegal path characters %r" % (_name, sorted(_stray))
    assert _purpose and _purpose.strip(), "icon %r has no purpose label" % _name
print("PASS _LUCIDE_ICONS: %d icons, all well-formed, all paths syntactically valid"
      % len(_LUCIDE_ICONS))

# The wrapper is what makes the icon restylable and non-announced. Both matter:
# stroke="currentColor" is why a CSS colour change reaches the icon without
# touching the HTML, and aria-hidden is why a screen reader reads the button's
# label instead of the glyph.
assert 'stroke="currentColor"' in _LUCIDE_WRAPPER, "icons would not inherit CSS colour"
assert 'aria-hidden="true"' in _LUCIDE_WRAPPER and 'focusable="false"' in _LUCIDE_WRAPPER
assert 'viewBox="0 0 24 24"' in _LUCIDE_WRAPPER
print("PASS _LUCIDE_WRAPPER: currentColor + aria-hidden + focusable=false")

_IB = _icon_catalogue_block()
for _name in _LUCIDE_ICONS:
    assert _name in _IB, "catalogue omits %r" % _name
    assert _LUCIDE_ICONS[_name][1] in _IB, "catalogue omits the geometry for %r" % _name
assert _LUCIDE_WRAPPER in _IB, "the catalogue never shows the wrapper to use"
assert "unicode" in _IB.lower(), "the catalogue does not warn off unicode glyphs"
print("PASS _icon_catalogue_block: all %d icons and the wrapper are shown"
      % len(_LUCIDE_ICONS))

_gen, _ = _select_prompt({"intent": "generate"})
_mod, _ = _select_prompt({"intent": "modify"})
assert "Lucide v1.31.0" in _gen and "Lucide v1.31.0" in _mod, \
    "the icon catalogue must reach BOTH modes"
print("PASS html_prompt_selector: the icon catalogue reaches BOTH modes")

# Icons are not on disk, so unlike the photographs they cannot go missing --
# but an empty dict must still degrade rather than emit a headless block.
_ic_real = _LUCIDE_ICONS
try:
    _LUCIDE_ICONS = {}
    assert _icon_catalogue_block() == "", "an empty icon set must yield no block"
finally:
    _LUCIDE_ICONS = _ic_real
print("PASS _icon_catalogue_block: an empty set degrades to no block")


# The anchor-target rule (2026-08-31). On run po01e9a8b4 the HTML agent invented
# six <section> wrappers purely to hold the ids the category tiles linked to.
# Those wrappers became the items of the product grid, so the eight real cards
# sat two levels below it and never reached the grid; each wrapper then stretched
# to 2863px and its cards overflowed onto the row beneath. Both modes need the
# rule: a modify that adds a link must not add a wrapper either.
_gen_a, _ = _select_prompt({"intent": "generate"})
_mod_a, _ = _select_prompt({"intent": "modify"})
for _label, _p in (("generate", _gen_a), ("modify", _mod_a)):
    assert "anchor target is an ATTRIBUTE" in _p, (
        f"the anchor-target rule is missing from the {_label} prompt, so nothing "
        f"stops the agent wrapping elements in extra <section>s to carry ids")
print("PASS html_prompt_selector: the anchor-target rule reaches BOTH modes")

# The Control-Value Contract (2026-09-02). On po0118d1da the roast <select>
# shipped value="All roasts" while the JS matched value == "all", so every
# filter and the search that inherits its value at load emptied the grid and
# the control read as dead. A generation rule so the first output uses tokens;
# a page-health sweep (_sweep_filter_value_dead) catches a miss.
_gen_cv, _ = _select_prompt({"intent": "generate"})
assert "Control-Value Contract" in _gen_cv and "machine value is a TOKEN" in _gen_cv, \
    "the Control-Value Contract (option value = token) is missing from generation"
print("PASS html_prompt_selector: the Control-Value Contract reaches the generation prompt")
