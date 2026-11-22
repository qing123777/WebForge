# Ported from fyp.ipynb cell 205 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: store_js_code (mirrors store_html_code tests)
from types import SimpleNamespace
import json

TEST_JS = 'document.querySelector(".btn").addEventListener("click", () => {});'
r = store_js_code.func(TEST_JS, SimpleNamespace(
    state={"js_code": "", "lint_passed": False}, tool_call_id="test-sjc-001"))
assert r.update.get("js_code") == TEST_JS
assert "lint_passed" not in r.update, "store_js_code must not touch lint_passed"
print("[Case 1 · NORMAL] Store: js_code saved to state, lint_passed left untouched.")
print(r.update["messages"][0].content)
print("PASS: store_js_code stores js_code, lint_passed untouched")

r = store_js_code.func(TEST_JS, SimpleNamespace(
    state={"js_code": "old();", "lint_passed": True}, tool_call_id="test-sjc-002"))
assert r.update["js_code"] == TEST_JS
print("\n[Case 2 · NORMAL] Overwrite: a second store replaces the js_code already in state.")
print(r.update["messages"][0].content)
print("PASS: store_js_code overwrites existing js_code\n")

# ── New cases (2026-07-08): interaction coverage check ───────────────────────
_INTERACTION_SPEC_COV = {"pages": [{"pageName": "listing", "flows": [
    {"name": "add-to-cart-flow",
     "trigger": {"event": "click", "targetId": "add-to-cart-button"},
     "actions": [{"type": "addToCart"}]},
]}]}
_COMPONENTS_SPEC_JS = {"pages": [{"pageName": "listing", "regionComponents": {"main": [
    {"id": "add-to-cart-button", "tag": "button", "className": "add-to-cart-btn"},
]}}]}

def _rt_js_gen(js_code, **state_extra):
    state = {"js_code": js_code}
    state.update(state_extra)
    return SimpleNamespace(state=state, tool_call_id="test-sjc-gen")

# Case 3: generate + trigger target never referenced in JS -> rejected
r3 = store_js_code.func("console.log('nothing wired');", _rt_js_gen(
    "console.log('nothing wired');", intent="generate",
    interaction_specification=_INTERACTION_SPEC_COV,
    components_specification=_COMPONENTS_SPEC_JS))
assert "js_code" not in r3.update, "FAIL: rejected call must not store js_code"
msg3 = r3.update["messages"][0].content
assert "add-to-cart-button" in msg3
print("\n[Case 3 · GUARD] Unwired interaction target: the coverage guard rejects the submission.")
print(msg3)
print("PASS: unreferenced interaction target rejected\n")

# Case 4: JS references the RESOLVED className selector -> accepted
# (targetId is the spec id "add-to-cart-button"; components_specification
# says it renders via className "add-to-cart-btn" — the check must resolve
# through the Naming Contract, not string-match the raw targetId)
_JS_WIRED = "document.querySelector('.add-to-cart-btn').addEventListener('click', () => {});"
r4 = store_js_code.func(_JS_WIRED, _rt_js_gen(
    _JS_WIRED, intent="generate",
    interaction_specification=_INTERACTION_SPEC_COV,
    components_specification=_COMPONENTS_SPEC_JS))
assert r4.update.get("js_code") == _JS_WIRED
print("\n[Case 4 · NORMAL] Naming Contract: the resolved className selector satisfies coverage.")
print(r4.update["messages"][0].content)
print("PASS: resolved className selector satisfies coverage\n")

# Case 5: targetId with NO components_specification entry -> falls back to
# raw targetId string match
_INTERACTION_NO_COMP = {"pages": [{"pageName": "listing", "flows": [
    {"name": "f", "trigger": {"event": "click", "targetId": "mystery-button"},
     "actions": []},
]}]}
r5 = store_js_code.func("wireUp('mystery-button');", _rt_js_gen(
    "wireUp('mystery-button');", intent="generate",
    interaction_specification=_INTERACTION_NO_COMP))
assert r5.update.get("js_code") == "wireUp('mystery-button');"
print("\n[Case 5 · NORMAL] Raw-id fallback: a target with no className resolves by its id.")
print(r5.update["messages"][0].content)
print("PASS: unresolved targetId falls back to raw-id match\n")

# Case 6 (regression safety): intent="modify" -> coverage check exempt
r6 = store_js_code.func("console.log('partial');", _rt_js_gen(
    "console.log('partial');", intent="modify",
    interaction_specification=_INTERACTION_SPEC_COV,
    components_specification=_COMPONENTS_SPEC_JS))
