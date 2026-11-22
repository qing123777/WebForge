# Ported from fyp.ipynb cell 153 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: store_html_code
from types import SimpleNamespace

TEST_HTML = '<!DOCTYPE html><html lang="en"><head><title>T</title></head><body><p>Hi</p></body></html>'

# Case 1: html_code stored correctly
dummy_runtime = SimpleNamespace(
    state={"html_code": "", "lint_passed": False},
    tool_call_id="test-sc-001"
)
result = store_html_code.func(TEST_HTML, dummy_runtime)
update = result.update
assert update.get("html_code") == TEST_HTML, "FAIL: html_code not stored correctly"
assert "messages" in update, "FAIL: messages missing"
print("[Case 1 · NORMAL] Valid HTML is admitted into state and a confirmation returned.")
print(update["messages"][0].content)
print("PASS: html_code stored correctly\n")

# Case 2: must NOT touch lint_passed
assert "lint_passed" not in update, "FAIL: store_html_code must not touch lint_passed"
print("[Case 2 · INVARIANT] Storing code must never open the lint gate on its own.")
print(f"lint_passed present in returned update: {'lint_passed' in update}")
print("PASS: lint_passed not modified by store_html_code\n")

# Case 3: overwrites existing html_code
dummy_runtime2 = SimpleNamespace(
    state={"html_code": "<old/>", "lint_passed": True},
    tool_call_id="test-sc-002"
)
result2 = store_html_code.func(TEST_HTML, dummy_runtime2)
assert result2.update["html_code"] == TEST_HTML, "FAIL: existing html_code not overwritten"
print("[Case 3 · NORMAL] A second submission replaces the stored artifact rather than "
      "appending to it.")
print(f"stored value now begins: {result2.update['html_code'][:45]}...")
print("PASS: store_html_code overwrites existing html_code\n")

# ── New cases (2026-07-08): link/script include-tag + component coverage ────
_FULL_HTML_NO_TAGS = (
    '<!DOCTYPE html><html lang="en"><head><title>T</title></head>'
    '<body><nav id="navbar"></nav><div class="product-card"></div></body></html>'
)
_FULL_HTML_WITH_TAGS = (
    '<!DOCTYPE html><html lang="en"><head><title>T</title>'
    '<link rel="stylesheet" href="preview_abc123.css"></head>'
    '<body><nav id="navbar"></nav><div class="product-card"></div>'
    '<script src="preview_abc123.js" defer></script></body></html>'
)
_COMPONENTS_SPEC = {"pages": [{"pageName": "listing", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "product-card", "tag": "div", "className": "product-card"},
]}}]}

def _rt_html(html_code, **state_extra):
    state = {"html_code": html_code, "lint_passed": False}
    state.update(state_extra)
    return SimpleNamespace(state=state, tool_call_id="test-sc-gen")

# Case 4: generate + session_id set + BOTH include tags missing -> rejected,
# html_code NOT stored, both missing tags named in the message
r4 = store_html_code.func(_FULL_HTML_NO_TAGS, _rt_html(
    _FULL_HTML_NO_TAGS, intent="generate", session_id="abc123"))
assert "html_code" not in r4.update, "FAIL: rejected call must not store html_code"
msg4 = r4.update["messages"][0].content
assert "preview_abc123.css" in msg4 and "preview_abc123.js" in msg4
print("[Case 4 · GUARD] Generation mode with both include tags absent: rejected before "
      "storing, and both missing filenames are named.")
print(msg4)
print("PASS: missing include tags rejected, both filenames named\n")

# Case 5: tags present, no components_specification provided -> accepted
r5 = store_html_code.func(_FULL_HTML_WITH_TAGS, _rt_html(
    _FULL_HTML_WITH_TAGS, intent="generate", session_id="abc123"))
assert r5.update.get("html_code") == _FULL_HTML_WITH_TAGS
print("[Case 5 · EDGE] Include tags present but no specification supplied: the coverage "
      "check is skipped rather than failing on absent data.")
print(r5.update["messages"][0].content)
print("PASS: no spec supplied -> coverage check skipped, code accepted\n")

# Case 6: tags present, components_specification has an id NOT in the HTML -> rejected
_html_missing_one = _FULL_HTML_WITH_TAGS.replace('<nav id="navbar"></nav>', "")
r6 = store_html_code.func(_html_missing_one, _rt_html(
    _html_missing_one, intent="generate", session_id="abc123",
    components_specification=_COMPONENTS_SPEC))
assert "html_code" not in r6.update
msg6 = r6.update["messages"][0].content
assert "navbar" in msg6 and "product-card" not in msg6.split("navbar")[0], \
    f"FAIL: expected only 'navbar' missing: {msg6}"
print("[Case 6 · GUARD] A specification component absent from the markup is rejected, and "
      "only the genuinely missing one is named.")
print(msg6)
print("PASS: missing component named, present one not falsely flagged\n")

# Case 7: tags present, all spec components present -> accepted
r7 = store_html_code.func(_FULL_HTML_WITH_TAGS, _rt_html(
    _FULL_HTML_WITH_TAGS, intent="generate", session_id="abc123",
    components_specification=_COMPONENTS_SPEC))
assert r7.update.get("html_code") == _FULL_HTML_WITH_TAGS
print("[Case 7 · NORMAL] Include tags present and every specification component "
      "addressable: accepted.")
print(r7.update["messages"][0].content)
print("PASS: full coverage + tags present -> accepted\n")

# Case 8 (regression safety): intent="modify" (Step 0 read-back) with tags/
# components missing entirely -> NOT blocked, exemption holds
r8 = store_html_code.func(_FULL_HTML_NO_TAGS, _rt_html(
    _FULL_HTML_NO_TAGS, intent="modify", session_id="abc123",
    components_specification=_COMPONENTS_SPEC))
assert r8.update.get("html_code") == _FULL_HTML_NO_TAGS, \
    "FAIL: modify-mode Step 0 must be exempt from tag/coverage checks"
print("[Case 8 · EDGE] Modification mode reads the existing file back into state at Step 0, "
      "so it is exempt from the tag and coverage checks a fresh generation must pass.")
