# Ported from fyp.ipynb cell 303 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 295
# LIVE-LLM: costs credits, run manually only
# ═══════════════════════════════════════════════════════════════════════════
# END-TO-END CSS AGENT TESTS  (no mocking — REAL LLM CALLS, spends credits)
#
# COST: ~1–2 GPT-5.4 calls per test case (generation re-loops if stylelint
#       reports errors). Six test cases below → budget ~6–12 calls per full run.
#
# PREREQS
#   * Run every cell above this one first (imports, State, tools, prompts,
#     css_agent) — this cell calls the real `css_agent`.
#   * cwd must be the repo root: run_stylelint resolves ./.lint_tmp and the
#     repo-local stylelint binary from os.getcwd().
#
# WHY A LIVE SUITE: the offline tests for store_css_code/run_stylelint mock
# subprocess entirely. They cannot catch what only appears against the real
# binary + the real model — exactly the class of bug that left run_stylelint
# silently broken (v16+ writes its JSON report to stderr, not stdout).
#
# E2E-CSS-GM-01  Generation   — lint passes, every decoration className has a
#                               rule, css_code non-empty, disk matches state
# E2E-CSS-MM-01  Modification — targeted change applied, no rules lost,
#                               updated file on disk
# E2E-CSS-GM-02  Generation   — fuller spec: every declared hover state
#                               variant materialises as a .class:hover rule
# E2E-CSS-MM-02  Modification — multi-block edge: edit product-card
#                               (base + :hover); other rules survive
# E2E-CSS-MM-03  Modification — dead end: selector matches nothing;
#                               disk unchanged, no diff, no save
# E2E-CSS-MM-04  Modification — batch: two components in one session;
#                               each extracted, saved once at the end
# ═══════════════════════════════════════════════════════════════════════════
import uuid, os, re, pathlib

# Ticket 18: the preview folder comes from webforge/config.py (was C:/Users/Lenovo/Desktop/FYP/static/preview).
from webforge.config import PREVIEW_DIR as _WF_PREVIEW_DIR
_CSS_PREVIEW_ROOT = str(_WF_PREVIEW_DIR)
os.makedirs(_CSS_PREVIEW_ROOT, exist_ok=True)

if not os.path.isfile(os.path.join(os.getcwd(), "eslint.config.fyp.mjs")):
    print(f"[WARN] cwd={os.getcwd()!r} does not look like the repo root — "
          f"run_stylelint resolves .lint_tmp and the local stylelint binary "
          f"from cwd, so linting may fail for environmental reasons.")

_css_session_id = uuid.uuid4().hex[:8]
_css_path       = os.path.join(_CSS_PREVIEW_ROOT, f"preview_{_css_session_id}.css")
_css_html_path  = os.path.join(_CSS_PREVIEW_ROOT, f"preview_{_css_session_id}.html")

# ── decoration_specification (real dict — store_css_code calls .get() on it;
#    a JSON string would raise AttributeError, so never json.dumps this) ──────
_CSS_DECORATION_SPEC = {
    "pages": [{
        "pageName": "plp",
        "componentDecorations": [
            {"componentId": "navbar", "className": "site-navbar",
             "baseStyles": {"background-color": "#111827", "color": "#f9fafb"}},
            {"componentId": "product-grid", "className": "product-grid",
             "baseStyles": {"display": "grid", "gap": "1rem"}},
            {"componentId": "product-card", "className": "product-card",
             "baseStyles": {"border-radius": "8px", "background-color": "#ffffff"},
             "stateVariants": [
                 {"state": "hover",
                  "styles": {"box-shadow": "0 2px 8px rgba(0, 0, 0, 0.15)"}}
             ]},
            {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
             "baseStyles": {"background-color": "#1a73e8", "color": "#ffffff"}},
            {"componentId": "product-image", "className": "product-image-placeholder",
             "baseStyles": {"aspect-ratio": "4 / 3"}},
        ],
    }]
}
_EXPECTED_CLASSNAMES = [cd["className"]
                        for _p in _CSS_DECORATION_SPEC["pages"]
                        for cd in _p["componentDecorations"]]