assert r6.update.get("js_code") == "console.log('partial');", \
    "FAIL: modify mode must be exempt from coverage check"
print("\n[Case 6 · NORMAL] Modify mode: the coverage check is skipped, so the code is stored.")
print(r6.update["messages"][0].content)
print("PASS: modify mode exempt from coverage check\n")

# Case 7 (backward compat): no interaction_specification in state at all
# (old-style fixtures, like Cases 1-8 above) -> skipped gracefully
r7 = store_js_code.func("console.log('x');", _rt_js_gen("console.log('x');"))
assert r7.update.get("js_code") == "console.log('x');"
print("\n[Case 7 · EDGE] No interaction_specification: the check is skipped without crashing.")
print(r7.update["messages"][0].content)
print("PASS: missing interaction_specification -> check skipped, no crash")


# ── New cases (2026-07-21): string-spec coercion ────────────────────────────

# Case 8 (REGRESSION): specs passed as JSON STRINGS must still be enforced
r8 = store_js_code.func("console.log('nothing wired');", _rt_js_gen(
    "console.log('nothing wired');", intent="generate",
    interaction_specification=json.dumps(_INTERACTION_SPEC_COV),
    components_specification=json.dumps(_COMPONENTS_SPEC_JS)))
assert "js_code" not in r8.update, "FAIL: string specs must not disable the check"
assert "add-to-cart-button" in r8.update["messages"][0].content
print("\n[Case 8 · GUARD] JSON-string specs: coerced, so the coverage guard still rejects.")
print(r8.update["messages"][0].content)
print("PASS: string specs coerced, coverage check still active\n")

# Case 9 (GUARD): unparseable string spec -> loud [INTERNAL] refusal
r9 = store_js_code.func("console.log('x');", _rt_js_gen(
    "console.log('x');", intent="generate",
    interaction_specification="{not valid json"))
assert "js_code" not in r9.update
assert "[INTERNAL]" in r9.update["messages"][0].content
print("\n[Case 9 · GUARD] Unparseable spec: refused loudly with an [INTERNAL] message.")
print(r9.update["messages"][0].content)
print("PASS: unparseable spec -> [INTERNAL] refusal")

# ── Disabled-State Contract (2026-08-09) ──────────────────────────────────────
# The first live Secondary Orchestrator run produced JS that ALREADY guarded its
# handler on aria-disabled correctly, and then set button.disabled = true on top.
# That extra line takes the control out of the tab order, out of the
# accessibility tree, and out of Playwright's reach -- a second click on it times
# out, so a later test case fails for a reason unrelated to the page.

# Case 10 (GUARD): the exact line from the defective artifact -> rejected
_JS_NATIVE = """
document.querySelectorAll('.add-to-cart-btn').forEach((button) => {
  const setDisabled = (isDisabled) => {
    button.disabled = isDisabled;
    button.setAttribute('aria-disabled', String(isDisabled));
  };
  button.addEventListener('click', () => {
    if (button.getAttribute('aria-disabled') === 'true') { return; }
    setDisabled(true);
  });
});
"""
r10 = store_js_code.func(_JS_NATIVE, _rt_js_gen(_JS_NATIVE, intent="generate"))
assert "js_code" not in r10.update, "FAIL: native .disabled write was stored"
_m10 = r10.update["messages"][0].content
assert "Disabled-State Contract" in _m10 and "aria-disabled" in _m10, _m10
print("\n[Case 10 · GUARD] `button.disabled = ...` is refused, and the message names "
      "the replacement rather than only the offence.")
print(_m10)
print("PASS: native property assignment rejected\n")

# Case 11 (GUARD): the attribute route to the same defect
_JS_SETATTR = "document.querySelector('.btn').setAttribute('disabled', 'true');"
r11 = store_js_code.func(_JS_SETATTR, _rt_js_gen(_JS_SETATTR, intent="generate"))
assert "js_code" not in r11.update
assert "Disabled-State Contract" in r11.update["messages"][0].content
_JS_REMOVE = "document.querySelector('.btn').removeAttribute(\'disabled\');"
r11b = store_js_code.func(_JS_REMOVE, _rt_js_gen(_JS_REMOVE, intent="generate"))
assert "js_code" not in r11b.update, "removeAttribute('disabled') is the same defect"
print("[Case 11 · GUARD] setAttribute and removeAttribute for 'disabled' are caught too.")
print("PASS: attribute route closed\n")

