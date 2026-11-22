# Ported from fyp.ipynb cell 295 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: css_prompt_selector (@dynamic_prompt middleware)
#
# This cell sits HERE, below the prompts, and not next to the middleware it
# tests, because it compares against `_css_generation_prompt` and
# `_css_modification_prompt`. A test cell sits above every cell that follows
# it, so from up there those names do not exist yet and the cell dies on its
# first assertion. Do not move it back.
#
# These drive the REAL middleware object. The previous version of this cell
# re-implemented the selector as a local copy (_css_sel_fn) and asserted on
# that, so it could silently drift from the middleware actually bound to the
# agent - a passing test that proved nothing. @dynamic_prompt compiles the
# function into a wrap_model_call hook, so the tests go through that hook and
# read back the system message it installs.
from types import SimpleNamespace

_MODEL_SENTINEL_css = object()


class _FakeRequest_css:
    """Stand-in for ModelRequest: records the system message the hook installs."""

    def __init__(self, state):
        self.state = state
        self.system_message = None

    def override(self, system_message=None, **kwargs):
        self.system_message = system_message
        return self


def _select_css_prompt(state):
    """Run the real middleware; return (installed prompt, handler return value)."""
    req = _FakeRequest_css(state)
    seen = {}

    def _handler(request):
        seen["request"] = request
        return _MODEL_SENTINEL_css

    out = css_prompt_selector.wrap_model_call(req, _handler)
    assert seen.get("request") is req, "FAIL: middleware never called the model handler"
    return req.system_message.content, out


# Case 1 [NORMAL] generation intent selects the generation prompt
_prompt, _out = _select_css_prompt({"intent": "generate"})
print("[Case 1 · NORMAL] intent=generate installs the generation prompt")
print("  installed prompt is _css_generation_prompt:", _prompt == _css_generation_prompt)
assert _prompt == _css_generation_prompt, "FAIL: wrong prompt for generate"
assert _out is _MODEL_SENTINEL_css, "FAIL: model call was not forwarded"
print("PASS: generation prompt installed and the model call forwarded\n")

# Case 2 [NORMAL] modify intent selects the modification prompt
_prompt, _ = _select_css_prompt({"intent": "modify"})
print("[Case 2 · NORMAL] intent=modify installs the modification prompt")
print("  installed prompt is _css_modification_prompt:", _prompt == _css_modification_prompt)
assert _prompt == _css_modification_prompt, "FAIL: wrong prompt for modify"
print("PASS: modification prompt installed\n")

# Case 3 [EDGE] no intent in state falls back to generation
_prompt, _ = _select_css_prompt({})
print("[Case 3 · EDGE] missing intent falls back to generation")
print("  fell back to generation prompt:", _prompt == _css_generation_prompt)
assert _prompt == _css_generation_prompt, "FAIL: expected generation as the default"
print("PASS: safe default - a fresh run generates rather than trying to diff nothing\n")

# Case 4 [GUARD] any unrecognised intent also falls back to generation.
# Only "generate" and "modify" exist; anything else must not select the
# modification prompt, which would ask the model to diff against absent code.
for _bad in ("unknown", "MODIFY", "", "add_page"):
    _prompt, _ = _select_css_prompt({"intent": _bad})
    assert _prompt == _css_generation_prompt, f"FAIL: intent={_bad!r} did not fall back"
print("[Case 4 · GUARD] unrecognised intents never reach the modification prompt")
print("  tested:", ["unknown", "MODIFY", "", "add_page"])
print("PASS: only the exact string 'modify' selects modification mode\n")

# Case 5 [EDGE] state=None handled by the (request.state or {}) guard
_prompt, _ = _select_css_prompt(None)
print("[Case 5 · EDGE] state=None handled without raising")
print("  fell back to generation prompt:", _prompt == _css_generation_prompt)
assert _prompt == _css_generation_prompt
print("PASS: no AttributeError on a missing state\n")