# ── Fixture HTML: the CSS agent's Step 0 reads this file for selector context.
#    Every className in the decoration spec above must actually appear here —
#    otherwise the agent is told to style selectors the page does not have.
_CSS_FIXTURE_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Product Listing</title>
<link rel="stylesheet" href="preview_{_css_session_id}.css">
</head>
<body>
<nav class="site-navbar" aria-label="Main navigation">
<a href="index.html">Shop</a>
</nav>
<main>
<section id="product-grid" class="product-grid">
<article class="product-card">
<div class="product-image-placeholder">Running Shoe</div>
<h2>Running Shoe</h2>
<p class="price">$89.00</p>
<button class="add-to-cart-btn" type="button">Add to cart</button>
</article>
<article class="product-card">
<div class="product-image-placeholder">Trail Shoe</div>
<h2>Trail Shoe</h2>
<p class="price">$99.00</p>
<button class="add-to-cart-btn" type="button">Add to cart</button>
</article>
</section>
</main>
<footer id="site-footer"><p>&copy; 2026 Shop</p></footer>
<script src="preview_{_css_session_id}.js" defer></script>
</body>
</html>
"""
with open(_css_html_path, "w", encoding="utf-8") as _f:
    _f.write(_CSS_FIXTURE_HTML)

# Fixture/spec consistency — fail fast here rather than blaming the model for
# a contradiction the fixture itself introduced.
for _cn in _EXPECTED_CLASSNAMES:
    assert f'class="{_cn}"' in _CSS_FIXTURE_HTML, \
        f"FIXTURE BUG: decoration className {_cn!r} absent from the fixture HTML"

print(f"CSS session ID : {_css_session_id}")
print(f"Fixture HTML   : {_css_html_path}")
print(f"Expected CSS   : {_css_path}")
print(f"Decoration classNames: {_EXPECTED_CLASSNAMES}\n")


def _stream_css_agent(session_id, query, intent,
                      target_component="", target_instance=1,
                      decoration_specification=None, target_components=None,
                      layout_specification=None, components_specification=None,
                      run_name=None):
    """Mirror of call_css_agent's payload construction.

    Deliberately kept key-for-key identical to the orchestrator tool: a live
    suite that assembles a different payload would be exercising a contract
    that never actually runs in production. In modify mode the orchestrator
    pre-loads the existing file into css_code (deterministic disk->state seed),
    exactly as call_css_agent now does; generation passes "".
    """
    _cap     = globals().get("_MODIFY_BATCH_CAP", 12)
    _comps   = list(target_components) if target_components else (
               [target_component] if target_component else [])
    _comps   = _comps[:_cap]
    _primary = _comps[0] if _comps else target_component
    payload = {
        "messages":          [{"role": "user", "content": query}],
        "session_id":        session_id,
        "intent":            intent,
        "target_component":  _primary,
        "target_components": _comps,
        "target_instance":   target_instance,
        "css_specification": query,
        "css_code":          _read_preview_source(session_id, "css") if intent == "modify" else "",
        "lint_passed":       False,
        "decoration_specification": decoration_specification or {},
        # Added 2026-08-31 with the Region Coverage Contract. Missing it
        # here while call_css_agent had it broke the key-for-key promise
        # above, and the live suite spent a run measuring a contract the
        # agent had never been given.
        "layout_specification": layout_specification or {},
        # Forwarded for the same key-for-key reason as layout above:
        # call_css_agent now sends components_specification (the selector
        # allowlist's data source), so a suite that omitted it would measure
        # an allowlist the agent never received.
        "components_specification": components_specification or {},
    }
    captured = {}
    captured_tools_called = []
    captured_tool_calls_full = []

    def _merge(update):
        if isinstance(update, dict):
            for k, v in update.items():
                if k != "messages":
                    captured[k] = v

    for chunk in css_agent.stream(
        payload,
        stream_mode=["updates", "custom"],
        version="v2",
        config={
            "configurable": {"session_id": session_id},
            **({"run_name": run_name} if run_name else {}),
        },
    ):
        chunk_type, data = (
            chunk if isinstance(chunk, tuple)
            else (chunk.get("type"), chunk.get("data"))
        )
        if chunk_type == "custom":
            print(data if isinstance(data, str) else str(data))
        elif chunk_type == "updates" and isinstance(data, dict):
            for _step, up in data.items():
                if isinstance(up, dict):
                    for _m in (up.get("messages") or []):
                        for _tc in (getattr(_m, "tool_calls", None) or []):
                            captured_tools_called.append(_tc.get("name"))
                            captured_tool_calls_full.append(
                                {"name": _tc.get("name"), "args": _tc.get("args") or {}})
                _merge(up)

    captured["tools_called"] = captured_tools_called
    captured["tool_calls_full"] = captured_tool_calls_full
    return captured


_css_e2e_passed = 0

# ─────────────────────────────────────────────────────────────────────────────
# E2E-CSS-GM-01  Generation mode — normal case
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-CSS-GM-01  Generation mode — full pipeline (normal case)")
print("=" * 64)

_css_gm01 = _stream_css_agent(
    _css_session_id,
    "Style this product listing page: dark navbar, white product cards with "
    "rounded corners and a hover shadow, and a blue primary add-to-cart button.",
    intent="generate",
    decoration_specification=_CSS_DECORATION_SPEC,
    run_name="CSS Agent - GM-01",
)
_css_generated = _css_gm01.get("css_code", "")

assert _css_gm01.get("lint_passed") is True, \
    f"E2E-CSS-GM-01 FAIL: lint_passed={_css_gm01.get('lint_passed')}"
assert len(_css_generated) > 50, \
    f"E2E-CSS-GM-01 FAIL: css_code too short ({len(_css_generated)} chars)"
assert os.path.exists(_css_path), \
    f"E2E-CSS-GM-01 FAIL: file not written to disk at {_css_path}"

_css_on_disk = open(_css_path, encoding="utf-8").read()
assert _css_on_disk == _css_generated, \
    "E2E-CSS-GM-01 FAIL: file on disk does not match css_code in state"

# Independent re-check of the coverage contract store_css_code enforces.
# Duplicated on purpose: if the guard ever silently stops firing, this catches
# it — a guard that no longer runs would otherwise look identical to a pass.
_css_missing = [cn for cn in _EXPECTED_CLASSNAMES
                if not re.search(rf"\.{re.escape(cn)}\b", _css_generated)]
assert not _css_missing, \
    f"E2E-CSS-GM-01 FAIL: decoration className(s) with no CSS rule: {_css_missing}"

_css_e2e_passed += 1
print(f"PASS E2E-CSS-GM-01  lint=True  {len(_css_generated)} chars  "
      f"{len(_EXPECTED_CLASSNAMES)} classNames covered  file on disk")

# Soft checks — model-phrasing dependent, reported not asserted. A hard assert
# here would produce false failures unrelated to what this suite verifies.
print(f"[soft] hover state variant present : "
      f"{bool(re.search(r'\.product-card\s*:\s*hover', _css_generated))}")
print(f"[soft] responsive media query      : "
      f"{'@media' in _css_generated}")

# LAYOUT SYSTEM signals (added 2026-08-25). The CSS prompt now instructs a
# centered container, an auto-fill product grid, and fixed-ratio image boxes.
# :root is contract-backed -- store_css_code refuses a stylesheet without one --
# so it is HARD-asserted here as an independent re-check of that guard (same
# spirit as the className coverage re-check above). The layout SHAPES depend on
# the model's phrasing and on what the fixture offers (a #product-grid and a
# product-image-placeholder box), so they are SOFT-reported, not asserted.
assert re.search(r':root\s*\{', _css_generated), \
    "E2E-CSS-GM-01 FAIL: no :root token block -- the Design Token Contract requires one"
print(f"[soft] centered container (max-width): "
      f"{bool(re.search(r'max-width\s*:', _css_generated))}")
print(f"[soft] auto-fill/fit product grid   : "
      f"{bool(re.search(r'repeat\(\s*auto-(?:fill|fit)', _css_generated))}")
print(f"[soft] fixed-ratio image box        : "
      f"{bool(re.search(r'aspect-ratio\s*:', _css_generated))}  (product-image-placeholder declares an aspect-ratio baseStyle)")
print("\n── Generated CSS (first 800 chars) ─────────────────────────────────")
print(_css_generated[:800])
print()


# ─────────────────────────────────────────────────────────────────────────────
# E2E-CSS-GM-02  Generation mode — contract conformance under a FULLER spec
#
# GM-01 hard-asserts only that each decoration className has SOME rule, and
# leaves hover as a soft check. This spec declares hover state variants on TWO
# components and asserts every one materialises as a `.class:hover` rule — the
# CSS analogue of the State Materialization Contract. Fresh session.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-CSS-GM-02  Generation mode — contract conformance (full spec)")
print("=" * 64)

_css_session_id2 = uuid.uuid4().hex[:8]
_css_path2       = os.path.join(_CSS_PREVIEW_ROOT, f"preview_{_css_session_id2}.css")
_css_html_path2  = os.path.join(_CSS_PREVIEW_ROOT, f"preview_{_css_session_id2}.html")

_CSS_DECORATION_SPEC2 = {
    "pages": [{
        "pageName": "plp",
        "componentDecorations": [
            {"componentId": "navbar", "className": "site-navbar",
             "baseStyles": {"background-color": "#111827", "color": "#f9fafb"}},
            {"componentId": "product-card", "className": "product-card",
             "baseStyles": {"border-radius": "8px", "background-color": "#ffffff"},
             "stateVariants": [
                 {"state": "hover",
                  "styles": {"box-shadow": "0 2px 8px rgba(0, 0, 0, 0.15)"}}]},
            {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
             "baseStyles": {"background-color": "#1a73e8", "color": "#ffffff"},
             "stateVariants": [
                 {"state": "hover",
                  "styles": {"background-color": "#0b5cd5"}}]},
        ],
    }]
}
_EXPECTED_CLASSNAMES2 = [cd["className"]
                         for _p in _CSS_DECORATION_SPEC2["pages"]
                         for cd in _p["componentDecorations"]]
_HOVER_CLASSNAMES2 = [cd["className"]
                      for _p in _CSS_DECORATION_SPEC2["pages"]
                      for cd in _p["componentDecorations"]
                      if any(sv.get("state") == "hover"
                             for sv in cd.get("stateVariants", []))]

_CSS_FIXTURE_HTML2 = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Product Listing</title>
<link rel="stylesheet" href="preview_{_css_session_id2}.css">
</head>
<body>
<nav class="site-navbar" aria-label="Main navigation">
<a href="index.html">Shop</a>
</nav>
<main>
<section id="product-grid">
<article class="product-card">
<h2>Running Shoe</h2>
<p class="price">$89.00</p>
<button class="add-to-cart-btn" type="button">Add to cart</button>
</article>
<article class="product-card">
<h2>Trail Shoe</h2>
<p class="price">$99.00</p>
<button class="add-to-cart-btn" type="button">Add to cart</button>
</article>
</section>
</main>
<footer id="site-footer"><p>&copy; 2026 Shop</p></footer>
<script src="preview_{_css_session_id2}.js" defer></script>
</body>
</html>
"""
# The regions the fixture above actually contains, in the shape the layout
# generator emits. Named here so the run and its proof read the SAME list:
# a proof against a layout the agent never received measures nothing.
# site-footer is ownedBy JavaScript on purpose. That is the case that
# shipped broken on PO-08 po018f8158 -- the components generator exempts a
# JavaScript-owned region, so nothing downstream ever asked for its
# container styling, and it rendered flush against the window edge.
_CSS_LAYOUT_SPEC2 = {"pages": [{"pageName": "listing", "regions": [
    {"name": "site-navbar",  "ownedBy": "HTML"},
    {"name": "product-grid", "ownedBy": "HTML"},
    {"name": "site-footer",  "ownedBy": "JavaScript"},
]}]}