# Case 12 (NORMAL): the compliant shape is accepted, and a READ is not a defect.
# `if (el.disabled)` is harmless once nothing writes it, and flagging reads would
# send the model chasing something that is not broken.
_JS_ARIA = """
document.querySelectorAll('.add-to-cart-btn').forEach((button) => {
  button.addEventListener('click', () => {
    if (button.getAttribute('aria-disabled') === 'true') { return; }
    if (button.disabled) { return; }
    button.setAttribute('aria-disabled', 'true');
    button.textContent = 'Added to cart';
  });
});
"""
r12 = store_js_code.func(_JS_ARIA, _rt_js_gen(_JS_ARIA, intent="generate"))
assert r12.update.get("js_code") == _JS_ARIA, \
    f"FAIL: compliant aria-only code rejected: {r12.update['messages'][0].content}"
assert store_js_code.func("if (a.disabled === b.disabled) {}", _rt_js_gen(
    "if (a.disabled === b.disabled) {}", intent="generate")).update.get("js_code"), \
    "FAIL: a comparison is not an assignment"
print("[Case 12 · NORMAL] aria-disabled only is accepted; reading `.disabled` and "
      "comparing with `===` are not writes and must not be flagged.")
print(r12.update["messages"][0].content)
print("PASS: compliant code admitted, reads and comparisons untouched\n")

# Case 13 (INVARIANT): modification mode is exempt, same reasoning as
# store_html_code -- modify mode opens by re-storing the file on disk, and
# rejecting it over a line it already contained would deadlock the correction
# loop that exists to remove that very line.
r13 = store_js_code.func(_JS_NATIVE, _rt_js_gen(_JS_NATIVE, intent="modify"))
assert r13.update.get("js_code") == _JS_NATIVE, \
    "FAIL: modify mode must not be blocked by pre-existing code"
print("[Case 13 · INVARIANT] Modification mode accepts code whose native property "
      "predates the guard, so the correction loop is never deadlocked by it.")
print("PASS: modify-mode exemption holds\n")

# ── Shared Data Contract (2026-08-15) ────────────────────────────────────────
# A flow that REWRITES content needs the same records the page was rendered
# from. A flow that only displays them does not, and demanding a duplicate array
# there would leave dead code the linter then flags as unused.
_SDJ_COMPONENTS = {
    "dataSets": {"products": [
        {"id": "p1", "name": "Aurora Headphones"},
        {"id": "p2", "name": "Meridian Desk Lamp"},
    ]},
    "pages": [{"pageName": "home", "regionComponents": {"main": [
        {"id": "product-card", "tag": "div", "className": "product-card"},
    ]}}],
}
_SDJ_REWRITES = {"pages": [{"pageName": "home", "flows": [
    {"name": "show-detail",
     "trigger": {"event": "click", "targetId": "product-card"},
     "actions": [{"type": "updateData", "targetId": "product-card"}]},
]}]}
_SDJ_DISPLAY_ONLY = {"pages": [{"pageName": "home", "flows": [
    {"name": "highlight",
     "trigger": {"event": "click", "targetId": "product-card"},
     "actions": [{"type": "updateState", "targetId": "product-card"}]},
]}]}


def _sdj(js, interaction):
    return store_js_code.func(js, SimpleNamespace(
        state={"js_code": "", "intent": "generate",
               "interaction_specification": interaction,
               "components_specification": _SDJ_COMPONENTS},
        tool_call_id="sdj-1"))


_JS_WITH = ('const products = [{id: "p1", name: "Aurora Headphones"},'
            ' {id: "p2", name: "Meridian Desk Lamp"}];'
            ' document.querySelectorAll(".product-card");')
_JS_WITHOUT = 'document.querySelectorAll(".product-card");'

r14 = _sdj(_JS_WITH, _SDJ_REWRITES)
assert r14.update.get("js_code") == _JS_WITH, r14.update["messages"][0].content
print("[Case 14 · NORMAL] A rewriting flow whose script carries the shared records "
      "is accepted.")
print("PASS: shared records present -> stored\n")

r15 = _sdj(_JS_WITHOUT, _SDJ_REWRITES)
assert "js_code" not in r15.update, "FAIL: a rewriting flow with no records was stored"
_m = r15.update["messages"][0].content
assert "Shared Data Contract" in _m and "Aurora Headphones" in _m, _m
print("[Case 15 · GUARD] A flow that rewrites content but carries no records is "
      "refused, because a click could never resolve to a record.")
print("PASS: missing shared records -> refused\n")

r16 = _sdj(_JS_WITHOUT, _SDJ_DISPLAY_ONLY)
assert r16.update.get("js_code") == _JS_WITHOUT, r16.update["messages"][0].content
print("[Case 16 · INVARIANT] A display-only flow is untouched, so no run is forced "
      "to carry an array it never reads.")
