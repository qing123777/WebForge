# Ported from fyp.ipynb cell 18 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: DesignSchema and its parts
#
# The schema is what the Context Engineering Agent fills in and what the
# planning layer reads. A field that silently defaults to the wrong thing here
# is invisible until a page is generated wrongly.
import typing
_DS_CASES = 0

# ── Case 1: an empty schema is still a complete schema ──────────────────────
# The agent is allowed to leave fields out. Downstream code reads them anyway,
# so every branch must exist even when the user said nothing about it.
_ds = DesignSchema()
assert _ds.ui.type is None and _ds.theme.mode is None, \
    "Case 1 FAIL: an unfilled field should be None, not missing"
assert _ds.extra_requirements == [], "Case 1 FAIL: extra_requirements did not default to a list"
assert set(DesignSchema().model_dump()) == {
    "ui", "theme", "constraints", "extra_requirements"}, \
    f"Case 1 FAIL: unexpected top-level keys: {sorted(DesignSchema().model_dump())}"
_DS_CASES += 1
print("PASS Case 1 - an empty schema still carries all five branches")

# ── Case 2: the technology list cannot be changed ───────────────────────────
# The generated app is plain HTML, CSS and JavaScript with no build step. A
# model that asks for React would produce something this system cannot lint,
# cannot test and cannot preview, so the field is overwritten rather than
# validated.
for _attempt in (["react", "tailwind"], [], ["html"], None, "typescript"):
    _c = Constraints(tech_stack=_attempt)
    assert _c.tech_stack == ["html", "css", "javascript"], \
        f"Case 2 FAIL: tech_stack={_attempt!r} was not overwritten, got {_c.tech_stack}"
assert DesignSchema().constraints.tech_stack == ["html", "css", "javascript"], \
    "Case 2 FAIL: the default constraints do not carry the fixed stack"
_DS_CASES += 1
print("PASS Case 2 - every attempt to change the technology list is overwritten")

# ── Case 3: the constant itself is never mutated ────────────────────────────
# The default is FIXED_TECH_STACK.copy(). Without the copy, one schema editing
# its own list would change the constant for every schema built afterwards.
_a, _b = Constraints(), Constraints()
_a.tech_stack.append("react")
assert FIXED_TECH_STACK == ["html", "css", "javascript"], \
    f"Case 3 FAIL: the module constant was mutated: {FIXED_TECH_STACK}"
assert _b.tech_stack == ["html", "css", "javascript"], \
    f"Case 3 FAIL: two schemas share one list object: {_b.tech_stack}"
_DS_CASES += 1
print("PASS Case 3 - each schema owns its own list, so the constant survives")

# Case 5: two schemas never share a mutable default list
_d1, _d2 = DesignSchema(), DesignSchema()
_d1.extra_requirements.append("sticky banner")
assert _d2.extra_requirements == [], \
    f"Case 5 FAIL: two schemas share one list: {_d2.extra_requirements}"
_DS_CASES += 1
print("PASS Case 5 - each schema owns its own extra_requirements list")

# ── Case 6: a schema survives a round trip through plain data ───────────────
# The agent returns a dict, the state stores a dict, and the planning layer
# rebuilds the object. Anything lost in that trip is lost silently.
_full = DesignSchema(
    ui=UI(type="product_listing", style="catalog_heavy",
          commerce_type="multi_brand_retailer",
          density="comfortable", navigation="top_nav"),
    theme=Theme(name="warm-artisanal", mode="light"),
    extra_requirements=["sticky promo banner", "free shipping badge"],
)
_round = DesignSchema.model_validate(_full.model_dump())
assert _round.model_dump() == _full.model_dump(), "Case 6 FAIL: the round trip lost or changed a field"
assert _round.theme.name == "warm-artisanal", "Case 6 FAIL: the theme name did not survive"
_DS_CASES += 1
print("PASS Case 6 - a fully populated schema survives dict and back unchanged")

# ── Case 7: a partial payload from the model is accepted ────────────────────
# The agent often returns only what the user mentioned. That must not error.
_partial = DesignSchema.model_validate({"ui": {"type": "cart"},
                                        "extra_requirements": ["dark mode toggle"]})
assert _partial.ui.type == "cart" and _partial.theme.mode is None, \
    "Case 7 FAIL: a partial payload was not filled in correctly"
assert _partial.constraints.tech_stack == ["html", "css", "javascript"], \
    "Case 7 FAIL: the fixed stack was not applied to a partial payload"
_DS_CASES += 1
print("PASS Case 7 - a partial payload is accepted and the rest is defaulted")

# ── Case 9: what kind of shop, and how it looks, are separate questions ────
# Until 2026-08-15 there was no field for the kind of shop at all, so "build me a
# marketplace" and "build me a brand store" produced the same page. `style` was
# free text, so the CSS agent had no fixed word to respond to.
assert DesignSchema().ui.commerce_type is None, \
    "Case 9 FAIL: saying nothing about the shop kind must leave the field null"
assert UI(commerce_type="marketplace").commerce_type == "marketplace"
assert UI(style="minimal_premium").style == "minimal_premium"
for _bad_field, _bad in (("commerce_type", "shopee-like"), ("style", "modern")):
    try:
        UI(**{_bad_field: _bad})
    except Exception:
        pass
    else:
        raise AssertionError(
            f"Case 9 FAIL: {_bad_field}={_bad!r} was accepted, so the planner "
            f"could be handed a word it has no checklist for")
# The two axes must not overlap: a shop kind is never a look, and vice versa.
assert not set(typing.get_args(CommerceType)) & set(typing.get_args(DesignStyle)), \
    "Case 9 FAIL: a value appears in both lists, so the two axes are not separate"
_DS_CASES += 1
print("PASS Case 9 - shop kind and look are separate fixed lists, invented words refused")

print("=" * 64)
print(f"DesignSchema family: {_DS_CASES}/7 cases PASSED")

print("=" * 64)