with open(_css_html_path2, "w", encoding="utf-8") as _f:
    _f.write(_CSS_FIXTURE_HTML2)
for _cn in _EXPECTED_CLASSNAMES2:
    assert f'class="{_cn}"' in _CSS_FIXTURE_HTML2, \
        f"FIXTURE BUG: className {_cn!r} absent from GM-02 fixture"
print(f"Session ID (GM-02): {_css_session_id2}")
print(f"Hover classNames  : {_HOVER_CLASSNAMES2}\n")

_css_gm02 = _stream_css_agent(
    _css_session_id2,
    "Style the page: dark navbar; white product cards with rounded corners "
    "that lift with a shadow on hover; a blue primary add-to-cart button that "
    "darkens on hover.",
    intent="generate",
    decoration_specification=_CSS_DECORATION_SPEC2,
    layout_specification=_CSS_LAYOUT_SPEC2,
    run_name="CSS Agent - GM-02",
)
_css_gen2 = _css_gm02.get("css_code", "")

assert _css_gm02.get("lint_passed") is True, \
    f"E2E-CSS-GM-02 FAIL: lint_passed={_css_gm02.get('lint_passed')}"
assert os.path.exists(_css_path2), "E2E-CSS-GM-02 FAIL: file not on disk"
assert open(_css_path2, encoding="utf-8").read() == _css_gen2, \
    "E2E-CSS-GM-02 FAIL: disk != state"

