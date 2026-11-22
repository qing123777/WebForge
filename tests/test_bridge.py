"""Ticket 13: a narrow bridge, a ThreadStore, and a UI that imports no agent code.

    python -m pytest tests/test_bridge.py        (or python tests/test_bridge.py)

Offline, no model calls.

  BR-1  stream_lit.py imports no agent code: only the standard library,
        streamlit, bridge, ui_assets and the two stdlib-only webforge
        modules (config, contract); no `fyp`, and no private bridge name.
        Nor reaches it through importlib, __import__, `from bridge import`,
        getattr(bridge, ...) or a "fyp"/"webforge" string.
  BR-2  bridge.__all__ is exactly what the UI uses plus StreamSession and
        ThreadStore; importing bridge loads no agent code; warm_up and
        label_model load the backend only when called, and warm_up raises
        if it fails.
  BR-3  ThreadStore keeps the threads: labels newest first from each first
        user message, history without step narrations, delete, heal a
        dangling tool call, read the pending question, repair on SQLite
        (leaves the tail, or deletes a thread with no clean checkpoint),
        rewind a cancelled tail in memory.
"""
import ast
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI = ROOT / "stream_lit.py"

# What the UI may import at all, anywhere in the file.
_UI_MAY_IMPORT = {"bridge", "ui_assets", "streamlit", "streamlit.components.v1",
                  "webforge.config", "webforge.contract", "webforge"}


def _imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module == "webforge":
                for alias in node.names:
                    yield f"webforge.{alias.name}", node.lineno
            elif node.level == 0:
                yield node.module, node.lineno


# BR-1 ------------------------------------------------------------------------

def test_the_ui_imports_no_agent_code():
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    stdlib = set(sys.stdlib_module_names)
    bad = [(name, line) for name, line in _imports(tree)
           if name not in _UI_MAY_IMPORT and name.split(".")[0] not in stdlib
           and name != "__future__"]
    assert not bad, f"stream_lit.py imports agent code (or something new): {bad}"


def test_the_ui_uses_only_public_bridge_names():
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    private = sorted({(n.attr, n.lineno) for n in ast.walk(tree)
                      if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                      and n.value.id == "bridge" and n.attr.startswith("_")})
    assert not private, f"stream_lit.py reaches into bridge's private names: {private}"


def test_the_ui_has_no_back_door_to_agent_code():
    """The two checks above read static imports and ``bridge.<name>``. These
    are the other ways to reach the same code."""
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in ("importlib", "__import__"):
            bad.append((n.id, n.lineno))
        elif isinstance(n, ast.ImportFrom) and n.module in ("bridge", "importlib"):
            bad.append((f"from {n.module} import ...", n.lineno))
        elif isinstance(n, ast.Constant) and n.value in ("fyp", "webforge"):
            bad.append((repr(n.value), n.lineno))
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "getattr" and n.args
              and isinstance(n.args[0], ast.Name) and n.args[0].id == "bridge"):
            bad.append(("getattr(bridge, ...)", n.lineno))
    assert not bad, f"stream_lit.py reaches agent code another way: {bad}"


def _ui_bridge_names():
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    return {n.attr for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "bridge"}


# BR-2 ------------------------------------------------------------------------

def test_bridge_public_interface_is_what_the_ui_uses():
    """``bridge.__all__`` is the narrow interface: every name in it exists,
    and apart from the two classes behind it (``StreamSession``, which
    ``stream_message`` returns, and ``ThreadStore``) the UI uses each one."""
    import bridge
    missing = [name for name in bridge.__all__ if not hasattr(bridge, name)]
    assert not missing, f"bridge.__all__ names what bridge lacks: {missing}"
    behind = {"StreamSession", "ThreadStore"}
    assert _ui_bridge_names() == set(bridge.__all__) - behind

def test_importing_bridge_loads_no_agent_code():
    probe = ("import sys, bridge; "
             "print(sorted(m for m in sys.modules if m.startswith('langchain')"
             " or (m.startswith('webforge.') and m not in ('webforge.contract', 'webforge.config'))))")
    out = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True,
                         text=True, timeout=120)
    assert out.stdout.strip() == "[]", out.stdout + out.stderr


def test_warm_up_and_label_model_load_the_backend_lazily(monkeypatch):
    import types
    import bridge
    fake = types.ModuleType("webforge.entry")
    fake.graph, fake._spec_model = object(), object()
    monkeypatch.setitem(sys.modules, "webforge.entry", fake)
    assert bridge.warm_up() is None
    assert bridge.label_model() is fake._spec_model
    monkeypatch.setitem(sys.modules, "webforge.entry", None)   # backend fails to load
    with pytest.raises(ImportError):
        bridge.warm_up()


def test_the_mock_backend_fakes_what_bridge_loads(tmp_path):
    """tools/mock_ui.py's zero-credit harness: after mock_backend.install(),
    bridge gets the mock graph and label model, and no agent module loads.
    (Ticket 15: the fake moved from a `fyp` module to `webforge.entry`.)"""
    probe = (
        "import sys; sys.path.insert(0, 'tools'); import mock_backend, bridge\n"
        "mod = mock_backend.install()\n"
        "bridge.warm_up()\n"
        "ok = (bridge._get_graph() is mod.graph, bridge.label_model() is mod._spec_model,\n"
        "      mock_backend.install() is mod)\n"
        "agent = sorted(m for m in sys.modules if m.startswith('webforge.')\n"
        "               and m not in ('webforge.contract', 'webforge.config', 'webforge.entry'))\n"
        "print(ok, agent)\n")
    env = {**__import__("os").environ, "WEBFORGE_MOCK_DB": str(tmp_path / "mock.db")}
    out = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "(True, True, True) []", out.stdout + out.stderr[-3000:]