# Case 6 [INVARIANT] the two prompts are genuinely different documents, so
# Cases 1-2 are distinguishing real behaviour rather than comparing a string
# to itself.
print("[Case 6 · INVARIANT] the two prompts are distinct, so the assertions above bite")
print(f"  generation {len(_css_generation_prompt)} chars,"
      f" modification {len(_css_modification_prompt)} chars")
assert _css_generation_prompt != _css_modification_prompt, "FAIL: prompts identical"
print("PASS: generation and modification prompts differ\n")

# ── New cases (2026-07-21): spec injection in generation mode ───────────────

# Case 7 [NORMAL] generation + specs in state -> specs appended to the prompt.
# Before this change NOTHING surfaced state to the model; the model could only
# learn spec ids/classNames/states from coverage-guard rejections.
_spec7 = {"pages": [{"rootComponents": [{"id": "spec-probe-7", "tag": "nav"}]}]}
_prompt, _ = _select_css_prompt({"intent": "generate", "decoration_specification": _spec7})
assert _prompt.startswith(_css_generation_prompt), "FAIL: base prompt must stay the head"
assert "Binding specifications" in _prompt and '"spec-probe-7"' in _prompt, \
    "FAIL: spec content not injected"
print("[Case 7 · NORMAL] generation mode appends the specs to the base prompt")
print("  injected block found:", '"spec-probe-7"' in _prompt)
print("PASS: specs reach the model's context in generation mode\n")

# Case 8 [GUARD] modify mode never injects - the stored spec may be stale
# relative to the hand-edited page.
_prompt, _ = _select_css_prompt({"intent": "modify", "decoration_specification": _spec7})
assert _prompt == _css_modification_prompt, "FAIL: modify mode must not inject specs"
print("[Case 8 · GUARD] modify mode installs the bare modification prompt")
print("PASS: stale-spec injection impossible in modify mode\n")

# Case 9 [EDGE] a JSON-string spec renders verbatim; an empty "{}" spec is
# skipped so the base prompt stays byte-identical.
_prompt, _ = _select_css_prompt({"intent": "generate",
                             "decoration_specification": '{"pages": ["string-probe-9"]}'})
assert "string-probe-9" in _prompt and _prompt.startswith(_css_generation_prompt)
_prompt, _ = _select_css_prompt({"intent": "generate", "decoration_specification": "{}"})
assert _prompt == _css_generation_prompt, "FAIL: empty spec must leave the prompt unchanged"
print("[Case 9 · EDGE] string specs render verbatim, empty specs are skipped")
print("PASS: string and empty specs handled\n")

# Case 10 [NORMAL] generation injects a Selector Allowlist from the component
# spec, so the CSS stage targets real selectors instead of inventing class
# names (the CSS<->DOM drift that left 47 dead selectors on run po015b2ac9).
_spec10 = {"pages": [{"regionComponents": {"header": [
    {"id": "nav_links", "tag": "ul", "className": "header-links"},
    {"id": "site_brand", "tag": "a"}]}}]}
_prompt, _ = _select_css_prompt({"intent": "generate", "components_specification": _spec10})
assert "Selector allowlist" in _prompt, "FAIL: allowlist header missing"
assert ".header-links" in _prompt and "#site_brand" in _prompt, "FAIL: contract selectors missing"
assert "never invent" in _prompt.lower() or "do not invent" in _prompt.lower()
print("[Case 10 · NORMAL] generation injects the Selector Allowlist (className else #id)")
print("PASS: CSS stage is handed the exact real selectors\n")

# Case 11 [NORMAL] modify mode NOW injects the allowlist too (fixed 2026-09-01).
# It used to be generation-only, and that gap was E2E-SO-01's root cause: a
# correction work order named a component, the modify prompt handed over no
# selector map, and the CSS agent styled the componentCategory
# `.add-to-cart-button` while the HTML carried `.add-to-cart-btn` -- both
# rounds edited a dead rule. The component selector map is safe here because
# the correction loop runs on the freshly built page (its className map IS the
# page); the full decoration/layout specs are still withheld (Cases 8, 16).
_prompt, _ = _select_css_prompt({"intent": "modify", "components_specification": _spec10})
assert ".header-links" in _prompt and "#site_brand" in _prompt, \
    "FAIL: the selector allowlist must now reach modify mode"