# Every decoration className has a base rule (guard-backed).
_css_missing2 = [cn for cn in _EXPECTED_CLASSNAMES2
                 if not re.search(rf"\.{re.escape(cn)}\b", _css_gen2)]
assert not _css_missing2, \
    f"E2E-CSS-GM-02 FAIL: className(s) with no rule: {_css_missing2}"
# Every declared hover state variant materialises as a `.class:hover` rule.
_css_no_hover = [cn for cn in _HOVER_CLASSNAMES2
                 if not re.search(rf"\.{re.escape(cn)}\s*:\s*hover", _css_gen2)]
assert not _css_no_hover, \
    f"E2E-CSS-GM-02 FAIL: declared hover state not materialised for: {_css_no_hover}"

# ── B1 proof: the CSS/DOM Drift Contract, measured on THIS run ──────────────
# Without these two lines the suite would pass identically with B1 absent. A
# healthy generation produces no drift, so nothing above ever exercises the
# guard, exactly as a healthy modify exercises neither the patch cap nor the
# hunk relocation. So both halves are reported: what this run actually shipped,
# and what the guard does to a sheet that drifts.
from types import SimpleNamespace as _PrNS

_pr_html2 = open(_css_html_path2, encoding="utf-8").read()
_pr_dead = _css_dead_selectors(_css_gen2, _pr_html2, limit=10 ** 6)
_pr_drift = _css_drifted_selectors(_css_gen2, _pr_html2, limit=10 ** 6)
print(f"[proof] drift guard live: {len(_pr_drift)} drifted rule(s) reached disk, "
      f"{len(_pr_dead) - len(_pr_drift)} dead-but-allowed (reset or defensive). "
      f"Run po018f8158 shipped 14 and 4.")
