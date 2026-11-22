# Ported from fyp.ipynb cell 74 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the shared spec rules  (offline)
#
# The point of keying the tables by the schema literals is that a value cannot
# exist without a rule. These tests enforce exactly that, plus the builder's
# lookup-and-assemble behaviour and its defaults.
import typing as _sr_typing

_sr_passed = 0

# Every CommerceType / DesignStyle / PageType value has a rule, and no rule
# names a value the schema does not allow.
_commerce_vals = set(_sr_typing.get_args(CommerceType))
_style_vals = set(_sr_typing.get_args(DesignStyle))
_page_vals = set(_sr_typing.get_args(PageType))

assert set(_COMMERCE_RULES) == _commerce_vals, \
    f"commerce mismatch: {_commerce_vals ^ set(_COMMERCE_RULES)}"
assert set(_STYLE_RULES) == _style_vals, \
    f"style mismatch: {_style_vals ^ set(_STYLE_RULES)}"
assert set(_BAYMARD_CHECKLISTS) == _page_vals, \
    f"page-type mismatch: {_page_vals ^ set(_BAYMARD_CHECKLISTS)}"
assert all(len(v) >= 3 for v in _BAYMARD_CHECKLISTS.values()), \
    "every page checklist needs at least 3 items"
print("SR-1 PASS  every commerce/style/page value has a rule, none is orphaned")
_sr_passed += 1

# The defaults exist in their own tables.
assert _COMMERCE_DEFAULT in _COMMERCE_RULES and _STYLE_DEFAULT in _STYLE_RULES
print("SR-2 PASS  the null-value defaults resolve to a real rule")
_sr_passed += 1

# _run_page_type reads the single page's type, and tolerates junk.
assert _run_page_type({"pages": [{"pageType": "plp"}]}) == "plp"
assert _run_page_type({"pages": []}) is None
assert _run_page_type({}) is None and _run_page_type(None) is None
print("SR-3 PASS  _run_page_type extracts the chosen page type and tolerates empties")
_sr_passed += 1

# A later stage gets the ONE commerce line, the ONE style line, and the checklist
# for the chosen page type only.
_brief = _build_run_brief({"ui": {"commerce_type": "marketplace", "style": "minimal_premium"}},
                          page_type="plp")
assert "marketplace" in _brief and "seller name" in _brief.lower()
assert "minimal_premium" in _brief and "at most 3 cards" in _brief
assert "Baymard checklist for the plp page" in _brief
assert "Filter panel" in _brief
assert "checkout" not in _brief  # only the chosen page type's checklist appears
print("SR-4 PASS  a later stage gets its one commerce line, one style line, one checklist")
_sr_passed += 1

# The layout stage (no page type yet) gets the menu instead of one checklist.
_menu = _build_run_brief({"ui": {}}, page_type=None)
assert "Page types you may choose" in _menu
assert "plp:" in _menu and "checkout:" in _menu
# null commerce/style fall back to the defaults
assert "single_brand" in _menu and "catalog_heavy" in _menu
print("SR-5 PASS  the layout stage gets the page-type menu and the null defaults")
_sr_passed += 1

assert _sr_passed == 5, f"expected 5, got {_sr_passed}"
print(f"shared spec rules: {_sr_passed}/5 PASSED")
