# Ported from fyp.ipynb cell 209 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: extract_js_component
from types import SimpleNamespace

_JS_SAMPLE = """
document.addEventListener('DOMContentLoaded', () => {
  const nav = document.querySelector('#navbar');
  nav.addEventListener('click', () => console.log('nav clicked'));
});

document.addEventListener('DOMContentLoaded', () => {
  const card = document.querySelector('.product-card');
  card.addEventListener('mouseenter', () => card.classList.add('hovered'));
});

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.querySelector('#add-to-cart-btn');
  btn.addEventListener('click', () => console.log('added to cart'));
});
""".strip()

_mk_rt = lambda component, js_code=_JS_SAMPLE: SimpleNamespace(
    state={"js_code": js_code, "target_component": component},
    tool_call_id="test-ej"
)

# Case 1: CSS selector (#id) — correct block returned
r1 = extract_js_component.func(_mk_rt("#navbar"))
msg1 = r1.update["messages"][0].content
assert "navbar" in msg1
assert "product-card" not in msg1
print("[Case 1 · NORMAL] #id selector: resolves to the correct block.")
print(msg1)
print("PASS: #id selector finds correct block\n")

# Case 2: CSS selector (.class)
r2 = extract_js_component.func(_mk_rt(".product-card"))
msg2 = r2.update["messages"][0].content
assert "product-card" in msg2
assert "navbar" not in msg2
print("[Case 2 · NORMAL] .class selector: resolves to the correct block.")
print(msg2)
print("PASS: .class selector finds correct block\n")

# Case 3: bare word — strips # prefix and still finds block
r3 = extract_js_component.func(_mk_rt("navbar"))
msg3 = r3.update["messages"][0].content
assert "navbar" in msg3
print("[Case 3 · NORMAL] Bare word: found by raw name after the prefix is stripped.")
print(msg3)
print("PASS: bare word finds block by raw name\n")

# Case 4: component not found
r4 = extract_js_component.func(_mk_rt("#nonexistent"))
assert "no js code found" in r4.update["messages"][0].content.lower()
print("[Case 4 · EDGE] Selector matches nothing: reported, not crashed.")
print(r4.update["messages"][0].content)
print("PASS: not-found handled\n")

# Case 5: empty js_code
r5 = extract_js_component.func(SimpleNamespace(
    state={"js_code": "", "target_component": "#navbar"},
    tool_call_id="test-ej-empty"
))
assert "empty" in r5.update["messages"][0].content.lower()
print("[Case 5 · EDGE] Empty js_code: handled gracefully.")
print(r5.update["messages"][0].content)
print("PASS: empty js_code handled\n")

# Case 6: every referencing paragraph comes back, not just the first, even when
#   an unrelated paragraph sits between them.
_JS_MULTI = ('const cart = document.querySelector("#mini-cart");\n\n'
             'document.querySelector("#unrelated").addEventListener("click", () => {});\n\n'
             'document.querySelector("#mini-cart .badge").textContent = "0";')
r6 = extract_js_component.func(_mk_rt("#mini-cart", _JS_MULTI))
msg6 = r6.update["messages"][0].content
assert msg6.count("WebForge block") == 2 and "block 2 of 2" in msg6
assert "unrelated" not in msg6, "an unrelated paragraph was pulled in"
print("[Case 6 · NORMAL] Multiple references: every paragraph returned, not just the first.")
print(f"Extracted:\n{msg6}")
print("PASS: both non-adjacent paragraphs returned\n")

# Case 7: a single match carries no marker lines.
assert "WebForge block" not in \
    extract_js_component.func(_mk_rt("#navbar")).update["messages"][0].content
print("[Case 7 · INVARIANT] Single match: no marker lines are added.")
print("WebForge block marker present: False")
print("PASS: single-match extraction is unmarked\n")


# ── Suggestion 2 (batching) additions ───────────────────────────────────────
# Case 8 [NORMAL] explicit component= parameter overrides the state target
_r8 = extract_js_component.func(
    SimpleNamespace(state={"js_code": _JS_SAMPLE, "target_component": "#navbar"},
                    tool_call_id="ej-8"),
    component=".product-card")
_m8 = _r8.update["messages"][0].content
assert "product-card" in _m8 and "navbar" not in _m8, "component= must win over state"
print("[Case 8 · NORMAL] explicit component= parameter selects the block, overriding state.")
print("PASS: component= overrides state target_component\n")

# Case 9 [INVARIANT] a successful extract resets the per-component lint budget
_r9 = extract_js_component.func(SimpleNamespace(
    state={"js_code": _JS_SAMPLE, "target_component": "#navbar",
           "lint_attempts": 2, "lint_escalated": True}, tool_call_id="ej-9"))
assert _r9.update.get("lint_attempts") == 0 and _r9.update.get("lint_escalated") is False, \
    "extract must reset the session-global lint budget so a batch cannot blow the cap"
print("[Case 9 · INVARIANT] extract resets lint_attempts/lint_escalated for the new component.")
print("PASS: per-component lint budget reset on extract\n")

# ── Naming Contract resolution (2026-08-09) ──────────────────────────────────
# SO-01: "`add-to-cart-button` was not found in the current JavaScript". The
# script addresses the button as '.add-to-cart-btn', because that is what the
# Naming Contract rendered; the work order names the specification id.
_NCJ_JS = ("document.addEventListener('DOMContentLoaded', () => {\n"
           "  const btns = document.querySelectorAll('.add-to-cart-btn');\n"
           "  btns.forEach((b) => b.setAttribute('aria-disabled', 'false'));\n"
           "});\n\n"
           "const nav = document.querySelector('#navbar');\n")
_NCJ_SPEC = {"pages": [{"pageName": "plp", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "add-to-cart-button", "tag": "button", "className": "add-to-cart-btn"},
]}}]}


def _rt_ncj(target, spec=_NCJ_SPEC):
    return SimpleNamespace(
        state={"js_code": _NCJ_JS, "target_component": target,
               "components_specification": spec},
        tool_call_id="ncj-1")


_m = extract_js_component.func(_rt_ncj("add-to-cart-button")).update["messages"][0].content
assert "No JS code found" not in _m, f"FAIL: spec id still unresolved:\n{_m}"
assert "add-to-cart-btn" in _m, _m
print("[NCJ-1 · GUARD] The specification id resolves to the selector string the script "
      "actually uses.")
print("PASS: id -> className resolution in extract_js_component\n")

for _n in ("add-to-cart-btn", ".add-to-cart-btn", "navbar"):
    _mm = extract_js_component.func(_rt_ncj(_n)).update["messages"][0].content
    assert "No JS code found" not in _mm, f"FAIL for {_n}: {_mm}"
print("[NCJ-2 · NORMAL] className, .selector and a bare id all still work.")
print("PASS: existing call shapes unaffected\n")

_m3 = extract_js_component.func(_rt_ncj("ghost-widget")).update["messages"][0].content
assert "No JS code found" in _m3
assert ".add-to-cart-btn" in _m3 and "#navbar" in _m3, \
    f"FAIL: the message must list the selectors the script references: {_m3}"
print("[NCJ-3 · GUARD] An absent component still fails, and the message names the "
      "selectors the script does reference.")
print(_m3)
print("PASS: actionable not-found message\n")

_m4 = extract_js_component.func(_rt_ncj("add-to-cart-button", spec=None)
                                ).update["messages"][0].content
assert "No JS code found" in _m4, "without a spec there is nothing to map with"
print("[NCJ-4 · EDGE] With no components_specification the tool degrades cleanly.")
print("PASS: degrades cleanly\n")

print("All 4 Naming Contract cases passed - extract_js_component")