assert not _pr_drift, (
    "E2E-CSS-GM-02 FAIL: a rule whose container exists and whose descendant "
    "does not reached disk, so store_css_code's drift guard did not run: "
    f"{[d[0] for d in _pr_drift]}")

# ARMED, not merely absent by luck. `.product-card` is in the fixture and
# carries h2, p and button, so `.product-card h3` is drift by construction.
# Pure Python, no model call, no credits.
_pr_probe = _css_gen2 + "\n.product-card h3 { font-size: 2rem; }\n"
_pr_real = globals()["_read_preview_source"]
globals()["_read_preview_source"] = lambda sid, ext: (
    _pr_html2 if ext == "html" else "")
try:
    _pr_r = store_css_code.func(_pr_probe, _PrNS(
        state={"css_code": "", "intent": "generate",
               "session_id": _css_session_id2, "decoration_specification": {}},
        tool_call_id="proof-drift"))
finally:
    globals()["_read_preview_source"] = _pr_real
_pr_msg = _pr_r.update["messages"][0].content
assert "css_code" not in _pr_r.update, (
    "E2E-CSS-GM-02 FAIL: a drifted rule was STORED. The guard is not wired "
    "into the css_agent that just ran -- re-run the store_css_code cell AND "
    "the create_agent cell below it.")
