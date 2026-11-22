"""Ticket 08: one engine builds the developer agents' shared parts.

    pytest tests/test_dev_agent.py        (or python tests/test_dev_agent.py)

Offline, no model calls.

  DA-1  the engine, given a language, makes that language's save tool: its
        name, the docstring the model reads, and the gate (refuse before lint
        settles, write state verbatim after).
  DA-2  it makes that language's progress hooks and filesystem guard, with
        the language's own labels.
  DA-4  build_dev_agent adds the save tool after the language's tools and
        stacks the middleware in the one fixed order; new_preview_backend is
        rooted at the preview folder from webforge.config.
  DA-5  the adapter's extract_none is the text extract_js_component really
        says when nothing matches, so the progress feed stays silent on it.
  DA-6  (ticket 09) the CSS agent's parts come from the engine too, and its
        extract_none is extract_css_component's real "nothing matched" text.
  DA-7  (ticket 09) the fix loop's shared core (caps, batch helpers,
        _batch_apply_text, the lint subprocess) lives in the engine, and the
        three agents hold the same objects.
  DA-8  (ticket 09) one lint runner: refuses after the cap, guards empty
        code, lints a temp file in the lint folder, always deletes it; the
        language passes only the linter call and its output parser.
  DA-9  (ticket 09) one extract core: resolve a name through the language's
        aliases, serve every block, merge components that share a block,
        name the ones with none, reset the lint budget.
  DA-10 no later module shadows a name the engine defines.
  DA-11 (ticket 09) one apply-and-lint core: apply a diff to every block,
        lint the result in the same call, hand back the current block on a
        patch or lint failure, and batch several diffs through one lint.
  DA-12 (ticket 10) a language may name its extract tool, its extract and
        lint labels, extra tool labels and several silent extract replies.
  DA-13 (ticket 10) the HTML agent's parts come from the engine too.
  DA-14 (ticket 10) html-validate runs through the one lint runner too.
  DA-3  the JS agent's parts come from the engine, not from hand-written
        copies in js_agent.py. (That they are byte-identical to the copies
        is the baseline's job, and cells 222, 227 and 234 pin the strings.)
"""
import ast
import contextlib
import io
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import webforge.dev_agent as engine  # noqa: E402
    import webforge.js_agent as js_mod  # noqa: E402
    import webforge.css_agent as css_mod  # noqa: E402
    from webforge.dev_shared import OverwritingFilesystemBackend  # noqa: E402
    from langchain.agents.middleware import AgentState  # noqa: E402
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
    from webforge.config import REPO_ROOT  # noqa: E402


class PyState(AgentState):
    py_code: str
    session_id: str
    intent: str
    lint_passed: bool
    lint_escalated: bool


@pytest.fixture
def py(tmp_path):
    backend = OverwritingFilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    lang = engine.DevLanguage(key="py", tag="PY", noun="module", linter="Ruff",
                              lint_tool="run_ruff", extract_none="No PY code found",
                              save_backend=lambda: backend)
    return lang, engine.dev_parts(lang, PyState), tmp_path


def _rt(**state):
    return SimpleNamespace(state=state, tool_call_id="t1")


def _said(cmd):
    return cmd.update["messages"][0].content


def test_save_tool_is_the_languages_own(py):
    lang, parts, root = py
    save = parts.save_tool
    assert save.name == "save_py_file"
    assert save.description.startswith("Write py_code from state to preview_{session_id}.py on disk.")
    assert save.args == {}
    refused = _said(save.func(_rt(session_id="s1", py_code="x = 1")))
    assert refused.endswith("Run run_ruff first.") and not (root / "preview_s1.py").exists()
    ok = _said(save.func(_rt(session_id="s1", py_code="x = 1", lint_escalated=True)))
    assert ok == "Saved 5 characters of py_code from state to preview_s1.py."
    assert (root / "preview_s1.py").read_text(encoding="utf-8") == "x = 1"
    assert _said(save.func(_rt(session_id="s1", py_code="", lint_passed=True))) \
        == "py_code is empty in state. Nothing to save."


