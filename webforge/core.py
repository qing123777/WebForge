"""core: imports, LangSmith tracing helpers, the streaming test helper, ToDoListMiddleware.

Lines 1-517 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

# Every filesystem path (preview folder, lint scratch folder, checkpoint DB)
# comes from webforge.config, derived from the repo root (refactor ticket 02).
from webforge import config as _wf_config


# ==========================================================================
# (no section)
# ==========================================================================
from dotenv import load_dotenv
load_dotenv()


# ==========================================================================
# Reasoning effort, one table for every model that reasons
# ==========================================================================
# How hard each model thinks before it answers. Every ChatOpenAI that takes a
# `reasoning` setting reads its effort here through _reasoning_for, and
# tests/test_reasoning_effort.py fails if a module writes one of its own.
# The planning generators (_spec_model, _intent_model) take no reasoning
# setting and are not listed.
#
# Where the tokens go, measured on PO-08 4fb17fbe (2026-11-10), 34,813
# reasoning tokens in all: css 16,932 (12,074 of them in ONE call), js 6,553,
# html 5,127, test_gen 5,073, the two orchestrators about 800 together,
# planning 0. So the orchestrators have nothing worth saving; the writing
# agents are where an effort change shows.
#
# html, css and test_gen went from medium to low on 2026-11-10, each measured
# on its own live suite, medium run then low run, every case passing in both:
#
#                     seconds        reasoning tokens     cost
#   css  (6 cases)    426 -> 207     11,196 -> 1,230      $0.583 -> $0.384
#   html (6 cases)    357 -> 130      5,795 ->   486      $0.486 -> $0.265
#   tg   (3 cases)    179 -> 107      6,534 -> 1,507      $0.192 -> $0.152
#
# One run each. Those suites use small specs and check contracts, not looks
# (HTML's drop is partly fewer refused saves, which one run cannot tell from
# chance), so the pass
# rate of a full PO-08 is the real judge (speed-cost ticket 08). If it drops,
# raise the agent back here. js stays at medium: it is the one agent writing
# logic, and its own note in js_agent.py says to judge it on PO-08 pass rate.
REASONING_EFFORT = {
    "context":                "medium",
    "html":                   "low",
    "css":                    "low",
    "js":                     "medium",
    "test_gen":               "low",
    "secondary_orchestrator": "medium",
    "primary_orchestrator":   "medium",
}
_REASONING_EFFORTS = ("low", "medium", "high")


def _reasoning_for(name: str) -> dict:
    """The `reasoning` setting for one model, by its REASONING_EFFORT name.

    WEBFORGE_REASONING_<NAME> (e.g. WEBFORGE_REASONING_CSS=low) overrides the
    table for one process, so a paid suite can measure another effort without
    a code change. A value that is not an effort raises: a typo must not run
    a paid suite at the default and report it as the experiment."""
    effort = REASONING_EFFORT[name]
    var = "WEBFORGE_REASONING_" + name.upper()
    override = (os.environ.get(var) or "").strip().lower()
    if override:
        if override not in _REASONING_EFFORTS:
            raise ValueError(f"{var}={override!r} is not one of {_REASONING_EFFORTS}")
        effort = override
    return {"effort": effort, "summary": "auto"}


# ==========================================================================
# Import libraries
# ==========================================================================
from langchain.agents import create_agent
from langchain.tools import tool,ToolRuntime
from langchain.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.middleware import before_model, AgentState, HumanInTheLoopMiddleware, wrap_tool_call, before_agent
from deepagents.middleware import FilesystemMiddleware
from deepagents.backends import CompositeBackend, FilesystemBackend, StoreBackend 
from langgraph.store.memory import InMemoryStore
from langgraph.runtime import Runtime
import json
from typing import Any, Optional, Literal, List, Dict, Annotated
from tavily import TavilyClient
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel, Field, model_validator, field_validator
from langgraph.types import Command, interrupt, Overwrite
from pathlib import Path
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableBranch
from langchain_openai import ChatOpenAI
from operator import add
import sys
from langchain_core.messages import AIMessageChunk
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableLambda
import io
import re
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
import os
import subprocess
import tempfile


# ==========================================================================
# Import libraries
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# LangSmith tracing helpers
#
# Why the environment gets normalised at all: LangChain's tracer reads
# LANGCHAIN_* variables, while most tutorials and .env files set LANGSMITH_*.
# A run traced under one name and read under the other simply does not appear
# in LangSmith, with no error to explain it.
# ═══════════════════════════════════════════════════════════════════════════
import os
import uuid
from typing import Any, Dict, List, Optional


def _bootstrap_langsmith_env() -> None:
    """Best-effort env var normalization for LangSmith tracing.

    Some setups (and older tutorials) use LANGSMITH_* vars while LangChain's
    tracer expects LANGCHAIN_* vars. This function maps between them without
    leaking secrets or overriding user-provided values.
    """

    # API key
    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", api_key)
        os.environ.setdefault("LANGCHAIN_API_KEY", api_key)

    # Tracing enabled flag
    tracing_flag = os.getenv("LANGSMITH_TRACING")
    if tracing_flag:
        os.environ.setdefault("LANGSMITH_TRACING", tracing_flag)
        # LangChain expects "LANGCHAIN_TRACING_V2=true"
        if tracing_flag.strip().lower() in {"1", "true", "yes", "on"}:
            os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")

    # Endpoint
    endpoint = os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT")
    if endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", endpoint)
        os.environ.setdefault("LANGCHAIN_ENDPOINT", endpoint)

    # Project
    project = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT")
    if project:
        os.environ.setdefault("LANGCHAIN_PROJECT", project)
        os.environ.setdefault("LANGSMITH_PROJECT", project)


def enable_langsmith(*, project: Optional[str] = None) -> bool:
    """Enable LangSmith tracing via env vars.

    This is a no-op unless either `LANGSMITH_API_KEY` or `LANGCHAIN_API_KEY` is set.
    """

    _bootstrap_langsmith_env()

    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        return False

    # If project not explicitly provided, fall back to either env var.
    if not project:
        project = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT")

    os.environ.setdefault("LANGSMITH_API_KEY", api_key)
    os.environ.setdefault("LANGCHAIN_API_KEY", api_key)
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")

    endpoint = os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT")
    os.environ.setdefault("LANGSMITH_ENDPOINT", endpoint or "https://api.smith.langchain.com")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", endpoint or "https://api.smith.langchain.com")
    if project:
        # LangChain uses LANGCHAIN_PROJECT; many people set LANGSMITH_PROJECT.
        os.environ.setdefault("LANGCHAIN_PROJECT", project)
        os.environ.setdefault("LANGSMITH_PROJECT", project)
    return True


# Bootstrap tracing if possible (keeps behavior deterministic across notebooks/Studio).
_bootstrap_langsmith_env()
enable_langsmith()


def langsmith_config(
    *,
    run_name: Optional[str] = None,
    project: Optional[str] = None,
    thread_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a runnable config dict you can pass to `.invoke(..., config=...)`."""

    enable_langsmith(project=project)
    cfg: Dict[str, Any] = {}
    if run_name:
        cfg["run_name"] = run_name
    if tags:
        cfg["tags"] = tags
    if metadata:
        cfg["metadata"] = metadata
    # Many LangGraph graphs require a thread_id when a checkpointer is present.
    # Auto-generate one so ad-hoc scripts/notebooks don't fail.
    if not thread_id:
        thread_id = f"run_{uuid.uuid4().hex[:12]}"
    cfg.setdefault("configurable", {})["thread_id"] = thread_id
    return cfg


