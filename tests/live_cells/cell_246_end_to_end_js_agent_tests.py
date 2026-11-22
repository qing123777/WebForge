# Ported from fyp.ipynb cell 246 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# LIVE-LLM: costs credits, run manually only
# ═══════════════════════════════════════════════════════════════════════════
# END-TO-END JS AGENT TESTS  (no mocking — REAL LLM CALLS, spends credits)
#
# COST: ~1–2 GPT-5.4 calls per test case (generation re-loops if eslint reports
#       errors; this agent runs at reasoning effort "high"). Six cases below →
#       budget ~6–12 calls per full run.
#
# PREREQS
#   * Run every cell above this one first (imports, State, tools, prompts,
#     js_agent) — this cell calls the real `js_agent`.
#   * cwd must be the repo root: run_eslint resolves ./.lint_tmp, the repo-local
#     eslint binary, and eslint.config.fyp.mjs from os.getcwd().
#
# WHY A LIVE SUITE: run_eslint had NEVER worked against the real binary while
# every mocked test was green (it passed flags removed in eslint v9). Only a
# live call surfaces that class of failure.
#
# E2E-JS-GM-01  Generation   — lint passes, BOTH Naming Contract branches
#                              resolve (className target + raw-id fallback),
#                              js_code non-empty, disk matches state
# E2E-JS-MM-01  Modification — targeted change applied, wiring intact,
#                              updated file on disk
# E2E-JS-GM-02  Generation   -- fuller spec: two flows, both className
#                              targets and the raw-id fallback wired
#                              (all guard-backed, asserted hard)
# E2E-JS-MM-02  Modification -- multi-block edge: edit mini-cart (touched
#                              by both flows); both button flows survive
# E2E-JS-MM-03  Modification -- dead end: selector matches nothing;
#                              disk unchanged, no diff, no save
# E2E-JS-MM-04  Modification -- batch: two components in one session;
#                              each extracted, saved once at the end
# ═══════════════════════════════════════════════════════════════════════════
import uuid, os, re, pathlib

# Ticket 18: the preview folder comes from webforge/config.py (was C:/Users/Lenovo/Desktop/FYP/static/preview).
from webforge.config import PREVIEW_DIR as _WF_PREVIEW_DIR
_JS_PREVIEW_ROOT = str(_WF_PREVIEW_DIR)
os.makedirs(_JS_PREVIEW_ROOT, exist_ok=True)

if not os.path.isfile(os.path.join(os.getcwd(), "eslint.config.fyp.mjs")):
    print(f"[WARN] cwd={os.getcwd()!r} does not look like the repo root — "
          f"run_eslint resolves .lint_tmp, the local eslint binary and "
          f"eslint.config.fyp.mjs from cwd, so linting may fail for "
          f"environmental reasons.")

_js_session_id = uuid.uuid4().hex[:8]
_js_path       = os.path.join(_JS_PREVIEW_ROOT, f"preview_{_js_session_id}.js")
_js_html_path  = os.path.join(_JS_PREVIEW_ROOT, f"preview_{_js_session_id}.html")

# ── Specs (real dicts — store_js_code calls .get() on both; a JSON string
#    would raise AttributeError, so never json.dumps these) ──────────────────
_JS_INTERACTION_SPEC = {
    "pages": [{
        "pageName": "plp",
        "flows": [
            {"name": "add-to-cart-flow",
             "trigger": {"event": "click", "targetId": "add-to-cart-button"},
             "actions": [{"type": "addToCart", "targetId": "mini-cart"}]},
        ],
    }]
}

# Deliberately exercises BOTH branches of the Naming Contract resolution that
# store_js_code performs:
#   add-to-cart-button -> has className -> JS must reference "add-to-cart-btn"
#   mini-cart          -> no className  -> falls back to the raw id "mini-cart"
_JS_COMPONENTS_SPEC = {
    "pages": [{
        "pageName": "plp",
        "rootComponents": [
            {"id": "add-to-cart-button", "tag": "button",
             "componentCategory": "add-to-cart-button",
             "className": "add-to-cart-btn"},
            {"id": "mini-cart", "tag": "div",
             "componentCategory": "mini-cart"},
        ],
    }]
}

# Resolve the expected selector values the same way store_js_code does, so the
# assertion below tracks the contract rather than a hardcoded guess.
_js_identity_map   = dict(_spec_component_identities(_JS_COMPONENTS_SPEC))
_JS_EXPECTED_REFS  = []
for _p in _JS_INTERACTION_SPEC["pages"]:
    for _flow in _p["flows"]:
        for _tid in ([(_flow.get("trigger") or {}).get("targetId")]
                     + [a.get("targetId") for a in (_flow.get("actions") or [])]):
            if _tid:
                _JS_EXPECTED_REFS.append(_js_identity_map.get(_tid) or _tid)