def _emit(monkeypatch, fn, *args):
    out = []
    monkeypatch.setattr(engine, "get_stream_writer", lambda: out.append)
    fn(*args)
    return out


def _after(tool, content, intent="modify"):
    return {"intent": intent, "messages": [
        HumanMessage(content="go"),
        AIMessage(content="", tool_calls=[{"name": tool, "args": {}, "id": "c1"}]),
        ToolMessage(content=content, tool_call_id="c1")]}


def test_progress_and_guard_speak_the_language(py, monkeypatch):
    _, parts, _ = py
    bm = parts.before_model_progress.before_model
    assert _emit(monkeypatch, parts.agent_progress.before_agent, {}, None) \
        == ["   [PY Agent] Processing request..."]
    assert _emit(monkeypatch, bm, {"intent": "modify", "messages": []}, None) \
        == ["   [PY Agent] Reading the current module..."]
    assert _emit(monkeypatch, bm, {"messages": []}, None) == ["   [PY Agent] Generating PY code..."]
    assert _emit(monkeypatch, bm, _after("extract_py_component", "No PY code found"), None) == []
    assert _emit(monkeypatch, bm, _after("run_ruff", "[Lint attempt 1/3]"), None) \
        == ["   [PY Agent] Revising after linter feedback..."]
    req = SimpleNamespace(tool_call={"name": "run_ruff", "id": "c1"})
    assert _emit(monkeypatch, parts.tool_progress.wrap_tool_call, req, lambda r: None) \
        == ["   [PY Agent] Linting PY code with Ruff..."]
    names = {m.name for m in (parts.agent_progress, parts.before_model_progress,
                              parts.tool_progress, parts.fs_guard)}
    assert names == {"py_agent_progress", "py_before_model_progress",
                     "py_tool_progress", "py_fs_guard"}
    refused = parts.fs_guard.wrap_tool_call(
        SimpleNamespace(tool_call={"name": "grep", "id": "g1"}), lambda r: "ran")
    assert "'grep' tool is disabled" in refused.content and "your module is in py_code" in refused.content
    assert parts.fs_guard.wrap_tool_call(
        SimpleNamespace(tool_call={"name": "read_file", "id": "r1"}), lambda r: "ran") == "ran"


