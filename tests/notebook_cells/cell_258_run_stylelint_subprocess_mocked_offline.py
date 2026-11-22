# Ported from fyp.ipynb cell 258 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: run_stylelint (subprocess mocked — offline)
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

_CSS_CLEAN_JSON  = '[{"source":"x.css","parseErrors":[],"warnings":[]}]'
_CSS_ERRORS_JSON = ('[{"source":"x.css","parseErrors":[],"warnings":['
                    '{"line":2,"column":7,"rule":"block-no-empty","severity":"error","text":"Empty block (block-no-empty)"},'
                    '{"line":1,"column":15,"rule":"color-no-invalid-hex","severity":"error","text":"Invalid hex color"}]}]')

def _rt_css(css_code):
    return SimpleNamespace(state={"css_code": css_code, "lint_passed": False},
                           tool_call_id="test-sl-001")

# Case 1: empty css_code caught before subprocess
r = run_stylelint.func(_rt_css(""))
assert r.update["lint_passed"] is False
assert "empty" in r.update["messages"][0].content.lower()
print("[Case 1 · EDGE] Empty css_code: caught before any subprocess runs.")
print(r.update["messages"][0].content)
print("PASS: empty css_code caught before subprocess")

# Case 2: clean CSS -> lint_passed True. Realistic v16+/v17 behaviour: the JSON
# report arrives on STDERR, stdout empty.
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=0, stdout="", stderr=_CSS_CLEAN_JSON)
    r = run_stylelint.func(_rt_css(".a { color: #fff; }"))
    cmd = m.call_args[0][0]
assert "stylelint" in cmd and "--formatter json" in cmd
assert ".lint_tmp" in cmd, "FAIL: temp file must live inside repo .lint_tmp"
assert r.update["lint_passed"] is True
assert r.update["messages"][0].content == "No issues found."
print("\n[Case 2 · NORMAL] Clean CSS: the report arrives on stderr (v17) and the gate opens.")
print(r.update["messages"][0].content)
print("PASS: clean CSS (report on stderr, v17) -> lint_passed=True")

# Case 2b: legacy behaviour (report on stdout) still handled
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=0, stdout=_CSS_CLEAN_JSON, stderr="")
    r = run_stylelint.func(_rt_css(".a { color: #fff; }"))
assert r.update["lint_passed"] is True
print("\n[Case 2b · NORMAL] Legacy path: a report on stdout is also parsed.")
print(r.update["messages"][0].content)
print("PASS: legacy stdout report also parsed")

# Case 3: problems -> lint_passed False, formatted lines with rule tags
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=2, stdout="", stderr=_CSS_ERRORS_JSON)
    r = run_stylelint.func(_rt_css(".card { colr: #zzz; }"))
msg = r.update["messages"][0].content
assert r.update["lint_passed"] is False
assert "Found 2 problem(s):" in msg and "[block-no-empty]" in msg and "Line 1, Col 15" in msg
print("\n[Case 3 · NORMAL] Problems: formatted with line, column and rule.")
print(msg)
print("PASS: problems formatted with line/col/rule")

# Case 4: config error (exit 78) reported as infra problem, not CSS bug
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=78, stdout="",
                               stderr="Error: No configuration provided")
    r = run_stylelint.func(_rt_css(".a{}"))
assert r.update["lint_passed"] is False
assert "configuration problem" in r.update["messages"][0].content.lower()
print("\n[Case 4 · INFRA] Config error (exit 78): reported as environment, not broken CSS.")
print(r.update["messages"][0].content)
print("PASS: exit-78 config error reported distinctly")

# Case 5: npx missing -> helpful install message
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=1, stdout="",
                               stderr="'npx' is not recognized")
    r = run_stylelint.func(_rt_css(".a{color:red}"))
assert "npx" in r.update["messages"][0].content
print("\n[Case 5 · INFRA] Absent toolchain: npx-missing reported distinctly.")
print(r.update["messages"][0].content)
print("PASS: npx-missing guard fires")

# Case 6: unparseable output -> clean failure, no crash
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=2, stdout="not json at all", stderr="")
    r = run_stylelint.func(_rt_css(".a{color:red}"))
assert r.update["lint_passed"] is False
assert "unparseable" in r.update["messages"][0].content.lower()
print("\n[Case 6 · INFRA] Unparseable output: clean failure, no crash.")
print(r.update["messages"][0].content)
print("PASS: unparseable output handled\n")
