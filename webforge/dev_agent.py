"""dev_agent: the engine the developer agents share (tickets 08, 09 and 10).

The HTML, CSS and JS agents each run one loop: generate, lint, fix, save. Five
parts of that loop were written out three times, the same code with a few words
changed: the save tool, three progress hooks, and the filesystem guard. This
module writes them once. A language adapter, `DevLanguage`, carries the words
that differ, and `dev_parts` turns it into the five parts; `build_dev_agent`
puts them into the agent in the order every developer agent uses.

Fit today: all three agents. JS (ticket 08) and CSS (ticket 09) differ only
in the adapter's words. HTML (ticket 10) words its tools its own way: its
extract tool is `extract_component` (no language key), its lint label is
"Linting HTML...", and its second apply tool, `apply_and_lint_html_full`, has
a label of its own; DevLanguage's optional fields carry those.

The loop's core is here too. One lint runner for all three agents
(`lint_source`, tickets 09 and 10: the language passes its linter call and
output parser). For the text languages, CSS and JS (ticket 09): one extract (`loop_extract`, `loop_resolve`) and one
apply-and-lint (`loop_apply_diff`, `loop_apply_and_lint`, batches through
`_batch_apply_text`). A second adapter, `DevLoop`, carries what the loop
differs by: the spec field, the alias list, the block finder, the messages
and the lint. The caps, the batch helpers and `_run_lint_subprocess` moved
here from html_agent with it. The engine's function names start with `loop_`
where a plain name was free in a later module: html_agent's tool
`extract_component` once replaced an engine function of that name.

The text these parts produce is byte-identical to the hand-written copies they
replace: the save tool's docstring and messages reach the model, and the
progress labels reach the UI. The baseline (`baseline/compare.py`) and the
ported cells 222, 227 and 234 pin both.

No `from __future__ import annotations` here: the save tool's `runtime`
annotation must be a real `ToolRuntime[...]` object, built from the agent's own
state schema, so that @tool recognises the argument as injected and keeps it
out of the schema the model sees.
"""
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable

from webforge.dev_shared import *  # noqa: F401,F403


@dataclass(frozen=True)
class DevLanguage:
    """The words one developer agent's shared parts differ by.

    key           names the parts and the state field: "js" gives js_code,
                  save_js_file, js_fs_guard, extract_js_component, ...
    tag           the progress tag, "[JS Agent]", and the code's label
    noun          what the agent calls its file ("script", "stylesheet")
    linter        the linter's display name ("ESLint")
    lint_tool     the lint tool's name ("run_eslint")
    extract_none  the extract tool's "nothing matched" reply (a string, or a
                  tuple of them), which must stay silent in the progress feed
    save_backend  returns the backend the save tool writes through. Read at
                  call time, so a test that swaps the module-level backend
                  (cell 222) reaches the tool, as it did when the tool read
                  the global itself.
    """
    key: str
    tag: str
    noun: str
    linter: str
    lint_tool: str
    extract_none: "str | tuple[str, ...]"
    save_backend: Callable[[], Any]
    # Ticket 10: HTML words its tools its own way. Empty means the default,
    # derived from the words above, which is what CSS and JS use.
    extract_tool: str = ""        # default extract_<key>_component
    extract_label: str = ""       # default "Extracting <TAG> block for component..."
    lint_label: str = ""          # default "Linting <TAG> code with <linter>..."
    extra_tool_labels: tuple = ()  # more (tool name, label) pairs to label

    @property
    def code_field(self) -> str:
        return f"{self.key}_code"

    @property
    def extract_name(self) -> str:
        return self.extract_tool or f"extract_{self.key}_component"

    @property
    def extract_silent(self) -> tuple:
        none = self.extract_none
        return (none,) if isinstance(none, str) else tuple(none)


_SAVE_DOC = """
    Write CODE from state to preview_{session_id}.EXT on disk.

    Call this to save — never paste file content into write_file. The file the
    user opens must be byte-identical to the CODE that was linted, and the
    only guarantee is writing it FROM state (E2E-MM-01 proved the two can
    silently diverge when the model re-types the content).

    Refuses unless the lint gate is settled: lint_passed is True (clean), or
    lint_escalated is True (cap reached and the best-effort save was
    instructed). "LLMs decide, Python guarantees" applied to the save step.
    """


def _save_tool(lang: DevLanguage, state_schema):
    field = lang.code_field

    def save(runtime) -> Command:
        session_id = runtime.state.get("session_id", "")
        code       = runtime.state.get(field, "")

        if not code:
            return Command(update={"messages": [ToolMessage(
                content=f"{field} is empty in state. Nothing to save.",
                tool_call_id=runtime.tool_call_id)]})
        if not session_id:
            return Command(update={"messages": [ToolMessage(
                content="session_id not set in state. Cannot name the preview file.",
                tool_call_id=runtime.tool_call_id)]})
        if not (runtime.state.get("lint_passed", False)
                or runtime.state.get("lint_escalated", False)):
            return Command(update={"messages": [ToolMessage(
                content=("Save refused: lint has not passed and the fix loop has not "
                         f"been escalated. Run {lang.lint_tool} first."),
                tool_call_id=runtime.tool_call_id)]})

        fname  = f"preview_{session_id}.{lang.key}"
        result = lang.save_backend().write(fname, code)
        if getattr(result, "error", None):
            return Command(update={"messages": [ToolMessage(
                content=f"Save failed: {result.error}",
                tool_call_id=runtime.tool_call_id)]})
        return Command(update={"messages": [ToolMessage(
            content=f"Saved {len(code)} characters of {field} from state to {fname}.",
            tool_call_id=runtime.tool_call_id)]})

    save.__name__ = save.__qualname__ = f"save_{lang.key}_file"
    save.__doc__ = _SAVE_DOC.replace("CODE", field).replace("EXT", lang.key)
    save.__annotations__ = {"runtime": ToolRuntime[state_schema], "return": Command}
    return tool(save)