print(r8.update["messages"][0].content)
print("PASS: modify-mode Step 0 read-back not blocked\n")

# Case 9 (backward compat): no session_id in state at all (old-style test
# fixtures, like Cases 1-3 above) -> check skipped gracefully, no crash
r9 = store_html_code.func(_FULL_HTML_NO_TAGS, _rt_html(_FULL_HTML_NO_TAGS))
assert r9.update.get("html_code") == _FULL_HTML_NO_TAGS
print("[Case 9 · EDGE] No session_id in state: the include-tag check is skipped rather than "
      "raising, since the expected filenames cannot be derived.")
print(r9.update["messages"][0].content)
print("PASS: missing session_id -> check skipped, no crash")


# ── New cases (2026-07-21): string-spec coercion + state materialization ────
import json

# Case 10 (REGRESSION): a spec passed as a JSON STRING must still be enforced.
# E2E-GM-02 found the dict-walk silently returning [] on a str, which turned
# the whole component check into a no-op.
r10 = store_html_code.func(_html_missing_one, _rt_html(
    _html_missing_one, intent="generate", session_id="abc123",
    components_specification=json.dumps(_COMPONENTS_SPEC)))
assert "html_code" not in r10.update, "FAIL: string spec must not disable the guard"
assert "navbar" in r10.update["messages"][0].content
print("[Case 10 · REGRESSION] A JSON-string spec is parsed and enforced, not skipped.")
print(r10.update["messages"][0].content)
print("PASS: string spec coerced, guard still active\n")

# Case 11 (GUARD): unparseable string spec -> loud [INTERNAL] refusal
r11 = store_html_code.func(_FULL_HTML_WITH_TAGS, _rt_html(
    _FULL_HTML_WITH_TAGS, intent="generate", session_id="abc123",
    components_specification="{not valid json"))
assert "html_code" not in r11.update
assert "[INTERNAL]" in r11.update["messages"][0].content
print("[Case 11 · GUARD] An unparseable spec fails loudly instead of checking nothing.")
print(r11.update["messages"][0].content)
print("PASS: unparseable spec -> [INTERNAL] refusal\n")

# ── State Materialization Contract enforcement ──────────────────────────────
_SPEC_STATES = {"pages": [{"pageName": "listing", "rootComponents": [
    {"className": "product-card", "id": "product-card", "tag": "article",
     "states": [{"name": "hover"}, {"name": "selected"}]},
]}]}

def _cards_html(second_attrs=""):
    return (
        '<!DOCTYPE html><html lang="en"><head><title>T</title>'
        '<link rel="stylesheet" href="preview_abc123.css"></head>'
        '<body><article class="product-card" aria-selected="false"></article>'
        f'<article class="product-card"{second_attrs}></article>'
        '<script src="preview_abc123.js" defer></script></body></html>'
    )

# Case 12 (GUARD): a declared state absent from ONE instance -> rejected; the
# message names the attribute and instance count; hover is never demanded
_bare12 = _cards_html()
r12 = store_html_code.func(_bare12, _rt_html(
    _bare12, intent="generate", session_id="abc123",
    components_specification=_SPEC_STATES))
assert "html_code" not in r12.update, "FAIL: unmaterialized state must be rejected"
_m12 = r12.update["messages"][0].content
assert "aria-selected" in _m12 and "1 of 2" in _m12, _m12
assert "state 'hover'" not in _m12, "FAIL: hover is a CSS pseudo-class, never an attribute"
print("[Case 12 · GUARD] A card missing aria-selected is rejected; hover stays exempt.")
print(_m12)
print("PASS: unmaterialized state rejected, pseudo-class states exempt\n")

# Case 13 (NORMAL): every instance carries the resting attribute -> accepted
_ok13 = _cards_html(' aria-selected="false"')
r13 = store_html_code.func(_ok13, _rt_html(
    _ok13, intent="generate", session_id="abc123",
    components_specification=_SPEC_STATES))
assert r13.update.get("html_code") == _ok13
print("[Case 13 · NORMAL] All instances materialized: accepted.")
print(r13.update["messages"][0].content)
print("PASS: fully materialized states accepted\n")

# Case 14 (EDGE): a state with no aria-* mapping falls back to data-state
_SPEC_CUSTOM = {"pages": [{"pageName": "listing", "rootComponents": [
    {"id": "hero", "tag": "section", "states": [{"name": "featured"}]},
]}]}
_hero_bare = _FULL_HTML_WITH_TAGS.replace(
    '<nav id="navbar"></nav>',
    '<nav id="navbar"></nav><section id="hero"></section>')
r14a = store_html_code.func(_hero_bare, _rt_html(
    _hero_bare, intent="generate", session_id="abc123",
    components_specification=_SPEC_CUSTOM))
assert "html_code" not in r14a.update
assert "data-state" in r14a.update["messages"][0].content
_hero_ok = _hero_bare.replace(
    '<section id="hero">', '<section id="hero" data-state="default">')
r14b = store_html_code.func(_hero_ok, _rt_html(
    _hero_ok, intent="generate", session_id="abc123",
    components_specification=_SPEC_CUSTOM))
assert r14b.update.get("html_code") == _hero_ok
print("[Case 14 · EDGE] A custom state name requires data-state; present -> accepted.")
print(r14b.update["messages"][0].content)
print("PASS: non-aria state falls back to data-state\n")

# ── No-image contract (2026-08-29) ───────────────────────────────────
# The image feature was removed. An <img> now has no supported source and is
# refused; products use a labelled .product-image-placeholder and decoration is
# drawn in CSS or an inline <svg> element.
def _img_html(tag_html):
    """_FULL_HTML_WITH_TAGS with markup dropped inside the product card."""
    return _FULL_HTML_WITH_TAGS.replace(
        '<div class="product-card"></div>',
        f'<div class="product-card">{tag_html}</div>')


