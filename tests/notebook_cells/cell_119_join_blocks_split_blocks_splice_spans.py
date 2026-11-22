# Ported from fyp.ipynb cell 119 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _join_blocks / _split_blocks / _splice_spans

# Case 1: single block round-trips with no markers added at all
_b1 = ["a {\n  color: red;\n}"]
_j1 = _join_blocks(_b1)
assert _j1 == _b1[0], "single block must be returned untouched"
assert "WebForge block" not in _j1
assert _split_blocks(_j1, 1) == _b1
print("[Case 1] PASS: single block unchanged (backwards compatible)\n")

# Case 2: multi-block join/split round-trip
_b2 = ["a { color: red; }", "a:hover { color: blue; }", "@media (max-width: 600px) {\n  a { color: green; }\n}"]
_j2 = _join_blocks(_b2)
assert _j2.count("WebForge block") == 3
assert "block 1 of 3" in _j2 and "block 3 of 3" in _j2
assert _split_blocks(_j2, 3) == _b2, f"round-trip failed:\n{_split_blocks(_j2, 3)}"
print("[Case 2] PASS: 3 blocks join and split back identically\n")

# Case 3: any tampering with the markers is rejected, not silently guessed.
#   The FIRST-marker case matters most: deleting it still leaves 3 sections, so
#   a plain count check would have waved it through and merged blocks 1 and 2.
for _label, _broken in [
    ("middle marker deleted", _j2.replace("/* @@ WebForge block 2 of 3 @@ */\n", "")),
    ("first marker deleted",  _j2.replace("/* @@ WebForge block 1 of 3 @@ */\n", "")),
    ("marker renumbered",     _j2.replace("block 2 of 3", "block 9 of 3")),
    ("extra marker added",    "/* @@ WebForge block 4 of 3 @@ */\n" + _j2),
]:
    try:
        _split_blocks(_broken, 3)
        raise AssertionError(f"Case 3 FAIL: {_label} was not detected")
    except ValueError as e:
        assert "Re-extract" in str(e), str(e)
    print(f"[Case 3] PASS: {_label} rejected")
print()

# Case 4: spans splice right-to-left; two IDENTICAL blocks stay distinct
#   str.replace(block, new, 1) would have rewritten the first block twice.
_code = "x { c: 1; }\nMID\nx { c: 1; }"
_spans = [(0, 11), (16, 27)]
assert _code[0:11] == "x { c: 1; }" and _code[16:27] == "x { c: 1; }"
_out = _splice_spans(_code, _spans, ["FIRST", "SECOND"])
assert _out == "FIRST\nMID\nSECOND", f"Case 4 FAIL: got {_out!r}"
print(f"[Case 4] PASS: identical blocks spliced independently -> {_out!r}\n")

# Case 5: non-contiguous blocks keep everything between them untouched
_code5 = "AAA\n\nKEEP-ME\n\nBBB"
_out5 = _splice_spans(_code5, [(0, 3), (14, 17)], ["aaa", "bbb"])
assert _out5 == "aaa\n\nKEEP-ME\n\nbbb", f"Case 5 FAIL: got {_out5!r}"
print(f"[Case 5] PASS: text between blocks preserved -> {_out5!r}\n")

# Case 6: count mismatch is a hard error, never a partial splice
try:
    _splice_spans("abc", [(0, 1)], ["x", "y"])
    raise AssertionError("Case 6 FAIL: mismatch not detected")
except ValueError as e:
    assert "mismatch" in str(e)
    print("[Case 6] PASS: span/block count mismatch rejected\n")

# Case 7: _apply_patch terminates added lines with "\n". Patching a block's LAST
#   line therefore returns trailing whitespace that must not survive the splice,
#   or every such edit would inject a blank line into the artifact.
_patched = _apply_patch(".a { c: red; }",
                        "--- original\n+++ revised\n@@ -1,1 +1,1 @@\n"
                        "-.a { c: red; }\n+.a { c: green; }")
assert _patched.endswith("\n"), "precondition: _apply_patch adds the newline"
assert _split_blocks(_patched, 1) == [".a { c: green; }"], _split_blocks(_patched, 1)
print("[Case 7] PASS: trailing newline trimmed on the single-block path too\n")

print("_join_blocks / _split_blocks / _splice_spans: all 7 cases passed.")
