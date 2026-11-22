# Ported from fyp.ipynb cell 157 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: extract_component (reads target_component CSS selector from state)
from types import SimpleNamespace

SAMPLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Test</title></head>
<body>
  <nav id="navbar"><a>Home</a></nav>
  <div class="product-card"><p>Card 1</p></div>
  <div class="product-card"><p>Card 2</p></div>
</body>
</html>"""

# Case 1: id selector
dummy_runtime = SimpleNamespace(
    state={"html_code": SAMPLE_HTML, "target_component": "#navbar"},
    tool_call_id="test-ec-001"
)
result = extract_component.func(dummy_runtime)
msg    = result.update["messages"][0].content
assert "Home" in msg, f"FAIL: expected nav content, got: {msg}"
print("[Case 1 · NORMAL] An #id selector resolves to the matching element.")
print(msg[:80])
print("PASS: #id selector works\n")

# Case 2: class selector — multiple matches, returns first
dummy_runtime2 = SimpleNamespace(
    state={"html_code": SAMPLE_HTML, "target_component": ".product-card"},
    tool_call_id="test-ec-002"
)
result2 = extract_component.func(dummy_runtime2)
msg2    = result2.update["messages"][0].content
assert "Card 1" in msg2, f"FAIL: expected Card 1, got: {msg2}"
assert "2 match(es)" in msg2, f"FAIL: expected match count note, got: {msg2}"
print("[Case 2 · NORMAL] A .class selector matching several elements returns the targeted "
      "one and reports how many matched.")
print(msg2[:120])
print("PASS: .class selector returns the targeted match with a count note\n")

# Case 3: bare word fallback — tries #word then .word
dummy_runtime3 = SimpleNamespace(
    state={"html_code": SAMPLE_HTML, "target_component": "navbar"},
    tool_call_id="test-ec-003"
)
result3 = extract_component.func(dummy_runtime3)
msg3    = result3.update["messages"][0].content
assert "Home" in msg3, f"FAIL: expected nav content for bare-word fallback, got: {msg3}"
print("[Case 3 · NORMAL] A bare component name with no prefix falls back to #name, then .name.")
print(msg3[:80])
print("PASS: bare-word fallback finds #navbar\n")

# Case 4: not found
dummy_runtime4 = SimpleNamespace(
    state={"html_code": SAMPLE_HTML, "target_component": "#nonexistent"},
    tool_call_id="test-ec-004"
)
result4 = extract_component.func(dummy_runtime4)
msg4    = result4.update["messages"][0].content
assert "no element found" in msg4.lower(), f"FAIL: expected not-found message, got: {msg4}"
print("[Case 4 · EDGE] A selector matching nothing reports which forms were tried.")
print(msg4)
print("PASS: not-found handled correctly\n")

# Case 5: empty html_code
dummy_runtime5 = SimpleNamespace(
    state={"html_code": "", "target_component": "#navbar"},
    tool_call_id="test-ec-005"
)
result5 = extract_component.func(dummy_runtime5)
msg5    = result5.update["messages"][0].content
assert "empty" in msg5.lower(), f"FAIL: expected empty message, got: {msg5}"
print("[Case 5 · EDGE] No HTML in state: reported rather than parsed as an empty document.")
print(msg5)
print("PASS: empty html_code handled\n")

# Case 6: target_instance selects the Nth match, not always the first
REPEATED_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Test</title></head>
<body>
  <div class="product-card"><p>Alpha</p></div>
  <div class="product-card"><p>Beta</p></div>
  <div class="product-card"><p>Gamma</p></div>
</body>
</html>"""

dummy_runtime6 = SimpleNamespace(
    state={"html_code": REPEATED_HTML, "target_component": ".product-card",
           "target_instance": 2},
    tool_call_id="test-ec-006"
)
result6 = extract_component.func(dummy_runtime6)
msg6    = result6.update["messages"][0].content
assert "Beta" in msg6, f"FAIL: expected instance 2 (Beta), got: {msg6}"
assert "Alpha" not in msg6 and "Gamma" not in msg6, f"FAIL: wrong instance returned: {msg6}"
assert "instance 2" in msg6, f"FAIL: expected instance note, got: {msg6}"
print("[Case 6 · NORMAL] target_instance selects the Nth repeated element, not always the first.")
print(msg6[:120])
print("PASS: target_instance=2 returns the second match\n")

