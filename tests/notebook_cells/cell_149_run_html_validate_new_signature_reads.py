# Ported from fyp.ipynb cell 149 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: run_html_validate (new signature — reads html_code from state)
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

VALID_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Dummy Testing</title>
  </head>
  <body>
    <main>
      <h1>Dummy HTML for Unit Testing</h1>
      <p>This file exists to satisfy unit tests.</p>
    </main>
  </body>
</html>"""

INVALID_HTML1 = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Dummy Testing</title>
  </head>
  <body>
    <main><h1>Test</h1></main>
  </body>
</html>"""

INVALID_HTML2 = """<html>
<body>
<P>Uppercase tag
<div><p>Bad nesting</div>
</body>"""

# Case 1: empty html_code in state → caught before subprocess, lint_passed=False
dummy_runtime = SimpleNamespace(
    state={"html_code": "", "lint_passed": False},
    tool_call_id="test-rv-001"
)
result = run_html_validate.func(dummy_runtime)
update = result.update
assert "lint_passed" in update,              "FAIL: lint_passed missing"
assert update["lint_passed"] is False,       "FAIL: expected lint_passed=False"
assert "empty" in update["messages"][0].content.lower(), \
    f"FAIL: expected empty message, got: {update['messages'][0].content}"
print("[Case 1 · EDGE] Empty html_code: caught before any subprocess runs.")
print(update["messages"][0].content)
print("PASS: empty html_code in state caught before subprocess\n")

# Case 2: valid HTML in state → subprocess called, lint_passed=True
dummy_runtime2 = SimpleNamespace(
    state={"html_code": VALID_HTML, "lint_passed": False},
    tool_call_id="test-rv-002"
)
with patch("subprocess.run") as mock_run:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result2 = run_html_validate.func(dummy_runtime2)
    called_cmd = mock_run.call_args[0][0]
    assert "html-validate" in called_cmd, "FAIL: subprocess not called with html-validate"
    assert VALID_HTML not in called_cmd,  "FAIL: html_code must NOT appear in command"
update2 = result2.update
assert update2["lint_passed"] is True,                   "FAIL: expected lint_passed=True"
assert update2["messages"][0].content == "No issues found.", \
    f"FAIL: expected 'No issues found.', got: {update2['messages'][0].content}"
print("[Case 2 · NORMAL] Clean HTML: lint gate opens, and the code travels by temp file "
      "rather than on the command line.")
print(f"lint_passed={update2['lint_passed']}  message={update2['messages'][0].content}")
print("PASS: valid HTML in state → lint passed, html_code read from state not argument\n")

# Case 3: invalid HTML1 → lint_passed=False, formatted errors returned
LINT_OUTPUT1 = '[{"messages":[{"line":2,"column":1,"ruleId":"doctype-style","message":"Doctype error"},{"line":5,"column":5,"ruleId":"void-style","message":"Void element error"}]}]'
dummy_runtime3 = SimpleNamespace(
    state={"html_code": INVALID_HTML1, "lint_passed": True},
    tool_call_id="test-rv-003"
)
with patch("subprocess.run") as mock_run:
    mock_run.return_value = MagicMock(returncode=1, stdout=LINT_OUTPUT1, stderr="")
    result3 = run_html_validate.func(dummy_runtime3)
update3 = result3.update
msg3 = update3["messages"][0].content
assert update3["lint_passed"] is False,    "FAIL: expected lint_passed=False"
assert msg3.startswith("Found "),          f"FAIL: expected formatted output, got: {msg3[:80]}"
assert "error(s):" in msg3,               "FAIL: expected 'error(s):' in message"
assert "Line "      in msg3,              "FAIL: expected line numbers"
assert "doctype-style" in msg3,           "FAIL: expected doctype-style ruleId"
assert "void-style"    in msg3,           "FAIL: expected void-style ruleId"
print("[Case 3 · NORMAL] Broken HTML: the raw JSON report becomes readable feedback "
      "carrying line, column and rule id.")