# Case 15: every <img> is refused now -- local path, remote host and data: URI
# alike. There is no allowed image source any more.
for _src in ("img/running-shoe.jpg",
             "https://picsum.photos/seed/x/400/300",
             "https://via.placeholder.com/400x300",
             "data:image/svg+xml,%3Csvg%3E%3C/svg%3E"):
    _h = _img_html(f'<img src="{_src}" alt="x">')
    _r = store_html_code.func(_h, _rt_html(
        _h, intent="generate", session_id="abc123",
        components_specification=_COMPONENTS_SPEC))
    assert "html_code" not in _r.update, f"FAIL: an <img> was stored: {_src}"
    assert "does not embed images" in _r.update["messages"][0].content, \
        _r.update["messages"][0].content
print("[Case 15] Every <img> source is refused -- local, remote and data: alike.")
print("PASS: no <img> has a supported source\n")

# Case 16: the message points the model at the two supported paths -- a labelled
# placeholder for products, CSS/inline <svg> for decoration.
_h16 = _img_html('<img src="img/phone.jpg" alt="Product">')
r16 = store_html_code.func(_h16, _rt_html(
    _h16, intent="generate", session_id="abc123",
    components_specification=_COMPONENTS_SPEC))
_m16 = r16.update["messages"][0].content
assert "product-image-placeholder" in _m16 and "inline <svg>" in _m16, _m16
print("[Case 16] The refusal names the placeholder and the inline-SVG route.")
print(_m16)
print("PASS: the fix is discoverable from the message\n")

# Case 17: an <img> with no src at all is refused too -- no src makes it pass.
_h17 = _img_html('<img alt="Product">')
r17 = store_html_code.func(_h17, _rt_html(
    _h17, intent="generate", session_id="abc123",
    components_specification=_COMPONENTS_SPEC))
assert "html_code" not in r17.update
assert "does not embed images" in r17.update["messages"][0].content
print("[Case 17 · EDGE] An <img> carrying no src is refused like any other.")
print("PASS: a src-less <img> is caught\n")

# Case 18: an inline <svg> is NOT an <img> -- it carries no src and cannot fail
# to load, so decoration drawn as inline SVG is untouched by the rule.
_h18 = _FULL_HTML_WITH_TAGS.replace(
    '<div class="product-card"></div>',
    '<div class="product-card">'
    '<div class="product-image-placeholder">Running Shoe</div>'
    '<svg role="img" aria-label="Inline"><rect width="10" height="10"/></svg>'
    '</div>')
r18 = store_html_code.func(_h18, _rt_html(
    _h18, intent="generate", session_id="abc123",
    components_specification=_COMPONENTS_SPEC))
assert r18.update.get("html_code") == _h18, \
    f"FAIL: inline SVG + placeholder rejected: {r18.update['messages'][0].content}"
print("[Case 18 · NORMAL] Inline <svg> and a labelled placeholder are accepted -- "
      "neither is an <img>.")
print("PASS: the drawn/placeholder route is admitted\n")

# Case 19: MODIFICATION MODE IS EXEMPT. Modify mode opens by re-storing the file
# already on disk; if that re-store were rejected over an <img> the file already
# had, the correction loop that exists to REPAIR it could never start.
_h19 = _img_html('<img src="img/phone.jpg" alt="Product">')
r19 = store_html_code.func(_h19, _rt_html(_h19, intent="modify", session_id="abc123"))
assert r19.update.get("html_code") == _h19, \
    "FAIL: modify mode must not be blocked by a pre-existing <img>"
print("[Case 19 · INVARIANT] Modification mode accepts a file whose <img> predates "
      "the guard, so the correction loop is never deadlocked by it.")
print("PASS: modify-mode exemption holds\n")

# Case 21 (GUARD): the markup must not ship the native attribute either. The
# resting aria-disabled="false" is required (Case 12); the native one is refused
# outright, because it takes the control out of the tab order before any script
# runs.
_SPEC_DIS = {"pages": [{"pageName": "p", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "product-card", "tag": "div", "className": "product-card",
     "states": [{"name": "disabled"}]},
]}}]}
_h21_bad = _FULL_HTML_WITH_TAGS.replace(
    '<div class="product-card"></div>',
    '<div class="product-card" aria-disabled="false" disabled></div>')
r21 = store_html_code.func(_h21_bad, _rt_html(
    _h21_bad, intent="generate", session_id="abc123",
    components_specification=_SPEC_DIS))
assert "html_code" not in r21.update, "FAIL: native disabled attribute was stored"
assert "Disabled-State Contract" in r21.update["messages"][0].content
print("[Case 21 · GUARD] A native disabled attribute is refused even when the "
      "resting aria-disabled is correctly present.")
print(r21.update["messages"][0].content)
_h21_ok = _h21_bad.replace(' disabled>', '>')
r21b = store_html_code.func(_h21_ok, _rt_html(
    _h21_ok, intent="generate", session_id="abc123",
    components_specification=_SPEC_DIS))
assert r21b.update.get("html_code") == _h21_ok, \
    f"FAIL: aria-only markup rejected: {r21b.update['messages'][0].content}"
print("PASS: native attribute rejected, aria-only markup accepted\n")

print("store_html_code: no-image contract + disabled-state cases passed.")


# ── Resting-value check (2026-08-09) ─────────────────────────────────────────
# The SO-01 run shipped this, and every test passed:
#   <button aria-disabled="true" class="add-to-cart-btn" data-state="disabled">
# Probed in a real browser: opacity 0.5, cursor not-allowed, click refused. The
# add-to-cart button arrived unusable. The guard's own message said "missing
# aria-disabled=false", but the check only asked whether the ATTRIBUTE EXISTED,
# so any value passed. Presence is not materialization.
_SPEC_RV = {"pages": [{"pageName": "plp", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "product-card", "tag": "div", "className": "product-card",
     "states": [{"name": "disabled"}]},
]}}]}


def _rv(markup):
    _h = _FULL_HTML_WITH_TAGS.replace('<div class="product-card"></div>', markup)
    return _h, store_html_code.func(_h, _rt_html(
        _h, intent="generate", session_id="abc123",
        components_specification=_SPEC_RV))


# Case 23: the exact defect -- present, but already active
_h23, r23 = _rv('<div class="product-card" aria-disabled="true"></div>')
assert "html_code" not in r23.update, "FAIL: a page delivered already-disabled was accepted"
_m23 = r23.update["messages"][0].content
assert "RESTING" in _m23 and 'aria-disabled="false"' in _m23, _m23
print("[Case 23 · GUARD] aria-disabled=\"true\" at rest is refused: the attribute is "
      "present, but the control ships unusable.")
