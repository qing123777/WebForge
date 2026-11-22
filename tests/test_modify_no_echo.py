"""Speed-cost ticket 03, part 1: a modify call does not copy the file out again.

    pytest tests/test_modify_no_echo.py   (or python tests/test_modify_no_echo.py)

Offline, no model calls.

Measured free on the 2026-11-10 PO-08 run (4fb17fbe): in the correction round
each developer agent began by sending its WHOLE file back through
store_*_code before changing anything: HTML 7,626 output tokens (64.2 s), CSS
8,461 (70.5 s), JS 6,327 (55.1 s). That is 22,414 tokens, about $0.38 of the
round's $0.80, to put in state a file the orchestrator had already put there
(call_*_agent's payload reads it from disk). The modify prompts still told
the model to do it: "Step 0: read_file, then store_*_code(<file content>)".

  NE-1  each modify prompt says the file is already loaded, and no longer
        tells the model to read_file or store the file at Step 0.
  NE-2  the fallback is real: with nothing in state, the extract tool says so
        in the words the prompt tells the model to look for.
  NE-3  the orchestrator really pre-loads it: each call_*_agent payload reads
        the file from disk in modify mode.
"""
import contextlib
import io
import pathlib
import re
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import webforge.primary_orchestrator as wf  # noqa: E402  the whole flat namespace
    import webforge.html_agent as html_mod  # noqa: E402
    import webforge.css_agent as css_mod  # noqa: E402
    import webforge.js_agent as js_mod  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

# agent -> (its module, the store tool, the extract tool, the state key)
AGENTS = {
    "html": (html_mod, "store_html_code", "extract_component", "html_code"),
    "css": (css_mod, "store_css_code", "extract_css_component", "css_code"),
    "js": (js_mod, "store_js_code", "extract_js_component", "js_code"),
}


def _modify_prompt(mod, store):
    """The module's own modify-mode prompt text: the string that carries the
    Step 0 heading and names this agent's store tool."""
    own = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    hits = [v for v in vars(mod).values()
            if isinstance(v, str) and "### Step 0" in v and store in v and v[:200] in own]
    assert hits, f"no modify prompt found in {mod.__name__}"
    return max(hits, key=len)


def _step0(prompt):
    return prompt[prompt.index("### Step 0"):prompt.index("### Step 1")]


@pytest.mark.parametrize("agent", sorted(AGENTS))
def test_modify_prompt_does_not_ask_for_the_file_again(agent):
    mod, store, extract, key = AGENTS[agent]
    prompt = _modify_prompt(mod, store)
    step0 = _step0(prompt)
    assert "already" in step0 and "state" in step0, step0
    assert f"{key} is empty" in step0, step0            # the fallback's trigger, verbatim
    # no instruction to load or store the file up front, anywhere in the prompt
    assert f"read_file -> {store}" not in prompt
    assert not re.search(r"^- Call read_file\(", step0, re.M), step0
    assert not re.search(rf"^- Call {store}\(", step0, re.M), step0
    assert f"Your FIRST tool call is\n{extract}(" in prompt.replace("\r", "")


@pytest.mark.parametrize("agent", sorted(AGENTS))
def test_empty_state_reports_the_words_the_prompt_names(agent):
    mod, store, extract, key = AGENTS[agent]
    rt = SimpleNamespace(state={key: "", "target_components": [".a"], "session_id": "s"},
                         tool_call_id="ne")
    said = getattr(wf, extract).func(rt, components=[".a"]).update["messages"][0].content
    assert f"{key} is empty" in said, said


@pytest.mark.parametrize("agent", sorted(AGENTS))
def test_orchestrator_preloads_the_file_in_modify_mode(agent):
    key = AGENTS[agent][3]
    src = (ROOT / "webforge" / "secondary_orchestrator.py").read_text(encoding="utf-8")
    assert re.search(rf'"{key}":\s+_read_preview_source\(session_id, "{agent}"\) if intent == "modify"',
                     src), key


@pytest.mark.parametrize("agent", sorted(AGENTS))
def test_store_tool_description_does_not_describe_an_opening_store(agent):
    """NE-4 (review of 3a797c4). A tool's docstring reaches the model as the
    tool description. It must not say modify mode opens by storing the file,
    which the prompt's Step 0 now forbids, nor name a tool the agent lacks."""
    store = AGENTS[agent][1]
    said = getattr(wf, store).description
    for stale in ("re-storing", "Step 0 load", "store_css_diff", "store_js_diff"):
        assert stale not in said, f"{store}: {stale!r}"


@pytest.mark.parametrize("agent", sorted(AGENTS))
def test_modify_prompt_counts_its_own_calls(agent):
    """NE-5 (review of 3a797c4). The prompt says a batch is three tool calls
    (extract, apply-and-lint, save). The one-at-a-time comparison beside it
    must use the same count: six components cost 6 x 2 + 1 = thirteen calls
    against three, not the old fifteen against five, whose extra two were
    read_file and the opening store."""
    mod, store, _extract, _key = AGENTS[agent]
    prompt = " ".join(_modify_prompt(mod, store).split())
    assert "Three tool calls" in prompt
    assert "thirteen calls and six linter runs instead of three and one" in prompt
    assert "fifteen calls" not in prompt and "five and one" not in prompt


LIVE_CELLS = {
    "html": "cell_191_e2e_mm_01_modification_mode_single.py",
    "css": "cell_305_e2e_css_mm_01_modification_mode.py",
    "js": "cell_248_e2e_js_mm_01_modification_mode.py",
}


@pytest.mark.parametrize("agent", sorted(AGENTS))
def test_live_modify_suite_can_see_the_change(agent):
    """NE-6 (review of 3a797c4). Each agent's live modify cell allowed one
    store call, so it passed the same with the change present or absent. It
    now prints the count as a [proof] line and fails on any store call."""
    store = AGENTS[agent][1]
    src = (ROOT / "tests" / "live_cells" / LIVE_CELLS[agent]).read_text(encoding="utf-8")
    assert "[proof] no echo live" in src
    assert f'_ne_tools.count("{store}")' in src and "assert _ne_store == 0" in src
    assert f'count("{store}") <= 1' not in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