assert "<h2>" in _pr_msg or "<button>" in _pr_msg, (
    "E2E-CSS-GM-02 FAIL: the refusal did not name the container's real "
    f"children, so the agent cannot act on it: {_pr_msg[:300]}")
print("[proof] drift is refused and the refusal names the real child tags "
      "(B1 live); reset rules such as `img` are still only advised")

# -- B2 proof: every layout region ends up styled ---------------------------
# Same shape and the same reason as the drift proof above. On PO-08
# po018f8158, filter-sort-bar and cart-drawer were the two regions with
# ownedBy: JavaScript, and both shipped with zero rules reaching anything
# inside them, so both rendered flush against the window edge.
# The SAME object handed to the run above. Building a second one here is
# how the first version of this proof came to report a failure for a
# contract the agent had never been given.
_pr_layout = _CSS_LAYOUT_SPEC2
_pr_bare = _css_unstyled_regions(_css_gen2, _pr_html2, _pr_layout)
assert not _pr_bare, (
    "E2E-CSS-GM-02 FAIL: region(s) reached by no rule at all: "
    f"{[n for n, _ in _pr_bare]}. The agent was given the region list, so "
    "either the guard in store_css_code did not run (re-run its cell AND "
    "the create_agent cell below it) or it ran out of attempts.")
print(f"[proof] region coverage live: {len(_pr_bare)} of "
      f"{len(_layout_region_names(_pr_layout))} region(s) reached by no rule "
      f"{[n for n, _ in _pr_bare]}. Run po018f8158 shipped 2 of 9 bare, both "
      f"of them ownedBy: JavaScript.")

# And the region list actually reaches the agent -- without it the guard would
# be a wall, refusing a plan the model was never given the means to produce.
_pr_prompt, _ = _select_css_prompt({"intent": "generate",
                                    "layout_specification": _pr_layout})
assert "#site-footer" in _pr_prompt and "NOT exempt" in _pr_prompt, \
    ("E2E-CSS-GM-02 FAIL: the region list or the JavaScript rule is missing "
     "from the prompt the agent receives, so the region guard has no way to "
     "be satisfied")
print("[proof] the region list and the JavaScript-is-not-exempt rule both "
      "reach the CSS agent's prompt (B2 live)")

_css_e2e_passed += 1
print(f"PASS E2E-CSS-GM-02  lint=True  {len(_css_gen2)} chars  "
      f"{len(_EXPECTED_CLASSNAMES2)} base rules + {len(_HOVER_CLASSNAMES2)} hover rules\n")


# -----------------------------------------------------------------------------
# E2E-CSS-GM-03  Generation mode -- a show/hide region binds visibility to the
#                `hidden` attribute, never to :empty (Design A, 2026-09-01)
#
# The cart drawer shipped broken on PO-08 po01e82f54: the CSS gated its
# visibility on :not(:empty), so a closed-but-seeded drawer stayed fixed over
# the whole right side of the page. The State Variant Selectors rule now forbids
# that. This case hands the agent a drawer (with `hidden` at rest in the fixture)
# and checks the generated CSS never gates #cart-drawer / .cart-drawer on :empty.
# -----------------------------------------------------------------------------
print("=" * 64)
print("E2E-CSS-GM-03  Generation mode -- drawer visibility binds to `hidden`, not :empty")
print("=" * 64)