print(_m23)
print("PASS: resting VALUE enforced, not just presence\n")

# Case 24: the correct resting value is accepted
_h24, r24 = _rv('<div class="product-card" aria-disabled="false"></div>')
assert r24.update.get("html_code") == _h24, \
    f"FAIL: correct resting markup rejected: {r24.update['messages'][0].content}"
print("[Case 24 · NORMAL] aria-disabled=\"false\" at rest is accepted.")
print("PASS: the compliant form still passes\n")

# Case 25: EVERY instance is checked, not just the first, and the count is honest
_h25 = _FULL_HTML_WITH_TAGS.replace(
    '<div class="product-card"></div>',
    '<div class="product-card" aria-disabled="false"></div>'
    '<div class="product-card" aria-disabled="true"></div>'
    '<div class="product-card" aria-disabled="false"></div>')
r25 = store_html_code.func(_h25, _rt_html(
    _h25, intent="generate", session_id="abc123", components_specification=_SPEC_RV))
assert "html_code" not in r25.update
assert "1 of 3" in r25.update["messages"][0].content, r25.update["messages"][0].content
print("[Case 25 · GUARD] One bad instance among three is caught and counted.")
print(r25.update["messages"][0].content)
print("PASS: per-instance check\n")

# Case 26: a data-state component resting at anything but "default"
_SPEC_DS = {"pages": [{"pageName": "plp", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "product-card", "tag": "div", "className": "product-card",
     "states": [{"name": "loading"}]},
]}}]}
_h26 = _FULL_HTML_WITH_TAGS.replace(
    '<div class="product-card"></div>',
    '<div class="product-card" data-state="loading"></div>')
r26 = store_html_code.func(_h26, _rt_html(
    _h26, intent="generate", session_id="abc123", components_specification=_SPEC_DS))
assert "html_code" not in r26.update
assert 'data-state="default"' in r26.update["messages"][0].content
print("[Case 26 · GUARD] A non-aria state must rest at data-state=\"default\" too.")
print("PASS: the rule is not aria-specific\n")

# Case 27: hover/focus stay exempt -- they are CSS pseudo-classes, never attributes
_SPEC_PS = {"pages": [{"pageName": "plp", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "product-card", "tag": "div", "className": "product-card",
     "states": [{"name": "hover"}, {"name": "focus"}]},
]}}]}
r27 = store_html_code.func(_FULL_HTML_WITH_TAGS, _rt_html(
    _FULL_HTML_WITH_TAGS, intent="generate", session_id="abc123",
    components_specification=_SPEC_PS))
assert r27.update.get("html_code") == _FULL_HTML_WITH_TAGS, \
    "FAIL: pointer states must not require an attribute at all"
print("[Case 27 · INVARIANT] hover and focus remain exempt from both halves of the check.")
print("PASS: pseudo-state exemption unchanged\n")


# ── Anchor Navigation Contract (added 2026-08-10) ───────────────────────────
# One document, several sections, <a href="#shop"> -> <section id="shop">. A
# dangling link is silent on the page, so it needs a build-time guard rather
# than a test case.
print("[Case 28 \u00b7 GUARD] A nav link to a non-existent section is REFUSED.")
_AN_BAD = ('<html><head><link rel="stylesheet" href="preview_anc.css">'
           '<script src="preview_anc.js" defer></script></head><body>'
           '<nav><a href="#shop">Shop</a><a href="#support">Support</a></nav>'
           '<section id="shop"><h2>Shop</h2></section></body></html>')
_r = store_html_code.func(_AN_BAD, _rt_html(_AN_BAD, intent="generate",
                                            session_id="anc"))
_m = _r.update["messages"][0].content
assert "html_code" not in _r.update, "FAIL: a dangling link was saved"
assert "Anchor Navigation Contract" in _m and "#support" in _m, _m
print("   ", _m[:104])
print("PASS: refused, and the message names the offending link\n")

print("[Case 29 \u00b7 NORMAL] Every link resolving to a section is accepted.")
_AN_OK = _AN_BAD.replace("<section id=\"shop\"><h2>Shop</h2></section>",
                         '<section id="shop"><h2>Shop</h2></section>'
                         '<section id="support"><h2>Support</h2></section>')
_r = store_html_code.func(_AN_OK, _rt_html(_AN_OK, intent="generate",
                                           session_id="anc"))
assert _r.update.get("html_code") == _AN_OK, _r.update["messages"][0].content
print("PASS: two sections, two links, saved\n")

print("[Case 30 \u00b7 EDGE] '#', '#top' and external links are never flagged.")
_AN_EXT = _AN_OK.replace('<a href="#support">Support</a>',
                         '<a href="#">x</a><a href="#top">Top</a>'
                         '<a href="https://example.com">Out</a>'
                         '<a href="#support">Support</a>')
_r = store_html_code.func(_AN_EXT, _rt_html(_AN_EXT, intent="generate",
                                            session_id="anc"))
assert _r.update.get("html_code") == _AN_EXT, _r.update["messages"][0].content
print("PASS: conventional and external hrefs pass through\n")

print("[Case 31 \u00b7 GUARD] The check runs in MODIFY mode too, unlike the others.")
# Every other guard here is generate-only. This one needs no specification, so
# exempting modify would let the correction loop introduce a silent dead link.
_r = store_html_code.func(_AN_BAD, _rt_html(_AN_BAD, intent="modify",
                                            session_id="anc"))
assert "Anchor Navigation Contract" in _r.update["messages"][0].content
assert "html_code" not in _r.update, "FAIL: modify mode saved a dangling link"
print("PASS: modify mode is NOT exempt from this one\n")

print("store_html_code: 4 anchor-navigation cases passed.")