def _progress_hooks(lang: DevLanguage):
    tag = f"   [{lang.tag} Agent]"
    k = lang.key
    tool_labels = {
        f"store_{k}_code":         f"Storing {lang.tag} code...",
        lang.lint_tool:            (lang.lint_label
                                    or f"Linting {lang.tag} code with {lang.linter}..."),
        lang.extract_name:         (lang.extract_label
                                    or f"Extracting {lang.tag} block for component..."),
        f"apply_and_lint_{k}":     "Applying diff and linting...",
        f"save_{k}_file":          f"Saving {lang.tag} to filesystem...",
        **dict(lang.extra_tool_labels),
    }

    def agent_progress(state, runtime):
        get_stream_writer()(f"{tag} Processing request...")
        return None

    def tool_progress(request, handler):
        writer = get_stream_writer()
        tool_name = ""
        try:
            tool_name = (request.tool_call or {}).get("name") or ""
        except Exception:
            tool_name = ""
        if tool_name in tool_labels:
            writer(f"{tag} {tool_labels[tool_name]}")
        return handler(request)

    def before_model_progress(state, runtime):
        # A before_model hook fires BEFORE the model speaks, so it cannot know
        # what the model is about to do. It CAN know what the model is responding
        # to: the last completed tool call. Every label below is derived from that
        # observation (tool name via the AIMessage's tool_calls, outcome via
        # stable message markers). Success paths stay silent - the next tool's
        # own wrap_tool_call label tells the story, and a guessed label on the
        # wrap-up turn would promise work that never comes (observed live:
        # E2E-MM-01 printed "Generating modification diff..." after write_file,
        # then the run ended).
        writer = get_stream_writer()
        st     = state or {}
        msgs   = st.get("messages") or []
        last   = msgs[-1] if msgs else None

        if getattr(last, "type", None) != "tool":
            # Start of the run: nothing to observe yet, so announce the mode.
            if st.get("intent", "generate") == "modify":
                writer(f"{tag} Reading the current {lang.noun}...")
            else:
                writer(f"{tag} Generating {lang.tag} code...")
            return None

        # Resolve which tool produced the last result.
        tcid, name = getattr(last, "tool_call_id", None), None
        for m in reversed(msgs):
            if getattr(m, "type", None) == "ai":
                for c in (getattr(m, "tool_calls", None) or []):
                    if c.get("id") == tcid:
                        name = c.get("name")
                        break
                if name:
                    break
        content = last.content if isinstance(last.content, str) else str(last.content)

        if name == lang.lint_tool:
            if "[LINT CAP REACHED]" in content:
                writer(f"{tag} Lint cap reached, saving best effort...")
            elif "[Lint attempt" in content:
                writer(f"{tag} Revising after linter feedback...")
            # A clean verdict ("No issues found.") and infrastructure messages
            # stay silent: "Revising..." would be wrong on both.
        elif name == f"store_{k}_code":
            if "saved to state" not in content:
                writer(f"{tag} Completing the items the guard reported...")
        elif name == lang.extract_name:
            if not any(m in content for m in ("is empty", "not set in state",
                                              *lang.extract_silent)):
                writer(f"{tag} Writing the modification diff...")
        elif name == f"apply_and_lint_{k}":
            if "[LINT CAP REACHED]" in content:
                writer(f"{tag} Lint cap reached, saving best effort...")
            elif "[PATCH CAP REACHED]" in content:
                writer(f"{tag} Patch cap reached, leaving this component as it is...")
            elif content.startswith("Patch failed"):
                writer(f"{tag} Regenerating the diff...")
            elif "[Lint attempt" in content:
                writer(f"{tag} Revising after linter feedback...")
        return None

    return (before_agent(agent_progress, name=f"{k}_agent_progress"),
            before_model(before_model_progress, name=f"{k}_before_model_progress"),
            wrap_tool_call(tool_progress, name=f"{k}_tool_progress"))


# FilesystemMiddleware contributes ls / glob / grep on top of the registered
# tools. A developer agent works on ONE file (preview_{session_id}.<ext>), so
# the three SEARCH tools answer a question it never has, and the only files
# they can reach belong to OTHER sessions. read_file stays allowed and the
# backend write path stays open.
FORBIDDEN_FS_TOOLS = frozenset({"ls", "glob", "grep"})


def _fs_guard(lang: DevLanguage):
    def fs_guard(request, handler):
        tc   = request.tool_call or {}
        name = tc.get("name") or ""
        if name in FORBIDDEN_FS_TOOLS:
            return ToolMessage(
                content=(
                    f"The '{name}' tool is disabled for this agent. You already have "
                    f"everything in scope: in modification mode your {lang.noun} is in "
                    f"{lang.code_field} (read only your own preview_{{session_id}}.{lang.key}), and "
                    f"in generation mode you build a new {lang.noun} from the "
                    f"specifications. Do not search the filesystem - the other files "
                    f"in the preview directory belong to other sessions. If a "
                    f"modification target cannot be found, the selector is stale: "
                    f"stop and report it rather than looking for it elsewhere."
                ),
                tool_call_id=tc.get("id", ""),
            )
        return handler(request)

    return wrap_tool_call(fs_guard, name=f"{lang.key}_fs_guard")


