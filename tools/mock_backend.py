"""Zero-credit stand-in for ``webforge.entry`` so the live UI path can be exercised.

    python -m streamlit run tools/mock_ui.py --server.port 8599

``install()`` puts a fake ``webforge.entry`` module into ``sys.modules``
before the UI imports it. ``bridge`` then loads ``webforge.entry.graph``
exactly as it does in production and never knows the difference. (Before
ticket 15 deleted the ``fyp.py`` shim, the fake was a ``fyp`` module.)
Everything from ``bridge`` up (``StreamSession``, the SqliteSaver thread list, delete, switch, heal,
``stream_lit.py``) is the real code. Only the agents are fake.

What the fake graph is
    A real ``create_agent`` graph with a real SqliteSaver checkpointer. Its
    model is a scripted chat model that streams tokens like ChatOpenAI does,
    and its tools carry the production tool names, emit the production
    progress strings through ``get_stream_writer`` and return the production
    ToolMessage wording. ``call_secondary_orchestrator`` writes a real page
    to ``static/preview/preview_<sid>.{html,css,js}``.

How the script picks a path, per user turn
    modify marker present            -> modify the page on disk
    short message, no shop words     -> capabilities reply, no tools
    first brief in the thread        -> ask_user (one clarifying question)
    anything else                    -> full generate pipeline

Not a test of agent quality. It proves the plumbing between the agents and
the screen: progress lines, streamed narration, the question box, the
preview files, the modify marker and thread persistence.

WEBFORGE_MOCK_SPEED scales every delay (default 1.0, about 25 s per build;
0 runs instantly). WEBFORGE_MOCK_DB moves the thread database.

Three opt-in flags make the mock behave like the real backend in ways the
default flow does not (all off by default, so ui_smoke and the UI baseline see
the same flow as before):
    WEBFORGE_MOCK_LOAD_S=<s>        importing ``webforge.entry`` takes <s> seconds,
                                    as the real one does (26 s measured 2026-11-10)
                                    while the UI's warm-up thread holds the import
    WEBFORGE_MOCK_STAGED_FILES=1    a generate writes the HTML when the HTML agent
                                    saves it and the CSS/JS when those agents do,
                                    not all three at the end
    WEBFORGE_MOCK_CORRECTION=1      a generate runs one correction round after the
                                    first Test Execution, with the production lines
"""


import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
import time
import types
import uuid
from typing import Any, Dict, Iterator, List, Optional

# The modify marker the real panel writes and the real orchestrator reads.
from webforge import contract

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREVIEW_DIR = ROOT / "static" / "preview"
DB_PATH = pathlib.Path(os.environ.get("WEBFORGE_MOCK_DB") or ROOT / "logs" / "mock_threads.db")
SEED_SESSION = "demo-coffee-before"

_SHOP_WORDS = re.compile(
    r"\b(build|store|shop|storefront|page|sell|selling|site|brand)\b", re.I)


def _speed() -> float:
    try:
        return max(0.0, float(os.environ.get("WEBFORGE_MOCK_SPEED", "1.0")))
    except ValueError:
        return 1.0


def _pause(seconds: float) -> None:
    s = seconds * _speed()
    if s > 0:
        time.sleep(s)


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip() not in ("", "0")


def _load_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("WEBFORGE_MOCK_LOAD_S", "0")))
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Scripted model
# ---------------------------------------------------------------------------