print("[Case 32 \u00b7 GUARD] Two nav links may not share one section.")
# E2E-SO-01 on 2026-08-10: the contract only required a fragment to RESOLVE, so
# the agent pointed Shop, New Arrivals, Best Sellers and Cart all at #main.
# Four links, one destination, every one of them resolving. A guard that can be
# satisfied by collapsing what it protects is not a guard.
_AN_DUP = ('<html><head><link rel="stylesheet" href="preview_anc.css">'
           '<script src="preview_anc.js" defer></script></head><body>'
           '<nav><a href="#main">Shop</a><a href="#main">New</a>'
           '<a href="#main">Sale</a></nav><main id="main">x</main>'
           '</body></html>')
_r = store_html_code.func(_AN_DUP, _rt_html(_AN_DUP, intent="generate",
                                            session_id="anc"))
_m = _r.update["messages"][0].content
assert "html_code" not in _r.update, "FAIL: three links to one target were saved"
assert "Anchor Navigation Contract" in _m and "not navigation" in _m, _m
assert "'#main'" in _m and "Shop" in _m, _m
print("   ", _m.split(": ")[-1][:96])
print("PASS: duplicated nav targets refused, and the labels are named\n")

print("[Case 33 \u00b7 EDGE] Distinct targets, '#top' and a second <nav> are fine.")
_AN_OKN = ('<html><head><link rel="stylesheet" href="preview_anc.css">'
           '<script src="preview_anc.js" defer></script></head><body>'
           '<nav><a href="#">x</a><a href="#top">T</a><a href="#top">T2</a>'
           '<a href="#shop">Shop</a><a href="#sale">Sale</a></nav>'
           '<nav><a href="#shop">Shop again</a></nav>'
           '<section id="shop"></section><section id="sale"></section>'
           '</body></html>')
_r = store_html_code.func(_AN_OKN, _rt_html(_AN_OKN, intent="generate",
                                            session_id="anc"))
assert _r.update.get("html_code") == _AN_OKN, _r.update["messages"][0].content
print("PASS: '#'/'#top' repeat freely, and separate navs may reuse a target\n")

print("[Case 33b \u00b7 GUARD] A link to a SECOND DOCUMENT is REFUSED.")
# The two checks above both open by skipping any href that is not a fragment,
# because they ask whether a fragment resolves. That left the opposite mistake
# unguarded: a run builds ONE document, named after the session, so
# href="checkout.html" can only ever be a 404. It is silent in exactly the same
# way -- the click succeeds and the user lands on nothing.
_XD_BAD = ('<html><head><link rel="stylesheet" href="preview_anc.css">'
           '<script src="preview_anc.js" defer></script></head><body>'
           '<nav><a href="#shop">Shop</a><a href="checkout.html">Checkout</a></nav>'
           '<section id="shop"><h2>Shop</h2></section></body></html>')
_r = store_html_code.func(_XD_BAD, _rt_html(_XD_BAD, intent="generate",
                                            session_id="anc"))
_m = _r.update["messages"][0].content
assert "html_code" not in _r.update, "FAIL: a link to a second page was saved"
assert "checkout.html" in _m and "second document" in _m, _m
print("   ", _m.split(": ")[-1][:100])
print("PASS: refused, and the message names the file that cannot exist\n")

print("[Case 33c \u00b7 EDGE] Root, relative and parent paths are refused too.")
for _bad_href in ("/checkout", "./cart.html", "../index.html", "pages/pdp.html"):
    _h = _XD_BAD.replace("checkout.html", _bad_href)
    _r = store_html_code.func(_h, _rt_html(_h, intent="generate", session_id="anc"))
    assert "html_code" not in _r.update, f"FAIL: {_bad_href!r} was saved"
print("PASS: every shape of local path is caught, not just .html\n")

print("[Case 33d \u00b7 INVARIANT] Off-page links that are legitimate still pass.")
# Refusing these would break real pages. An external shop link, an email link, a
# phone link and a javascript: placeholder all leave the document legitimately.
_XD_OK = _XD_BAD.replace(
    '<a href="checkout.html">Checkout</a>',
    '<a href="https://example.com">Out</a>'
    '<a href="http://example.com">Out2</a>'
    '<a href="mailto:shop@example.com">Mail</a>'
    '<a href="tel:+60123456789">Call</a>'
    '<a href="javascript:void(0)">Menu</a>')
_r = store_html_code.func(_XD_OK, _rt_html(_XD_OK, intent="generate",
                                           session_id="anc"))
assert _r.update.get("html_code") == _XD_OK, _r.update["messages"][0].content
print("PASS: external, mail, phone and placeholder links untouched\n")

print("[Case 33e \u00b7 GUARD] The cross-document check runs in MODIFY mode too.")
# Same reason as the dangling-link check: it compares the document with itself,
# needs no specification, and a correction round can introduce one just as
# easily as a first generation can.
_r = store_html_code.func(_XD_BAD, _rt_html(_XD_BAD, intent="modify",
                                            session_id="anc"))
assert "html_code" not in _r.update, "FAIL: modify mode saved a link to a second page"
assert "second document" in _r.update["messages"][0].content
print("PASS: modify mode is not exempt from this one either\n")

# ── Component Category Contract (Cases 34-37) ────────────────────────────────
# On 2026-08-11 a sweep found data-component in test fixtures and in fyp.py's
# schema text only, never in a generated page: no prompt asked for it and no
# guard required it. The role-aware image rule and the preview's select mode
# both resolve through that attribute, so an absent one is a silent failure of
# both.
_CAT_SPEC = {"pages": [{"pageName": "plp", "rootComponents": [
    {"id": "navbar", "tag": "nav", "componentCategory": "navbar"},
    {"id": "product-card", "tag": "article", "className": "product-card",
     "componentCategory": "product-card"},
    {"id": "wrapper", "tag": "div"},          # no category -> never checked
]}]}


def _cat_html(nav_attr="", card_attr="", cards=1):
    # The card carries a LABELLED placeholder because the Product Image Contract
    # applies the moment card_attr declares data-component="product-card". These
    # cases are about the category attribute, not about images, so the placeholder
    # is here to keep them focused rather than to be tested.
    card = ('<article class="product-card" %s>'
            '<div class="product-image-placeholder">Shoe</div>'
            '<h3>Shoe</h3></article>' % card_attr)
    return ('<html><head><link rel="stylesheet" href="preview_cat.css">'
            '<script src="preview_cat.js" defer></script></head><body>'
            '<nav id="navbar" %s></nav><div id="wrapper">%s</div>'
            '</body></html>' % (nav_attr, card * cards))