# ==========================================================================
# Streaming tool
# ==========================================================================
import uuid
import sys
import json
from typing import Any, Optional
from langchain_core.messages import AIMessageChunk


# Toggle for streaming output:
# - debug=False: show only custom progress events + final assistant text
# - debug=True: also print raw update payloads (tool/framework events)
debug = False


def _infer_input_query_from_payload(payload: dict, fallback: str = "") -> str:
    if isinstance(payload.get("input_query"), str) and payload.get("input_query"):
        return payload.get("input_query")

    msgs = payload.get("messages") or []
    if isinstance(msgs, list):
        try:
            for m in reversed(list(msgs)):
                if isinstance(m, dict) and m.get("role") in ("user", "human") and isinstance(m.get("content"), str):
                    content = (m.get("content") or "").strip()
                    if content:
                        return content
                if hasattr(m, "type") and getattr(m, "type") in ("human", "user") and hasattr(m, "content"):
                    content = str(getattr(m, "content") or "").strip()
                    if content:
                        return content
        except Exception:
            pass

    return (fallback or "").strip()


def _flat_namespace() -> dict:
    """The whole system's namespace, as fyp.py's globals() was before the
    split (ticket 04): the last module re-exports every name."""
    import sys as _sys
    _last = _sys.modules.get("webforge.primary_orchestrator")
    return vars(_last) if _last is not None else globals()


