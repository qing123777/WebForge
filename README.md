# WebForge: Autonomous B2C Webapp Development via Multi-Expert Agent Orchestration

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1.0+-1C3C3C?logo=chainlink&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1.2+-1C3C3C?logo=chainlink&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-gpt--5.4-412991?logo=openai&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Test%20Execution-2EAD33?logo=playwright&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-chat%20UI-FF4B4B?logo=streamlit&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-one%20command-2496ED?logo=docker&logoColor=white)

> A multi-agent system that turns a natural-language request into a **frontend B2C
> e-commerce page** (HTML + CSS + JS), then **tests the page it built in a real browser
> and fixes what fails**, with no human in the loop. Final year project.

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Design Principles](#design-principles)
4. [Tech Stack](#tech-stack)
5. [Project Structure](#project-structure)
6. [Setup & Usage](#setup--usage)
7. [Testing](#testing)
8. [Contributors](#contributors)

---

## Overview

You describe a page in the chat (*"A product listing page for a sneaker store with
filters and a sort bar"*). WebForge:

1. **Understands** the request and asks a clarifying question when it needs one.
2. **Plans** the page as four typed specifications: layout, components, interactions
   and decoration.
3. **Builds** it with three developer agents (HTML, CSS, JS). Each one lints its own
   output and fixes it until the linter is clean.
4. **Tests** it: a Test Generation agent writes test cases from the specifications, and
   a Playwright pipeline runs them against the page in Chromium.
5. **Corrects** it: failures go back to the developer agent that owns them, for one
   bounded correction round.
6. **Modifies** it afterwards: click a component in the preview and say what to change.

**One page per run.** Every file is named after the session
(`preview_<session_id>.{html,css,js}`). A multi-section site is one page whose sections
are reached by in-page anchor links. Frontend only: no backend code is generated.

A full generate run through the UI takes about 18 minutes and about $2.80 of OpenAI API
calls (measured 2026-11-10).

---

## Architecture

```
User (Streamlit chat UI)
  └── Primary Orchestrator                    intent: "generate" | "modify"
        ├── Context Engineering Agent         request → design_schema (asks if unclear)
        ├── System Planning and Design        4 specification generators
        └── Secondary Orchestrator            build, test, correct
              ├── HTML Agent   ┐
              ├── CSS Agent    ├─ generate → lint → fix → save
              ├── JS Agent     ┘
              ├── Test Generation Agent       specifications → JSON test cases
              └── Test Execution pipeline     runs the cases in Playwright (no LLM)
                    └── failures → work orders → one correction round
```

Every agent is built with `langchain.agents.create_agent` on `gpt-5.4`, and each has its
**own state schema, tools and middleware**. `deepagents` supplies the
`FilesystemMiddleware` and filesystem backends the developer agents write through.
Agents never call each other: they communicate only through typed state fields that the
orchestrator tools set, so every guard (the round cap, the work-order capture) sits on
one boundary.

### The four specifications

| Schema | Purpose |
|---|---|
| `LayoutSpecification` | Page layout: regions and layout types (`grid`, `flex-row`, …) |
| `ComponentSpecification` | Component tree: tags, `componentCategory`, data bindings, states, events |
| `InteractionSpecification` | Event → action flows: `addToCart`, `applyFilter`, `toggleWishlist`, … |
| `DecorationSpecification` | Visual tokens and per-component, per-state styles |

They are produced once per run and shared by every developer agent and by Test
Generation. Three contracts derived from them hold the system together:

- **Naming Contract**: a spec component's `id` / `className` becomes the element's
  `id` / `class` in the HTML.
- **Selector Contract**: tests locate a component by `.className` if it has one, else
  `#id`.
- **State Materialization Contract**: every declared state is on the DOM at rest, as
  `aria-*` or `data-state` attributes, so CSS, JS and the tests can all address it.

Page types: `home`, `plp`, `pdp`, `cart`, `checkout`, `account`, `search`.

### Test Generation and Test Execution

Test Generation is an LLM agent that writes **structured JSON test cases**, not
`.spec.ts` files. Test Execution is a **pipeline, not an agent**: it interprets those
cases directly through Playwright's Python API (clicks, typing, hovering, and
assertions on text, attributes, used CSS values and the URL fragment). It needs no LLM,
so the verdict on a page never depends on a model's judgement. Its report is turned
into work orders for the agent that owns each failure.

---

## Design Principles

**LLMs decide, Python guarantees.** The prompt tells a model what to do; a Python guard
tool makes sure it happened. Each developer agent's store tool runs a coverage check
first (is every specified component present and addressable? is every state
materialised?) and refuses an incomplete submission before linting even starts. The
correction loop's cap of one round is enforced in code, not asked for in a prompt.

**Self-correcting developer agents.** HTML, CSS and JS each loop generate → lint
(`html-validate`, `stylelint`, `eslint`) → fix until the linter is clean, then save.

**Edits trust the diff's body, not its header.** In modify mode an agent sends a unified
diff. Models routinely miscalculate the `@@` line numbers but copy the lines correctly,
so the patcher takes the position and length from the body, relocating only on a unique
context match.

**A guard the model cannot satisfy is a wall.** Every refusal comes with prompt text that
tells the model how to produce an acceptable answer, and no other rule may forbid it.

**Generate vs modify.** Only two intents exist. Modify mode extracts the target
component, applies a diff and re-validates, leaving the rest of the page untouched.
Structural changes are not allowed in modify mode, because the specifications go stale
once a page is hand-edited.

---

## Tech Stack

| Area | Library / tool |
|---|---|
| Agents | `langchain` (`create_agent`), `langgraph`, `langchain-openai` (`gpt-5.4`) |
| Agent filesystem | `deepagents` (`FilesystemMiddleware`, filesystem backends) |
| Conversation persistence | `langgraph-checkpoint-sqlite` (`SqliteSaver`) |
| Specifications | Pydantic |
| Web search | `tavily-python` |
| HTML handling | `beautifulsoup4` |
| Linting | `html-validate`, `stylelint`, `eslint` (Node, via `npx`) |
| Test Execution | Playwright (Python API, Chromium) |
| UI | Streamlit, with a local preview server for the generated page |
| Tracing | LangSmith (optional) |
| Packaging | Docker, Docker Compose, GitHub Actions |

---

## Project Structure

```
.
├── webforge/                   # The multi-agent system, one module per part
│   ├── core.py                 # shared LLM backbone and helpers
│   ├── context_agent.py        # Context Engineering Agent
│   ├── specs.py                # the four specification schemas and generators
│   ├── dev_shared.py, dev_agent.py   # shared developer-agent machinery
│   ├── html_agent.py, css_agent.py, js_agent.py
│   ├── test_gen_agent.py       # Test Generation Agent
│   ├── test_exec.py            # Test Execution entry point
│   ├── test_execution/         # the Test Execution pipeline (Playwright)
│   ├── secondary_orchestrator.py, primary_orchestrator.py
│   ├── config.py               # every filesystem path
│   ├── contract.py             # the UI ↔ agent wire contract
│   └── entry.py                # the graph the UI and LangGraph load
├── stream_lit.py               # Streamlit chat UI
├── ui_assets/                  # the UI's CSS and JS
├── bridge.py                   # streams graph progress to the UI
├── tools/                      # mock backend (no-key demo), UI smoke test, run tracing
├── tests/                      # offline pytest suite; tests/live_cells/ are paid live suites
├── run_live_suite.py           # runs one live suite (calls the OpenAI API)
├── static/preview/             # generated pages: preview_<session_id>.{html,css,js}
├── Dockerfile, docker-compose.yml
├── requirements.txt, package.json
├── .env.example                # copy to .env and add your keys
└── GLOSSARY.md                 # the project's terms
```

---

## Setup & Usage

You need two API keys: an **OpenAI** key (the agents run on `gpt-5.4`) and a
**Tavily** key (the Context Engineering Agent's web search). Every generate run calls
the OpenAI API and is billed to that key.

### Option A: Docker (recommended)

Only [Docker Desktop](https://www.docker.com/products/docker-desktop/) is needed.
Python, Node, the linters and Playwright's Chromium are all installed inside the image.

```bash
git clone https://github.com/qing123777/WebForge.git
cd WebForge
cp .env.example .env          # then put your OPENAI_API_KEY and TAVILY_API_KEY in .env
docker compose up --build webforge
```

Open <http://localhost:8501>. The first build takes several minutes; later starts are fast.
Generated pages are written to `static/preview/` on your machine.

**Try the UI without an API key.** The `demo` service runs the same interface on a
scripted backend. It costs nothing and needs no `.env`, but it does not really
generate: it replays a fixed coffee-shop page.

```bash
docker compose up --build demo
```

Stop either one with `Ctrl+C`, or `docker compose down`.

### Option B: install locally

Prerequisites: Python 3.10+ and Node.js 20.19+.

```bash
git clone https://github.com/qing123777/WebForge.git
cd WebForge
pip install -r requirements.txt
playwright install chromium   # the browser Test Execution drives
npm install                   # html-validate, stylelint, eslint
cp .env.example .env          # then put your OPENAI_API_KEY and TAVILY_API_KEY in .env
streamlit run stream_lit.py
```

The no-key demo is `streamlit run tools/mock_ui.py`.

---

## Testing

Two independent axes: **scope** (unit → agent → cross-agent → system) and
**environment** (offline with scripted models, or live against the real model).

```bash
pip install pytest
pytest                        # the offline suite: about 550 tests, no API calls
python tools/ui_smoke.py      # 9 browser steps through the real UI on the mock backend
```

`tests/conftest.py` sets dead API keys before anything is imported, so an offline test
that reaches a model by mistake fails instead of costing money. On every push to `main`,
GitHub Actions builds the Docker image on a clean machine and runs both of the above
inside it (`.github/workflows/docker-smoke.yml`).

The live suites (`python run_live_suite.py <suite>`, `--dry-run` to see the plan) call
the real model and cost money.

---

## Contributors

**Name**
1. [Lim Qing](https://github.com/qing123777)