def _cat_store(html, intent="generate"):
    return store_html_code.func(html, _rt_html(
        html, intent=intent, session_id="cat",
        components_specification=_CAT_SPEC))


print("[Case 34 \u00b7 NORMAL] Category present on every instance -> stored.")
_CAT_OK = _cat_html('data-component="navbar"',
                    'data-component="product-card"', cards=2)
_r = _cat_store(_CAT_OK)
assert _r.update.get("html_code") == _CAT_OK, _r.update["messages"][0].content
print("PASS: data-component accepted on both the id branch and the class branch\n")

print("[Case 35 \u00b7 GUARD] A missing data-component is refused and named.")
_r = _cat_store(_cat_html('', 'data-component="product-card"'))
_m = _r.update["messages"][0].content
assert "html_code" not in _r.update, "FAIL: a page with no category was saved"
assert "Component Category Contract" in _m, _m
assert "'navbar'" in _m and 'data-component="navbar"' in _m, _m
assert "product-card" not in _m.split("Component Category")[1].split("\n")[0], _m
print("   ", [l for l in _m.splitlines() if "Category" in l][0][:104])
print("PASS: only the offending component is named, and the fix is spelled out\n")

print("[Case 36 \u00b7 GUARD] Present but WRONG is refused too, not just absent.")
# Same lesson as aria-disabled: a presence check accepted any value, so the
# SO-01 page shipped aria-disabled="true" and passed. A data-component carrying
# the wrong category silently routes the image rule to the wrong component.
_r = _cat_store(_cat_html('data-component="footer"',
                          'data-component="product-card"'))
_m = _r.update["messages"][0].content
assert "html_code" not in _r.update, "FAIL: a wrong category was saved"
assert 'data-component="footer"' in _m and '"navbar"' in _m, _m
print("PASS: a wrong value is refused and both the shipped and expected value shown\n")

print("[Case 37 \u00b7 EDGE] No category in the spec, and modify mode, are exempt.")
# A node without componentCategory must never be asked for the attribute --
# fyp.py's schema says to omit it for structural wrappers.
_CAT_NONE = {"pages": [{"pageName": "plp", "rootComponents": [
    {"id": "wrapper", "tag": "div"}]}]}
_html = ('<html><head><link rel="stylesheet" href="preview_cat.css">'
         '<script src="preview_cat.js" defer></script></head><body>'
         '<div id="wrapper"></div></body></html>')
_r = store_html_code.func(_html, _rt_html(
    _html, intent="generate", session_id="cat",
    components_specification=_CAT_NONE))
assert _r.update.get("html_code") == _html, _r.update["messages"][0].content
# Modify mode re-stores the file already on disk; the stored spec may be stale
# after a hand-edit, so every spec-driven guard is exempt there.
_BAD = _cat_html('', '')
_r = _cat_store(_BAD, intent="modify")
assert _r.update.get("html_code") == _BAD, "FAIL: modify mode is not exempt"
print("PASS: an uncategorised node is silent, and modify mode is exempt\n")

print("store_html_code: 4 component-category cases passed (37 total).")

# ── Product Image Contract (Cases 41-45) ─────────────────────────────
# The image feature was removed (2026-08-29). A product role can no longer show a
# photograph; its image slot is a labelled .product-image-placeholder carrying the
# product name as real DOM text. An <img> in a product role is refused twice over:
# the no-image contract refuses the tag, and this contract wants the labelled
# placeholder in its place.
_SOE_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "viewBox='0 0 400 300'%3E%3Crect width='400' height='300'/%3E%3Ctext "
    "x='200' y='150'%3EShoe%3C/text%3E%3C/svg%3E")


def _pi_page(body):
    return ('<html><head><link rel="stylesheet" href="preview_pi.css">'
            '<script src="preview_pi.js" defer></script></head><body>'
            + body + '</body></html>')


def _pi_store(body, intent="generate"):
    html = _pi_page(body)
    return html, store_html_code.func(html, _rt_html(
        html, intent=intent, session_id="pi"))


print("[Case 41 · NORMAL] A product card with a labelled placeholder is stored.")
_h, _r = _pi_store(
    '<article class="product-card" data-component="product-card">'
    '<div class="product-image-placeholder">Trail Running Shoe</div>'
    '<h3>Trail Running Shoe</h3></article>')
assert _r.update.get("html_code") == _h, _r.update["messages"][0].content
print("PASS: a labelled placeholder in a product role is accepted\n")

print("[Case 42 · GUARD] A product <img> is REFUSED (no-image contract).")
_h, _r = _pi_store(
    '<article class="product-card" data-component="product-card">'
    f'<img alt="Trail running shoe" src="{_SOE_SVG}">'
    '<h3>Trail Running Shoe</h3></article>')
assert "html_code" not in _r.update, "FAIL: a product <img> was stored"
assert "does not embed images" in _r.update["messages"][0].content
print("PASS: an <img> in a product card no longer passes\n")

print("[Case 43 · GUARD] A product role with no placeholder at all is refused.")
# The CSS-drawn card: drawn art has no lower bound, and no check can tell a
# well-drawn phone from a grey box. A product role must name its product.
_h, _r = _pi_store(
    '<article class="product-card" data-component="product-card">'
    '<div class="mini-phone"><div class="mini-screen"></div></div>'
    '<h3>Nova X Pro</h3></article>')
assert "html_code" not in _r.update, "FAIL: a card with no placeholder was stored"
_m = _r.update["messages"][0].content
assert "Product Image Contract" in _m and "product-image-placeholder" in _m, _m
print("PASS: a CSS-drawn product card with no placeholder is refused\n")

print("[Case 44 · NORMAL] Decorative regions need no placeholder and may be drawn.")
# The rule is scoped by ROLE. A hero banner claims to depict nothing in
# particular, so a gradient or an inline <svg> there misleads nobody.
_h, _r = _pi_store(
    '<section data-component="hero-section">'
    '<div class="hero-art"></div>'
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3h18v18H3z"/></svg>'
    '</section>'
    '<div data-component="promo-banner"><span class="stripe"></span></div>')
