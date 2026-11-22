# Ported from fyp.ipynb cell 199 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: run_eslint (subprocess mocked — offline)
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

_JS_CLEAN_JSON = '[{"filePath":"x.js","messages":[],"errorCount":0,"warningCount":0}]'
_JS_WARN_JSON  = ('[{"filePath":"x.js","messages":['
                  '{"ruleId":"no-unused-vars","severity":1,"message":"unused","line":1,"column":7}],'
                  '"errorCount":0,"warningCount":1}]')
_JS_ERR_JSON   = ('[{"filePath":"x.js","messages":['
                  '{"ruleId":"no-undef","severity":2,"message":"foo is not defined","line":2,"column":1},'
                  '{"ruleId":"no-unused-vars","severity":1,"message":"unused","line":1,"column":7}],'
                  '"errorCount":1,"warningCount":1}]')

def _rt_js(js_code):
    return SimpleNamespace(state={"js_code": js_code, "lint_passed": False},
                           tool_call_id="test-el-001")

# Case 1: empty js_code caught before subprocess
r = run_eslint.func(_rt_js(""))
assert r.update["lint_passed"] is False
assert "empty" in r.update["messages"][0].content.lower()
print("[Case 1 · EDGE] Empty js_code: caught before any subprocess runs.")
print(r.update["messages"][0].content)
print("PASS: empty js_code caught before subprocess")

# Case 2: clean JS -> lint_passed True; flat-config command; repo-local temp
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=0, stdout=_JS_CLEAN_JSON, stderr="")
    r = run_eslint.func(_rt_js("console.log(1);"))
    cmd = m.call_args[0][0]
assert "eslint" in cmd and "--config eslint.config.fyp.mjs" in cmd
assert "--no-eslintrc" not in cmd, "FAIL: removed-in-v9 flag must not be used"
assert ".lint_tmp" in cmd, "FAIL: temp file must live inside repo .lint_tmp"
assert r.update["lint_passed"] is True
assert r.update["messages"][0].content == "No issues found."
print("\n[Case 2 · NORMAL] Clean JS: the lint gate opens under the v10 flat-config invocation.")
print(f"lint_passed={r.update['lint_passed']}  message={r.update['messages'][0].content}")
print("PASS: clean JS -> lint_passed=True, v10 flat-config invocation")

# Case 3 (loop-safety property): warnings ONLY -> still lint_passed True,
# reported as advisory — cosmetic issues cannot trap the JS agent's fix loop
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=0, stdout=_JS_WARN_JSON, stderr="")
    r = run_eslint.func(_rt_js("const a = 1;"))
assert r.update["lint_passed"] is True, "FAIL: warnings must not block lint_passed"
assert "Advisory warnings" in r.update["messages"][0].content
print("\n[Case 3 · NORMAL] Warnings only: advisory text, and the fix loop is never blocked.")
print(r.update["messages"][0].content)
print("PASS: warnings-only -> lint_passed=True with advisory text")

# Case 4: errors -> lint_passed False, formatted; warnings listed separately
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=1, stdout=_JS_ERR_JSON, stderr="")
    r = run_eslint.func(_rt_js("foo(b)"))
msg = r.update["messages"][0].content
assert r.update["lint_passed"] is False
assert "Found 1 error(s):" in msg and "[no-undef]" in msg
assert "advisory warning" in msg.lower()
print("\n[Case 4 · NORMAL] Errors block: the raw report becomes readable line/col/rule feedback.")
print(msg)
print("PASS: errors block, formatted with line/col/rule + advisory section")

# Case 5: npx missing -> helpful install message
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=1, stdout="",
                               stderr="'npx' is not recognized")
    r = run_eslint.func(_rt_js("console.log(1);"))
assert "npx" in r.update["messages"][0].content
print("\n[Case 5 · INFRA] Absent toolchain: reported as a broken environment, not broken JS.")
print(r.update["messages"][0].content)
print("PASS: npx-missing guard fires")

# Case 6: unparseable output -> clean failure, no crash
with patch("subprocess.run") as m:
    m.return_value = MagicMock(returncode=2, stdout="Invalid option '--eslintrc'", stderr="")
    r = run_eslint.func(_rt_js("console.log(1);"))
assert r.update["lint_passed"] is False
assert "unparseable" in r.update["messages"][0].content.lower()
print("\n[Case 6 · INFRA] Unparseable CLI output: clean failure, no crash.")
print(r.update["messages"][0].content)
print("PASS: unparseable/CLI-error output handled\n")