print("PASS: display-only flow exempt\n")

# ── No-image contract (2026-08-30) ───────────────────────────────────────────
# The HTML never emits <img>, but the JS agent built product photos at runtime
# with createElement("img") and set .src to a fabricated URL, clobbering the
# placeholder cards (PO-08 po0113ce72). Generated JS must create no image.
_JS_IMG_CREATE = ('const image = document.createElement("img");'
                  ' image.src = "https://images.example.com/x.jpg";')
_JS_IMG_TEMPLATE = 'el.innerHTML = "<img src=\\"x.jpg\\">";'

r17 = _sdj(_JS_IMG_CREATE, _SDJ_DISPLAY_ONLY)
assert "js_code" not in r17.update, "Case 17 FAIL: a JS-created <img> was stored"
_m17 = r17.update["messages"][0].content
assert "Image contract" in _m17 and "createElement('img')" in _m17, _m17
print("[Case 17 · GUARD] JS createElement(\"img\") is refused, and the fix names "
      "the placeholder route.")
print("PASS: runtime <img> creation rejected\n")

r18 = _sdj(_JS_IMG_TEMPLATE, _SDJ_DISPLAY_ONLY)
assert "js_code" not in r18.update, "Case 18 FAIL: an '<img>' template was stored"
assert "Image contract" in r18.update["messages"][0].content
print("[Case 18 · GUARD] An '<img>' tag inside an innerHTML template is refused too.")
print("PASS: template <img> rejected\n")

r19 = store_js_code.func(_JS_IMG_CREATE, _rt_js_gen(_JS_IMG_CREATE, intent="modify"))
assert r19.update.get("js_code") == _JS_IMG_CREATE, \
    "Case 19 FAIL: modify mode must not be blocked by a pre-existing <img>"
print("[Case 19 · INVARIANT] Modification mode accepts code whose <img> predates "
      "the guard, so the correction loop is never deadlocked by it.")
print("PASS: modify-mode exemption holds\n")

# ── DOM Ownership Contract (2026-08-31) ──────────────────────────────────────
# PO-08 po01e9a8b4 shipped a cart that could never render a line item. The
# script rebuilt the cart shell under names of its own, guarded the rebuild
# with `if (!region.querySelector('#cart-heading'))`, and the HTML had already
# shipped that heading -- so the block never ran, `.cart-item-list` was never
# created, and renderCart() returned on its first line for the life of the
# page. eslint was clean, the console was silent, and every generated
# assertion passed, because each element those assertions name IS on the page.
#
# The rule is "the script creates no class the page and the specification have
# never heard of". Measured over the 53 preview pairs on disk when it was
# written: 46 runs score 0, 7 score at least one, po01e9a8b4 scores 20.
_JSDOM_SID = "jsdom01"
_JSDOM_HTML = (
    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    '<title>t</title></head><body>'
    '<section id="cart"><h2 id="cart-heading">Cart</h2>'
    '<ul class="cart-lines"></ul><p class="cart-total">$0.00</p></section>'
    '<article class="product-card"><div class="product-actions">'
    '<button class="add-to-cart-button" type="button">Add</button>'
    '</div></article></body></html>')
(_PREVIEW_ROOT / f"preview_{_JSDOM_SID}.html").write_text(
    _JSDOM_HTML, encoding="utf-8")

_JSDOM_COMPONENTS = {"pages": [{"pageName": "home", "components": [
    {"componentId": "cart-lines", "className": "cart-lines"},
    {"componentId": "cart-line", "className": "cart-line"},
]}]}


def _rt_jsdom(js, intent="generate", dom_attempts=0, sid=_JSDOM_SID):
    return SimpleNamespace(state={
        "js_code": "", "intent": intent, "session_id": sid,
        "dom_attempts": dom_attempts,
        "interaction_specification": {},
        "components_specification": _JSDOM_COMPONENTS,
    }, tool_call_id="jsdom-1")


# Case 20 [GUARD] the exact shape that killed po01e9a8b4's cart.
_JS_INVENTS = ('const list = document.createElement("ul");'
               ' list.className = "cart-item-list";'
               ' const total = document.createElement("p");'
               ' total.classList.add("cart-subtotal");')
