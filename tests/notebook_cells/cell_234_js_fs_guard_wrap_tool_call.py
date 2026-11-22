# Ported from fyp.ipynb cell 234 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: js_fs_guard (@wrap_tool_call filesystem exploration guard)
#
# Drives the REAL decorated middleware object. Mirrors html_fs_guard's test:
# the guard refuses the three search tools FilesystemMiddleware adds, and lets
# read_file and the five registered tools pass through untouched.
from types import SimpleNamespace

_JSFSG_SENTINEL = object()


def _jsfsg_handler(request):
    return _JSFSG_SENTINEL


def _call_js_fs_guard(name, tcid="jsfsg-1"):
    req = SimpleNamespace(tool_call={"name": name, "id": tcid, "args": {}})
    return js_fs_guard.wrap_tool_call(req, _jsfsg_handler)


# Case 1 [GUARD] ls / glob / grep refused WITHOUT reaching the handler
print("[Case 1 · GUARD] ls / glob / grep are refused before executing")
for _name in ("ls", "glob", "grep"):
    _out = _call_js_fs_guard(_name)
    assert _out is not _JSFSG_SENTINEL, f"FAIL: {_name} reached the handler"
    assert isinstance(_out, ToolMessage), f"FAIL: {_name} did not return a ToolMessage"
    assert _out.tool_call_id == "jsfsg-1", "FAIL: tool_call_id not echoed back"
    assert _name in _out.content and "disabled" in _out.content, "FAIL: message unclear"
    print(f"  {_name}: refused, message names the tool")
print("PASS: the three search tools are blocked with a redirect message\n")

# Case 2 [NORMAL] read_file, the write path, and every REGISTERED tool pass through
print("[Case 2 · NORMAL] read_file and the registered tools are not intercepted")
_allowed = ("read_file", "write_file", "edit_file", "store_js_code", "run_eslint", "extract_js_component", "apply_and_lint_js", "save_js_file")
for _name in _allowed:
    assert _call_js_fs_guard(_name) is _JSFSG_SENTINEL, f"FAIL: {_name} wrongly intercepted"
print(f"  passed through: {list(_allowed)}")
print("PASS: only the search tools are affected; read_file stays allowed\n")

# Case 3 [EDGE] an empty / missing tool name passes through
print("[Case 3 · EDGE] an unnamed tool call is not mistaken for a forbidden one")
assert _call_js_fs_guard("") is _JSFSG_SENTINEL, "FAIL: empty name should pass through"
_req_none = SimpleNamespace(tool_call=None)
assert js_fs_guard.wrap_tool_call(_req_none, _jsfsg_handler) is _JSFSG_SENTINEL, \
    "FAIL: tool_call=None should pass through, not raise"
print("PASS: empty and missing tool names pass through without raising\n")

print("All 3 cases passed - js_fs_guard (real middleware object).")