def dev_parts(lang: DevLanguage, state_schema) -> SimpleNamespace:
    """The five shared parts for one language: save_tool, agent_progress,
    before_model_progress, tool_progress, fs_guard."""
    agent_progress, before_model_progress, tool_progress = _progress_hooks(lang)
    return SimpleNamespace(save_tool=_save_tool(lang, state_schema),
                           agent_progress=agent_progress,
                           before_model_progress=before_model_progress,
                           tool_progress=tool_progress,
                           fs_guard=_fs_guard(lang))


def new_preview_backend():
    """A backend rooted at the preview folder (webforge.config), overwrite on."""
    return OverwritingFilesystemBackend(root_dir=str(_wf_config.PREVIEW_DIR),
                                        virtual_mode=True)


def build_dev_agent(parts, *, model, tools, prompt_selector, state_schema, backend):
    """The developer agent: `tools` plus the save tool, and the middleware stack
    every developer agent uses, in this order: the filesystem, the guard, the
    prompt, then the three progress hooks."""
    return create_agent(
        model=model,
        tools=[*tools, parts.save_tool],
        middleware=[
            FilesystemMiddleware(backend=backend),
            parts.fs_guard,
            prompt_selector,
            parts.agent_progress,
            parts.before_model_progress,
            parts.tool_progress,
        ],
        state_schema=state_schema,
    )


# ==========================================================================
# The fix loop's shared core: caps, batch helpers, the lint subprocess
# ==========================================================================
# Moved verbatim from html_agent by ticket 09. All three developer agents use
# them, and the engine's loop core below needs them before html_agent loads.
# ── Lint fix-loop cap and graceful escalation (shared by all three agents) ────
# The generate -> lint -> fix loop had no bound in code. The prompts say to
# iterate until "No issues found.", so a defect the model cannot fix had no stop
# condition at all. The installed LangGraph (1.0.10) defaults recursion_limit to
# 10000 supersteps — roughly 5000 model calls — so the loop would burn real money
# for a long time before crashing with GraphRecursionError, producing no artifact
# and no report. (Older LangGraph 0.x defaulted to 25; do not assume that here.)
#
# This mirrors the correction loop in call_test_exec_pipeline: a hard cap enforced
# in Python, and a partial result instead of a failure. Two rules matter:
#
#   1. Only a REAL lint verdict consumes an attempt. Infrastructure problems
#      (npx missing, config error, unparseable output, empty code) must not burn
#      the budget — the same reasoning that makes the Playwright pipeline retry
#      transient page-load failures before entering the correction loop.
#   2. Past the cap the linter REFUSES to run at all. The escalation message
#      instructs the model to stop, but a reasoning lapse could re-invoke the
#      tool; refusing makes the cap non-negotiable and costs no subprocess.

_LINT_ATTEMPT_CAP = 2          # 1 initial lint run + 1 fix attempt

# Modification batching: the most components one developer-agent modify
# session will fix in a single call. The orchestrator groups failing
# components by file and sends at most this many per call, so a warm session
# is reused across several fixes without letting one session grow unbounded.
_MODIFY_BATCH_CAP = 12

# ── Batching the modify loop: several components in ONE tool call ───────────
# The separator carries no diff meaning. '@@', '---', '+++' and a leading '-',
# '+' or ' ' all do, so a marker built from any of them would be read as part of
# a hunk. _join_blocks can use '/* @@ ... @@ */' because it only ever joins CSS
# and JS, where that is a comment; this one also has to survive HTML.
_COMPONENT_SEP = "===== WebForge component {n} of {total}: {label} ====="


def _join_components(items: list) -> str:
    """Join several components' extracted text into one diffable message.

    `items` is [(label, text)]. A single item comes back UNTOUCHED, so every
    existing one-component call sees exactly the text it saw before batching
    existed. That matters more than it looks: the model diffs against this
    string verbatim, so an added header line becomes context it may copy into
    the hunk, and the apply would then fail to find it inside the element.
    """
    if len(items) <= 1:
        return items[0][1] if items else ""
    total = len(items)
    return "\n\n".join(
        _COMPONENT_SEP.format(n=n, total=total, label=lab) + "\n" + txt
        for n, (lab, txt) in enumerate(items, 1))


def _clean_batch(components, cap: int = None):
    """Normalise a batch argument to a de-duplicated list of names.

    Returns (wanted, dropped). Nothing is dropped SILENTLY -- the caller puts
    `dropped` in the message. A silent cap reads as "all of it was handled",
    which is the failure mode this project keeps paying for.

    A name appearing twice is one intent expressed twice, and the second diff
    would be written against text the first already changed, so the duplicate
    goes rather than the batch.
    """
    cap = _MODIFY_BATCH_CAP if cap is None else cap
    seen, wanted, dropped = set(), [], []
    for c in components or []:
        name = str(c).strip()
        if not name:
            continue
        if name in seen:
            dropped.append(f"{name} (named twice in one call)")
            continue
        seen.add(name)
        if len(wanted) >= cap:
            dropped.append(f"{name} (over the batch cap of {cap})")
            continue
        wanted.append(name)
    return wanted, dropped


def _batch_status_table(rows: list) -> str:
    """One line per component: what happened to its diff.

    The reason the per-component lint feedback is not lost when the lint moves
    to the end of the batch. A bare "Found 2 error(s)" after five diffs is two
    errors with five suspects; this table says which diffs even landed.
    """
    return "\n".join(f"  {ok:<7} {label}{(' -- ' + why) if why else ''}"
                      for ok, label, why in rows)




