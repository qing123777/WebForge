# Ported from fyp.ipynb cell 117 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: a misnumbered hunk is relocated by its context (2026-08-30).
# REGRESSION for PO-08 po01ba89e9. Every patch failure there was the same:
# "Hunk at original line 16 does not match current content at line 16" -- the
# model miscounted line numbers, the applicator trusted only the number, and the
# uncapped retry loop burned 2.19M tokens. A unified diff says WHERE in the @@
# header and WHAT in its context lines; a real patch tool treats the number as a
# hint. The relocation must stay SAFE: unique match only, or a hunk could land in
# the wrong place and silently corrupt the file, which is exactly why the
# whole-page generation diff was rolled back.
_fz_passed = 0

_FZ_DOC = "a\nb\nTARGET-OLD\nc\nd\n"

# A correctly numbered diff must behave exactly as it always did.
_good = ("--- original\n+++ revised\n@@ -3,1 +3,1 @@\n"
         "-TARGET-OLD\n+TARGET-NEW\n")
assert _apply_patch(_FZ_DOC, _good) == "a\nb\nTARGET-NEW\nc\nd\n"
print("PASS FZ-1 - a correctly numbered hunk applies unchanged")
_fz_passed += 1

# The real defect: the same hunk with a WRONG line number. The context appears
# once, so it is relocated and applied instead of failing.
_wrong = ("--- original\n+++ revised\n@@ -16,1 +16,1 @@\n"
          "-TARGET-OLD\n+TARGET-NEW\n")
assert _apply_patch(_FZ_DOC, _wrong) == "a\nb\nTARGET-NEW\nc\nd\n", \
    "FZ-2 FAIL: a misnumbered hunk still fails -- the po01ba89e9 defect"
print("PASS FZ-2 - a misnumbered hunk is relocated by its context and applies")
_fz_passed += 1

# Safety: ambiguous context must NOT be guessed at. Two candidates means there
# is no way to know which the author meant, and guessing corrupts the file.
_dup = "x\nDUP\ny\nDUP\nz\n"
_amb = ("--- original\n+++ revised\n@@ -40,1 +40,1 @@\n"
        "-DUP\n+CHANGED\n")
try:
    _apply_patch(_dup, _amb)
    raise AssertionError("FZ-3 FAIL: an ambiguous hunk was applied somewhere")
except ValueError as _e:
    assert "does not appear exactly once" in str(_e), str(_e)
print("PASS FZ-3 - an ambiguous hunk is refused, never guessed at")
_fz_passed += 1

# A genuinely stale diff -- its context is nowhere in the document -- must still
# fail, or the guard would stop catching real staleness.
_stale = ("--- original\n+++ revised\n@@ -2,1 +2,1 @@\n"
          "-NOT-IN-THE-DOCUMENT\n+whatever\n")
try:
    _apply_patch(_FZ_DOC, _stale)
    raise AssertionError("FZ-4 FAIL: a stale diff was applied")
except ValueError:
    pass
print("PASS FZ-4 - a genuinely stale diff still fails")
_fz_passed += 1

# Relocation must use the whole context block, not just the first line, and must
# not disturb anything around it.
_ctx_doc = "h1\nkeep\nA\nB\nkeep\ntail\n"
_ctx = ("--- original\n+++ revised\n@@ -99,3 +99,3 @@\n"
        " keep\n-A\n-B\n+MERGED\n keep\n")
assert _apply_patch(_ctx_doc, _ctx) == "h1\nkeep\nMERGED\nkeep\ntail\n", \
    _apply_patch(_ctx_doc, _ctx)
print("PASS FZ-5 - a multi-line hunk relocates as a whole and leaves neighbours intact")
_fz_passed += 1

# FZ-6..FZ-8 (2026-08-31). REGRESSION for E2E-CSS-MM-01, which applied its edit
# and then failed stylelint with "133:1 Unexpected }" -- a second closing brace
# left directly after the block the modify had just rewritten. A unified diff
# states its length twice: the @@ header counts it, the body lists it.
# _apply_patch spliced by the header, so a header saying 3 over a body listing 4
# removed three lines and wrote four back, and the fourth stayed behind. The
# header is the model's arithmetic; the body is what it copied out of the file.
# The body wins. Predates Fix 6 -- the version at 376e9426 spliced by the header
# too -- so this is the same mistake corrected for POSITION and left standing
# for LENGTH.
_FZ_DOC2 = "head\nA {\n  x: 1;\n}\ntail\n"
# The body lists FOUR lines it consumes: head, A {, x: 1;, }
_FZ_BODY = " head\n A {\n-  x: 1;\n+  x: 2;\n }\n"
_FZ_WANT = "head\nA {\n  x: 2;\n}\ntail\n"

# The header UNDERCOUNTS: 3 stated over 4 real. Splicing by it leaves the fourth
# line in place while the replacement writes it again -- the live defect, and in
# a stylesheet the leftover is a closing brace.
_under = "--- original\n+++ revised\n@@ -1,3 +1,4 @@\n" + _FZ_BODY
_got = _apply_patch(_FZ_DOC2, _under)
assert _got == _FZ_WANT, \
    "FZ-6 FAIL: an undercounting header duplicated a line: %r" % _got
print("PASS FZ-6 - an @@ header that undercounts does not duplicate a line")
_fz_passed += 1

# The header OVERCOUNTS: 6 stated over 4 real. Splicing by it swallows whatever
# follows the hunk -- the same defect in the other direction.
_over = "--- original\n+++ revised\n@@ -1,6 +1,4 @@\n" + _FZ_BODY
_got = _apply_patch(_FZ_DOC2, _over)
assert _got == _FZ_WANT, \
    "FZ-7 FAIL: an overcounting header swallowed a line: %r" % _got
print("PASS FZ-7 - an @@ header that overcounts does not swallow a line")
_fz_passed += 1

# A pure insertion has no context and no removals, so its body lists nothing and
# the hunk must consume nothing. Taking the length from the body has to keep
# that working, or every insertion would start deleting. Position is not
# asserted here: where a zero-length hunk lands is a separate convention this
# change does not touch.
_ins = "--- original\n+++ revised\n@@ -3,0 +3,1 @@\n+middle\n"
_got = _apply_patch(_FZ_DOC2, _ins).splitlines()
assert "middle" in _got, "FZ-8 FAIL: the inserted line is missing: %r" % _got
for _line in ("head", "A {", "  x: 1;", "}", "tail"):
    assert _line in _got, \
        "FZ-8 FAIL: a pure insertion deleted %r: %r" % (_line, _got)
assert len(_got) == 6, "FZ-8 FAIL: expected 6 lines, got %d: %r" % (len(_got), _got)
print("PASS FZ-8 - a pure insertion adds without removing anything")
_fz_passed += 1

print("=" * 64)
print("misnumbered-hunk relocation: %d/8 PASSED (no model calls)" % _fz_passed)