# Case 7: instance out of range
dummy_runtime7 = SimpleNamespace(
    state={"html_code": REPEATED_HTML, "target_component": ".product-card",
           "target_instance": 5},
    tool_call_id="test-ec-007"
)
result7 = extract_component.func(dummy_runtime7)
msg7    = result7.update["messages"][0].content
assert "out of range" in msg7.lower(), f"FAIL: expected out-of-range message, got: {msg7}"
assert "3 instance(s)" in msg7, f"FAIL: expected match count in message, got: {msg7}"
print("[Case 7 · EDGE] An instance beyond the number present is rejected, and the message "
      "states how many exist.")
print(msg7)
print("PASS: out-of-range instance rejected\n")

# NOTE: the cross-tool check — that extract_component and store_html_diff address
# the SAME element — lives in the store_html_diff test cell, not here.
# store_html_diff is defined after this cell, so calling it from here would raise
# NameError on a straight top-to-bottom run of the notebook.

# ── Naming Contract resolution (2026-08-09) ──────────────────────────────────
# In the SO-01 run the HTML agent replied "The target selector
# `add-to-cart-button` no longer matches any element on the current page" for a
# button that was right there as class="add-to-cart-btn" with NO id -- which is
# exactly what the Naming Contract prescribes. Both correction attempts were
# spent on a lookup that could not succeed.
_NCH_HTML = ('<!DOCTYPE html><html lang="en"><head><title>T</title></head><body>'
             '<nav id="navbar"></nav>'
             '<article class="product-card">'
             '<button class="add-to-cart-btn" aria-disabled="false">Add to Cart</button>'
             '</article></body></html>')
_NCH_SPEC = {"pages": [{"pageName": "plp", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "add-to-cart-button", "tag": "button", "className": "add-to-cart-btn"},
]}}]}


def _rt_nch(target, spec=_NCH_SPEC):
    return SimpleNamespace(
        state={"html_code": _NCH_HTML, "target_component": target,
               "target_instance": 1, "components_specification": spec},
        tool_call_id="nch-1")


_m = extract_component.func(_rt_nch("add-to-cart-button")).update["messages"][0].content
assert "No element found" not in _m, f"FAIL: spec id still unresolved:\n{_m}"
assert "add-to-cart-btn" in _m and "Add to Cart" in _m, _m
print("[NCH-1 · GUARD] A work order naming the specification id now resolves to the "
      "className the page actually carries.")
print("PASS: id -> className resolution in extract_component\n")

for _n in ("add-to-cart-btn", ".add-to-cart-btn", "#navbar", "navbar"):
    _mm = extract_component.func(_rt_nch(_n)).update["messages"][0].content
    assert "No element found" not in _mm, f"FAIL for {_n}: {_mm}"
print("[NCH-2 · NORMAL] className, .selector, #id and bare id all still work.")
print("PASS: every existing call shape unaffected\n")

_m3 = extract_component.func(_rt_nch("add to cart button")).update["messages"][0].content
assert "No element found" not in _m3, f"FAIL: space form unresolved: {_m3}"
print("[NCH-3 · EDGE] 'add to cart button' resolves via the hyphenated form.")
print("PASS: space form handled\n")

_m4 = extract_component.func(_rt_nch("ghost-widget")).update["messages"][0].content
assert "No element found" in _m4
assert ".add-to-cart-btn" in _m4 and "#navbar" in _m4, \
    f"FAIL: the not-found message must list what the page offers: {_m4}"
print("[NCH-4 · GUARD] A genuinely absent target still fails, and the message names "
      "the ids and classNames the page does offer.")
print(_m4)
print("PASS: actionable not-found message\n")

_m5 = extract_component.func(_rt_nch("add-to-cart-button", spec=None)
                             ).update["messages"][0].content
assert "No element found" in _m5, "without a spec there is nothing to map with"
_m5b = extract_component.func(_rt_nch("navbar", spec=None)).update["messages"][0].content
assert "No element found" not in _m5b, "literal matching must still work with no spec"
print("[NCH-5 · EDGE] With no components_specification the tool degrades to literal "
      "matching rather than raising.")
print("PASS: degrades cleanly\n")

print("All 5 Naming Contract cases passed - extract_component")
