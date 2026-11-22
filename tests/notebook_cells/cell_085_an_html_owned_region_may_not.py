# Ported from fyp.ipynb cell 85 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: an HTML-owned region may not be left empty (2026-08-30).
# REGRESSION for PO-08 po01c3d233. The layout declared 8 regions; the components
# generator filled 3 and was ACCEPTED on the first attempt. featured-coffees (the
# product grid), brand-story, brewing-journal and newsletter-footer shipped
# unplanned, so decoration had nothing to decorate there and the CSS agent wrote
# 444 lines containing not one `product` selector -- eight product cards rendered
# as full-width blocks with no gap, border or background, and the footer had no
# boundary. The name comparison could not see it, because
# _repair_component_spec_from_layout turns a region the model never wrote into a
# present-but-empty key.
_er_passed = 0

_ER_LAYOUT = {"pages": [{
    "pageName": "coffee-roaster-home", "pageType": "home",
    "pageLayoutType": "stack", "responsive": True,
    "regions": [
        {"name": "hero",             "ownedBy": "HTML",       "layoutType": "stack"},
        {"name": "featured-coffees", "ownedBy": "HTML",       "layoutType": "grid"},
        {"name": "mini-cart",        "ownedBy": "JavaScript", "layoutType": "single-column"},
    ],
}]}


def _er_node(nid, cls, cat):
    return {"id": nid, "className": cls, "tag": "section",
            "componentCategory": cat, "ownedBy": "HTML",
            "role": ["structure"], "props": {}, "states": [], "events": [],
            "children": []}


_ER_DATASETS = {"products": [
    {"id": "p1", "name": "Aurora Bloom", "price": "22.00"},
    {"id": "p2", "name": "Copper Field", "price": "23.00"},
]}


def _er_components(featured_nodes):
    return {"dataSets": _ER_DATASETS, "pages": [{
        "pageName": "coffee-roaster-home",
        "regionComponents": {
            "hero":             [_er_node("hero_main", "hero-section", "hero-section")],
            "featured-coffees": featured_nodes,
            "mini-cart":        [],
        },
    }]}


_lay_obj = _coerce_layout_spec(_ER_LAYOUT)

# The real defect: the product region arrives present but empty, and must be refused.
_bad = _coerce_component_spec(_er_components([]))
_msg = _validate_component_contract_for_downstream(_lay_obj, _bad)
assert _msg, "ER-1 FAIL: an empty HTML region was accepted -- the po01c3d233 defect"
assert "featured-coffees" in _msg and "EMPTY" in _msg, _msg
print("PASS ER-1 - an empty HTML-owned region is refused and named")
_er_passed += 1

# The refusal has to be actionable: it must say what to do, not just what is wrong.
assert "at least one component" in _msg, "ER-2 FAIL: the refusal does not say how to fix it"
print("PASS ER-2 - the refusal tells the generator how to fix it")
_er_passed += 1

# mini-cart is ownedBy JavaScript and is built at runtime: filling every other
# region must be enough, and the JS region staying empty must NOT be reported.
_ok = _coerce_component_spec(_er_components(
    [_er_node("coffee_grid", "product-grid", "product-grid")]))
_msg_ok = _validate_component_contract_for_downstream(_lay_obj, _ok)
assert not _msg_ok, "ER-3 FAIL: a complete plan was refused: %s" % _msg_ok
print("PASS ER-3 - a JavaScript-owned region may stay empty; a complete plan passes")
_er_passed += 1

# The older check still bites: a region key dropped entirely is still reported.
_dropped = _er_components([_er_node("coffee_grid", "product-grid", "product-grid")])
del _dropped["pages"][0]["regionComponents"]["featured-coffees"]
_msg_drop = _validate_component_contract_for_downstream(
    _lay_obj, _coerce_component_spec(_dropped))
assert _msg_drop and "featured-coffees" in _msg_drop, \
    "ER-4 FAIL: a missing region key must still be reported"
print("PASS ER-4 - a dropped region key is still caught by the original check")
_er_passed += 1

# The prompt must not grant the permission the guard now refuses.
assert "keeps its key and takes an empty list" not in components_prompt.template, \
    "ER-5 FAIL: the prompt still tells the model an empty region is fine"
assert "ownedBy JavaScript" in components_prompt.template, \
    "ER-5 FAIL: the prompt does not name the one exemption"
print("PASS ER-5 - the prompt no longer permits an empty HTML region")
_er_passed += 1

# ER-6 (2026-08-31). The guard and the prompt used to disagree, and PO-08
# po015c7e79 is what that costs: all three components attempts were refused for
# leaving 'featured-brewing-guidance' and 'newsletter-footer' empty, and the
# build never started. Both regions hold nothing but copy, and the same prompt
# says in COMPONENT vs CONTENT that "headings and copy" earn no node. The model
# was obeying one rule and being refused by the other, so a retry could not
# help -- it produced the identical answer three times. A guard the model cannot
# satisfy is not a guard, it is a wall.
_er_tpl = components_prompt.template
# whitespace-normalized view: the tie-break guard checks the RULE is stated,
# not the exact line-wrapping (retired the \n-sensitivity 2026-09-03).
_er_norm = " ".join(_er_tpl.split())
assert "the region rule wins" in _er_tpl, \
    "ER-6 FAIL: the prompt does not say which rule wins, so a prose-only region " \
    "is still an unwinnable refusal"
assert "ONE node" in _er_norm and "never one per paragraph" in _er_norm, \
    "ER-6 FAIL: the tie-break does not say HOW to plan a prose region, so the " \
    "model can satisfy it by over-modelling every paragraph instead"
assert "COMPONENT vs CONTENT describes" in _er_norm, \
    "ER-6 FAIL: the region constraint does not point at the tie-break, so a " \
    "model reading only the constraints still sees a contradiction"
print("PASS ER-6 - a prose-only region has a stated, satisfiable answer")
_er_passed += 1

print("=" * 64)
print("empty-region guard: %d/6 PASSED (no model calls)" % _er_passed)