assert _r.update.get("html_code") == _h, _r.update["messages"][0].content
print("PASS: hero and promo regions are untouched by the rule\n")

print("[Case 45 · EDGE] Cart thumbnails count; a labelled placeholder satisfies them.")
_h, _r = _pi_store(
    '<li data-component="cart-item"><div class="cart-thumb"></div>'
    '<b>Shoe</b></li>')
assert "html_code" not in _r.update, "FAIL: a cart item with no placeholder was stored"
assert "cart-item" in _r.update["messages"][0].content
_h, _r = _pi_store(
    '<li data-component="cart-item">'
    '<div class="product-image-placeholder">Trail Running Shoe</div>'
    '<b>Shoe</b></li>')
assert _r.update.get("html_code") == _h, _r.update["messages"][0].content
# ...and modify mode is exempt, like every other spec-era guard here.
_bad = ('<article class="product-card" data-component="product-card">'
        '<h3>Shoe</h3></article>')
_h, _r = _pi_store(_bad, intent="modify")
assert _r.update.get("html_code") == _h, "FAIL: modify mode is not exempt"
print("PASS: cart-item enforced, placeholder satisfies it, modify exempt\n")

print("store_html_code: product-image cases passed.")

# ── Labelled placeholder detail (Cases 46-48) ─────────────────────
# The placeholder is now the ONLY product-image path. The label is the whole
# point: assert_text can read it and a screen reader can announce it, neither of
# which is true of an empty box.
print("[Case 46 · NORMAL] A labelled placeholder stands in for the product image.")
_h, _r = _pi_store(
    '<article class="product-card" data-component="product-card">'
    '<div class="product-image-placeholder">Orchid Bouquet</div>'
    '<h3>Orchid Bouquet</h3></article>')
assert _r.update.get("html_code") == _h, _r.update["messages"][0].content
print("PASS: a named placeholder is accepted\n")

print("[Case 47 · GUARD] An EMPTY placeholder is still refused.")
# Without the text it is the grey box again, only with a class name on it.
_h, _r = _pi_store(
    '<article class="product-card" data-component="product-card">'
    '<div class="product-image-placeholder"></div><h3>Orchid</h3></article>')
assert "html_code" not in _r.update, "FAIL: an empty placeholder was stored"
_m = _r.update["messages"][0].content
assert "EMPTY" in _m and "real text" in _m, _m
print("   ", [l for l in _m.splitlines() if "EMPTY" in l][0][-92:])
print("PASS: the label is what makes a placeholder honest, and it is enforced\n")

print("[Case 48 · EDGE] Whitespace is not a label; every product role accepts one.")
_h, _r = _pi_store(
    '<article class="product-card" data-component="product-card">'
    '<div class="product-image-placeholder">   \n  </div></article>')
assert "html_code" not in _r.update, "FAIL: whitespace counted as a label"
# The placeholder is allowed in EVERY product role, cart-item included.
_h, _r = _pi_store(
    '<li data-component="cart-item">'
    '<div class="product-image-placeholder">Orchid Bouquet</div>'
    '<b>Orchid Bouquet</b></li>')
assert _r.update.get("html_code") == _h, _r.update["messages"][0].content
print("PASS: blank label refused, cart-item accepts a tile\n")

# ── Icon Accessibility Contract (Cases 49-51) ────────────────────────────────
# One piece of markup satisfies two separate requirements, which is why this is
# a contract rather than a lint preference. aria-hidden keeps a screen reader on
# the ACTION ("Search") instead of the glyph. The same attribute, plus
# pointer-events: none from the CSS agent, keeps the preview's select mode off
# the icon: clicking the search glyph must select the search bar, because an
# icon's colour and size are modifiable but its GEOMETRY is not -- swapping a
# glyph means rewriting SVG path data, which modification mode excludes.
print("[Case 49 \u00b7 NORMAL] Hidden icon plus a labelled control is accepted.")
_h, _r = _pi_store(
    '<button class="icon-btn" aria-label="Search">'
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
    '<path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/></svg></button>'
    '<a href="#cart" aria-label="Cart">'
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg></a>'
    # the anchor needs a real target: the Anchor Navigation Contract runs in
    # BOTH modes and refuses a fragment that resolves to nothing
    '<section id="cart"></section>')
assert _r.update.get("html_code") == _h, _r.update["messages"][0].content
print("PASS: the Lucide wrapper's own markup satisfies the contract\n")

print("[Case 50 \u00b7 GUARD] An announced icon is refused.")
_h, _r = _pi_store(
    '<button id="cart-button" aria-label="Cart">'
    '<svg viewBox="0 0 24 24"><path d="M5 12h14"/></svg></button>')
assert "html_code" not in _r.update, "FAIL: an announced icon was stored"
_m = _r.update["messages"][0].content
assert "Icon Accessibility Contract" in _m, _m
assert "cart-button" in _m and 'aria-hidden' in _m, _m
assert "select mode" in _m, "the message must give the second reason too: %s" % _m
print("   ", [l for l in _m.splitlines() if "Icon Accessibility" in l][0][:100])
print("PASS: refused, and both reasons are stated\n")