assert "Selector allowlist" in _prompt, "FAIL: allowlist header missing in modify mode"
print("[Case 11 · NORMAL] modify mode now installs the selector allowlist")
print("  [proof] modify prompt carries '.header-links'/'#site_brand' (the real "
      "selectors); before 2026-09-01 this branch appended no allowlist, which is "
      "why E2E-SO-01 styled '.add-to-cart-button' instead of '.add-to-cart-btn'.")
print("PASS: the CSS agent sees real selectors in BOTH modes\n")

# Case 12 [NORMAL] the generation prompt carries the LAYOUT SYSTEM block + its
# tokens, so the CSS stage applies one shared layout (centered container,
# auto-fill grid, fixed-ratio image box) instead of free-styling every section.
_prompt, _ = _select_css_prompt({"intent": "generate"})
assert "Layout system" in _prompt, "FAIL: the layout system block is missing"
for _tok in ("--page-gutter", "--grid-min", "--card-aspect", "--section-gap"):
    assert _tok in _prompt, f"FAIL: {_tok} not named in the layout block"
assert "aspect-ratio" in _prompt and "object-fit:cover" in _prompt, \
    "FAIL: the fixed-ratio image rule is missing"
# Added 2026-08-31 after PO-08 po01e9a8b4 shipped both of these defects.
# The navigation-list reset: five <ul> on that page still computed
# list-style-type: disc, and #navbar-category-links came out 129 x 146
# display:block, so the navbar rendered as a bulleted vertical strip.
assert "list-style: none" in _prompt, (
    "FAIL: the navigation-list reset is missing from the layout block. "
    "Without it a nav <ul> keeps the browser default -- a block with "
    "bullets, one item per line -- and the navbar renders as a vertical "
    "strip whatever width its container has.")
# The container rule must name the TAGS, not just "section". <footer> is
# not a <section>, and on that run #footer measured w=1440 x=0 while all
# seven real sections measured w=1200 x=120.
assert "<footer>" in _prompt and "direct child of <body>" in _prompt.lower(), (
    "FAIL: the container rule no longer names <footer> as a top-level "
    "region. The old wording said 'every top-level section', which let the "
    "model leave the footer full-bleed while every other region sat in the "
    "1200px column.")
# The reverse fault (2026-09-02, po0105c9d9): a footer with a CONTRASTING
# background got max-width on the painted element itself, so the dark band
# stopped at 1200px and the page showed through on both sides on a wide
# screen. The rule now gives the no-inner-wrapper case a padding fallback.
assert "padding-inline: max(var(--page-gutter)" in _prompt \
        and "background stays full-bleed" in _prompt, (
    "FAIL: the full-bleed padding fallback (footer background capped by "
    "max-width) is missing from the layout rule")
# The Grid Target Contract (2026-08-31). #category-navigation on run
# po01e9a8b4 declared six columns over two children, an <h2> and a <ul>:
# the heading took column one, the list was squeezed into 168px, its six
# <li> piled on top of one another, and Playwright refused to click any
# category tile -- while the page's own suite passed.
assert "DIRECT CHILDREN ARE THE REPEATING ITEMS" in _prompt, (
    "FAIL: the grid-target rule is missing. Without it the agent reads a's "
    "region layoutType as 'display:grid on the region' and the grid lands "
    "on an element whose children are a heading and a wrapper.")
assert "grid-column: 1 / -1" in _prompt, (
    "FAIL: the prompt states the rule but never says what to do with the "
    "section heading, so the rule cannot be satisfied.")
assert "declared column count exceeds its item count" in _prompt, (
    "FAIL: the prompt does not warn that a build sweep enforces this.")
print("[Case 12 · NORMAL] generation prompt carries the layout system + tokens")
print("PASS: the CSS stage is told how to apply the shared layout tokens\n")

