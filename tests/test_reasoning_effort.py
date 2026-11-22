"""Speed-cost ticket 06: each model's reasoning effort is set in one place.

    pytest tests/test_reasoning_effort.py   (or python tests/test_reasoning_effort.py)

Offline, no model calls.

  RE-1  REASONING_EFFORT in webforge/core.py names every reasoning model, and
        each model object carries exactly the effort the table gives it.
  RE-2  no module writes an effort of its own.
  RE-3  WEBFORGE_REASONING_<NAME> overrides one entry for one process, so a
        paid suite can measure another effort without a code change; a value
        that is not an effort is refused.

Measured free on the 2026-11-10 PO-08 run (4fb17fbe): 34,813 reasoning tokens,
and they are not where the ticket expected. Planning used 0, the two
orchestrators about 800 together. The four writing agents used the rest: CSS
16,932 (12,074 in one call), JS 6,553, HTML 5,127, Test Generation 5,073.
"""
import contextlib
import io
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import webforge.primary_orchestrator as wf  # noqa: E402  the whole flat namespace
    import webforge.core as core  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

# table name -> the model object that must carry it
MODELS = {
    "context": "_context_model",
    "html": "_html_model",
    "css": "_css_model",
    "js": "_js_model",
    "test_gen": "_test_gen_model",
    "secondary_orchestrator": "_secondary_orch_model",
    "primary_orchestrator": "_orc_model",
}


def test_the_table_names_every_reasoning_model():
    assert sorted(core.REASONING_EFFORT) == sorted(MODELS)
    assert set(core.REASONING_EFFORT.values()) <= {"low", "medium", "high"}


@pytest.mark.parametrize("name,attr", sorted(MODELS.items()))
def test_each_model_carries_the_effort_the_table_gives(name, attr):
    model = getattr(wf, attr)
    assert model.reasoning == {"effort": core.REASONING_EFFORT[name], "summary": "auto"}


def test_the_efforts_measured_on_2026_11_10():
    # Pinned, so a change to the table is a deliberate edit here too. html,
    # css and test_gen were measured at low on their live suites (see the
    # table's comment); js and the rest were not, and stay at medium.
    assert core.REASONING_EFFORT == {
        "context": "medium", "html": "low", "css": "low", "js": "medium",
        "test_gen": "low", "secondary_orchestrator": "medium",
        "primary_orchestrator": "medium"}


def test_no_module_writes_an_effort_of_its_own():
    found = []
    for f in sorted((ROOT / "webforge").rglob("*.py")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'["\']effort["\']\s*:', line) and f.name != "core.py":
                found.append(f"{f.name}:{n}: {line.strip()}")
    assert not found, found


def _effort_in_child(env):
    # Not through conftest: it clears WEBFORGE_REASONING_* on purpose.
    code = ("import sys, contextlib, io; sys.path.insert(0, 'tests'); sys.path.insert(0, '.')\n"
            "from cell_runner import disable_api_keys; disable_api_keys('sk-DISABLED-offline')\n"
            "with contextlib.redirect_stdout(io.StringIO()):\n"
            "    import webforge.css_agent as c\n"
            "print('EFFORT', c._css_model.reasoning['effort'], c._html_model.reasoning['effort'])")
    return subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=ROOT,
                          env={**os.environ, **env}, capture_output=True, text=True,
                          encoding="utf-8")


def test_env_overrides_one_entry():
    out = _effort_in_child({"WEBFORGE_REASONING_CSS": "high"})
    assert f"EFFORT high {core.REASONING_EFFORT['html']}" in out.stdout, out.stdout + out.stderr


def test_env_value_that_is_not_an_effort_is_refused():
    out = _effort_in_child({"WEBFORGE_REASONING_CSS": "tiny"})
    assert out.returncode != 0 and "WEBFORGE_REASONING_CSS" in out.stderr, out.stderr[-400:]


def test_conftest_clears_a_stray_override():
    # A value left in the shell must not change what the offline tests check.
    code = ("import os, sys; sys.path.insert(0, 'tests'); import conftest\n"
            "print('LEFT', sorted(v for v in os.environ if v.startswith('WEBFORGE_REASONING_')))")
    out = subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=ROOT,
                         env={**os.environ, "WEBFORGE_REASONING_CSS": "tiny"},
                         capture_output=True, text=True, encoding="utf-8")
    assert "LEFT []" in out.stdout, out.stdout + out.stderr


def test_reasoning_for_an_unknown_name_is_an_error():
    with pytest.raises(KeyError):
        core._reasoning_for("nobody")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
