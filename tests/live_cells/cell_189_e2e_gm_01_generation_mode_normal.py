# Ported from fyp.ipynb cell 189 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 188
# LIVE-LLM: costs credits, run manually only
# ─────────────────────────────────────────────────────────────────────────────
# E2E-GM-01  Generation mode — normal case
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-GM-01  Generation mode — full pipeline (normal case)")
print("=" * 64)

_gm01           = _stream_html_agent(_session_id, "Build a product listing page.", intent="generate", run_name="HTML Agent - GM-01")
_html_generated = _gm01.get("html_code", "")

assert _gm01.get("lint_passed") is True, \
    f"E2E-GM-01 FAIL: lint_passed={_gm01.get('lint_passed')}"
assert len(_html_generated) > 100, \
    f"E2E-GM-01 FAIL: html_code too short ({len(_html_generated)} chars)"
assert os.path.exists(_preview_path), \
    f"E2E-GM-01 FAIL: file not written to disk at {_preview_path}"

_disk_html = open(_preview_path, encoding="utf-8").read()
assert _disk_html == _html_generated, \
    "E2E-GM-01 FAIL: file on disk does not match html_code in state"

_e2e_passed += 1
print(f"PASS E2E-GM-01  lint=True  {len(_html_generated)} chars  file on disk")
print("\n── Generated HTML (first 1 000 chars) ──────────────────────────────")
print(_html_generated[:1000])
print()


# ─────────────────────────────────────────────────────────────────────────────
# E2E-GM-02  Generation mode — contract conformance under a full spec
#
# GM-01's spec declares everything by id, no states are asserted on, and no
# events exist — so it only exercises half of the Naming Contract and none of
# the state/event machinery the downstream agents rely on. This spec forces
# every clause, and the asserts check the output honoured each one. Runs in a
# FRESH session so the GM-01/MM chain artifacts stay untouched.
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 64)
print("E2E-GM-02  Generation mode — contract conformance (full spec)")
print("=" * 64)

_components_spec2 = {
    "dataSets": {"products": [
        {"id": "p1", "name": "Aurora Headphones", "price": "89.00"},
        {"id": "p2", "name": "Meridian Desk Lamp", "price": "42.00"},
        {"id": "p3", "name": "Cobalt Water Bottle", "price": "24.00"},
    ]},
    "pages": [{
        "pageName": "plp",
        "rootComponents": [
            {
                "id": "navbar", "tag": "nav",
                "componentCategory": "navbar", "ownedBy": "HTML",
                "role": ["structure"], "props": {}, "states": [], "events": [], "children": []
            },
            {
                "id": "product-grid", "tag": "section",
                "componentCategory": "product-grid", "ownedBy": "HTML",
                "role": ["structure"], "props": {}, "states": [], "events": [],
                "children": [
                    {
                        # REPEATED component: className, not id — the half of the
                        # Naming Contract GM-01 never exercises.
                        "className": "product-card", "tag": "article",
                        "componentCategory": "product-card", "ownedBy": "HTML",
                        "role": ["content"], "props": {},
                        "states": [{"name": "selected"}],
                        "events": [{"name": "click"}],
                        "children": [
                            {
                                "className": "add-to-cart-btn", "id": "add-to-cart-btn",
                                "tag": "button",
                                "componentCategory": "add-to-cart-button", "ownedBy": "HTML",
                                "role": ["interactive"], "props": {},
                                "states": [{"name": "disabled"}],
                                "events": [{"name": "click"}], "children": []
                            }
                        ]
                    }
                ]
            },
            {
                "id": "footer", "tag": "footer",
                "componentCategory": "footer", "ownedBy": "HTML",
                "role": ["structure"], "props": {}, "states": [], "events": [], "children": []
            },
        ]
    }]
}

_session_id2   = uuid.uuid4().hex[:8]
_preview_path2 = os.path.join(_HTML_PREVIEW_ROOT, f"preview_{_session_id2}.html")
print(f"Session ID (GM-02): {_session_id2}")

_gm02      = _stream_html_agent(_session_id2, "Build a product listing page.",
                                intent="generate", components_spec=_components_spec2, run_name="HTML Agent - GM-02")
_html_gm02 = _gm02.get("html_code", "")

assert _gm02.get("lint_passed") is True, \
    f"E2E-GM-02 FAIL: lint_passed={_gm02.get('lint_passed')}"
assert os.path.exists(_preview_path2), "E2E-GM-02 FAIL: file not on disk"
assert open(_preview_path2, encoding="utf-8").read() == _html_gm02, \
    "E2E-GM-02 FAIL: disk != state (save_html_file should make this impossible)"

# Naming Contract, className half: the repeated card is addressed by class
_gm02_cards = re.findall(r'<[^>]*class="[^"]*\bproduct-card\b[^"]*"[^>]*>', _html_gm02)
assert len(_gm02_cards) >= 2, \
    f"E2E-GM-02 FAIL: expected >= 2 class='product-card' instances, found {len(_gm02_cards)}"

# Naming Contract, id half: unique components stay addressable
for _comp in ("navbar", "product-grid", "footer"):
    assert f'id="{_comp}"' in _html_gm02 or f"<{_comp}" in _html_gm02, \
        f"E2E-GM-02 FAIL: unique component '{_comp}' not addressable"

# State Materialization Contract: the declared 'selected' state must exist on
# the DOM as data-state / aria-selected, on EVERY card — this is what the CSS
# agent's state selectors and Test Gen's assertions will resolve against.
_gm02_unmaterialized = [t[:70] for t in _gm02_cards
                        if "data-state=" not in t and "aria-selected=" not in t]
assert not _gm02_unmaterialized, \
    f"E2E-GM-02 FAIL: card(s) without a state attribute: {_gm02_unmaterialized}"

# Event clause: the clickable button exists, is a real <button>, addressable by class
assert re.search(r'<button[^>]*class="[^"]*\badd-to-cart-btn\b', _html_gm02), \
    "E2E-GM-02 FAIL: clickable add-to-cart-btn missing or not a <button> with its className"

_e2e_passed += 1
print(f"PASS E2E-GM-02  {len(_gm02_cards)} cards by class, all state-marked, "
      f"button addressable, disk == state\n")