# BR-3 ------------------------------------------------------------------------

def _graph(saver):
    from langgraph.graph import END, START, MessagesState, StateGraph
    g = StateGraph(MessagesState)
    g.add_node("echo", lambda state: {})
    g.add_edge(START, "echo")
    g.add_edge("echo", END)
    return g.compile(checkpointer=saver)


def _cfg(tid):
    return {"configurable": {"thread_id": tid}}


@pytest.fixture
def sqlite_graph(tmp_path):
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    conn = sqlite3.connect(str(tmp_path / "threads.db"), check_same_thread=False)
    yield _graph(SqliteSaver(conn))
    conn.close()


def test_thread_store_lists_reads_and_deletes(sqlite_graph):
    import bridge
    from langchain_core.messages import AIMessage, HumanMessage
    g = sqlite_graph
    g.invoke({"messages": [HumanMessage(content="Build   me a coffee shop")]}, _cfg("t1"))
    g.update_state(_cfg("t1"), {"messages": [
        AIMessage(content="Recording your brief", tool_calls=[
            {"name": "x", "args": {}, "id": "c1"}]),
        AIMessage(content="Your page is ready.")]})
    g.invoke({"messages": [HumanMessage(content="x" * 50)]}, _cfg("t2"))
    store = bridge.ThreadStore(g)
    assert list(store.labels().items()) == [("t2", "x" * 40 + "…"),
                                           ("t1", "Build me a coffee shop")]
    assert store.history("t1") == [
        {"role": "user", "content": "Build   me a coffee shop"},
        {"role": "assistant", "content": "Your page is ready."}]
    assert store.history("never") == []
    store.delete("t1")
    assert list(store.labels()) == ["t2"]


def test_thread_store_heals_a_dangling_tool_call(sqlite_graph):
    import bridge
    from langchain_core.messages import AIMessage, HumanMessage
    g = sqlite_graph
    g.invoke({"messages": [HumanMessage(content="hi")]}, _cfg("t1"))
    g.update_state(_cfg("t1"), {"messages": [AIMessage(content="", tool_calls=[
        {"name": "call_secondary_orchestrator", "args": {}, "id": "c9"}])]})
    store = bridge.ThreadStore(g)
    assert store.heal("t1") == 1
    last = g.get_state(_cfg("t1")).values["messages"][-1]
    assert (last.type, last.tool_call_id, last.content) == (
        "tool", "c9", "Cancelled by the user before this step returned.")
    assert store.heal("t1") == 0


def test_thread_store_reads_the_pending_question():
    import bridge
    from typing import Annotated, Any
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.message import add_messages
    from typing_extensions import TypedDict

    class AskState(TypedDict, total=False):
        messages: Annotated[list, add_messages]
        pending_question: Any

    g = StateGraph(AskState)
    g.add_node("ask", lambda s: {"pending_question": {"question": "Which colour?"}})
    g.add_edge(START, "ask")
    g.add_edge("ask", END)
    g = g.compile(checkpointer=InMemorySaver())
    store = bridge.ThreadStore(g)
    assert store.pending_question("t1") == {}          # never run
    g.invoke({"messages": []}, _cfg("t1"))
    assert store.pending_question("t1") == {"question": "Which colour?"}
    g.update_state(_cfg("t1"), {"pending_question": "not a dict"})
    assert store.pending_question("t1") == {}


def test_thread_store_repair_on_sqlite(sqlite_graph):
    """Production's saver. With a clean checkpoint to go back to, repair
    cannot rewind (only an InMemorySaver exposes its storage), so the tail
    stays and heal answers it at the next turn. With none, it deletes the
    thread."""
    import bridge
    from langchain_core.messages import AIMessage, HumanMessage
    g = sqlite_graph
    dangling = lambda i: {"messages": [AIMessage(content="", tool_calls=[  # noqa: E731
        {"name": "x", "args": {}, "id": i}])]}
    g.invoke({"messages": [HumanMessage(content="hi")]}, _cfg("t1"))
    g.update_state(_cfg("t1"), dangling("c1"))
    g.update_state(_cfg("t2"), dangling("c2"))          # no clean checkpoint
    store = bridge.ThreadStore(g)
    assert store.repair("t1") is False
    assert [m.type for m in store.messages("t1")] == ["human", "ai"]
    assert store.repair("t2") is True
    assert store.messages("t2") == [] and list(store.labels()) == ["t1"]


def test_thread_store_rewinds_a_cancelled_tail_in_memory():
    import bridge
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    g = _graph(InMemorySaver())
    g.invoke({"messages": [HumanMessage(content="hi")]}, _cfg("t1"))
    g.update_state(_cfg("t1"), {"messages": [AIMessage(content="", tool_calls=[
        {"name": "x", "args": {}, "id": "c1"}])]})
    messages = bridge.ThreadStore(g).messages("t1")
    assert [m.type for m in messages] == ["human"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
