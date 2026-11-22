# Terminology

One concept, one term, everywhere. Silent synonyms are the most common way these reports lose the
reader. Use the left column. Never use the right column. This applies to the report, the docs,
diagram labels, and code comments.

---

## 1. Canonical names (never paraphrase)

| Use this | Never use |
|---|---|
| Primary Orchestrator | controller, master, manager, top-level agent |
| Secondary Orchestrator | sub-controller, coordinator, executor |
| Context Engineering Agent | requirement agent, parser |
| System Design & Planning Pipeline | System Design Planning Agent, System Design & Planning Agent, Planning Pipeline, planner, architect agent |
| Developer Agent (HTML / CSS / JS) | coder, generator, worker |
| Test Generation Agent | test writer, QA agent |
| Test Execution **pipeline** | test agent, execution agent |
| generation mode / modification mode | create mode, edit mode, update mode |
| specification schema | spec object, blueprint, plan |
| episodic memory (removed 2026-08-15; use the term only when describing what was dropped) | history, log, cache |
| Naming Contract / Selector Contract | naming convention, ID rule |
| Component Category Contract | data-component rule, role attribute |
| Product Image Contract | image rule, photo requirement |
| Image Source Contract | image allowlist, host whitelist |
| Decoration Colour Contract | colour rule, palette rule |
| Icon Accessibility Contract | icon rule, aria rule |
| blackboard architecture | shared memory, message bus |

### Two names that carry real meaning and must not blur

- **Test Execution is a pipeline, not an agent.** It runs no LLM. Calling it an agent
  misrepresents the architecture and invites a viva question you cannot answer well.
- **System Design & Planning Pipeline is the report-facing component name.** In the implementation,
  its structured specification generation is executed by the fixed-order `run_planning_pipeline`
  routine.
- **Only two intents exist:** `generate` and `modify`. There is no incremental or add-a-page
  mode. If a draft implies one, it is wrong.

---

## 2. Method vs metric (do not conflate)

- A **method** is an approach to evaluating something. Examples: trajectory evaluation,
  benchmark-based evaluation, LLM-as-judge, scope-based evaluation, comparative evaluation.
- A **metric** is a number a method produces. Examples: Task Completion Rate, Silent Failure
  Rate, Lighthouse Accessibility.

Never list a method inside a metric taxonomy. An examiner will catch it. A method can be **applied
without being scored** — this project asserts tool-call sequences (trajectory evaluation) but
reports no trajectory-adherence score. Say that plainly rather than claiming a metric that was
never computed or disowning work that was done.

---

## 3. Classification shape: tree vs matrix

- **Hierarchical (taxonomy):** each member has exactly one parent, branches mutually exclusive.
  The **evaluation metrics** are a taxonomy — Lighthouse Accessibility belongs to output quality
  and nothing else.
- **Faceted (matrix):** two attributes vary independently, every combination is meaningful. The
  **test suite** is a matrix — every test has a scope **and** an environment. Call the axes
  **facets**.

Two separate figures, never one combined tree.

---

## 4. Memory and learning terms

- **Working memory** — current-run state.
- **Short-term memory** — per-thread, held by the checkpointer. Not itself a cognitive type; it
  is a temporal layer whose content is mostly episodic (the message history).
- **Long-term memory** — cross-session. **WebForge has none.** The Store that held bug-fix
  episodes was removed on 2026-08-15.
- **Episodic / Semantic / Procedural** — the cognitive types. Only procedural applies here,
  and it is static: prompts and tool docstrings, fixed at build time.
- **Do NOT call this a Self-Evolving Agent**, and do not use *Runtime Continuous Learning*,
  *Verbal Reinforcement Learning* or *self-improving*. Every one of them claims that
  something learned in one run affects the next, and nothing does. Those terms were correct
  while the episodic memory existed and are now false.
- The correction loop is **adaptive within a run** — each attempt is informed by the previous
  test report. That is the honest claim, and it is worth making.

---

## 5. Benchmarks: adapted vs executed

- **Executed** — the benchmark's suite, dataset, and scoring are run as published.
- **Adapted** — its rubric, taxonomy, or observed baselines are used to ground metrics you
  defined.

This project **adapts far more than it executes**. MAESTRO and WebCoderBench are adapted;
Lighthouse is the one genuine execution case (and it is an audit tool, not a research benchmark).
Always add the consequence: **a benchmark that is adapted rather than executed does not license
comparison with results published against that benchmark.** Do not use unsourced term pairs like
"benchmark execution" as if they were terms of art — they could not be traced to any source.

---

## 6. Definitions to give at first use (what / why / why here)

Give these three things in one or two sentences the first time each term appears in the report.

- **Blackboard architecture** — agents share a common typed state instead of messaging each
  other. It keeps coordination logic in one place. It matters here because every guard (the
  attempt cap, the work-order capture) lives on the orchestrator boundary, and
  a direct agent-to-agent channel would bypass all of them.
- **Naming Contract** — a spec `id`/`className` maps directly to the HTML `id`/`class`. It fixes a
  shared vocabulary so CSS, JS, and tests all target the same names.
- **Selector Contract** — the selector is `.className` if present, else `#id`. It is how Test
  Generation and the modify tools locate an element.
- **State Materialization Contract** — component state is always present in the DOM as an
  attribute with a resting value. It exists so there is a "before" value to assert against at
  every test tier.
- **Component Category Contract** — a spec `componentCategory` reaches the DOM verbatim as
  `data-component`. `className` says what a component is *called*; `data-component` says what it
  *is*. Downstream stages read the role, not the name.
- **Product Image Contract** — a component in a product-bearing role must show a real
  photograph or a labelled placeholder. Decorative regions may be drawn. It is scoped by role
  rather than by technique, because no check can distinguish good drawn artwork from bad.
- **Image Source Contract** — an `<img>` may load only from an allowed remote host, a `data:`
  URI, or a relative path that resolves to a real file under the preview root. It exists because
  an unreachable image renders blank while passing every DOM assertion.
- **Decoration Colour Contract** — every colour the decoration specification pins must appear
  in the stylesheet. It exists because the Design Token Contract and the specification could
  otherwise both be satisfied while disagreeing, and the test suite asserts the computed value.
  The value is pinned, never the spelling, so tokenising stays free.
- **Icon Accessibility Contract** — an inline `<svg>` inside a control is `aria-hidden` and the
  control carries the label. The same markup keeps a screen reader on the action and keeps the
  preview's select mode off the glyph.
- **Loop engineering** — designing the system that prompts, checks, remembers, and re-runs an
  agent, instead of typing every instruction by hand. It matters here because all six control
  loops are explicitly bounded and verified.
- **"LLMs decide, Python guarantees"** — the prompt instructs the model; a deterministic Python
  guard enforces the contract and refuses to proceed if it is broken.
