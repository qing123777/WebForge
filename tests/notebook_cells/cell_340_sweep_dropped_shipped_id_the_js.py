# Ported from fyp.ipynb cell 340 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: _sweep_dropped_shipped_id -- the JS deleted ids the HTML shipped.
# renderCart() on po015df552 rebuilt the quantity <option>s with text only, wiping
# #cart-qty-option-1..4, so every case that selected one by id found nothing
# (TC-073..076). The sweep compares the ids the STATIC html shipped against the ids
# present after the script has run. A page that rebuilds WITHOUT ids is flagged; one
# that leaves them alone, or rebuilds WITH ids, is not. set_content runs the inline
# <script>, so the "after the script ran" DOM is what the sweep reads -- exactly the
# production order (sweeps run after page load). Deterministic, no LLM.
_SDI_SHIPPED = (
    "<!doctype html><html><head></head><body>"
    "<nav id='navbar'>n</nav>"
    "<ul id='cart'><li id='cart-line-1'><select id='qty-1'>"
    "<option id='cart-qty-option-1' value='1'>1</option>"
    "<option id='cart-qty-option-2' value='2'>2</option>"
    "</select></li></ul>"
)
_SDI_DROP = _SDI_SHIPPED + (
    "<script>"
    "var sel=document.getElementById('qty-1');sel.innerHTML='';"
    "[1,2].forEach(function(n){var o=document.createElement('option');"
    "o.value=String(n);o.textContent=String(n);sel.appendChild(o);});"   # rebuilt, NO id -- the bug
    "</script></body></html>"
)
_SDI_OK = _SDI_SHIPPED + (
    "<script>"
    "var sel=document.getElementById('qty-1');sel.innerHTML='';"
    "[1,2].forEach(function(n){var o=document.createElement('option');"
    "o.id='cart-qty-option-'+n;o.value=String(n);o.textContent=String(n);sel.appendChild(o);});"  # rebuilt WITH id
    "</script></body></html>"
)
_SDI_UNTOUCHED = _SDI_SHIPPED + "</body></html>"

def _sdi_core(html):
    browser = _get_browser()
    page = browser.new_page()
    try:
        page.set_content(html)
        return _sweep_dropped_shipped_id(page, html)
    finally:
        page.close()

_sdi_drop = _pw_run(lambda: _sdi_core(_SDI_DROP))
_sdi_ok   = _pw_run(lambda: _sdi_core(_SDI_OK))
_sdi_none = _pw_run(lambda: _sdi_core(_SDI_UNTOUCHED))

# DROP: the two rebuilt options lost their ids -> flagged; the reason names them.
assert len(_sdi_drop) == 1, f"SDI-1 FAIL: a rebuild-without-ids must produce one finding, got {_sdi_drop}"
assert _sdi_drop[0]["action"] == "dropped_shipped_id", f"SDI-1 FAIL: wrong action {_sdi_drop[0]}"
assert _ACTION_TO_AGENT[_sdi_drop[0]["action"]] == "js_agent", "SDI-1 FAIL: must route to js_agent"
assert "cart-qty-option-1" in _sdi_drop[0]["reason"] and "cart-qty-option-2" in _sdi_drop[0]["reason"], \
    f"SDI-1 FAIL: reason does not name the dropped ids: {_sdi_drop[0]['reason']}"
print("[SDI-1] PASS: a re-render that rebuilds <option>s without ids is flagged and routed to js_agent")

# OK: rebuilt WITH ids -> nothing dropped. UNTOUCHED: no rebuild -> nothing dropped.
assert _sdi_ok == [],   f"SDI-2 FAIL: rebuilding WITH the ids must not be flagged, got {_sdi_ok}"
assert _sdi_none == [], f"SDI-3 FAIL: a page that never rebuilds must not be flagged, got {_sdi_none}"
print("[SDI-2] PASS: rebuilding the options WITH their ids is clean")
print("[SDI-3] PASS: a page that leaves the shipped ids alone is clean")

print(f"[proof] dropped-shipped-id sweep: the bug page (renderCart rebuilds <option>s with "
      f"text only) now yields {len(_sdi_drop)} finding naming "
      f"{[d for d in ('cart-qty-option-1','cart-qty-option-2')]} -> js_agent; before this sweep "
      f"the same page produced 0 findings and shipped green (po015df552 TC-073..076 failed "
      f"individually with no named cause). The WITH-ids and untouched pages both yield "
      f"{len(_sdi_ok)}/{len(_sdi_none)}, so a correct re-render is not punished.")