def _build_model_cls():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, AIMessageChunk
    from langchain_core.outputs import (ChatGeneration, ChatGenerationChunk,
                                        ChatResult)

    class MockOrchestratorModel(BaseChatModel):
        """Decides the next orchestrator turn from the thread's own messages."""

        @property
        def _llm_type(self) -> str:
            return "webforge-mock"

        def bind_tools(self, tools, **kwargs):
            return self

        # -- the script -----------------------------------------------------
        def _next(self, messages) -> AIMessage:
            last_h = max(i for i, m in enumerate(messages) if m.type == "human")
            human = str(messages[last_h].content)
            done = [tc["name"]
                    for m in messages[last_h + 1:] if m.type == "ai"
                    for tc in (getattr(m, "tool_calls", None) or [])]
            asked_before = any(
                tc["name"] == "ask_user"
                for m in messages[:last_h] if m.type == "ai"
                for tc in (getattr(m, "tool_calls", None) or []))

            def call(text, name, args):
                return AIMessage(content=text, tool_calls=[{
                    "name": name, "args": args,
                    "id": f"call_{uuid.uuid4().hex[:12]}"}])

            if contract.split_modify_message(human) is not None:
                attrs = contract.modify_marker_fields(human)
                if "call_secondary_orchestrator" not in done:
                    return call(
                        "I'm entering the modify stage for the selected component.",
                        "call_secondary_orchestrator",
                        {"query": human, "intent": "modify",
                         "target_component": attrs.get("target_component", "").strip(),
                         "target_instance": attrs.get("target_instance", "1").strip()})
                return AIMessage(content=(
                    "The selected component has been updated and the page passed "
                    "verification. The new version is in Preview."))

            if not _SHOP_WORDS.search(human) and len(human) < 60 and not asked_before:
                return AIMessage(content=(
                    "Hi! I build one-page e-commerce storefronts in plain HTML, CSS "
                    "and JavaScript. Tell me what you sell, who it is for and the "
                    "look you want."))

            if not asked_before and not done:
                return call("", "ask_user", {
                    "question": "What should the build prioritise?",
                    "options": [
                        {"value": "Confirmed, continue with the brief.",
                         "label": "Confirm and continue",
                         "help": "Use the brief exactly as written."},
                        {"value": "Confirmed, prioritise mobile shopping.",
                         "label": "Prioritise mobile",
                         "help": "Extra weight on the phone layout."},
                    ]})
            if done == ["ask_user"]:
                return AIMessage(content="")

            steps = [
                ("update_input", "I've recorded your brief.", {}),
                ("call_context_engineering_agent",
                 "I'm moving into context design to get a design schema.",
                 {"query": human}),
                ("call_system_design_planning_agent",
                 "I got a design schema back, and next I'm entering planning.",
                 {"query": human}),
                ("call_secondary_orchestrator",
                 "I got the planning outputs and I'm handing them to the build stage.",
                 {"query": human, "intent": "generate",
                  "target_component": "", "target_instance": "1"}),
            ]
            for name, text, args in steps:
                if name not in done:
                    return call(text, name, args)
            return AIMessage(content=(
                "The storefront is ready in Preview. Shoppers can browse the "
                "collection, filter products and use the cart. Select any element "
                "in Preview to change it."))

        # -- LangChain plumbing --------------------------------------------
        def _generate(self, messages, stop=None, run_manager=None, **kw):
            return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

        def _stream(self, messages, stop=None, run_manager=None, **kw
                    ) -> Iterator[ChatGenerationChunk]:
            msg = self._next(messages)
            text = msg.content or ""
            for i in range(0, len(text), 4):
                _pause(0.015)
                piece = text[i:i + 4]
                chunk = ChatGenerationChunk(message=AIMessageChunk(content=piece))
                if run_manager:
                    run_manager.on_llm_new_token(piece, chunk=chunk)
                yield chunk
            if msg.tool_calls:
                tc = msg.tool_calls[0]
                yield ChatGenerationChunk(message=AIMessageChunk(
                    content="", tool_call_chunks=[{
                        "name": tc["name"], "args": json.dumps(tc["args"]),
                        "id": tc["id"], "index": 0}]))
            elif not text:
                yield ChatGenerationChunk(message=AIMessageChunk(content=""))

    return MockOrchestratorModel


class _LabelLLM:
    """Stands in for ``webforge.entry._spec_model`` when bridge titles a new thread."""

    def invoke(self, prompt):
        msg = str(prompt).split("Message:", 1)[-1].strip()
        words = re.findall(r"[A-Za-z']+", msg)[:4]
        return types.SimpleNamespace(content=" ".join(words).title() or "New Chat")


# ---------------------------------------------------------------------------
# Tools with production names and wording
# ---------------------------------------------------------------------------

def _emit(lines, gap=0.5):
    from langgraph.config import get_stream_writer
    w = get_stream_writer()
    for line in lines:
        _pause(gap)
        w(line)


def _write_page(sid: str, src_sid: str, exts=("html", "css", "js")) -> List[str]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for ext in exts:
        src = PREVIEW_DIR / f"preview_{src_sid}.{ext}"
        dst = PREVIEW_DIR / f"preview_{sid}.{ext}"
        if src != dst:
            text = src.read_text(encoding="utf-8")
            # The page links its own css/js by name; point them at this session.
            dst.write_text(text.replace(f"preview_{src_sid}.", f"preview_{sid}."),
                           encoding="utf-8")
        out.append(dst.name)
    return out


def _apply_modify(sid: str, instruction: str) -> int:
    """Apply 'change "A" to "B"' to the page on disk. Returns replacements made."""
    m = re.search(r'["“](.+?)["”]\s*to\s*["“](.+?)["”]', instruction)
    if not m:
        return 0
    old, new = m.group(1), m.group(2)
    n = 0
    for ext in ("html", "js"):
        p = PREVIEW_DIR / f"preview_{sid}.{ext}"
        if p.exists():
            text = p.read_text(encoding="utf-8")
            n += text.count(old)
            p.write_text(text.replace(old, new), encoding="utf-8")
    return n