print(f"lint_passed={update3['lint_passed']}\n{msg3}")
print("PASS: invalid HTML1 → lint_passed=False, formatted errors returned\n")

# Case 4: invalid HTML2 → lint_passed=False, formatted errors returned
LINT_OUTPUT2 = '[{"messages":[{"line":3,"column":1,"ruleId":"no-uppercase-element-name","message":"Uppercase tag"},{"line":4,"column":6,"ruleId":"element-permitted-content","message":"Bad nesting"}]}]'
dummy_runtime4 = SimpleNamespace(
    state={"html_code": INVALID_HTML2, "lint_passed": True},
    tool_call_id="test-rv-004"
)
with patch("subprocess.run") as mock_run:
    mock_run.return_value = MagicMock(returncode=1, stdout=LINT_OUTPUT2, stderr="")
    result4 = run_html_validate.func(dummy_runtime4)
update4 = result4.update
msg4 = update4["messages"][0].content
assert update4["lint_passed"] is False, "FAIL: expected lint_passed=False"
assert msg4.startswith("Found "),       f"FAIL: expected formatted output, got: {msg4[:80]}"
assert "Line " in msg4,                 "FAIL: expected line numbers"
print("[Case 4 · NORMAL] The same formatting holds for a different class of error.")
print(f"lint_passed={update4['lint_passed']}\n{msg4}")
print("PASS: invalid HTML2 → lint_passed=False, formatted errors returned\n")

# Case 5: npx not found → specific install instruction returned
dummy_runtime5 = SimpleNamespace(
    state={"html_code": VALID_HTML, "lint_passed": False},
    tool_call_id="test-rv-005"
)
with patch("subprocess.run") as mock_run:
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="npx: command not found"
    )
    result5 = run_html_validate.func(dummy_runtime5)
update5 = result5.update
msg5 = update5["messages"][0].content
assert update5["lint_passed"] is False,  "FAIL: expected lint_passed=False"
assert "node" in msg5.lower() or "npx" in msg5.lower(), \
    f"FAIL: expected Node.js install instruction, got: {msg5}"
print("[Case 5 · INFRA] Absent toolchain: reported as a broken environment, not as broken HTML.")
print(msg5)
print("PASS: npx not found → install instruction returned\n")

# Case 6: html_code must never be written to state by this tool
for label, upd in [("Case 2", update2), ("Case 3", update3),
                    ("Case 4", update4), ("Case 5", update5)]:
    assert "html_code" not in upd, f"FAIL {label}: run_html_validate must not touch html_code"
print("[Case 6 · INVARIANT] Cross-check on Cases 2–5: linting never modifies the artifact.")
print("html_code present in any returned update: False")
print("PASS: html_code never written to state by run_html_validate")

# Case 7: linter output is decoded as UTF-8, not the Windows cp1252 default.
# All three linters run through _run_lint_subprocess, so testing it once here
# covers html/js/css. A generated file with a smart quote makes the linter
# echo byte 0x9d, which cp1252 cannot decode -- under the old text=True the
# reader thread died with UnicodeDecodeError and every lint round failed
# (seen live on PO-01b, 2026-08-22). This runs a real subprocess that emits
# that exact byte and proves it is replaced, not fatal. No mock: mocks return
# a ready-made str and never exercise the decode.
_enc_proc = _run_lint_subprocess(
    'python -c "import os; os.write(1, bytes([0x9d]))"')
assert isinstance(_enc_proc.stdout, str), "FAIL: linter output not decoded to str"
assert "\ufffd" in _enc_proc.stdout, \
    "FAIL: an undecodable byte must be replaced, not crash the reader"
print("[Case 7 · REGRESSION] linter output decoded as UTF-8 (errors=replace), not cp1252.")
print("PASS: a non-cp1252 byte is replaced, the reader does not crash\n")