print("[Case 51 \u00b7 GUARD] An icon-only control with no accessible name is refused.")
# The icon is hidden from assistive technology by rule, so without a label the
# control announces nothing at all -- the two halves have to travel together.
_h, _r = _pi_store(
    '<button class="icon-btn">'
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg></button>')
assert "html_code" not in _r.update, "FAIL: an unnamed icon button was stored"
assert "no accessible name" in _r.update["messages"][0].content
# Visible text is an accessible name too, so a labelled-plus-text control passes.
_h, _r = _pi_store(
    '<button class="text-btn">'
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>'
    'Add to bag</button>')
assert _r.update.get("html_code") == _h, _r.update["messages"][0].content
# A button with no icon at all is none of this rule's business.
_h, _r = _pi_store('<button class="plain">Checkout</button>')
assert _r.update.get("html_code") == _h
print("PASS: label or visible text required, icon-free controls untouched\n")


# ── Shared Data Contract (2026-08-15) ────────────────────────────────────────
# Every record in dataSets must appear on the page. Otherwise the agent read the
# tree, saw "a product card goes here", and invented its own products.
_SD_SPEC = {
    "dataSets": {"products": [
        {"id": "p1", "name": "Aurora Headphones", "price": "89.00"},
        {"id": "p2", "name": "Meridian Desk Lamp", "price": "42.00"},
    ]},
    "pages": [{"pageName": "home", "regionComponents": {"main": [
        {"id": "product-grid", "tag": "div", "className": "product-grid"},
    ]}}],
}


def _sd_store(body):
    html = ('<!DOCTYPE html><html lang="en"><head><title>T</title>'
            '<link rel="stylesheet" href="preview_sd.css"></head><body>'
            + body +
            '<script src="preview_sd.js" defer></script></body></html>')
    rt = SimpleNamespace(state={"html_code": "", "session_id": "sd",
                                "intent": "generate",
                                "components_specification": _SD_SPEC},
                          tool_call_id="sd-1")
    return html, store_html_code.func(html, rt)


_h, _r = _sd_store('<div class="product-grid">'
                   '<article>Aurora Headphones</article>'
                   '<article>Meridian Desk Lamp</article></div>')
assert _r.update.get("html_code") == _h, _r.update["messages"][0].content
print("PASS: a page rendering every dataSets record is accepted")

_h, _r = _sd_store('<div class="product-grid">'
                   '<article>Cosmic Earbuds</article>'
                   '<article>Studio Lamp</article></div>')
assert "html_code" not in _r.update, "FAIL: invented products were stored"
_m = _r.update["messages"][0].content
assert "Shared Data Contract" in _m and "Aurora Headphones" in _m, _m
print("PASS: a page that invented its own products is REJECTED, both names named\n")

print("store_html_code: icon-accessibility + shared-data cases passed.")

# ── Pagination exemption (2026-08-30) ────────────────────────────────────────
# The duplicate-target rule protects MENUS. Pagination legitimately points every
# page button at the same grid, and refusing it cost a full 26KB re-emission on
# PO-08 po019a8c61. The exemption must be narrow: a menu that collapses is still
# refused, and a pagination nav is still subject to every OTHER anchor check.
_pg_passed = 0

_PG_MENU = """<!DOCTYPE html><html lang="en"><head><title>t</title></head><body>
<nav aria-label="Primary">
  <a href="#main">Shop</a><a href="#main">New</a><a href="#main">Sale</a>
</nav>
<section id="main">m</section>
</body></html>"""
assert _duplicate_nav_anchors(BeautifulSoup(_PG_MENU, "html.parser")), \
    "PG-1 FAIL: a collapsing MENU must still be refused"
print("PASS PG-1 - a menu whose items all point at one section is still refused")
_pg_passed += 1

_PG_PAGER = """<!DOCTYPE html><html lang="en"><head><title>t</title></head><body>
<nav class="pagination" data-component="pagination" aria-label="Pagination">
  <a href="#coffee-grid">1</a><a href="#coffee-grid">2</a><a href="#coffee-grid">3</a>
</nav>
<section id="coffee-grid">g</section>
</body></html>"""
assert _duplicate_nav_anchors(BeautifulSoup(_PG_PAGER, "html.parser")) == [], \
    "PG-2 FAIL: pagination pointing every page at the grid must be allowed"
print("PASS PG-2 - pagination may point every page button at the same section")
_pg_passed += 1

for _attr in ('class="pagination"', 'id="pagination-nav"', 'aria-label="Pagination"'):
    _html = _PG_PAGER.replace(
        'class="pagination" data-component="pagination" aria-label="Pagination"', _attr)
    assert _duplicate_nav_anchors(BeautifulSoup(_html, "html.parser")) == [], \
        f"PG-3 FAIL: pagination not recognised by {_attr}"
print("PASS PG-3 - pagination is recognised by data-component, class, id or aria-label")
_pg_passed += 1

# The exemption is ONLY for the duplicate rule. A pagination link that resolves
# to nothing is still a dangling link and must still be caught.
_PG_DANGLING = _PG_PAGER.replace('<section id="coffee-grid">g</section>', '<section id="other">o</section>')
assert _dangling_anchors(BeautifulSoup(_PG_DANGLING, "html.parser")), \
    "PG-4 FAIL: a dangling pagination link must still be caught"
print("PASS PG-4 - the exemption covers ONLY the duplicate rule, not dangling links")
_pg_passed += 1

print(f"pagination exemption: {_pg_passed}/4 PASSED")


# Search-input Prefill Contract (PO-08 po019fa283): a type="search" input that
# ships a non-empty value filters the page at load and can hide every result --
# po019fa283 shipped value="coffee" and the store rendered with ZERO products, so
# every cart test failed on a hidden button. No session_id here, so the
# generate-only guards are skipped and this both-mode guard is what fires.
_SEARCH_BAD = ('<!DOCTYPE html><html lang="en"><head><title>T</title></head><body>'
               '<form role="search"><input id="header_search_input" type="search" '
               'value="coffee" placeholder="Search coffees"></form></body></html>')
_r_sbad = store_html_code.func(
    _SEARCH_BAD, SimpleNamespace(state={"html_code": "", "lint_passed": False},
                                 tool_call_id="test-search-bad"))
assert "html_code" not in _r_sbad.update, "FAIL: a prefilled search input was stored"
assert "prefill" in _r_sbad.update["messages"][0].content.lower(), \
    f"FAIL: expected a prefill refusal, got: {_r_sbad.update['messages'][0].content}"
print("[Search Prefill] PASS: type=search value=coffee is refused, store blocked")

# The empty-value twin is admitted (removing the value attribute is the fix).
_SEARCH_OK = _SEARCH_BAD.replace('value="coffee" ', '')
_r_sok = store_html_code.func(
    _SEARCH_OK, SimpleNamespace(state={"html_code": "", "lint_passed": False},
                                tool_call_id="test-search-ok"))
assert _r_sok.update.get("html_code") == _SEARCH_OK, \
    "FAIL: an empty-value search input was wrongly refused"
print("[Search Prefill] PASS: a search input with no value is admitted")