# Case 13 [NORMAL] the product-image placeholder styling constraint reaches BOTH
# modes -- the page embeds no <img>, so the CSS stage must know to shape the
# placeholder div as the card's image box rather than leave it as plain text.
for _intent in ("generate", "modify"):
    _prompt, _ = _select_css_prompt({"intent": _intent})
    assert "product-image-placeholder" in _prompt, \
        f"FAIL: placeholder styling constraint missing in {_intent} mode"
    assert "aspect ratio" in _prompt, \
        f"FAIL: the placeholder is not tied to a fixed aspect ratio in {_intent} mode"
print("[Case 13 · NORMAL] the placeholder styling constraint reaches both modes")
print("PASS: the CSS stage is told to shape the placeholder as the image box\n")

# Case 14 [NORMAL] the generation prompt forbids making a full-width block
# sticky. A full-width filter panel set position:sticky pins across the viewport
# and covers the content below it (the "Filter beans" overlap, PO-08 2026-08-29).
_prompt, _ = _select_css_prompt({"intent": "generate"})
assert "position: sticky" in _prompt, "FAIL: the sticky rule is missing from generation"
assert "full-width" in _prompt and "scroll normally" in _prompt, \
    "FAIL: the full-width-sticky prohibition is not stated"
# The header is the ONE full-width exception (2026-09-02, po0105c9d9): the
# page shipped sticky on the inner .header-nav-bar, whose containing block
# is the 79px <header>, so it un-stuck after 79px and the nav scrolled away.
assert "on the <header> LANDMARK" in _prompt and "scroll-margin-top" in _prompt, (
    "FAIL: the sticky-header carve-out (sticky on the <header> landmark, "
    "z-index below the drawer, scroll-margin-top on anchor targets) is missing")
print("[Case 14 - NORMAL] generation prompt forbids a full-width sticky region")
print("PASS: a full-width block will not be pinned over the page\n")

# Case 17 [NORMAL] the generation prompt carries the state/overlay honoring
# rules (2026-09-02): the three cross-agent contract faults page-health sweeps
# now catch -- [hidden] overridden, a drawer left in flow, a landmark bar left
# stacking -- each has a generation rule so the FIRST output can avoid it.
_prompt, _ = _select_css_prompt({"intent": "generate"})
assert "[hidden] { display: none !important; }" in _prompt, \
    "FAIL: the [hidden] reset rule is missing (search bug B)"
assert "position: fixed" in _prompt and ":not([hidden])" in _prompt \
        and '[data-state="open"]' in _prompt, \
    "FAIL: the drawer-as-overlay rule is missing (cart)"
assert "`aria-expanded` on the toggle" in _prompt, \
    "FAIL: the drawer prompt no longer warns against keying reveal to the button (cart)"
assert "grouping container out as a flex or" in _prompt, \
    "FAIL: the row-container rule is missing (nav/footer too tall)"
print("[Case 17 - NORMAL] generation prompt carries the [hidden] reset, drawer-overlay and row-container rules")
print("PASS: the three cross-agent contract faults each have a generation-time rule\n")

# Case 15: the region list reaches the agent (B2, 2026-08-31).
# A guard the model cannot satisfy is a wall. store_css_code now refuses a
# stylesheet that leaves a layout region's subtree untouched, and until this
# block existed the CSS stage received components + decoration ONLY -- so a
# region owning no components (every JavaScript-owned one, by the components
# generator's own rule) was invisible to it and no prompt wording could have
# helped. This is the data half of that contract.
_RGP_LAYOUT = {"pages": [{"pageName": "listing", "regions": [
    {"name": "hero", "ownedBy": "HTML"},
    {"name": "cart-drawer", "ownedBy": "JavaScript"}]}]}
_prompt, _ = _select_css_prompt({"intent": "generate",
                                 "layout_specification": _RGP_LAYOUT})
assert "#cart-drawer" in _prompt and "#hero" in _prompt, \
    "FAIL: the layout regions never reach the CSS agent"
assert "ownedBy: JavaScript" in _prompt, \
    "FAIL: the prompt does not say which regions JavaScript owns"
assert "NOT exempt" in _prompt, \
    ("FAIL: the prompt does not say a JavaScript-owned region still needs "
     "container styling, so the guard would refuse a plan the model was never "
     "told how to produce")
