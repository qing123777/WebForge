# Ported from fyp.ipynb cell 452 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: run_planning_pipeline  (offline, no LLM)
#
# The pipeline's own job is order, state threading and stop-on-failure. Those
# are what these tests check. The four generators are swapped for fakes so no
# model is called, and the real objects are restored in a finally so every cell
# after this keeps the real ones. Placed directly below the pipeline it tests.
#
# Ticket 07: the pipeline calls the plain generate_<stage>_specification
# functions, which take the state dict and return (spec, message). The fakes
# take that shape; the names below keep the cell's original structure.
_pp_calls = []


def _pp_fake(field, produce=True, seen=None):
    """A stand-in generator: records that it ran, optionally snapshots what it
    could see, and returns (spec, message) like the real one."""
    def _f(state):
        _pp_calls.append(field)
        if seen is not None:
            seen[field] = dict(state)
        if produce:
            return {"pages": [{"pageName": "p1"}]}, f"Stored {field}."
        return None, f"FAILED to generate {field}.\n[reason] forced"
    return _f


_pp_real = (generate_layout_specification, generate_components_specification,
            generate_interactions_specification, generate_decoration_specification)
_pp_passed = 0
try:
    # Case 1: happy path - fixed order, all four fields, and threading.
    _pp_calls.clear()
    _pp_seen = {}
    generate_layout_specification = _pp_fake("layout_specification")
    generate_components_specification = _pp_fake("components_specification", seen=_pp_seen)
    generate_interactions_specification = _pp_fake("interactions_specification")
    generate_decoration_specification = _pp_fake("decoration_specification")

    _state, _err = run_planning_pipeline(
        "build a shoe shop", {"ui": {"commerce_type": "single_brand"}})
    assert _err is None, _err
    assert _pp_calls == ["layout_specification", "components_specification",
                         "interactions_specification", "decoration_specification"], _pp_calls
    assert all(_state[f] for f in ("layout_specification", "components_specification",
                                   "interactions_specification", "decoration_specification"))
    # threading: the components stage saw the layout the stage before it wrote
    assert _pp_seen["components_specification"]["layout_specification"], "layout did not thread forward"
    print("PPL-1 PASS  fixed order, four fields filled, prior spec threads to the next stage")
    _pp_passed += 1

    # Case 2: a stage failure stops the run and reports; later stages do not run.
    _pp_calls.clear()
    generate_layout_specification = _pp_fake("layout_specification")
    generate_components_specification = _pp_fake("components_specification", produce=False)
    generate_interactions_specification = _pp_fake("interactions_specification")
    generate_decoration_specification = _pp_fake("decoration_specification")

    _state2, _err2 = run_planning_pipeline("build a shoe shop", {"ui": {}})
    assert _err2 and "components_specification" in _err2 and "forced" in _err2, _err2
    assert _pp_calls == ["layout_specification", "components_specification"], _pp_calls
    assert not _state2["interactions_specification"] and not _state2["decoration_specification"]
    print("PPL-2 PASS  a stage that yields nothing stops the run and reports, later stages skipped")
    _pp_passed += 1

    # Case 3: progress fires once per stage, in order, with the old wording.
    _pp_calls.clear()
    _pp_lines = []
    generate_layout_specification = _pp_fake("layout_specification")
    generate_components_specification = _pp_fake("components_specification")
    generate_interactions_specification = _pp_fake("interactions_specification")
    generate_decoration_specification = _pp_fake("decoration_specification")

    run_planning_pipeline("build a shoe shop", {"ui": {}}, progress=_pp_lines.append)
    assert _pp_lines == [
        "\t[Design Pipeline] Generating layout specification...",
        "\t[Design Pipeline] Generating component specifications...",
        "\t[Design Pipeline] Generating interaction specifications...",
        "\t[Design Pipeline] Generating decoration specifications...",
    ], _pp_lines
    print("PPL-3 PASS  one progress line per stage, in order, wording unchanged")
    _pp_passed += 1
finally:
    (generate_layout_specification, generate_components_specification,
     generate_interactions_specification, generate_decoration_specification) = _pp_real

assert _pp_passed == 3, f"expected 3 pipeline cases, got {_pp_passed}"


# PPL-4: the LangSmith run name reaches the structured .invoke as
# "<prefix> - <stage>", and is absent when no prefix is set.
class _PPCfgProbe:
    def __init__(self):
        self.configs = []

    def invoke(self, payload, config=None):
        self.configs.append(config)
        return {"decoration_specification": {"ok": True}}

_pp_probe = _PPCfgProbe()
_pp_tok = _RUN_NAME_PREFIX.set("E2E-SD-01")
try:
    _invoke_structured_with_retries(
        stage="decoration", structured_tool=_pp_probe,
        base_payload={"x": 1}, validate_result=lambda c: None)
finally:
    _RUN_NAME_PREFIX.reset(_pp_tok)
assert _pp_probe.configs == [{"run_name": "E2E-SD-01 - decoration"}], _pp_probe.configs

_pp_probe2 = _PPCfgProbe()
_invoke_structured_with_retries(
    stage="decoration", structured_tool=_pp_probe2,
    base_payload={"x": 1}, validate_result=lambda c: None)
assert _pp_probe2.configs == [None], _pp_probe2.configs
_pp_passed += 1
assert _pp_passed == 4, f"expected 4, got {_pp_passed}"
print("PASS PPL-4  run_name reaches the invoke as '<prefix> - <stage>', absent without a prefix")
print(f"run_planning_pipeline: {_pp_passed}/4 PASSED")
