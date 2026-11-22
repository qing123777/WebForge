# Ported from fyp.ipynb cell 109 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# NOTEBOOK-ONLY: scaffolding for manual runs, never exported to fyp.py
# ═══════════════════════════════════════════════════════════════════════════
# E2E (live LLM): SYSTEM DESIGN PLANNING CHAIN
#
# Run manually — this calls the REAL gpt-5.4. Runs AFTER the override cell above,
# which is what installs the enhanced planner.
#
#   E2E-SD-02  Normal brief — four specifications, ONE page, components LABELLED
#   E2E-SD-03  A storefront — the 'home' page type, and REAL product records
#
# WHY THE LABELLING CHECK IS THE POINT
# ------------------------------------
# Five code-enforced rules resolve through `componentCategory`: a product card
# must carry a labelled product-image placeholder, the page is refused if a declared category never
# reaches the markup, and the preview's select mode maps a click to the component
# that owns it. Every one is conditional on the planner emitting the category.
#
# The Secondary Orchestrator suite cannot detect a failure here, because its
# specifications are HAND-WRITTEN fixtures with the categories already filled in.
# If the planner omits them in a real run, all of those rules silently stop
# applying and the run still passes. That is the gap this scenario closes.
# ═══════════════════════════════════════════════════════════════════════════
import uuid as _sd_uuid, json as _sd_json, time as _sd_time

_SD_RESULTS = {}


def _sd_cfg(agent_name, tag):
    return {"configurable": {"thread_id": f"{tag.lower()}-{_sd_uuid.uuid4().hex[:8]}"},
            "run_name": f"{agent_name} - {tag}"}


_SD_QUERY = ("Build a product listing page for a small electronics shop. It needs a "
             "navigation bar with a cart, a grid of product cards each showing a "
             "photo, name, price and an add-to-cart button, and a footer.")

# Categories that carry a code-enforced consequence downstream. A plan naming
# none of these has switched those rules off without saying so.
_SD_LOAD_BEARING = {"product-card", "product-image-gallery", "cart-item", "navbar",
                    "add-to-cart-button", "product-grid", "footer", "search-bar",
                    "product-price", "mini-cart", "promo-banner"}


def _interactive_completeness(component_nodes):
    """Count the interactive-completeness contract over a flat list of nodes.

    Returns (qty_total, qty_ok, cart_total, cart_ok):
      qty  -- quantity-selector components; ok when the subtree has an
              event-bearing control (a working +/- stepper, not a static number).
      cart -- mini-cart drawers; ok when the subtree has a close control (an id
              or flowName reading close/dismiss/hide).
    Mirrors the two component-spec guards added 2026-09-07. A 0 total means the
    brief produced no such component; a total > 0 with ok < total means the guard
    was bypassed (PO-10 po07cdf97e was 1/0 quantity and 1/0 cart before the guard).
    """
    import re as _icc_re
    _close = _icc_re.compile(r"close|dismiss|hide", _icc_re.I)
    def _sub(n):
        yield n
        for ch in (n.get("children") or []):
            yield from _sub(ch)
    qty  = [c for c in component_nodes if str(c.get("componentCategory") or "") == "quantity-selector"]
    cart = [c for c in component_nodes if str(c.get("componentCategory") or "") == "mini-cart"]
    qty_ok  = [q for q in qty if any((n.get("events") or []) for n in _sub(q))]
    cart_ok = [m for m in cart if any(
        _close.search(str(n.get("id") or ""))
        or any(_close.search(str(e.get("flowName") or "")) for e in (n.get("events") or []))
        for n in _sub(m) if (n.get("events") or []))]
    return len(qty), len(qty_ok), len(cart), len(cart_ok)


def _sd_walk_components(spec):
    """Every ComponentNode in a components_specification, at any depth."""
    out = []
    if isinstance(spec, dict):
        if isinstance(spec.get("id"), str) and "tag" in spec:
            out.append(spec)
        for v in spec.values():
            out.extend(_sd_walk_components(v))
    elif isinstance(spec, list):
        for v in spec:
            out.extend(_sd_walk_components(v))
    return out


def _sd_target_count(comps_spec):
    """(#components, #states, #events, total) for a components_specification.
    total is the coverage-target count -- one test case per target -- so it is
    the number the 'component vs content' rule (C') is meant to shrink, and the
    number that drove the ~195-case suite before it."""
    nodes = _sd_walk_components(comps_spec)
    c = len(nodes)
    st = sum(len(n.get("states") or []) for n in nodes)
    ev = sum(len(n.get("events") or []) for n in nodes)
    return c, st, ev, c + st + ev


def _sd_spec(state, key):
    """A specification out of the captured state, whether dict or JSON string."""
    v = (state or {}).get(key)
    if isinstance(v, str):
        try:
            return _sd_json.loads(v)
        except ValueError:
            return None
    return v or {}


print("=" * 68)
print("[E2E] Planning-chain setup")
print("=" * 68)

# The planner is run_planning_pipeline now, not an agent. The rules that used to
# live in the agent prompt live in the data tables, so the pre-flight checks the
# pipeline and its rules are loaded instead of a prompt string.
assert callable(run_planning_pipeline), "PRE-FLIGHT FAIL: run_planning_pipeline is not defined"
assert "LABEL every recognisable component" in _SPEC_HOUSE_RULES
assert "ONE page only" in _SPEC_HOUSE_RULES
assert "every page includes a site search bar" in _SPEC_HOUSE_RULES, \
    "search-bar house rule missing: a search bar must default into every page type"
assert set(_BAYMARD_CHECKLISTS) and _COMMERCE_RULES and _STYLE_RULES, \
    "PRE-FLIGHT FAIL: the commerce/style/Baymard tables are not loaded"
print("[E2E] Pre-flight OK -- pipeline present, house rules and checklists loaded")

assert _sd_cfg("System Design Planning Chain", "SD-02")["run_name"] == \
    "System Design Planning Chain - SD-02"
# SD-03's brief asks for a storefront and names a specific number of specific
# goods, so both of the things it checks have an obvious right answer.
_SD_QUERY_2 = ("Build the home page for an online tea shop. It needs a hero "
               "banner, a row of tea categories, and a featured products strip "
               "showing six teas, each with a photo, a name and a price.")

print("[E2E] Setup ready — run E2E-SD-02, then E2E-SD-03.")
