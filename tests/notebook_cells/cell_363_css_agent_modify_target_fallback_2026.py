# Ported from fyp.ipynb cell 363 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: css_agent modify-target fallback (2026-09-15). Offline, no model.
# 13b71045: the SO model passed target_component='' on a click-to-select
# modify although state held the target. The tool now reads state when a
# modify call names nothing, and leaves a routed batch alone.
from types import SimpleNamespace as _TfNS
from unittest.mock import MagicMock as _TfMock


def _run_tf_css(state_extra, **kw):
    global css_agent, get_stream_writer
    _orig, _orig_gsw = css_agent, get_stream_writer
    _mock = _TfMock()
    _mock.stream.return_value = iter(())
    try:
        css_agent = _mock
        get_stream_writer = lambda: (lambda d: None)
        rt = _TfNS(state={"session_id": "tf01", **state_extra}, tool_call_id="tf-tc")
        call_css_agent.func(rt, "fix it", **kw)
    finally:
        css_agent, get_stream_writer = _orig, _orig_gsw
    return _mock.stream.call_args.args[0]


_p = _run_tf_css({"target_component": ".featured-product-card", "target_instance": 2},
                 intent="modify", target_component="")
assert _p["target_components"] == [".featured-product-card"], _p["target_components"]
assert _p["target_component"] == ".featured-product-card"
assert _p["target_instance"] == 2, _p["target_instance"]
print("[TF-CSS-1] PASS: empty modify target falls back to state target + instance")

_p = _run_tf_css({"target_component": ".featured-product-card", "target_instance": 2},
                 intent="modify", target_components=[".a", ".b"], target_instance=1)
assert _p["target_components"] == [".a", ".b"] and _p["target_instance"] == 1
print("[TF-CSS-2] PASS: a routed batch is not overridden by the click target")

_p = _run_tf_css({"target_component": ".featured-product-card"}, intent="generate")
assert _p["target_components"] == [] and _p["target_component"] == ""
print("[TF-CSS-3] PASS: generate mode ignores a stale target in state")
print("call_css_agent target fallback: 3/3 PASSED")