_css_session_id3 = uuid.uuid4().hex[:8]
_css_path3       = os.path.join(_CSS_PREVIEW_ROOT, f"preview_{_css_session_id3}.css")
_css_html_path3  = os.path.join(_CSS_PREVIEW_ROOT, f"preview_{_css_session_id3}.html")

_CSS_DECORATION_SPEC3 = {
    "pages": [{
        "pageName": "plp",
        "componentDecorations": [
            {"componentId": "navbar", "className": "site-navbar",
             "baseStyles": {"background-color": "#111827", "color": "#f9fafb"}},
            {"componentId": "cart-drawer", "className": "cart-drawer",
             "baseStyles": {"background-color": "#ffffff"}},
        ],
    }]
}
_EXPECTED_CLASSNAMES3 = [cd["className"]
                         for _p in _CSS_DECORATION_SPEC3["pages"]
                         for cd in _p["componentDecorations"]]

# The drawer ships CLOSED: `hidden` at rest, plus a close control inside it.
_CSS_FIXTURE_HTML3 = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Drawer</title>
<link rel="stylesheet" href="preview_{_css_session_id3}.css">
</head>
<body>
<nav class="site-navbar" aria-label="Main navigation"><a href="index.html">Shop</a>
<button type="button" id="cart-toggle" aria-controls="cart-drawer" aria-expanded="false">Cart</button>
</nav>
<main><p>Store</p></main>
<aside class="cart-drawer" id="cart-drawer" hidden aria-hidden="true">
<h2>Your cart</h2>
<button type="button" class="cart-close" aria-label="Close cart">Close</button>
<ul><li>Sample item</li></ul>
</aside>
<script src="preview_{_css_session_id3}.js" defer></script>
</body>
</html>
"""
with open(_css_html_path3, "w", encoding="utf-8") as _f:
    _f.write(_CSS_FIXTURE_HTML3)
for _cn in _EXPECTED_CLASSNAMES3:
    assert f'class="{_cn}"' in _CSS_FIXTURE_HTML3, \
        f"FIXTURE BUG: className {_cn!r} absent from GM-03 fixture"
print(f"Session ID (GM-03): {_css_session_id3}\n")

_css_gm03 = _stream_css_agent(
    _css_session_id3,
    "Style this page. The cart drawer is a panel that sits over the right edge "
    "when open and is hidden when closed; it starts closed.",
    intent="generate",
    decoration_specification=_CSS_DECORATION_SPEC3,
    run_name="CSS Agent - GM-03",
)
_css_gen3 = _css_gm03.get("css_code", "")

assert _css_gm03.get("lint_passed") is True, \
    f"E2E-CSS-GM-03 FAIL: lint_passed={_css_gm03.get('lint_passed')}"
assert os.path.exists(_css_path3), "E2E-CSS-GM-03 FAIL: file not on disk"
_css_missing3 = [cn for cn in _EXPECTED_CLASSNAMES3
                 if not re.search(rf"\.{re.escape(cn)}\b", _css_gen3)]
assert not _css_missing3, \
    f"E2E-CSS-GM-03 FAIL: className(s) with no rule: {_css_missing3}"

# The core check: no rule gates the drawer's visibility on emptiness.
_drawer_empty = [p for p in _rule_preludes(_css_gen3)
                 if "cart-drawer" in p and ":empty" in p]
assert not _drawer_empty, (
    "E2E-CSS-GM-03 FAIL: the drawer's visibility is gated on :empty "
    f"({_drawer_empty}). A seeded-but-closed drawer is not empty, so :not(:empty) "
    "leaves it stuck open. Bind visibility to the `hidden` attribute instead.")

_css_e2e_passed += 1
print("PASS E2E-CSS-GM-03  lint=True  drawer styled  0 :empty-gated drawer rule(s)")
print(f"[proof] drawer visibility binds to state, not content: "
      f"{len(_drawer_empty)} :empty-gated drawer rule(s) (want 0). PO-08 po01e82f54 "
      f"shipped a #cart-drawer:not(:empty) fixed rule that welded a closed-but-seeded "
      f"drawer over the whole right side of the page.")