r20 = store_js_code.func(_JS_INVENTS, _rt_jsdom(_JS_INVENTS))
assert "js_code" not in r20.update, "Case 20 FAIL: invented classes were stored"
_m20 = r20.update["messages"][0].content
assert "cart-item-list" in _m20 and "cart-subtotal" in _m20, _m20
# The refusal must hand over the lookup, or it is a wall rather than a guard.
assert "cart-lines" in _m20 and "cart-total" in _m20, (
    "Case 20 FAIL: the refusal does not list the class names actually on the "
    "page, so the model has no way to find the element it should have used.")
assert r20.update["dom_attempts"] == 1, r20.update
print("[Case 20 · GUARD] A script that CREATES classes the page has never heard "
      "of is refused, and the refusal names the real ones.")
print("PASS: invented classes rejected with the lookup attached\n")

# Case 21 [NORMAL] the same script written against the real markup.
_JS_HONEST = ('const row = document.createElement("li");'
              ' row.className = "cart-line";'
              ' document.querySelector(".cart-lines").appendChild(row);')
r21 = store_js_code.func(_JS_HONEST, _rt_jsdom(_JS_HONEST))
assert r21.update.get("js_code") == _JS_HONEST, r21.update["messages"][0].content
print("[Case 21 · NORMAL] Creating a data ROW whose class the specification "
      "declares, inside a container the page ships, is accepted.")
print("PASS: legitimate row creation is not blocked\n")

# Case 22 [INVARIANT] a name the SPEC declares but the markup has not caught up
# with is the HTML agent's debt, not this agent's invention.
_JS_SPEC_ONLY = 'const r = document.createElement("li"); r.className = "cart-line";'
r22 = store_js_code.func(_JS_SPEC_ONLY, _rt_jsdom(_JS_SPEC_ONLY))
assert r22.update.get("js_code") == _JS_SPEC_ONLY, r22.update["messages"][0].content
print("[Case 22 · INVARIANT] A className the component specification declares is "
      "allowed even before the markup carries it.")
print("PASS: one agent's omission cannot block another\n")

# Case 23 [INVARIANT] modify mode is exempt, like every other generate-mode
# guard here: modify opens by re-storing the file already on disk, and
# refusing that file over code it already contained deadlocks the loop.
r23 = store_js_code.func(_JS_INVENTS, _rt_jsdom(_JS_INVENTS, intent="modify"))
assert r23.update.get("js_code") == _JS_INVENTS, r23.update
print("[Case 23 · INVARIANT] Modification mode accepts code whose invented "
      "classes predate the guard.")
print("PASS: modify-mode exemption holds\n")

# Case 24 [INVARIANT] the cap. Two refusals, then the submission goes through,
# so a model that cannot satisfy the rule stalls the run for two calls, not
# forever.
r24 = store_js_code.func(_JS_INVENTS,
                         _rt_jsdom(_JS_INVENTS, dom_attempts=_JS_DOM_ATTEMPT_CAP))
assert r24.update.get("js_code") == _JS_INVENTS, (
    f"Case 24 FAIL: the guard is still refusing at attempt "
    f"{_JS_DOM_ATTEMPT_CAP}, so it can deadlock the run.")
print(f"[Case 24 · INVARIANT] After {_JS_DOM_ATTEMPT_CAP} refusals the "
      f"submission is stored, so the guard bounds the spend it can cause.")
print("PASS: attempt cap closes\n")

# Case 25 [INVARIANT] no page on disk -> fail OPEN. A missing file is a
# pipeline problem, not a defect in the code being checked.
r25 = store_js_code.func(_JS_INVENTS, _rt_jsdom(_JS_INVENTS, sid="nosuchsid"))
assert r25.update.get("js_code") == _JS_INVENTS, r25.update
print("[Case 25 · INVARIANT] With no generated page to compare against the "
      "guard fails OPEN.")
print("PASS: missing page does not block the run\n")

# Case 26 [NORMAL] the helper itself, on the two readings that matter. Only
# ASSIGNMENTS count: querying a class the script creates is ordinary
# JavaScript, and refusing that would be a wall.
assert _js_invented_classes(
    'document.querySelector(".cart-item-list");', _JSDOM_HTML) == [], (
    "Case 26 FAIL: a QUERY for an absent class was reported. Only creation "
    "counts -- this is exactly where the first design of this guard was wrong.")
assert _js_invented_classes(
    'x.className = "cart-item-list";', _JSDOM_HTML) == ["cart-item-list"]
print("[Case 26 · NORMAL] The helper counts creation only, never a query.")
print("PASS: assignment/query split holds\n")

(_PREVIEW_ROOT / f"preview_{_JSDOM_SID}.html").unlink(missing_ok=True)

print("All 26 cases passed - store_js_code (coverage, string specs, disabled state, "
      "shared data, no-image, DOM ownership)")
