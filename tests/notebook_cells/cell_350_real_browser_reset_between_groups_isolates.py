# Ported from fyp.ipynb cell 350 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test (real browser): reset-between-groups isolates interaction groups, so a
# drawer/overlay one group opens cannot intercept the NEXT group's click. Without
# it, po2r117e13f turned one open cart drawer into dozens of phantom "intercepts
# pointer events" failures. Driven through the real run_test_suite (not a replica
# loop) on a fixture whose first click opens a full-screen overlay. AUTO_OPEN is
# held off here so this measures reset alone.
import tempfile as _rg_tf, pathlib as _rg_pl
from types import SimpleNamespace as _SNS
_RG_DIR  = _rg_pl.Path(_rg_tf.mkdtemp(prefix="webforge_reset_"))
_RG_SID  = "resetgrp01"
_RG_FILE = _RG_DIR / f"preview_{_RG_SID}.html"
_RG_FILE.write_text(
    "<!doctype html><html><head><style>"
    "#ov{position:fixed;inset:0;display:none;background:rgba(0,0,0,.5)}"
    "#ov.on{display:block}</style></head><body>"
    "<button id='open'>open</button>"
    "<button id='behind'>behind</button>"
    "<div id='ov'></div>"
    "<script>document.getElementById('open').addEventListener('click',function(){"
    "document.getElementById('ov').classList.add('on');});</script>"
    "</body></html>", encoding="utf-8")
_RG_URL   = "file:///" + str(_RG_FILE).replace("\\", "/")
_RG_CASES = [
    {"id": "RG-1", "component": "opener", "action": "click", "selector": "#open",   "expected": "triggered", "passed": None},
    {"id": "RG-2", "component": "behind", "action": "click", "selector": "#behind", "expected": "triggered", "passed": None},
]
def _rg_run(reset):
    os.environ["WEBFORGE_CASE_RESET"] = reset
    os.environ["WEBFORGE_AUTO_OPEN"]  = "0"      # isolate A: keep B out of it
    _rt = _SNS(state={"test_cases": [dict(c) for c in _RG_CASES], "preview_url": _RG_URL,
                      "session_id": _RG_SID, "modification_context": ""}, tool_call_id="rg")
    _out = run_test_suite.func(_rt).update
    return {c["id"]: c.get("passed") for c in _out["test_cases"]}
try:
    _rg_off = _rg_run("0")
    _rg_on  = _rg_run("1")
    assert _rg_off["RG-2"] is False, f"reset OFF: behind-click should be intercepted, got {_rg_off}"
    assert _rg_on["RG-2"]  is True,  f"reset ON: behind-click should LAND, got {_rg_on}"
finally:
    os.environ.pop("WEBFORGE_CASE_RESET", None)
    os.environ.pop("WEBFORGE_AUTO_OPEN", None)
print(f"PASS: reset-between-groups -- an overlay left open by group 1 intercepts group 2's "
      f"#behind click with reset OFF (RG-2 -> {_rg_off['RG-2']}), but the reload restores the "
      f"shipped page and the click LANDS with reset ON (RG-2 -> {_rg_on['RG-2']}).")