def _build_tools():

    from langchain.tools import ToolRuntime
    from langchain_core.messages import ToolMessage
    from langchain_core.tools import tool
    from langgraph.types import Command

    @tool
    def update_input(runtime: ToolRuntime) -> Command:
        """Record the user's request."""
        _emit(["[Orchestrator] Processing request...",
               "[Orchestrator] Recording request..."], 0.3)
        return Command(update={"pending_question": {}, "messages": [ToolMessage(
            "\t[Orchestrator] Recorded request.", tool_call_id=runtime.tool_call_id)]})

    @tool
    def ask_user(question: str, options: List[Dict[str, Any]],
                 runtime: ToolRuntime) -> Command:
        """Ask the user one clarifying question and stop."""
        _emit(["[Orchestrator] Processing request..."], 0.3)
        cleaned = [{"field": None, "value": o["value"], "label": o["label"],
                    "help": o.get("help", "")} for o in options]
        return Command(update={
            "pending_question": {"question": question, "options": cleaned,
                                 "allow_free_text": True},
            "clarifier_used": True,
            "messages": [ToolMessage(
                f"\t[Orchestrator] Asked the user one question with {len(cleaned)} "
                "options. Waiting for their answer. Say nothing further this turn.",
                tool_call_id=runtime.tool_call_id)]})

    @tool
    def call_context_engineering_agent(query: str) -> str:
        """Run the Context Engineering Agent."""
        _emit(["[Orchestrator] Invoking Context Agent...",
               "\t[Context Agent] Processing request...",
               "\t[Context Agent] Extracting intent signals...",
               "\t[Context Agent] Updating design requirements..."], 0.6)
        return ("\t[Orchestrator] Context Engineering Agent completed. "
                "Returned design_schema backed to orchestrator.")

    @tool
    def call_system_design_planning_agent(query: str) -> str:
        """Run the System Design and Planning pipeline."""
        _emit(["[Orchestrator] Invoking System Design & Planning Chain...",
               "\t[Design Pipeline] Processing request...",
               "\t[Design Pipeline] Generating layout specification...",
               "\t[Design Pipeline] Generating component specifications...",
               "\t[Design Pipeline] Generating interaction specifications...",
               "\t[Design Pipeline] Generating decoration specifications..."], 0.8)
        return ("\t[Orchestrator] System Design & Planning Chain completed. "
                "Returned planning outputs backed to orchestrator.")

    @tool
    def call_secondary_orchestrator(query: str, intent: str, target_component: str,
                                    target_instance: str,
                                    runtime: ToolRuntime) -> Command:
        """Run the Secondary Orchestrator build or modify."""
        sid = (runtime.state.get("session_id") or "").strip()
        if not sid:
            return Command(update={"messages": [ToolMessage(
                "[Orchestrator] REFUSED: no usable session_id in state.",
                tool_call_id=runtime.tool_call_id)]})
        if intent == "modify":
            _emit(["[Orchestrator] Invoking Secondary Orchestrator...",
                   "\t[Secondary Orchestrator] Processing request...",
                   "\t[Secondary Orchestrator] Calling HTML Agent...",
                   "\t   [HTML Agent] Extracting target component...",
                   "\t   [HTML Agent] Applying diff and linting...",
                   "\t   [HTML Agent] Saving HTML to filesystem...",
                   "\t[Secondary Orchestrator] Calling Test Execution Pipeline...",
                   "\t   [Test Execution Pipeline] Running Playwright test suite...",
                   "\t[Secondary Orchestrator] Test Execution Pipeline completed."], 0.5)
            if not (PREVIEW_DIR / f"preview_{sid}.html").exists():
                _write_page(sid, SEED_SESSION)
            n = _apply_modify(sid, query)
            files = [f"preview_{sid}.{e}" for e in ("html", "css", "js")]
            note = f" ({n} text replacement(s))"
        else:
            html_part = [
                "[Orchestrator] Invoking Secondary Orchestrator...",
                "\t[Secondary Orchestrator] Processing request...",
                "\t[Secondary Orchestrator] Calling HTML Agent...",
                "\t   [HTML Agent] Processing request...",
                "\t   [HTML Agent] Generating HTML code...",
                "\t   [HTML Agent] Linting HTML...",
                "\t   [HTML Agent] Saving HTML to filesystem..."]
            build_part = [
                "\t[Secondary Orchestrator] Calling CSS Agent...",
                "\t[Secondary Orchestrator] Calling JS Agent...",
                "\t[Secondary Orchestrator] Calling Test Generation Agent...",
                "\t   [CSS Agent] Generating CSS code...",
                "\t   [JS Agent] Generating JS code...",
                "\t   [CSS Agent] Linting CSS code with Stylelint...",
                "\t   [JS Agent] Linting JS code with ESLint...",
                "\t   [CSS Agent] Saving CSS to filesystem...",
                "\t   [JS Agent] Saving JS to filesystem...",
                "\t[Secondary Orchestrator] Test Gen Agent completed."]
            test_part = [
                "\t[Secondary Orchestrator] Calling Test Execution Pipeline...",
                "\t   [Test Execution Pipeline] Running Playwright test suite...",
                "\t[Secondary Orchestrator] Test Execution Pipeline completed."]
            if _flag("WEBFORGE_MOCK_STAGED_FILES"):
                _emit(html_part, 0.7)
                _write_page(sid, SEED_SESSION, ("html",))
                _emit(build_part, 0.7)
                _write_page(sid, SEED_SESSION, ("css", "js"))
                _emit(test_part, 0.7)
            else:
                _emit(html_part + build_part + test_part, 0.7)
            if _flag("WEBFORGE_MOCK_CORRECTION"):
                # The lines production printed in the correction round of the
                # 2026-11-10 PO-08 run (session 4fb17fbe).
                _emit(["\t[Secondary Orchestrator] Calling HTML Agent...",
                       "\t   [HTML Agent] Processing request...",
                       "\t   [HTML Agent] Reading the current page...",
                       "\t   [HTML Agent] Applying diff and linting...",
                       "\t   [HTML Agent] Saving HTML to filesystem...",
                       "\t[Secondary Orchestrator] Calling CSS Agent...",
                       "\t   [CSS Agent] Processing request...",
                       "\t   [CSS Agent] Reading the current stylesheet...",
                       "\t   [CSS Agent] Saving CSS to filesystem...",
                       ] + test_part, 0.7)
            files = _write_page(sid, SEED_SESSION)
            note = ""
        return Command(update={"pending_question": {}, "messages": [ToolMessage(
            "[Orchestrator] Secondary Orchestrator completed. Files: "
            + ", ".join(files) + "." + note, tool_call_id=runtime.tool_call_id)]})

    return [update_input, ask_user, call_context_engineering_agent,
            call_system_design_planning_agent, call_secondary_orchestrator]