def _conflict_groups(n: int, conflicts) -> list:
    """Group the indices 0..n-1 that cannot take separate diffs.

    Two components resolving to the SAME text cannot take two diffs: the second
    is written against text the first already replaced. The first design refused
    such a batch. That was wrong, and JS proved it -- the JS agent writes the
    whole page as one IIFE, so every pair of components lands in the same
    paragraph, every batch was refused, and E2E-JS-MM-04 failed twice while the
    model was doing exactly what the prompt asked.

    Merging is strictly better. The block is served ONCE and the note names the
    other components it covers, so the model writes one diff instead of two --
    which is what it had to do anyway, minus a wasted round trip.

    `conflicts(i, j)` is the caller's test: overlapping spans for CSS and JS, an
    ancestor relationship for HTML. Returns a list of index lists, input order
    preserved inside each group and between groups.
    """
    parent = list(range(n))

    def _find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            if conflicts(i, j):
                ra, rb = _find(i), _find(j)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    groups = {}
    for i in range(n):
        groups.setdefault(_find(i), []).append(i)
    return [sorted(v) for _k, v in sorted(groups.items())]


def _merged_note(covered: list) -> str:
    """The sentence that replaces the old refusal.

    It has to be unambiguous about the ARGUMENT the model will pass back: the
    separator carries the keeper's bare name, and only that name resolves.
    """
    if not covered:
        return ""
    n = sum(len(others) for _k, others in covered)
    lines = [f"\n\n{n} of your targets share a block with another target, so "
             f"they are NOT shown separately above:"]
    for keeper, others in covered:
        lines.append(
            f"  - {', '.join(others)} live in the block shown for '{keeper}'. "
            f"Put ALL of those changes into the SINGLE diff for '{keeper}'. Do "
            f"not send a separate diff for "
            f"{' or '.join(repr(o) for o in others)} -- only '{keeper}' resolves "
            f"to that block, and a second diff would be written against text the "
            f"first one already replaced.")
    return "\n".join(lines)


def _overlapping_pair(spans_by_label: list):
    """The first pair of components whose blocks OVERLAP, or None.

    The text twin of the HTML nesting guard. A grouped selector belongs to
    every component it names, so `.card, .tile { ... }` is one block that both
    ".card" and ".tile" resolve to. Diffing it twice in one batch means the
    second diff is written against text the first already replaced, and it fails
    on a stale context match -- or worse, matches somewhere it should not.

    `spans_by_label` is [(label, [(start, end), ...])].
    """
    for i, (la, sa) in enumerate(spans_by_label):
        for lb, sb in spans_by_label[i + 1:]:
            if _spans_overlap(sa, sb):
                return la, lb
    return None


def _spans_overlap(spans_a: list, spans_b: list) -> bool:
    """True when any (start, end) span of one list overlaps one of the other."""
    return any(a0 < b1 and b0 < a1 for a0, a1 in spans_a for b0, b1 in spans_b)


def _batch_apply_text(loop, runtime, diffs):
    """Apply several diffs to one text file, then lint ONCE. CSS and JS share it;
    `loop` (a DevLoop) says which file, how to find a block and how to lint.

    Sequential inside a single Python call, each diff applied to the result of
    the last. That is the whole reason batching is an ARGUMENT here rather than
    several parallel tool calls: parallel applies would each start from the same
    stale *_code and one fix would silently overwrite another, and two Commands
    in one superstep would raise InvalidUpdateError outright.

    PARTIAL COMMIT is deliberate. All-or-nothing would discard four good fixes
    because a fifth diff miscounted its line numbers, and the model would have
    to rewrite all five. Sequential application makes the successes safe to
    keep, so they are kept and the reply says exactly which ones they are.
    """
    code_key = loop.lang.code_field
    spec = runtime.state.get(loop.spec_field)
    code = runtime.state.get(code_key, "")
    if not code:
        return Command(update={"messages": [ToolMessage(
            content=f"{code_key} is empty. Cannot apply diff.",
            tool_call_id=runtime.tool_call_id)]})

    rows, failed, n_ok = [], [], 0
    for entry in diffs:
        if not isinstance(entry, dict):
            rows.append(("FAILED", str(entry)[:40],
                         "not a {component, diff_output} object"))
            failed.append(str(entry)[:40])
            continue
        name = str(entry.get("component") or "").strip()
        body = entry.get("diff_output") or entry.get("diff") or ""
        if not name:
            rows.append(("FAILED", "(unnamed)", "no component named"))
            failed.append("")
            continue
        name = loop_resolve(loop, code, name, spec)[0]
        res  = loop_apply_diff(loop, code, name, body, spec)
        st   = res["status"]
        if st == "ok":
            code = res[f"new_{code_key}"]
            n_ok += 1
            rows.append(("OK", name, ""))
        elif st == "internal":
            rows.append(("FAILED", name, f"[INTERNAL] {res['etype']}: {res['error']}"))
            failed.append(name)
        elif st == "noblock":
            rows.append(("SKIPPED", name, f"no {loop.lang.tag} block matched"))
        else:
            rows.append(("FAILED", name, res.get("error", st)))
            failed.append(name)

    header = (f"Applied {n_ok} of {len(diffs)} diff(s) in one call.\n"
              + _batch_status_table(rows))

    # Nothing landed, so *_code is untouched: this is a plain patch failure and
    # counts against the patch budget exactly as the single-component path does.
    if n_ok == 0:
        tail = ""
        for name in failed:
            blk = loop_block_text(loop, code, name) if name else ""
            if blk:
                tail += (f"\n\nCurrent block for '{name}' (diff against THIS, "
                         f"do NOT re-extract):\n\n{blk}")
        return _patch_failure(runtime, header + tail)

    lint_cmd = loop.lint(code, runtime)
    upd = dict(lint_cmd.update)
    upd[code_key] = lint_cmd.update.get(code_key, code)
    lint_msg = upd["messages"][0]
    combined = f"{header}\n\n{lint_msg.content}"

    if failed:
        # Some landed and some did not. The budget is counted here rather than
        # through _patch_failure, which would throw away the ones that landed.
        attempts = runtime.state.get("patch_attempts", 0) + 1
        upd["patch_attempts"] = attempts
        if attempts >= _PATCH_ATTEMPT_CAP:
            combined += (f"\n\n[PATCH CAP REACHED] {attempts}/{_PATCH_ATTEMPT_CAP} "
                         "calls in a row left a diff unapplied. Do NOT rewrite the "
                         "failed diffs. Save the current best-effort code and END "
                         "your turn, naming what is unfixed.")
        else:
            for name in failed:
                blk = loop_block_text(loop, code, name) if name else ""
                if blk:
                    combined += (f"\n\nCurrent block for '{name}' AFTER the diffs "
                                 f"that did apply (diff against THIS, do NOT "
                                 f"re-extract):\n\n{blk}")
    else:
        upd["patch_attempts"] = 0

    if (not upd.get("lint_passed", False)
            and _LINT_CAP_MARKER not in lint_msg.content
            and not failed):
        for _ok, _lab, _why in rows:
            if _ok != "OK":
                continue
            blk = loop_block_text(loop, code, _lab)
            if blk:
                combined += (f"\n\nCurrent block for '{_lab}' AFTER this patch "
                             f"(diff against THIS, do NOT re-extract):\n\n{blk}")

    upd["messages"] = [ToolMessage(content=combined,
                                   tool_call_id=runtime.tool_call_id)]
    return Command(update=upd)