def test_js_agent_parts_come_from_the_engine():
    src = (REPO_ROOT / "webforge" / "js_agent.py").read_text(encoding="utf-8")
    defined = {n.name for n in ast.walk(ast.parse(src))
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    hand_written = defined & {"save_js_file", "js_agent_progress", "js_tool_progress",
                              "js_before_model_progress", "js_fs_guard"}
    assert not hand_written, f"js_agent.py still hand-writes {sorted(hand_written)}"
    assert js_mod.JS.key == "js"
    held = js_mod.js_agent.nodes["tools"].bound.tools_by_name
    assert held["save_js_file"] is js_mod.save_js_file
    assert js_mod.js_fs_guard.name == "js_fs_guard"


def test_build_dev_agent_assembles_in_the_fixed_order(py, monkeypatch):
    _, parts, _ = py
    seen = {}
    monkeypatch.setattr(engine, "create_agent", lambda **kw: seen.update(kw) or "agent")
    backend = engine.new_preview_backend()
    agent = engine.build_dev_agent(parts, model="m", tools=["store", "lint"],
                                   prompt_selector="prompt", state_schema=PyState,
                                   backend=backend)
    assert agent == "agent" and seen["model"] == "m" and seen["state_schema"] is PyState
    assert seen["tools"] == ["store", "lint", parts.save_tool]
    fs, *rest = seen["middleware"]
    assert type(fs).__name__ == "FilesystemMiddleware"
    assert rest == [parts.fs_guard, "prompt", parts.agent_progress,
                    parts.before_model_progress, parts.tool_progress]
    from webforge.config import PREVIEW_DIR
    assert pathlib.Path(backend.cwd).resolve() == PREVIEW_DIR.resolve()


def test_js_extract_none_matches_the_extract_tool():
    rt = _rt(js_code="const a = 1;\n", session_id="s1", intent="modify")
    said = _said(js_mod.extract_js_component.func(rt, component="no-such-thing"))
    assert said.startswith(js_mod.JS.extract_none), said[:80]


# Ticket 10: a language may name its extract tool and labels its own way, as
# HTML does (extract_component, "Linting HTML...", a second apply tool).

def test_a_language_can_word_its_tools_its_own_way(tmp_path, monkeypatch):
    backend = OverwritingFilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    lang = engine.DevLanguage(
        key="py", tag="PY", noun="module", linter="Ruff", lint_tool="run_ruff",
        extract_none=("Nothing matched", "out of range"),
        save_backend=lambda: backend,
        extract_tool="extract_thing", extract_label="Finding the thing...",
        lint_label="Checking PY...",
        extra_tool_labels=(("apply_all_py", "Applying every edit..."),))
    hash(lang)                    # frozen and hashable: nothing in it can change
    parts = engine.dev_parts(lang, PyState)
    wrap = parts.tool_progress.wrap_tool_call

    def label(tool):
        return _emit(monkeypatch, wrap, SimpleNamespace(tool_call={"name": tool, "id": "c"}),
                     lambda r: None)
    assert label("extract_thing") == ["   [PY Agent] Finding the thing..."]
    assert label("run_ruff") == ["   [PY Agent] Checking PY..."]
    assert label("apply_all_py") == ["   [PY Agent] Applying every edit..."]
    assert label("extract_py_component") == []
    assert label("store_py_code") == ["   [PY Agent] Storing PY code..."]
    bm = parts.before_model_progress.before_model
    for silent in ("Nothing matched for 'x'", "instance 3 out of range"):
        assert _emit(monkeypatch, bm, _after("extract_thing", silent), None) == []
    assert _emit(monkeypatch, bm, _after("extract_thing", "<div>...</div>"), None) \
        == ["   [PY Agent] Writing the modification diff..."]


def test_html_agent_parts_come_from_the_engine():
    import webforge.html_agent as html_mod
    src = (REPO_ROOT / "webforge" / "html_agent.py").read_text(encoding="utf-8")
    defined = {n.name for n in ast.walk(ast.parse(src))
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    hand_written = defined & {"save_html_file", "html_agent_progress", "html_tool_progress",
                              "html_before_model_progress", "html_fs_guard"}
    assert not hand_written, f"html_agent.py still hand-writes {sorted(hand_written)}"
    assert html_mod.HTML.key == "html" and html_mod.HTML.extract_name == "extract_component"
    held = html_mod.html_agent.nodes["tools"].bound.tools_by_name
    assert held["save_html_file"] is html_mod.save_html_file
    assert html_mod.html_fs_guard.name == "html_fs_guard"
    said = _said(html_mod.extract_component.func(
        _rt(html_code="<main id='m'></main>", session_id="s1", intent="modify"),
        component="#no-such-thing"))
    assert any(said.startswith(none) for none in html_mod.HTML.extract_silent), said[:80]


def test_html_lints_through_the_one_runner(monkeypatch):
    """html-validate lints a temp file in .lint_tmp/ like the other two
    linters; before ticket 10 it used the OS temp folder, which the lint
    skill forbids."""
    import subprocess
    import webforge.html_agent as html_mod
    from webforge.config import LINT_TMP_DIR
    seen = []

    def fake(command):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")
    monkeypatch.setattr(html_mod, "_run_lint_subprocess", fake)
    got = html_mod._lint_html_source("<p>x</p>", _rt())
    assert _said(got) == "No issues found." and got.update["lint_passed"] is True
    (command,) = seen
    path = pathlib.Path(command.rsplit('"', 2)[1])
    assert path.suffix == ".html" and path.parent.resolve() == LINT_TMP_DIR.resolve()
    assert not path.exists()
    assert _said(html_mod._lint_html_source("", _rt())) \
        == "html_code is empty in state. Call store_html_code first."

    report = ('[{"messages": [{"line": 3, "column": 5, "ruleId": "no-dup-id",'
              ' "message": "Duplicate ID \\"a\\""}]}]')
    monkeypatch.setattr(html_mod, "_run_lint_subprocess", lambda c: subprocess.CompletedProcess(
        c, 1, stdout=report, stderr=""))
    failed = html_mod._lint_html_source("<p>x</p>", _rt())
    assert failed.update["lint_passed"] is False and failed.update["lint_attempts"] == 1
    assert _said(failed).startswith(
        'Found 1 error(s):\n  Line 3, Col 5 [no-dup-id]: Duplicate ID "a"\n\n[Lint attempt 1/2]')
    monkeypatch.setattr(html_mod, "_run_lint_subprocess", lambda c: subprocess.CompletedProcess(
        c, 127, stdout="", stderr="sh: npx: not found"))
    missing = html_mod._lint_html_source("<p>x</p>", _rt())
    assert _said(missing).startswith("html-validate could not be executed because `npx`")
    assert "lint_attempts" not in missing.update, "an infrastructure fault burned an attempt"


# Ticket 09: the CSS agent is built the same way.

def test_css_agent_parts_come_from_the_engine():
    src = (REPO_ROOT / "webforge" / "css_agent.py").read_text(encoding="utf-8")
    defined = {n.name for n in ast.walk(ast.parse(src))
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    hand_written = defined & {"save_css_file", "css_agent_progress", "css_tool_progress",
                              "css_before_model_progress", "css_fs_guard"}
    assert not hand_written, f"css_agent.py still hand-writes {sorted(hand_written)}"
    assert css_mod.CSS.key == "css"
    held = css_mod.css_agent.nodes["tools"].bound.tools_by_name
    assert held["save_css_file"] is css_mod.save_css_file
    assert css_mod.css_fs_guard.name == "css_fs_guard"


def test_css_extract_none_matches_the_extract_tool():
    rt = _rt(css_code=".a { color: red; }\n", session_id="s1", intent="modify")
    said = _said(css_mod.extract_css_component.func(rt, component="no-such-thing"))
    assert said.startswith(css_mod.CSS.extract_none), said[:80]


_LOOP_CORE = {"_batch_apply_text", "_batch_status_table", "_clean_batch", "_conflict_groups",
              "_join_components", "_merged_note", "_overlapping_pair", "_lint_refused",
              "_lint_failure", "_patch_failure", "_run_lint_subprocess"}


def test_the_loop_core_lives_in_the_engine():
    import webforge.html_agent as html_mod
    src = (REPO_ROOT / "webforge" / "html_agent.py").read_text(encoding="utf-8")
    defined = {n.name for n in ast.walk(ast.parse(src))
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not defined & _LOOP_CORE, f"html_agent.py still defines {sorted(defined & _LOOP_CORE)}"
    for name in _LOOP_CORE:
        fn = getattr(engine, name)
        assert fn.__module__ == "webforge.dev_agent", name
        for mod in (html_mod, js_mod, css_mod):
            assert getattr(mod, name) is fn, (name, mod.__name__)


def test_one_lint_runner_guards_and_cleans_up(py):
    lang, _, _ = py
    seen = {}

    def check(tmp_path, runtime):
        path = pathlib.Path(tmp_path)
        seen.update(path=path, text=path.read_text(encoding="utf-8"))
        return "verdict"

    assert engine.lint_source(lang, "x = 1", _rt(), check) == "verdict"
    from webforge.config import LINT_TMP_DIR
    assert seen["text"] == "x = 1" and seen["path"].suffix == ".py"
    assert seen["path"].parent.resolve() == LINT_TMP_DIR.resolve()
    assert not seen["path"].exists(), "the temp file outlived the lint"

    empty = engine.lint_source(lang, "", _rt(), check)
    assert empty.update["lint_passed"] is False
    assert _said(empty) == "py_code is empty in state. Call store_py_code first."
    refused = engine.lint_source(lang, "x = 1", _rt(lint_escalated=True), check)
    assert _said(refused).startswith("[LINT CAP REACHED] Linter call REFUSED")

    def boom(tmp_path, runtime):
        seen["boom"] = pathlib.Path(tmp_path)
        raise RuntimeError("linter crashed")
    with pytest.raises(RuntimeError):
        engine.lint_source(lang, "x = 1", _rt(), boom)
    assert not seen["boom"].exists()


def test_no_later_module_shadows_an_engine_name():
    """The agents call the engine by bare name through the star imports, so a
    later module defining the same name silently swaps the engine out (ticket
    09 met it: html_agent's tool `extract_component` replaced an engine
    function of that name inside js_agent)."""
    import webforge.html_agent as html_mod
    src = (REPO_ROOT / "webforge" / "dev_agent.py").read_text(encoding="utf-8")
    names = [n.name for n in ast.parse(src).body
             if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    shadowed = [(name, mod.__name__) for name in names
                for mod in (html_mod, js_mod, css_mod)
                if getattr(mod, name, None) is not getattr(engine, name)]
    assert not shadowed, f"engine names replaced by a later module: {shadowed}"


# DA-9: a PY loop whose "blocks" are the lines naming a component.

def _py_spans(code, name):
    out, pos = [], 0
    for line in code.splitlines(keepends=True):
        if name in line:
            out.append((pos, pos + len(line.rstrip("\n"))))
        pos += len(line)
    return out


@pytest.fixture
def py_loop(py):
    lang, _, _ = py
    return engine.DevLoop(
        lang=lang, spec_field="py_spec",
        aliases=lambda name, spec: [name, *(spec or {}).get(name, [])],
        spans=_py_spans,
        extract_miss=lambda code, name, spec: f"No PY code found for '{name}'.",
        batch_miss=lambda code, wanted: f"No PY code found for any of {wanted}.",
        skipped_phrase="No code found",
        apply_miss=lambda code, name: f"No PY block found for '{name}'.",
        lint=_py_lint)


def _py_lint(code, runtime):
    """Passes unless the code holds 'bad'."""
    if "bad" in code:
        return engine._lint_failure(runtime, "Found 1 error(s):\n  Line 1 [no-bad]: bad")
    return engine.Command(update={"lint_passed": True, "messages": [
        engine.ToolMessage(content="No issues found.", tool_call_id=runtime.tool_call_id)]})


_PY = "alpha = 1\nbeta = 2\nalpha_beta = 3\n"


def test_extract_core_resolves_aliases_and_resets_the_budget(py_loop):
    rt = _rt(py_code=_PY, py_spec={"first": ["alpha"]}, lint_attempts=2, lint_escalated=True)
    assert engine.loop_resolve(py_loop, _PY, "first", rt.state["py_spec"]) == (
        "alpha", [(0, 9), (19, 33)])
    got = engine.loop_extract(py_loop, rt, component="first")
    assert got.update["lint_attempts"] == 0 and got.update["lint_escalated"] is False
    assert _said(got) == engine._join_blocks(["alpha = 1", "alpha_beta = 3"])
    assert _said(engine.loop_extract(py_loop, rt, component="gamma")) \
        == "No PY code found for 'gamma'."
    assert _said(engine.loop_extract(py_loop, _rt(py_code=""), component="alpha")) \
        == "py_code is empty. Cannot extract component."
    assert _said(engine.loop_extract(py_loop, _rt(py_code=_PY))) \
        == "target_component not set in state."


def test_extract_core_batches_merges_shared_blocks_and_names_the_rest(py_loop):
    rt = _rt(py_code=_PY)
    got = _said(engine.loop_extract(py_loop, rt, components=["beta", "alpha", "gamma"]))
    # beta and alpha share the line 'alpha_beta = 3', so they are merged under beta.
    assert got.startswith(engine._join_blocks(["beta = 2", "alpha_beta = 3"]))
    assert "'alpha' resolves" not in got and "live in the block shown for 'beta'" in got
    assert "No code found, so not included (treat as stale names and skip them): gamma." in got
    assert "in a single apply_and_lint_py call" in got
    upgraded = _said(engine.loop_extract(
        py_loop, _rt(py_code=_PY, target_components=["alpha", "beta"])))
    assert "You asked for ONE component" in upgraded
    assert _said(engine.loop_extract(py_loop, rt, components=["x", "y"])) \
        == "No PY code found for any of ['x', 'y']."


# DA-11: one apply-and-lint core.

_ALPHA_DIFF = "@@ -2,1 +2,1 @@\n-alpha = 1\n+alpha = 10\n"


def test_apply_core_applies_lints_and_hands_back_the_block(py_loop):
    ok = engine.loop_apply_diff(py_loop, _PY, "alpha", _ALPHA_DIFF, None)
    assert ok == {"status": "ok", "new_py_code": "alpha = 10\nbeta = 2\nalpha_beta = 3\n",
                  "n_blocks": 2}
    assert engine.loop_apply_diff(py_loop, _PY, "gamma", _ALPHA_DIFF, None) == {"status": "noblock"}
    assert engine.loop_apply_diff(py_loop, "", "alpha", _ALPHA_DIFF, None) == {"status": "empty"}

    rt = _rt(py_code=_PY, target_component="alpha", patch_attempts=1)
    got = engine.loop_apply_and_lint(py_loop, rt, _ALPHA_DIFF)
    assert got.update["py_code"] == ok["new_py_code"] and got.update["patch_attempts"] == 0
    assert _said(got) == "Diff applied. 2 PY blocks for 'alpha' updated.\nNo issues found."

    lint_bad = engine.loop_apply_and_lint(
        py_loop, _rt(py_code=_PY), "@@ -1,1 +1,1 @@\n-beta = 2\n+beta = bad\n", "beta")
    assert "[Lint attempt 1/2]" in _said(lint_bad)
    assert _said(lint_bad).endswith("do NOT re-extract):\n\n"
                                    + engine._join_blocks(["beta = bad", "alpha_beta = 3"]))

    stale = engine.loop_apply_and_lint(py_loop, _rt(py_code=_PY), "@@ -1 +1 @@\n-zzz\n+y\n",
                                       "beta")
    assert _said(stale).startswith("Patch failed:") and stale.update["patch_attempts"] == 1
    assert "py_code" not in stale.update
    assert _said(engine.loop_apply_and_lint(py_loop, _rt(py_code=_PY), "@@ -1 +1 @@\n-a\n+b\n",
                                            "gamma")) == "No PY block found for 'gamma'."
    assert _said(engine.loop_apply_and_lint(py_loop, _rt(py_code=_PY), "  ")).startswith(
        "No diff supplied: diffs is empty and diff_output is blank.")


def test_apply_core_batches_through_one_lint(py_loop):
    got = engine.loop_apply_and_lint(py_loop, _rt(py_code=_PY), diffs=[
        {"component": "alpha", "diff_output": _ALPHA_DIFF},
        {"component": "gamma", "diff_output": _ALPHA_DIFF}])
    assert got.update["py_code"] == "alpha = 10\nbeta = 2\nalpha_beta = 3\n"
    assert _said(got).startswith("Applied 1 of 2 diff(s) in one call.\n  OK      alpha\n"
                                 "  SKIPPED gamma -- no PY block matched")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