# ── Fixture HTML: the JS agent's Step 0 reads this file for DOM context.
#    Every resolved selector above must actually exist here.
_JS_FIXTURE_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Product Listing</title>
<link rel="stylesheet" href="preview_{_js_session_id}.css">
</head>
<body>
<nav class="site-navbar" aria-label="Main navigation">
<a href="index.html">Shop</a>
<div id="mini-cart" data-count="0" aria-live="polite">Cart: 0</div>
</nav>
<main>
<section id="product-grid">
<article class="product-card">
<h2>Running Shoe</h2>
<p class="price">$89.00</p>
<button class="add-to-cart-btn" type="button" aria-pressed="false">Add to cart</button>
</article>
<article class="product-card">
<h2>Trail Shoe</h2>
<p class="price">$99.00</p>
<button class="add-to-cart-btn" type="button" aria-pressed="false">Add to cart</button>
</article>
</section>
</main>
<footer id="site-footer"><p>&copy; 2026 Shop</p></footer>
<script src="preview_{_js_session_id}.js" defer></script>
</body>
</html>
"""
with open(_js_html_path, "w", encoding="utf-8") as _f:
    _f.write(_JS_FIXTURE_HTML)

# Fixture/spec consistency — fail fast rather than blaming the model for a
# contradiction the fixture itself introduced.
assert 'class="add-to-cart-btn"' in _JS_FIXTURE_HTML, \
    "FIXTURE BUG: .add-to-cart-btn absent from the fixture HTML"
assert 'id="mini-cart"' in _JS_FIXTURE_HTML, \
    "FIXTURE BUG: #mini-cart absent from the fixture HTML"
assert set(_JS_EXPECTED_REFS) == {"add-to-cart-btn", "mini-cart"}, \
    f"FIXTURE BUG: Naming Contract resolution changed: {_JS_EXPECTED_REFS}"

print(f"JS session ID  : {_js_session_id}")
print(f"Fixture HTML   : {_js_html_path}")
print(f"Expected JS    : {_js_path}")
print(f"Resolved refs  : {_JS_EXPECTED_REFS}  "
      f"(className branch + raw-id fallback)\n")


def _stream_js_agent(session_id, query, intent,
                     target_component="", target_instance=1,
                     interaction_specification=None, components_specification=None,
                     target_components=None, run_name=None):
    """Mirror of call_js_agent's payload construction.

    Deliberately kept key-for-key identical to the orchestrator tool: a live
    suite that assembles a different payload would be exercising a contract
    that never actually runs in production. In modify mode the orchestrator
    pre-loads the existing file into js_code (deterministic disk->state seed),
    exactly as call_js_agent now does; generation passes "".
    """
    _cap     = globals().get("_MODIFY_BATCH_CAP", 12)
    _comps   = list(target_components) if target_components else (
               [target_component] if target_component else [])
    _comps   = _comps[:_cap]
    _primary = _comps[0] if _comps else target_component
    payload = {
        "messages":         [{"role": "user", "content": query}],
        "session_id":       session_id,
        "intent":           intent,
        "target_component": _primary,
        "target_components": _comps,
        "target_instance":  target_instance,
        "js_specification": query,
        "js_code":          _read_preview_source(session_id, "js") if intent == "modify" else "",
        "lint_passed":      False,
        "interaction_specification": interaction_specification or {},
        "components_specification":  components_specification or {},
    }
    captured = {}
    captured_tools_called = []
    captured_tool_calls_full = []

    def _merge(update):
        if isinstance(update, dict):
            for k, v in update.items():
                if k != "messages":
                    captured[k] = v

    for chunk in js_agent.stream(
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


_js_e2e_passed = 0

# ─────────────────────────────────────────────────────────────────────────────
# E2E-JS-GM-01  Generation mode — normal case
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-JS-GM-01  Generation mode — full pipeline (normal case)")
print("=" * 64)

_js_gm01 = _stream_js_agent(
    _js_session_id,
    "Wire up the add-to-cart buttons: clicking one increments the mini-cart "
    "counter and reflects the pressed state on the button.",
    intent="generate",
    interaction_specification=_JS_INTERACTION_SPEC,
    components_specification=_JS_COMPONENTS_SPEC,
    run_name="JS Agent - GM-01",
)
_js_generated = _js_gm01.get("js_code", "")

assert _js_gm01.get("lint_passed") is True, \
    f"E2E-JS-GM-01 FAIL: lint_passed={_js_gm01.get('lint_passed')}"
assert len(_js_generated) > 30, \
    f"E2E-JS-GM-01 FAIL: js_code too short ({len(_js_generated)} chars)"
assert os.path.exists(_js_path), \
    f"E2E-JS-GM-01 FAIL: file not written to disk at {_js_path}"

_js_on_disk = open(_js_path, encoding="utf-8").read()
assert _js_on_disk == _js_generated, \
    "E2E-JS-GM-01 FAIL: file on disk does not match js_code in state"

# Independent re-check of the coverage contract store_js_code enforces, across
# BOTH resolution branches. Duplicated on purpose: a guard that silently stopped
# firing would otherwise be indistinguishable from a pass.
_js_missing = [ref for ref in _JS_EXPECTED_REFS if ref not in _js_generated]
assert not _js_missing, \
    f"E2E-JS-GM-01 FAIL: interaction target(s) never referenced in JS: {_js_missing}"

# -- D proof: the effort change reached the agent that RAN ------------------
# The dangerous failure is silent: create_agent copies the model object when
# its cell runs, so editing _js_model and re-running only that cell leaves the
# built agent on the old setting and nothing is raised. This reads the effort
# off the agent the test just used, not off the global.
def _e2e_bound_model(agent):
    """The chat model a COMPILED agent actually holds.

    create_agent stores it in the model node's closure, so
    getattr(agent, "model") returns nothing and the first version of this proof
    printed "unknown" every run. Walking to the real object is the point:
    reading the global _js_model instead would pass even when the built agent
    is still on the previous setting, which is the exact failure this catches.
    Duck-typed rather than isinstance, so it does not depend on which class
    langchain_openai exports this week.
    """
    seen = set()

    def walk(o, depth=0):
        if id(o) in seen or depth > 8:
            return None
        seen.add(id(o))
        if hasattr(o, "reasoning") and hasattr(o, "model_name"):
            return o
        _d = getattr(o, "__dict__", None)
        if isinstance(_d, dict):
            for _v in _d.values():
                _items = (_v.values() if isinstance(_v, dict)
                          else _v if isinstance(_v, (list, tuple, set))
                          else [_v])
                for _x in _items:
                    _r = walk(_x, depth + 1)
                    if _r is not None:
                        return _r
        for _cell in (getattr(o, "__closure__", None) or []):
            try:
                _r = walk(_cell.cell_contents, depth + 1)
            except ValueError:
                _r = None
            if _r is not None:
                return _r
        return None

    return walk((getattr(agent, "nodes", {}) or {}).get("model")) or walk(agent)


_d_model = _e2e_bound_model(js_agent)
_d_eff = ((getattr(_d_model, "reasoning", None) or {}).get("effort")
          or getattr(_d_model, "reasoning_effort", None)
          or "unknown")
_d_want = _reasoning_for("js")["effort"]   # the table, or WEBFORGE_REASONING_JS
assert _d_eff == _d_want, (
    f"E2E-JS-GM-01 FAIL: the JS agent is running on effort={_d_eff!r}, not "
    f"{_d_want}. If it says 'high', the _js_model cell was edited but "
    "js_agent's create_agent cell was not re-run, so the change never "
    "reached the agent. If it says 'unknown', _e2e_bound_model can no "
    "longer reach the model and the reader needs fixing, not the agent.")
print(f"[proof] JS reasoning effort on the agent that ran: {_d_eff} (D live; "
      f"was 'high', the only one of six models above medium). On PO-08 "
      f"po018f8158 at 'high', JS cost $0.953 of $2.559 and 72% of its output "
      f"was reasoning, peaking at 88% in the second correction round.")

# -- Patch 2 proof: the DOM Ownership Contract, measured on THIS run ---------
# PO-08 po01e9a8b4 shipped a cart that could never render a line item. Its
# script rebuilt the cart shell under 20 class names the page had never heard
# of, guarded the rebuild with `if (!region.querySelector('#cart-heading'))`,
# and the HTML had already shipped that heading -- so the block never ran,
# `.cart-item-list` was never created, and renderCart() returned on its first
# line for the life of the page. eslint was clean and every generated
# assertion passed. Across the 53 preview pairs on disk when this was written,
# 46 runs invented zero classes and 7 invented at least one; that run's 20 was
# five times the next worst (4).
from types import SimpleNamespace as _JsPrNS

_pr_js_html = open(_js_html_path, encoding="utf-8").read()
_pr_js_invented = _js_invented_classes(
    _js_generated, _pr_js_html, _JS_COMPONENTS_SPEC, limit=10 ** 6)
print(f"[proof] DOM ownership live: {len(_pr_js_invented)} invented class(es) "
      f"reached disk {_pr_js_invented}. PO-08 po01e9a8b4 shipped 20, and its "
      f"cart was dead because of them; 46 of the 53 runs on disk shipped 0.")
assert not _pr_js_invented, (
    "E2E-JS-GM-01 FAIL: the script creates class name(s) found neither on the "
    f"page nor in the specification: {_pr_js_invented}. store_js_code's DOM "
    "Ownership guard did not run -- re-run its cell AND the create_agent cell "
    "below it.")

# ARMED, not merely absent by luck. Pure Python, no model call, no credits.
_pr_js_probe = _js_generated + '\nconst _p = document.createElement("ul"); _p.className = "cart-item-list";\n'
_pr_js_real = globals()["_read_preview_source"]
globals()["_read_preview_source"] = lambda sid, ext: (
    _pr_js_html if ext == "html" else "")
try:
    _pr_js_r = store_js_code.func(_pr_js_probe, _JsPrNS(
        state={"js_code": "", "intent": "generate",
               "session_id": _js_session_id, "dom_attempts": 0,
               "interaction_specification": {},
               "components_specification": _JS_COMPONENTS_SPEC},
        tool_call_id="proof-jsdom"))
finally:
    globals()["_read_preview_source"] = _pr_js_real
_pr_js_msg = _pr_js_r.update["messages"][0].content
assert "js_code" not in _pr_js_r.update, (
    "E2E-JS-GM-01 FAIL: a script that invents a class was STORED, so the DOM "
    "Ownership guard is not reachable from store_js_code.")
assert "add-to-cart-btn" in _pr_js_msg, (
    "E2E-JS-GM-01 FAIL: the refusal does not list the class names actually on "
    f"the page, so the model has no lookup to act on: {_pr_js_msg[:300]}")
print("[proof] an invented class is refused and the refusal hands over the "
      "page's real class names (Patch 2 live)")

_js_e2e_passed += 1
print(f"PASS E2E-JS-GM-01  lint=True  {len(_js_generated)} chars  "
      f"refs {_JS_EXPECTED_REFS} all wired  file on disk")

# Soft checks — model-phrasing dependent, reported not asserted. The State
# Materialization Contract asks for aria-*/data-state toggling, but the exact
# attribute the model picks varies; a hard assert would fail spuriously.
print(f"[soft] State Materialization (aria-*/data-state toggled): "
      f"{bool(re.search(r'(setAttribute|aria-|dataset|data-state)', _js_generated))}")
print(f"[soft] keyboard accessibility handled: "
      f"{'keydown' in _js_generated or 'keyup' in _js_generated}")
print("\n── Generated JS (first 800 chars) ──────────────────────────────────")
print(_js_generated[:800])
print()




# ─────────────────────────────────────────────────────────────────────────────
# E2E-JS-GM-02  Generation mode — contract conformance under a FULLER spec
#
# GM-01 wires a single flow with two targets. This spec forces the guard's full
# breadth: TWO flows across two clickable controls, so BOTH className targets
# AND the raw-id fallback must all be wired, each asserted hard (GM-01 leaves
# state toggling as a soft check). Fresh session — GM-01/MM-01's page untouched.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-JS-GM-02  Generation mode — contract conformance (full spec)")
print("=" * 64)

_js_session_id2 = uuid.uuid4().hex[:8]
_js_path2       = os.path.join(_JS_PREVIEW_ROOT, f"preview_{_js_session_id2}.js")
_js_html_path2  = os.path.join(_JS_PREVIEW_ROOT, f"preview_{_js_session_id2}.html")

_JS_INTERACTION_SPEC2 = {
    "pages": [{
        "pageName": "plp",
        "flows": [
            {"name": "add-to-cart-flow",
             "trigger": {"event": "click", "targetId": "add-to-cart-button"},
             "actions": [{"type": "addToCart", "targetId": "mini-cart"}]},
            {"name": "clear-cart-flow",
             "trigger": {"event": "click", "targetId": "clear-cart-button"},
             "actions": [{"type": "clearCart", "targetId": "mini-cart"}]},
        ],
    }]
}
_JS_COMPONENTS_SPEC2 = {
    "pages": [{
        "pageName": "plp",
        "rootComponents": [
            {"id": "add-to-cart-button", "tag": "button",
             "componentCategory": "add-to-cart-button", "className": "add-to-cart-btn"},
            {"id": "clear-cart-button", "tag": "button",
             "componentCategory": "clear-cart-button", "className": "clear-cart-btn"},
            {"id": "mini-cart", "tag": "div", "componentCategory": "mini-cart"},
        ],
    }]
}

# Resolve expected refs the same way store_js_code does — track the contract,
# not a hardcoded guess.
_js_identity_map2  = dict(_spec_component_identities(_JS_COMPONENTS_SPEC2))
_JS_EXPECTED_REFS2 = []
for _p in _JS_INTERACTION_SPEC2["pages"]:
    for _flow in _p["flows"]:
        for _tid in ([(_flow.get("trigger") or {}).get("targetId")]
                     + [a.get("targetId") for a in (_flow.get("actions") or [])]):
            if _tid:
                _JS_EXPECTED_REFS2.append(_js_identity_map2.get(_tid) or _tid)
_JS_EXPECTED_REFS2 = sorted(set(_JS_EXPECTED_REFS2))

# Fixture the agent reads at Step 0 — every resolved selector must exist here.
_JS_FIXTURE_HTML2 = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Product Listing</title>
<link rel="stylesheet" href="preview_{_js_session_id2}.css">
</head>
<body>
<nav class="site-navbar" aria-label="Main navigation">
<a href="index.html">Shop</a>
<div id="mini-cart" data-count="0" aria-live="polite">Cart: 0</div>
<button class="clear-cart-btn" type="button">Clear cart</button>
</nav>
<main>
<section id="product-grid">
<article class="product-card">
<h2>Running Shoe</h2>
<p class="price">$89.00</p>
<button class="add-to-cart-btn" type="button" aria-pressed="false">Add to cart</button>
</article>
<article class="product-card">
<h2>Trail Shoe</h2>
<p class="price">$99.00</p>
<button class="add-to-cart-btn" type="button" aria-pressed="false">Add to cart</button>
</article>
</section>
</main>
<footer id="site-footer"><p>&copy; 2026 Shop</p></footer>
<script src="preview_{_js_session_id2}.js" defer></script>
</body>
</html>
"""
with open(_js_html_path2, "w", encoding="utf-8") as _f:
    _f.write(_JS_FIXTURE_HTML2)