# ---------------------------------------------------------------------------
# Graph + fake module
# ---------------------------------------------------------------------------

def build_graph(db_path: Optional[pathlib.Path] = None):
    db_path = db_path or DB_PATH
    from langchain.agents import AgentState, create_agent
    from langgraph.checkpoint.sqlite import SqliteSaver
    from typing_extensions import NotRequired

    class MockOrchestratorState(AgentState):
        session_id: NotRequired[str]
        tone: NotRequired[str]
        pending_question: NotRequired[Dict[str, Any]]
        clarifier_used: NotRequired[bool]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return create_agent(
        model=_build_model_cls()(),
        tools=_build_tools(),
        state_schema=MockOrchestratorState,
        checkpointer=SqliteSaver(conn),
    )


ENTRY = "webforge.entry"   # the module bridge loads the graph from


def _fill(mod: types.ModuleType) -> None:
    mod.WEBFORGE_MOCK = True
    mod.graph = build_graph()
    mod._spec_model = _LabelLLM()


class _SlowEntryFinder:
    """Makes ``import webforge.entry`` take WEBFORGE_MOCK_LOAD_S seconds.

    A real import, through ``sys.meta_path``, so Python's per-module import
    lock behaves as it does for the real backend: while the UI's warm-up
    thread is inside this import, any other thread that imports
    ``webforge.entry`` waits for it to finish."""

    def __init__(self, seconds: float):
        self.seconds = seconds

    def find_spec(self, fullname, path=None, target=None):
        if fullname != ENTRY:
            return None
        import importlib.util
        return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return None

    def exec_module(self, mod):
        mod.WEBFORGE_MOCK = True        # a rerun mid-import must not reinstall
        time.sleep(self.seconds)
        _fill(mod)


def install() -> Optional[types.ModuleType]:
    """Register the fake ``webforge.entry`` module. Idempotent across Streamlit
    reruns. The fake is only in ``sys.modules``; the real ``webforge`` package
    stays the parent, so ``webforge.contract`` and ``webforge.config`` are real.

    With WEBFORGE_MOCK_LOAD_S set, nothing is imported here: a finder is put on
    ``sys.meta_path`` and the first ``import webforge.entry`` pays the delay."""
    existing = sys.modules.get(ENTRY)
    if getattr(existing, "WEBFORGE_MOCK", False):
        return existing
    if existing is not None or "webforge.primary_orchestrator" in sys.modules:
        raise RuntimeError("the real backend is already imported; mock install is too late")
    load_s = _load_seconds()
    if load_s:
        if not any(isinstance(f, _SlowEntryFinder) for f in sys.meta_path):
            sys.meta_path.insert(0, _SlowEntryFinder(load_s))
        return None
    mod = types.ModuleType(ENTRY)
    _fill(mod)
    sys.modules[ENTRY] = mod
    return mod