_LINT_CAP_MARKER = "[LINT CAP REACHED]"


def _lint_refused(runtime) -> Command:
    """Response to a linter call made after the cap was already reached."""
    return Command(update={
        "lint_passed": False,
        "messages": [ToolMessage(
            content=(f"{_LINT_CAP_MARKER} Linter call REFUSED — the "
                     f"{_LINT_ATTEMPT_CAP}-attempt cap was already reached.\n"
                     "Do not lint again. Save the current best-effort code with "
                     "your save tool, then END your turn with a summary of the "
                     "unresolved problems."),
            tool_call_id=runtime.tool_call_id)]})


_PATCH_ATTEMPT_CAP = 2   # consecutive failed patches on one component


def _patch_failure(runtime, body: str) -> Command:
    """Build the Command for a diff that did not apply.

    The lint loop has been counted and capped since the beginning; this one was
    not. A patch fault handed the current block back and counted nothing, so the
    model could regenerate a diff forever and only recursion_limit ever stopped
    it. Raising that limit for batched correction removed the accidental brake
    and a single PO-08 run burned 2.19M tokens before it was killed by hand
    (po01ba89e9, 2026-08-30).

    The counter is separate from lint_attempts and RESETS on every successful
    apply, so the cap means "three failures in a row on the same component"
    rather than "three failures anywhere in this batch". Folding it into the
    lint budget would let one component's diff trouble escalate the run and
    leave every remaining component in the batch unlinted.
    """
    attempts = runtime.state.get("patch_attempts", 0) + 1
    if attempts >= _PATCH_ATTEMPT_CAP:
        return Command(update={
            "patch_attempts": attempts,
            "messages": [ToolMessage(
                content=(f"{body}\n\n"
                         f"[PATCH CAP REACHED] {attempts}/{_PATCH_ATTEMPT_CAP} diffs in a "
                         "row failed to apply to this component, so it is being left as "
                         "it is. Do NOT write another diff for it. If other components "
                         "were requested, move to the next one now. If this was the last "
                         "one, save the current best-effort code with your save tool and "
                         "END your turn, naming this component as unfixed."),
                tool_call_id=runtime.tool_call_id)]})
    return Command(update={
        "patch_attempts": attempts,
        "messages": [ToolMessage(
            content=(f"{body}\n\n"
                     f"[Patch attempt {attempts}/{_PATCH_ATTEMPT_CAP}] Line numbers are "
                     "the usual cause: count them against the block shown above, not "
                     "against the whole file."),
            tool_call_id=runtime.tool_call_id)]})


def _lint_failure(runtime, body: str) -> Command:
    """Build the Command for a lint run that found real problems.

    Counts the attempt, and escalates gracefully once the cap is reached rather
    than letting the fix loop spin. `body` is the formatted problem list and is
    always placed first, unchanged, so the model still sees the diagnostics.
    """
    attempts = runtime.state.get("lint_attempts", 0) + 1

    if attempts >= _LINT_ATTEMPT_CAP:
        return Command(update={
            "lint_passed":   False,
            "lint_attempts": attempts,
            "lint_escalated": True,
            "messages": [ToolMessage(
                content=(f"{body}\n\n"
                         f"{_LINT_CAP_MARKER} {attempts}/{_LINT_ATTEMPT_CAP} lint "
                         "attempts used and problems remain. STOP the fix loop — do "
                         "NOT call the linter again.\nSave the current best-effort "
                         "code with your save tool, then END your turn with a short "
                         "summary of the unresolved problems listed above."),
                tool_call_id=runtime.tool_call_id)]})

    return Command(update={
        "lint_passed":   False,
        "lint_attempts": attempts,
        "messages": [ToolMessage(
            content=(f"{body}\n\n[Lint attempt {attempts}/{_LINT_ATTEMPT_CAP}] "
                     "Fix the reported lines and re-lint."),
            tool_call_id=runtime.tool_call_id)]})


_LINT_SUBPROCESS_TIMEOUT = 60   # seconds. Above a real lint (2-3.5s), well
                                # below a dead run. A hang past this is a
                                # stall, not a slow lint.


