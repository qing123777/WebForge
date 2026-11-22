# Ported from fyp.ipynb cell 152 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: the Sold-Out Materialization guard (C2). A product-card at zero stock whose
# add-to-cart still reads aria-disabled="false" is buyable in the DOM while its content
# says sold out (preview_po2r117e13f p-sonivox-micpro). The guard refuses it; an "almost
# sold out" card (stock still > 0) must NOT trip it.
from bs4 import BeautifulSoup as _BS_SO
def _so_card(aria, stock_html):
    return ('<article data-component="product-card" data-id="p-x" data-state="default">'
            + stock_html
            + '<button data-component="add-to-cart-button" aria-disabled="' + aria
            + '" type="button">Add to cart</button></article>')
_s1 = _BS_SO(_so_card("false", '<div><progress max="100" value="0">0%</progress></div>'), "html.parser")
assert len(_sold_out_buyable_violations(_s1)) == 1, "sold-out + buyable button must be refused"
_s2 = _BS_SO(_so_card("true", '<div><progress max="100" value="0">0%</progress></div>'), "html.parser")
assert _sold_out_buyable_violations(_s2) == [], "a correctly disabled sold-out card must pass"
_s3 = _BS_SO(_so_card("false", '<div><span>0% left &middot; 0 remaining</span></div>'), "html.parser")
assert len(_sold_out_buyable_violations(_s3)) == 1, "text 0 remaining zero stock must be caught"
_s4 = _BS_SO(_so_card("false", '<div><span>Almost sold out - 5 left</span><progress max="100" value="20">20%</progress></div>'), "html.parser")
assert _sold_out_buyable_violations(_s4) == [], "an in-stock almost-sold-out card must NOT be refused"
print("PASS: Sold-Out Materialization guard refuses a zero-stock card with a buyable "
      "add-to-cart, passes it once aria-disabled=true, and never trips on an in-stock "
      "almost-sold-out card.")