print("[Case 15 - NORMAL] the layout regions and the JavaScript rule both reach the agent")

# And modify mode must NOT receive it, for the same reason it receives no other
# specification: the stored spec goes stale the moment the page is hand-edited.
_prompt_m, _ = _select_css_prompt({"intent": "modify",
                                   "layout_specification": _RGP_LAYOUT})
assert "#cart-drawer" not in _prompt_m, \
    "FAIL: a stale layout spec leaked into modify mode"
print("[Case 16 - EDGE] modify mode stays free of spec injection, layout included")
print("PASS: the region list is generation-only\n")

# Case 18 [NORMAL] the real generated HTML is injected into generate mode so the
# CSS agent lays out the ACTUAL DOM tree, not the flat spec list (2026-09-02, the
# hero-hole / filter-offset fix). Modify mode must NOT get it (same stale reason as
# every other spec: the page is hand-editable). A missing page -> empty block.
_sid18 = "__cssctxtest__"
_html18 = "<main><section id='hero-intro'><div class='wrap'>ctx-probe-18</div></section></main>"
_p18 = _PREVIEW_ROOT / f"preview_{_sid18}.html"
try:
    _p18.write_text(_html18, encoding="utf-8")
    assert _html18 in _css_html_context_block({"session_id": _sid18}), \
        "FAIL: the HTML context block does not carry the page HTML"
    _prompt18, _ = _select_css_prompt({"intent": "generate", "session_id": _sid18})
    assert _html18 in _prompt18, "FAIL: generate prompt did not receive the real HTML"
    assert "authoritative for structure" in _prompt18
    _prompt18m, _ = _select_css_prompt({"intent": "modify", "session_id": _sid18})
    assert _html18 not in _prompt18m, "FAIL: the HTML leaked into modify mode"
finally:
    try:
        _p18.unlink()
    except OSError:
        pass
assert _css_html_context_block({"session_id": "__nope__"}) == "", \
    "FAIL: a missing page must yield an empty block, not raise or inject"
print("[Case 18 - NORMAL] the real HTML reaches generate mode and not modify mode")

# Decorative-background contract (PO-08 item B, 2026-09-05): the CSS agent MAY use a
# direct images.unsplash.com URL in a decorative background, but every background-image
# must carry a solid background-color fallback so a dead URL degrades to a colour, not a
# blank rectangle. Lives in the shared base, so both modes carry it.
assert "images.unsplash.com" in _css_shared_base, \
    "BG-DECOR FAIL: the decorative-background allowance is missing"
assert "source.unsplash.com" in _css_shared_base, \
    "BG-DECOR FAIL: the dead-host (source.unsplash.com) warning is missing"
assert "solid background-color token" in _css_shared_base, \
    "BG-DECOR FAIL: the colour-fallback requirement is missing"
print("PASS BG-DECOR - images.unsplash.com allowed WITH a background-color fallback")
print("All 18 cases passed - css_prompt_selector (spec injection + allowlist + layout system + placeholder + sticky + regions + state/overlay honoring + real-HTML context).")

# -- nav wraps on a narrow screen instead of overflowing (2026-09-07). The CSS
# agent shipped a nav with overflow-x:auto that became a ~590px sideways-scroll
# strip on a 375px phone (po2r12253d9). The Layout system rule now tells it to
# wrap, matching the product-grid "reflows on its own" philosophy right beside it.
# The whole Layout system section is GENERATION-only (modify mode edits by diff and
# never re-lays-out), so the rule belongs to the generation prompt alone -- the same
# scope as every other layout rule beside it, and it must not leak into modify mode.
assert "reflow onto more rows" in _css_generation_prompt, \
    "FAIL: the mobile nav-wrap rule is missing from the CSS generation prompt"
assert "flex-wrap: wrap" in _css_generation_prompt, "FAIL: nav-wrap lost its flex-wrap declaration"
assert "reflow onto more rows" not in _css_modification_prompt, \
    "FAIL: a layout rule leaked into modify mode, which does not re-lay-out"
print("PASS: the mobile nav-wrap rule sits in the CSS generation Layout system, beside the grid rule")
