# Ported from fyp.ipynb cell 156 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the HTML round trip preserves ampersands (2026-08-31).
# REGRESSION for E2E-MM-01. The modify applied cleanly and html-validate then
# refused the page with
#   30:40  error  Raw "&" must be encoded as "&amp;"  no-raw-characters
# on a line in the PRODUCT GRID while the model was editing the NAVBAR. bs4's
# html5 formatter leaves an unambiguous ampersand bare, so every `&amp;` in the
# document became `&` the moment the page was re-serialised. The model could not
# reach the damage, and another apply would have undone any repair, so all three
# lint attempts went to an unwinnable loop and the page saved lint_passed=False.
from tests.package_source import package_cells, package_notebook  # Ticket 05: the package source, not the frozen notebook
_am_passed = 0

_AM_HTML = (
    '<meta charset="utf-8">'
    '<input type="checkbox" checked>'
    '<p>Curated essentials for work, travel &amp; everyday routines.</p>'
    '<p>Caf&eacute; &amp;amp; more &lt;tag&gt;</p>'
    '<img src="a.png" alt="x">'
    '<button disabled type="button">Go</button>'
)


def _am_round_trip(html, formatter):
    return BeautifulSoup(html, "html.parser").decode(formatter=formatter)


# THE REGRESSION. An escaped ampersand must survive being re-serialised.
_am_once = _am_round_trip(_AM_HTML, _HTML_FORMATTER)
assert "travel &amp; everyday" in _am_once, \
    "AM-1 FAIL: &amp; came back bare -- html-validate refuses the page and the " \
    "model cannot fix damage outside the block it is editing"
# And again, because the page is re-serialised once per apply, not once per run.
assert "travel &amp; everyday" in _am_round_trip(_am_once, _HTML_FORMATTER), \
    "AM-1 FAIL: the second round trip un-escaped it, so the loop still cannot win"
print("PASS AM-1 - an escaped ampersand survives repeated round trips")
_am_passed += 1

# The tag shape html5 was chosen for must not change. html-validate rejects
# both <meta/> and checked="", so losing either trades one lint failure for
# another.
assert '<meta charset="utf-8">' in _am_once and "<meta/>" not in _am_once, \
    "AM-2 FAIL: a void element gained a self-closing slash"
assert "<input checked " in _am_once and 'checked=""' not in _am_once, \
    "AM-2 FAIL: a boolean attribute gained an empty value"
assert "<button disabled " in _am_once and 'disabled=""' not in _am_once, \
    "AM-2 FAIL: a boolean attribute gained an empty value"
print("PASS AM-2 - void elements and boolean attributes keep the html5 shape")
_am_passed += 1

# The ampersand is the ONLY thing that changed. Asserted rather than assumed:
# this serialisation is what the model diffs against, so any second difference
# would silently stop diffs from matching.
_am_html5 = _am_round_trip(_AM_HTML, "html5")
assert _am_once.replace("&amp;", "&") == _am_html5.replace("&amp;", "&"), (
    "AM-3 FAIL: the new formatter differs from html5 by more than the "
    "ampersand.\n  new  : %s\n  html5: %s" % (_am_once, _am_html5))
assert _am_once != _am_html5, "AM-3 FAIL: nothing changed, so the bug is still live"
print("PASS AM-3 - exactly one difference from the html5 formatter: the ampersand")
_am_passed += 1

# An already-escaped entity must not be escaped twice, or the visible text
# changes and every assert_text case on that component starts failing.
assert "&amp;amp; more" in _am_once, \
    "AM-3b FAIL: &amp;amp; was double-escaped -- the page text changed"
assert "&lt;tag&gt;" in _am_once, "AM-3b FAIL: an escaped tag was mangled"
print("PASS AM-4 - an already-escaped entity round trips unchanged")
_am_passed += 1

# One formatter, everywhere. extract_component hands the model a block, the
# model diffs against THAT text, and store_html_diff must rebuild the identical
# string to find it again -- a second formatter anywhere is a diff that stops
# matching, with nothing reporting why. Read from the file, the way PS-6 does,
# because these are notebook-defined functions.
# Ticket 05: this read the frozen notebook and counted 'formatter=\\"html5\\"'
# (with backslashes), which plain source never contains, so it could not fail.
# It now counts the real spelling in the package source.
_am_nb = package_notebook()
_am_stale = sum(''.join(_c["source"]).count('formatter="html5"')
                for _c in _am_nb["cells"] if _c["cell_type"] == "code")
assert _am_stale == 0, \
    ("AM-5 FAIL: %d serialisation(s) still use the html5 formatter directly. "
     "Two formatters in one agent means the block the model was given and the "
     "block store_html_diff looks for are different strings." % _am_stale)
print("PASS AM-5 - every HTML serialisation shares one formatter")
_am_passed += 1

print("=" * 64)
print("HTML ampersand round trip: %d/5 PASSED (no model calls)" % _am_passed)