def make_dummy_design_schema(input_query: str) -> dict:
    """Create a conservative DesignSchema-shaped dict.

    This is intentionally minimal: it only sets values that are explicitly
    indicated by keywords in the user prompt.
    """
    q = (input_query or "").lower()

    schema: dict[str, Any] = {
        "ui": {
            "type": None,
            "style": None,
            "density": None,
            "navigation": None,
        },
        "theme": {
            "name": None,
            "mode": None,
        },
        "constraints": {"tech_stack": ["html", "css", "javascript"]},
        "extra_requirements": [],
    }

    if "dark mode" in q or "dark-mode" in q or " dark " in f" {q} ":
        schema["theme"]["mode"] = "dark"
    elif "light mode" in q or "light-mode" in q:
        schema["theme"]["mode"] = "light"

    if "top nav" in q or "top navigation" in q or "navbar" in q:
        schema["ui"]["navigation"] = "top_nav"
    elif "side nav" in q or "side navigation" in q or "sidebar" in q:
        schema["ui"]["navigation"] = "side_nav"
    elif "hamburger" in q:
        schema["ui"]["navigation"] = "hamburger"

    if "compact" in q:
        schema["ui"]["density"] = "compact"
    elif "comfortable" in q:
        schema["ui"]["density"] = "comfortable"

    # style became a fixed list on 2026-08-15, so these map onto the allowed
    # values. "modern" used to be written straight through and would now be
    # refused by the schema.
    if "minimal" in q or "premium" in q or "luxury" in q or "modern" in q:
        schema["ui"]["style"] = "minimal_premium"
    elif "catalog" in q or "catalogue" in q:
        schema["ui"]["style"] = "catalog_heavy"
    elif "spec" in q or "comparison" in q or "review" in q:
        schema["ui"]["style"] = "information_heavy"
    elif "deal" in q or "sale" in q or "promo" in q or "discount" in q:
        schema["ui"]["style"] = "promotion_heavy"
    elif "photo" in q or "gallery" in q or "visual" in q:
        schema["ui"]["style"] = "visual_first"

    if "marketplace" in q or "many sellers" in q or "multi-vendor" in q:
        schema["ui"]["commerce_type"] = "marketplace"
    elif "subscription" in q or "subscribe" in q or "monthly box" in q:
        schema["ui"]["commerce_type"] = "subscription"
    elif "flash sale" in q or "countdown" in q or "limited time" in q:
        schema["ui"]["commerce_type"] = "flash_sale"
    elif "custom" in q or "configure" in q or "build your own" in q:
        schema["ui"]["commerce_type"] = "customisable_products"
    elif "download" in q or "ebook" in q or "course" in q or "software" in q:
        schema["ui"]["commerce_type"] = "digital_products"

    if "product listing" in q or "product list" in q or "listing page" in q:
        schema["ui"]["type"] = "product_listing"
    elif "landing page" in q:
        schema["ui"]["type"] = "landing_page"
    elif "checkout" in q:
        schema["ui"]["type"] = "checkout"
    elif "cart" in q and "product" not in q:
        schema["ui"]["type"] = "cart"

    try:
        if "DesignSchema" in _flat_namespace():
            schema = _flat_namespace()["DesignSchema"].model_validate(schema).model_dump()
    except Exception:
        pass

    return schema


