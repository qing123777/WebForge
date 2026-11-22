# Ported from fyp.ipynb cell 106 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# LIVE-LLM: costs credits, run manually only
# E2E-SD-01  Smoke -- the lightest of the three end-to-end checks on the
# planning CHAIN (run_planning_pipeline). It runs the whole chain once and
# prints whether it stopped early and how big each of the four specs is. It
# does NOT inspect the contents; E2E-SD-02 and E2E-SD-03 below do that.
import json as _sm_json

test_query = (
    "Generate a product listing page for a sneaker store with a modern style, dark mode, "
    "top nav, compact grid, and features like search, filters, sorting, cart, and wishlist. "
    "Also add a sticky promo banner."
)

_state, _error = run_planning_pipeline(test_query, {}, progress=print, run_name_prefix="E2E-SD-01")

print("\n--- E2E-SD-01 smoke result ---")
print("stopped early:", _error)
for _k in ("layout_specification", "components_specification",
           "interactions_specification", "decoration_specification"):
    print(f"{_k}: {len(_sm_json.dumps(_state.get(_k) or {}))} chars")