def _run_lint_subprocess(command: str):
    """Run a linter CLI and return the completed process.

    One place owns how linter output is decoded. On Windows text=True
    defaults to cp1252, so a generated file carrying a smart quote makes the
    linter echo a byte cp1252 cannot decode and the reader thread dies with a
    UnicodeDecodeError -- every lint round then fails and an unlinted page
    ships. Decoding as UTF-8 with errors='replace' is the fix, and keeping it
    in one function gives the tests a single seam to exercise against the real
    byte. Seen live on PO-01b, 2026-08-22.
    """
    try:
        return subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", shell=True,
            timeout=_LINT_SUBPROCESS_TIMEOUT,
            # From the repo root whatever the process cwd is: npx finds the
            # repo's local linters there, and eslint is passed its config
            # (eslint.config.fyp.mjs) by a path relative to the root.
            cwd=str(_wf_config.REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        # A hang, not a lint result. Return a FAILED process so every
        # caller's existing error path handles it and the run keeps moving.
        # returncode 124 is the conventional timeout code; the stderr carries
        # no "npx" token, so the npx-missing guard is not tripped by mistake.
        return subprocess.CompletedProcess(
            command, 124, stdout="",
            stderr=(f"linter timed out after {_LINT_SUBPROCESS_TIMEOUT}s and "
                    f"was killed; treated as a lint failure so the run "
                    f"continues."),
        )


def lint_source(lang: DevLanguage, code: str, runtime, check) -> Command:
    """Lint a SOURCE STRING: the one lint runner the three developer agents share.

    The order is the loop's contract. Past the cap the linter refuses to run at
    all (see _lint_failure); empty code is an infrastructure problem and burns
    no attempt; otherwise the code goes to a temp file and `check(tmp_path,
    runtime)` runs the language's linter on it and turns its output into the
    verdict, and the file is deleted whatever happens.

    The temp file lives INSIDE the repo: eslint v9+ silently ignores files
    outside its base path, stylelint finds .stylelintrc.json by walking up
    from the file, and npx run from %TEMP% would download a throwaway linter
    instead of using the repo's local install.
    """
    if runtime.state.get("lint_escalated", False):
        return _lint_refused(runtime)
    if not code:
        return Command(update={
            "lint_passed": False,
            "messages": [ToolMessage(
                content=(f"{lang.code_field} is empty in state. "
                         f"Call store_{lang.key}_code first."),
                tool_call_id=runtime.tool_call_id
            )]
        })
    _lint_dir = str(_wf_config.LINT_TMP_DIR)
    os.makedirs(_lint_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=f".{lang.key}", mode="w", encoding="utf-8",
                                     dir=_lint_dir, delete=False) as f:
        f.write(code)
        tmp_path = f.name
    try:
        return check(tmp_path, runtime)
    finally:
        os.unlink(tmp_path)


# ==========================================================================
# The modify loop's core: extract (ticket 09)
# ==========================================================================
@dataclass(frozen=True)
class DevLoop:
    """What one text language's modify loop differs by (CSS and JS today).

    lang        the language's words (DevLanguage): key, tag, code_field
    spec_field  the state field that maps a specification id to the name the
                code uses (components_specification for JS,
                decoration_specification for CSS)
    aliases     (component, spec) -> every name to try, best guess first
    spans       (code, name) -> the (start, end) of every block for that name
    extract_miss    (code, component, spec) -> the extract tool's reply when
                    nothing matched one component
    batch_miss      (code, wanted) -> the same for a batch where nothing
                    matched any component
    skipped_phrase  how a batch reply names the components it found nothing
                    for ("No code found", "No blocks found")
    apply_miss      (code, component) -> the apply tool's reply when no block
                    matched
    lint            (code, runtime) -> the lint verdict for patched code (the
                    language's _lint_*_source); a verdict may carry the code
                    back in code_field, as CSS's dedupe does

    The callables are lambdas in the language modules, so a test that swaps
    one of the helpers a lambda names (_js_block_spans, _css_component_aliases,
    _lint_css_source, ...) reaches the loop. The engine does NOT go through
    the old per-language wrappers: swapping _js_resolve_component,
    _resolve_css_component, _apply_js_component_diff,
    _apply_css_component_diff, _js_blocks_for_component or
    _extract_css_blocks changes what other callers see, not what the tools do.
    """
    lang: DevLanguage
    spec_field: str
    aliases: Callable[[str, Any], list]
    spans: Callable[[str, str], list]
    extract_miss: Callable[[str, str, Any], str]
    batch_miss: Callable[[str, list], str]
    skipped_phrase: str
    apply_miss: Callable[[str, str], str]
    lint: Callable[[str, Any], Command]


def loop_resolve(loop: DevLoop, code: str, component: str, spec=None):
    """Return (the alias that matched, its spans). The code addresses a component
    by whatever name the page rendered ('.add-to-cart-btn') while the work order
    names the specification id, so a literal search finds nothing. Falls back to
    the name given, with no spans, so callers keep their not-found path."""
    for cand in loop.aliases(component, spec):
        spans = loop.spans(code, cand)
        if spans:
            return cand, spans
    return component, []


def _extract_batch(loop: DevLoop, runtime, wanted: list, dropped: list,
                   upgraded: bool = False) -> Command:
    """Extract several components' code in ONE call.

    Components whose blocks OVERLAP are merged, not refused: one block needs
    one diff either way, and two diffs against one block cannot both apply
    (the second is written against text the first already replaced).

    A component with no blocks is NOT a refusal: it is reported and the rest are
    returned. The code was written before the page was hand-edited, so a stale
    name is ordinary.
    """
    field = loop.lang.code_field
    code = runtime.state.get(field, "")
    if not code:
        return Command(update={"messages": [ToolMessage(
            content=f"{field} is empty. Cannot extract component.",
            tool_call_id=runtime.tool_call_id)]})

    _spec = runtime.state.get(loop.spec_field)
    picked, missing = [], []
    for name in wanted:
        label, spans = loop_resolve(loop, code, name, _spec)
        blocks = [code[a:b] for a, b in spans]
        if blocks:
            picked.append((label, blocks, spans))
        else:
            missing.append(name)

    if not picked:
        return Command(update={"messages": [ToolMessage(
            content=loop.batch_miss(code, wanted),
            tool_call_id=runtime.tool_call_id)]})

    # Components sharing a block are MERGED, not refused. Refusing was the
    # first design; the JS agent writes the whole page as one IIFE, so every
    # pair of components shares a block, every batch was refused, and batching
    # could never engage (E2E-JS-MM-04, twice, 2026-08-31). One block needs one
    # diff either way -- serving it once just saves the round trip.
    def _shares(_i, _j):
        return _spans_overlap(picked[_i][2], picked[_j][2])

    apply_tool = f"apply_and_lint_{loop.lang.key}"
    items, covered = [], []
    for _g in _conflict_groups(len(picked), _shares):
        _keep = _g[0]                      # the first named target keeps the label
        _lab  = picked[_keep][0]
        items.append((_lab, _join_blocks(picked[_keep][1])))
        _others = [picked[_k][0] for _k in _g if _k != _keep]
        if _others:
            covered.append((_lab, _others))
    note  = _merged_note(covered)
    if upgraded:
        note += ("\n\nYou asked for ONE component; this call carries "
                 f"{len(wanted)}, and all {len(wanted)} are above. Do NOT call "
                 "this tool again. Write one diff per component and send them "
                 f"together in a single {apply_tool} call using its `diffs` argument.")
    if missing:
        note += (f"\n\n{loop.skipped_phrase}, so not included (treat as stale names and "
                 f"skip them): {', '.join(missing)}.")
    if dropped:
        note += f"\n\nDropped from this call: {'; '.join(dropped)}."
    note += ("\n\nWrite ONE diff per component, each with line numbers starting "
             "at 1 for its own block, and never include a '=====' separator line "
             f"in a hunk. Then send them together in a single {apply_tool} "
             "call using its `diffs` argument.")

    return Command(update={
        # One reset for the whole batch: it is one apply and one lint, so it is
        # one budget.
        "lint_attempts": 0,
        "lint_escalated": False,
        "patch_attempts": 0,
        "messages": [ToolMessage(
            content=_join_components(items) + note,
            tool_call_id=runtime.tool_call_id)]})


def loop_extract(loop: DevLoop, runtime, component: str = "",
                      components=None) -> Command:
    """The extract tool's body: every block for one component, or for a batch.

    `components` extracts several in one call. Asked for ONE while state
    carries several target_components, it hands over the whole batch: the
    prompt already asks for that, and on 2026-08-31 the CSS and JS agents
    each ignored the ask once on a first live run while the other agents
    obeyed it. Making the first call complete leaves the second nothing to
    fetch.
    """
    if components:
        _batch, _dropped = _clean_batch(components)
        if len(_batch) > 1:
            return _extract_batch(loop, runtime, _batch, _dropped)
        if _batch:
            component = component or _batch[0]
    elif len(runtime.state.get("target_components", []) or []) > 1:
        _batch, _dropped = _clean_batch(runtime.state["target_components"])
        if len(_batch) > 1:
            return _extract_batch(loop, runtime, _batch, _dropped, upgraded=True)

    field = loop.lang.code_field
    component = component or runtime.state.get("target_component", "")
    code = runtime.state.get(field, "")

    if not code:
        return Command(update={"messages": [ToolMessage(
            content=f"{field} is empty. Cannot extract component.",
            tool_call_id=runtime.tool_call_id
        )]})
    if not component:
        return Command(update={"messages": [ToolMessage(
            content="target_component not set in state.",
            tool_call_id=runtime.tool_call_id
        )]})

    _spec = runtime.state.get(loop.spec_field)
    component, _spans = loop_resolve(loop, code, component, _spec)
    blocks = [code[a:b] for a, b in _spans]
    if not blocks:
        return Command(update={"messages": [ToolMessage(
            content=loop.extract_miss(code, component, _spec),
            tool_call_id=runtime.tool_call_id
        )]})

    # The message is the joined text and nothing else -- any preamble would
    # shift the line numbers the model diffs against.
    return Command(update={
        # A new component starts a fresh lint budget. lint_attempts /
        # lint_escalated are session-global, so without this reset a batch of
        # components would exhaust the cap after the first. extract runs once
        # per component, before its first apply_and_lint, so this is the
        # correct reset point.
        "lint_attempts": 0,
        "lint_escalated": False,
        "messages": [ToolMessage(
            content=_join_blocks(blocks),
            tool_call_id=runtime.tool_call_id
        )]
    })


# ==========================================================================
# The modify loop's core: apply and lint (ticket 09)
# ==========================================================================
def loop_block_text(loop: DevLoop, code: str, name: str) -> str:
    """Every block for an already-resolved name, joined as extract served it."""
    return _join_blocks([code[a:b] for a, b in loop.spans(code, name)])


def loop_apply_diff(loop: DevLoop, code: str, component: str, diff_output: str,
                    spec=None) -> dict:
    """
    Apply a unified diff to EVERY block for `component` and splice the results
    back. Pure function -- no state, no ToolMessage -- so the store_*_diff
    tools and apply_and_lint format their own responses from ONE source of
    truth. `spec` maps a specification id to the name the code uses; it is
    passed IN rather than read from state, which keeps this pure. Returns one
    of (new_<code_field> is new_js_code, new_css_code, ...):
      {"status": "empty"}                                  the code was empty
      {"status": "noblock"}                                no block matched component
      {"status": "diff_fault", "error": <str>}             stale/malformed diff -- regenerate
      {"status": "internal", "etype": <str>, "error": <str>}  wiring/env fault -- regenerating won't help
      {"status": "ok", "new_<code_field>": <str>, "n_blocks": <int>}  applied cleanly
    """
    if not code:
        return {"status": "empty"}
    # Resolve id -> the code's name the same way extract did, or the diff would
    # be applied against a name that matches nothing.
    component, spans = loop_resolve(loop, code, component, spec)
    if not spans:
        return {"status": "noblock"}
    original_blocks = [code[a:b] for a, b in spans]
    try:
        patched_joined = _apply_patch(_join_blocks(original_blocks), diff_output)
        patched_blocks = _split_blocks(patched_joined, len(original_blocks))
        new_code       = _splice_spans(code, spans, patched_blocks)
    except (ValueError, IndexError, KeyError) as e:
        # A genuine problem with the diff itself: stale context, a destroyed
        # block separator, a malformed hunk header. Regenerating it is the fix.
        return {"status": "diff_fault", "error": str(e)}
    except (NameError, ImportError, AttributeError, TypeError) as e:
        # A missing helper or import is an ENVIRONMENT fault, not a defective
        # diff -- the same code-vs-infrastructure distinction the linters make.
        return {"status": "internal", "etype": type(e).__name__, "error": str(e)}
    return {"status": "ok", f"new_{loop.lang.code_field}": new_code,
            "n_blocks": len(spans)}


def loop_apply_and_lint(loop: DevLoop, runtime, diff_output: str = "",
                        component: str = "", diffs=None) -> Command:
    """The apply_and_lint tool's body: apply a diff (or a batch of them) and
    lint the result in the same call. On a patch or lint failure the CURRENT
    block goes back in the message, so the model re-diffs without
    re-extracting."""
    # An EMPTY call is refused, never applied. diffs=[] is falsy, so before
    # this guard it fell through to the single-diff path with nothing to
    # apply, and patching nothing "succeeded": on 13b71045 (2026-09-15) the
    # agent read "Diff applied ... No issues found.", saved the unchanged
    # page, and the orchestrator reported the change as done.
    if not diffs and not (diff_output or "").strip():
        return Command(update={"messages": [ToolMessage(
            content=("No diff supplied: diffs is empty and diff_output is blank. "
                     "Nothing was applied and the code did not change. Write the "
                     "unified diff against the extracted block and call again. "
                     "If there is genuinely nothing to change, do not save; end "
                     "your turn and say the request needs no edit."),
            tool_call_id=runtime.tool_call_id)]})
    field = loop.lang.code_field
    spec = runtime.state.get(loop.spec_field)
    if diffs:
        return _batch_apply_text(loop, runtime, diffs)

    component = component or runtime.state.get("target_component", "")
    code      = runtime.state.get(field, "")

    component = loop_resolve(loop, code, component, spec)[0]
    res = loop_apply_diff(loop, code, component, diff_output, spec)
    st  = res["status"]

    if st == "empty":
        return Command(update={"messages": [ToolMessage(
            content=f"{field} is empty. Cannot apply diff.",
            tool_call_id=runtime.tool_call_id)]})
    if st == "noblock":
        return Command(update={"messages": [ToolMessage(
            content=loop.apply_miss(code, component),
            tool_call_id=runtime.tool_call_id)]})
    if st == "internal":
        return Command(update={"messages": [ToolMessage(
            content=(f"[INTERNAL] {res['etype']}: {res['error']}\n"
                     "This is a wiring or environment fault, not a defective diff. "
                     "Regenerating the diff will not help."),
            tool_call_id=runtime.tool_call_id)]})
    if st == "diff_fault":
        # The code did NOT change -- hand back the current block so the model
        # re-diffs without a separate extract round-trip. Counted and capped:
        # this path used to count nothing, so a model that kept miscounting
        # line numbers could re-diff forever.
        block = loop_block_text(loop, code, component)
        return _patch_failure(runtime,
            f"Patch failed: {res['error']}\n"
            "Regenerate the diff against the CURRENT block below "
            "(do NOT re-extract):\n\n" + block)

    # Applied cleanly -- lint the NEW code in the same call.
    new_code = res[f"new_{field}"]
    n = res["n_blocks"]
    plural = "block" if n == 1 else "blocks"
    applied_note = f"Diff applied. {n} {loop.lang.tag} {plural} for '{component}' updated."

    lint_cmd = loop.lint(new_code, runtime)
    upd = dict(lint_cmd.update)
    # A verdict may carry the code back (CSS collapses duplicate selectors
    # before linting); what was linted is what is stored.
    upd[field] = lint_cmd.update.get(field, new_code)
    upd["patch_attempts"] = 0      # applied: the run of failures is over
    lint_msg = upd["messages"][0]
    combined = f"{applied_note}\n{lint_msg.content}"
    # On a lint FAILURE the code changed, so hand back the NEW block too -- the
    # next diff is written against current text, again with no re-extract. The
    # cap-reached message is left alone (the loop must stop, not re-diff).
    if not upd.get("lint_passed", False) and _LINT_CAP_MARKER not in lint_msg.content:
        new_block = loop_block_text(loop, new_code, component)
        combined += ("\n\nCurrent block AFTER this patch (diff against THIS, "
                     "do NOT re-extract):\n\n" + new_block)
    upd["messages"] = [ToolMessage(content=combined, tool_call_id=runtime.tool_call_id)]
    return Command(update=upd)


# Re-export this module's whole namespace, so the next module
# starts from it, as every module in LOAD_ORDER does.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