assert set(_JS_EXPECTED_REFS2) == {"add-to-cart-btn", "clear-cart-btn", "mini-cart"}, \
    f"FIXTURE BUG: Naming Contract resolution changed: {_JS_EXPECTED_REFS2}"
print(f"Session ID (GM-02): {_js_session_id2}")
print(f"Resolved refs     : {_JS_EXPECTED_REFS2}  (2 className + 1 raw-id)\n")

_js_gm02 = _stream_js_agent(
    _js_session_id2,
    "Wire up the store controls: clicking an add-to-cart button adds the item "
    "to the mini-cart and reflects its pressed state; clicking Clear cart "
    "empties the mini-cart and resets its counter.",
    intent="generate",
    interaction_specification=_JS_INTERACTION_SPEC2,
    components_specification=_JS_COMPONENTS_SPEC2,
    run_name="JS Agent - GM-02",
)
_js_gen2 = _js_gm02.get("js_code", "")

assert _js_gm02.get("lint_passed") is True, \
    f"E2E-JS-GM-02 FAIL: lint_passed={_js_gm02.get('lint_passed')}"
assert os.path.exists(_js_path2), "E2E-JS-GM-02 FAIL: file not on disk"
assert open(_js_path2, encoding="utf-8").read() == _js_gen2, \
    "E2E-JS-GM-02 FAIL: disk != state"

# Every interaction target wired — both className targets AND the raw-id
# fallback. Guard-backed, asserted hard (unlike GM-01's soft state check).
_js_missing2 = [r for r in _JS_EXPECTED_REFS2 if r not in _js_gen2]
assert not _js_missing2, \
    f"E2E-JS-GM-02 FAIL: interaction target(s) never referenced: {_js_missing2}"
# Two distinct flows, not one merged handler: both controls must appear.
assert "add-to-cart-btn" in _js_gen2 and "clear-cart-btn" in _js_gen2, \
    "E2E-JS-GM-02 FAIL: one of the two flows' controls is unwired"

_js_e2e_passed += 1
print(f"PASS E2E-JS-GM-02  lint=True  {len(_js_gen2)} chars  "
      f"all {len(_JS_EXPECTED_REFS2)} targets wired across 2 flows  disk == state")
print(f"[soft] runtime state toggled: "
      f"{bool(re.search(r'(setAttribute|aria-|dataset|data-state|data-count)', _js_gen2))}\n")