def stream_agent_run(
    agent,
    *,
    query: Optional[str] = None,
    payload: Optional[dict] = None,
    design_schema: Optional[dict] = None,
    auto_add_design_schema: bool = True,
    config: Optional[dict] = None,
    stream_mode: Optional[list[str]] = None,
    version: str = "v2",
    header: Optional[str] = None,
    print_stream: bool = True,
    debug: bool = debug,
    print_updates: Optional[bool] = None,
    updates_max_chars: int = 4000,
) -> dict:
    """Stream an agent run.

    User-friendly mode (debug=False):
    - Prints custom events and final assistant text.

    Debug mode (debug=True):
    - Also prints raw updates payloads for tool/framework observability.

    Return contract (stable):
    - final, state, tool_feedback, custom_events, reasoning_summary
    """
    if payload is None:
        payload = {
            "messages": [
                {"role": "user", "content": (query or "")},
            ]
        }

    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    if query is not None and (not isinstance(payload.get("input_query"), str) or not payload.get("input_query")):
        payload["input_query"] = query
    if not isinstance(payload.get("input_query"), str) or not payload.get("input_query"):
        payload["input_query"] = _infer_input_query_from_payload(payload, fallback=(query or ""))

    if design_schema is not None:
        payload["design_schema"] = design_schema
    elif auto_add_design_schema:
        ds = payload.get("design_schema")
        if not isinstance(ds, dict) or not ds:
            payload["design_schema"] = make_dummy_design_schema(payload.get("input_query") or "")

    if stream_mode is None:
        stream_mode = ["updates", "messages", "custom"]

    if config is None:
        config = {"configurable": {"thread_id": f"run_{uuid.uuid4().hex[:8]}"}}

    if print_updates is None:
        print_updates = bool(debug)

    if header and print_stream:
        print(header)

    final_text_parts: list[str] = []
    tool_feedback: list[str] = []
    custom_events: list[Any] = []
    captured_state: dict[str, Any] = {}
    in_token_stream = False

    indent_level = 0
    indent_unit = "  "

    def _merge_state_update(update: Any) -> None:
        if not isinstance(update, dict):
            return
        for key, value in update.items():
            if key == "messages":
                continue
            # test_cases streams one CHUNK per store_test_cases call under chunked
            # generation. Mirror the graph's dedup-by-id reducer so the captured
            # snapshot is the UNION of all batches, not just the last one. (Other
            # fields, and agents that never chunk test_cases, are unaffected.)
            if key == "test_cases" and isinstance(value, list) and "_merge_test_cases" in _flat_namespace():
                captured_state["test_cases"] = _flat_namespace()["_merge_test_cases"](
                    captured_state.get("test_cases", []), value)
            else:
                captured_state[key] = value

    def _indent_text(text: str) -> str:
        prefix = indent_unit * indent_level
        lines = text.rstrip("\n").splitlines() or [""]
        return "\n".join(prefix + line for line in lines)

    for chunk in agent.stream(
        payload,
        stream_mode=stream_mode,
        version=version,
        config=config,
    ):
        if isinstance(chunk, tuple) and len(chunk) == 2:
            chunk_type, data = chunk
        else:
            chunk_type = chunk.get("type")
            data = chunk.get("data")

        if chunk_type == "updates" and isinstance(data, dict):
            for _step, update in data.items():
                _merge_state_update(update)

            if print_updates and print_stream:
                try:
                    rendered = json.dumps(data, default=str, ensure_ascii=False)
                except Exception:
                    rendered = str(data)
                if len(rendered) > updates_max_chars:
                    rendered = rendered[:updates_max_chars] + "…"
                if in_token_stream:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    in_token_stream = False
                print(rendered)

            try:
                tools_update = data.get("tools")
                if isinstance(tools_update, dict):
                    msgs = tools_update.get("messages") or []
                    if msgs:
                        last_msg = msgs[-1]
                        content = getattr(last_msg, "content", "")
                        if isinstance(content, str) and content.strip():
                            tool_feedback.append(content.strip())
            except Exception:
                pass

        elif chunk_type == "messages" and isinstance(data, (tuple, list)) and len(data) == 2:
            token, _metadata = data
            if not isinstance(token, AIMessageChunk):
                continue

            blocks = getattr(token, "content_blocks", []) or []
            emitted_any = False
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "text":
                    continue
                text = block.get("text", "") or ""
                if not text:
                    continue
                emitted_any = True
                final_text_parts.append(text)
                if print_stream:
                    sys.stdout.write(text)
                    sys.stdout.flush()
                    in_token_stream = True

            if not emitted_any:
                text = getattr(token, "content", "")
                if isinstance(text, str) and text:
                    final_text_parts.append(text)
                    if print_stream:
                        sys.stdout.write(text)
                        sys.stdout.flush()
                        in_token_stream = True

        elif chunk_type == "custom":
            custom_events.append(data)

            if isinstance(data, dict) and data.get("type") == "indent":
                try:
                    delta = int(data.get("delta") or 0)
                except Exception:
                    delta = 0
                indent_level = max(0, indent_level + delta)
                continue

            if print_stream:
                if in_token_stream:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    in_token_stream = False

                if isinstance(data, dict) and data.get("type") == "log":
                    text = str(data.get("text") or "")
                elif isinstance(data, str):
                    text = data
                else:
                    text = str(data)

                sys.stdout.write(_indent_text(text) + "\n")
                sys.stdout.flush()

    if print_stream and in_token_stream:
        sys.stdout.write("\n")
        sys.stdout.flush()

    final_text = "".join(final_text_parts).strip()

    return {
        "final": final_text,
        "state": captured_state,
        "tool_feedback": tool_feedback,
        "custom_events": custom_events,
        "reasoning_summary": "",
    }


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
