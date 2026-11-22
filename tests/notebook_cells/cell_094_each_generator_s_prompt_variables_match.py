# Ported from fyp.ipynb cell 94 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: each generator's prompt variables match what its tool feeds it.
#
# Three places must agree for a generator to run: the prompt's {placeholders},
# the base_payload dict the retry loop hands in, and the arg_types on .as_tool,
# which is the tool's input schema. A key in the payload but NOT in arg_types is
# silently DROPPED before the prompt sees it, so the prompt then raises "missing
# variable" only during a live run. That is exactly how house_rules/run_brief
# broke E2E-SD-02 on 2026-08-23: the prompt and payload had them, arg_types did
# not. This checks all three offline, straight from the notebook file.
from tests.package_source import package_cells, package_notebook  # Ticket 05: the package source, not the frozen notebook
import ast as _gv_ast
import json as _gv_json
import pathlib as _gv_path

_gv_cells = package_cells()


def _gv_cell_for(fn_name):
    # Ticket 05: a notebook cell held one generator: its `<fn>_tool = ...as_tool(`
    # and its `def <fn>(runtime`. A package module holds all four, so the two
    # statements are cut out of the module, which is what the cell held.
    # Ticket 07: the body (and its base_payload) moved into the plain function
    # generate_<stage>_specification; the @tool def is a one-line adapter. Both
    # defs are cut out with the structured tool.
    _plain = "generate_" + fn_name[: -len("_generator")]
    for c in _gv_cells:
        s = "".join(c["source"])
        if f"def {fn_name}(runtime" not in s:
            continue
        parts = [_gv_ast.get_source_segment(s, n) for n in _gv_ast.parse(s).body
                 if (isinstance(n, _gv_ast.FunctionDef) and n.name in (fn_name, _plain))
                 or (isinstance(n, _gv_ast.Assign)
                     and any(getattr(t, "id", "") == f"{fn_name}_tool" for t in n.targets))]
        assert len(parts) == 3, (f"{fn_name}: expected its tool, its plain function "
                                 f"and its @tool def, got {len(parts)}")
        return "\n\n".join(parts)
    raise AssertionError(f"cell not found for {fn_name}")


def _gv_payload_keys(src):
    for node in _gv_ast.walk(_gv_ast.parse(src)):
        if (isinstance(node, _gv_ast.Assign)
                and any(getattr(t, "id", "") == "base_payload" for t in node.targets)
                and isinstance(node.value, _gv_ast.Dict)):
            return {k.value for k in node.value.keys
                    if isinstance(k, _gv_ast.Constant)}
    raise AssertionError("base_payload not found")


def _gv_arg_types_keys(src):
    # the arg_types={...} keyword on the .as_tool(...) call in the same cell
    for node in _gv_ast.walk(_gv_ast.parse(src)):
        if (isinstance(node, _gv_ast.Call)
                and isinstance(node.func, _gv_ast.Attribute)
                and node.func.attr == "as_tool"):
            for kw in node.keywords:
                if kw.arg == "arg_types" and isinstance(kw.value, _gv_ast.Dict):
                    return {k.value for k in kw.value.keys
                            if isinstance(k, _gv_ast.Constant)}
    raise AssertionError("arg_types not found on any .as_tool call")


_gv_specs = [
    ("layout_specification_generator", layout_prompt),
    ("components_specification_generator", components_prompt),
    ("interactions_specification_generator", interactions_prompt),
    ("decoration_specification_generator", decoration_prompt),
]
_gv_passed = 0
for _fn, _prompt in _gv_specs:
    _src = _gv_cell_for(_fn)
    _keys = _gv_payload_keys(_src) | {"validation_feedback"}
    _vars = set(_prompt.input_variables)
    _at = _gv_arg_types_keys(_src)
    assert _vars == _keys, f"{_fn}: prompt vars {_vars} != payload keys {_keys}"
    # arg_types is the tool's input gate: it must pass every payload key through,
    # plus the validation_feedback the retry loop adds. A mismatch here is what
    # silently drops a key before the prompt.
    assert _at == _keys, f"{_fn}: arg_types {_at} != payload+feedback {_keys}"
    assert "house_rules" in _vars and "run_brief" in _vars, f"{_fn}: rules not injected"
    _prompt.format(**{k: "x" for k in _keys})   # raises if a brace is unbalanced
    print(f"GV PASS  {_fn}: prompt, payload and arg_types agree ({len(_vars)} vars)")
    _gv_passed += 1

assert _gv_passed == 4, f"expected 4, got {_gv_passed}"
print(f"generator prompt/payload/arg_types consistency: {_gv_passed}/4 PASSED")
