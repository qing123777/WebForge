"""context_agent: the Context Engineering Agent: ContextState, themes, DesignSchema, its tools and agent.

Lines 518-1517 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

from webforge.core import *  # noqa: F401,F403

# ==========================================================================
# Memory & State
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# ContextState - the shared notepad the Context Engineering Agent writes to
#
# Every field an agent may write has to be declared here first. LangGraph drops
# a write to a field it does not know about. It logs the drop and carries on,
# so the symptom is an empty result rather than an error.
#
# This class used to be called `state`, and three different classes shared that
# one name. Only the last survived as an importable name, and it declared two
# of these eight fields. Anything built against it would have lost every
# specification write, silently. The name is gone. Each schema now has its own.
# ═══════════════════════════════════════════════════════════════════════════
from typing import Any, Dict

from langchain.agents.middleware import AgentState
from pydantic import Field


class ContextState(AgentState):
    input_query: str = Field(default="", description="User request for this run.")
    compiled_query: str = Field(default="", description="Optional concise query for downstream processing.")
    design_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured planning schema, including meta fields.",
    )
    tavily_search_result: str = Field(default="")
    layout_specification: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured layout specification for UI generation.",
    )
    components_specification: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured components specification for UI generation.",
    )
    interactions_specification: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured interactions specification for UI generation.",
    )
    decoration_specification: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured decorations specification for UI generation.",
    )


# ==========================================================================
# extract_intent_signals
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# Theme library -- predefined VISUAL token bundles (warm-artisanal first)
#
# A THEME is the visual mood: colours, a font pairing, a type scale, spacing and
# radius. It is a DIFFERENT axis from ui.style (DesignStyle), which is the
# CONTENT emphasis (catalog-heavy, minimal-premium ...). The chosen theme is a
# NAME on design_schema.theme.name (Model A: the user picks a predefined theme,
# the system does not invent colours). _build_token_bundle looks it up; unknown
# or absent -> the default. Theme.primary_color/secondary_color were dropped
# 2026-08-24 -- free-form colour was the 'invent your own' path we removed.
#
# Why predefine: a curated bundle lets the decoration/CSS step APPLY tokens
# instead of inventing colours, which is how v0 stays visually consistent (it
# stands on shadcn's tokens). The values are grounded, not taste: Fraunces
# (serif display) + Inter (body) is a proven Google-Fonts pairing; the palette
# is a warm paper/espresso set; spacing is a 4/8pt grid; the type scale is a
# modular progression. Each bundle carries >= 6 custom properties, so a
# stylesheet built from it clears the Design Token Contract's :root floor by
# construction.
# ═══════════════════════════════════════════════════════════════════════════

_THEME_LIBRARY = {
    "warm-artisanal": {
        "label": "Warm artisanal",
        "mood": ("warm, earthy, handmade; a serif display over a clean sans, "
                 "paper and espresso tones, generous whitespace"),
        "google_fonts": ["Fraunces:opsz,wght@9..144,400;9..144,600",
                         "Inter:wght@400;500;600"],
        "tokens": {
            "--color-bg": "#faf5ee",
            "--color-surface": "#ffffff",
            "--color-text": "#2b1d12",
            "--color-muted": "#7a6a5a",
            "--color-accent": "#b5642a",
            "--color-accent-strong": "#8f4c1e",
            "--color-border": "#e4d8c8",
            "--font-heading": "'Fraunces', Georgia, 'Times New Roman', serif",
            "--font-body": "'Inter', system-ui, -apple-system, sans-serif",
            "--radius": "8px",
            "--radius-lg": "16px",
            "--space-1": "4px",
            "--space-2": "8px",
            "--space-3": "12px",
            "--space-4": "16px",
            "--space-6": "24px",
            "--space-8": "32px",
            "--space-12": "48px",
            "--shadow-card": ("0 1px 3px rgba(43,29,18,0.08), "
                              "0 8px 24px rgba(43,29,18,0.06)"),
        },
        "type_scale_px": [12, 14, 16, 18, 22, 28, 36, 48],
    },
    # Slate minimal -- based on shadcn's "Slate" base palette (its default
    # neutral look). Cool near-black slate on white; a modern grotesque display
    # over a clean sans. Suits electronics / apparel / minimal-premium stores.
    "slate-minimal": {
        "label": "Slate minimal",
        "mood": ("cool, minimal, premium; near-black slate on white, a modern "
                 "grotesque display over a clean sans, restrained accents"),
        "google_fonts": ["Space Grotesk:wght@500;600;700",
                         "Inter:wght@400;500;600"],
        "tokens": {
            "--color-bg": "#f8fafc",
            "--color-surface": "#ffffff",
            "--color-text": "#0f172a",
            "--color-muted": "#64748b",
            "--color-accent": "#1e293b",
            "--color-accent-strong": "#0f172a",
            "--color-border": "#e2e8f0",
            "--font-heading": "'Space Grotesk', 'Segoe UI', system-ui, sans-serif",
            "--font-body": "'Inter', system-ui, -apple-system, sans-serif",
            "--radius": "6px",
            "--radius-lg": "12px",
            "--space-1": "4px",
            "--space-2": "8px",
            "--space-3": "12px",
            "--space-4": "16px",
            "--space-6": "24px",
            "--space-8": "32px",
            "--space-12": "48px",
            "--shadow-card": ("0 1px 2px rgba(15,23,42,0.06), "
                              "0 8px 24px rgba(15,23,42,0.06)"),
        },
        "type_scale_px": [12, 14, 16, 18, 22, 28, 36, 48],
    },
    # Rose boutique -- based on shadcn's "Rose" base palette. A rose accent on
    # warm white, a classic serif display over a clean sans, rounded and
    # inviting. Suits beauty / fashion / lifestyle stores.
    "rose-boutique": {
        "label": "Rose boutique",
        "mood": ("soft, feminine, boutique; a rose accent on warm white, a "
                 "classic serif display over a clean sans, rounded and inviting"),
        "google_fonts": ["Playfair Display:wght@500;600;700",
                         "Inter:wght@400;500;600"],
        "tokens": {
            "--color-bg": "#fff7f8",
            "--color-surface": "#ffffff",
            "--color-text": "#1c1917",
            "--color-muted": "#78716c",
            "--color-accent": "#e11d48",
            "--color-accent-strong": "#be123c",
            "--color-border": "#f1dede",
            "--font-heading": "'Playfair Display', Georgia, 'Times New Roman', serif",
            "--font-body": "'Inter', system-ui, -apple-system, sans-serif",
            "--radius": "10px",
            "--radius-lg": "20px",
            "--space-1": "4px",
            "--space-2": "8px",
            "--space-3": "12px",
            "--space-4": "16px",
            "--space-6": "24px",
            "--space-8": "32px",
            "--space-12": "48px",
            "--shadow-card": ("0 1px 3px rgba(28,25,23,0.06), "
                              "0 10px 30px rgba(225,29,72,0.07)"),
        },
        "type_scale_px": [12, 14, 16, 18, 22, 28, 36, 48],
    },
    # Midnight bold -- a DARK theme (the only one), based on shadcn's "Zinc"
    # neutral scale with an electric lime accent. Near-black surfaces, high
    # contrast, sharp small radius, a geometric display. Suits sneaker / tech /
    # gaming / streetwear stores that want energy and punch.
    "midnight-bold": {
        "label": "Midnight bold",
        "mood": ("dark, high-contrast, energetic; near-black zinc surfaces with "
                 "an electric lime accent, a geometric display over a clean sans"),
        "google_fonts": ["Sora:wght@500;600;700",
                         "Inter:wght@400;500;600"],
        "tokens": {
            "--color-bg": "#09090b",
            "--color-surface": "#18181b",
            "--color-text": "#fafafa",
            "--color-muted": "#a1a1aa",
            "--color-accent": "#a3e635",
            "--color-accent-strong": "#84cc16",
            "--color-border": "#27272a",
            "--font-heading": "'Sora', 'Segoe UI', system-ui, sans-serif",
            "--font-body": "'Inter', system-ui, -apple-system, sans-serif",
            "--radius": "4px",
            "--radius-lg": "10px",
            "--space-1": "4px",
            "--space-2": "8px",
            "--space-3": "12px",
            "--space-4": "16px",
            "--space-6": "24px",
            "--space-8": "32px",
            "--space-12": "48px",
            "--shadow-card": ("0 1px 2px rgba(0,0,0,0.40), "
                              "0 8px 24px rgba(0,0,0,0.50)"),
        },
        "type_scale_px": [12, 14, 16, 18, 22, 28, 36, 48],
    },
    # Playful pop -- a BRIGHT, saturated theme based on shadcn's "Violet" accent
    # on a soft violet-white. Rounded corners, a friendly rounded display. Suits
    # toys / snacks / kids / lifestyle stores that want fun and approachability.
    "playful-pop": {
        "label": "Playful pop",
        "mood": ("bright, playful, saturated; a bold violet accent on soft "
                 "violet-white, rounded corners, a friendly rounded display"),
        "google_fonts": ["Poppins:wght@500;600;700",
                         "Inter:wght@400;500;600"],
        "tokens": {
            "--color-bg": "#faf5ff",
            "--color-surface": "#ffffff",
            "--color-text": "#2e1065",
            "--color-muted": "#6b7280",
            "--color-accent": "#7c3aed",
            "--color-accent-strong": "#6d28d9",
            "--color-border": "#ede9fe",
            "--font-heading": "'Poppins', 'Segoe UI', system-ui, sans-serif",
            "--font-body": "'Inter', system-ui, -apple-system, sans-serif",
            "--radius": "14px",
            "--radius-lg": "24px",
            "--space-1": "4px",
            "--space-2": "8px",
            "--space-3": "12px",
            "--space-4": "16px",
            "--space-6": "24px",
            "--space-8": "32px",
            "--space-12": "48px",
            "--shadow-card": ("0 1px 3px rgba(124,58,237,0.10), "
                              "0 10px 30px rgba(124,58,237,0.12)"),
        },
        "type_scale_px": [12, 14, 16, 18, 22, 28, 36, 48],
    },
}
_THEME_DEFAULT = "warm-artisanal"


# The shared LAYOUT PRESET -- one set for ALL themes (user decision 2026-08-25:
# regularity is universal; themes vary mood/colour, not grid math). Folded into
# every bundle's globalTokens by _bundle_global_tokens, so it reaches the CSS
# stage as :root custom properties. The CSS prompt's LAYOUT SYSTEM block says how
# to APPLY them (centered container, product grid, fixed-ratio image box). These
# are the values Codex/v0 write from trained reflex; we write them down as data.
_LAYOUT_PRESET = {
    "--page-max-width": "1200px",
    "--page-gutter": "clamp(1rem, 4vw, 3.5rem)",
    "--section-gap": "clamp(3rem, 8vw, 6rem)",
    "--grid-min": "220px",
    "--grid-gap": "1rem",
    "--card-aspect": "4 / 3",
}


def _build_token_bundle(design_schema=None):
    """Look up the token bundle for the run's chosen theme. Model A is "pick a
    predefined theme", not "invent colours": design_schema.theme.name selects a
    bundle; unknown or absent -> the default. No LLM, no derivation, no network.
    Call it ONCE at the top of run_planning_pipeline so every generator shares the
    same bundle. Returns the bundle dict."""
    theme = {}
    if isinstance(design_schema, dict):
        theme = design_schema.get("theme") or {}
        if not isinstance(theme, dict):
            theme = {}
    name = str(theme.get("name") or "").strip().lower().replace(" ", "-")
    return _THEME_LIBRARY.get(name, _THEME_LIBRARY[_THEME_DEFAULT])


def _theme_root_block(theme):
    """The `:root { ... }` block the chosen theme's tokens become -- ready to
    seed the Decoration Global Tokens or hand to the CSS agent verbatim."""
    body = "\n".join(f"  {k}: {v};" for k, v in theme["tokens"].items())
    return ":root {\n" + body + "\n}"


def _bundle_global_tokens(theme):
    """Group the chosen theme's flat CSS custom properties into the six
    DesignTokens buckets (colors / typography / spacing / borders / shadows /
    radii) that DecorationSpecification.globalTokens expects. Deterministic; the
    decoration stage copies this object instead of inventing colours."""
    t = theme.get("tokens", {})
    buckets = {"colors": {}, "typography": {}, "spacing": {},
               "borders": {}, "shadows": {}, "radii": {}}
    for k, v in t.items():
        if k.startswith("--color-"):
            buckets["colors"][k] = v
        elif k.startswith("--font-"):
            buckets["typography"][k] = v
        elif k.startswith("--space-"):
            buckets["spacing"][k] = v
        elif k.startswith("--radius"):
            buckets["radii"][k] = v
        elif k.startswith("--shadow-"):
            buckets["shadows"][k] = v
    # the shared layout preset rides along in every theme (see _LAYOUT_PRESET)
    buckets["spacing"].update(_LAYOUT_PRESET)
    return buckets


def _theme_tokens_block(theme):
    """The design-tokens instruction the decoration stage receives: the exact
    globalTokens object to emit (copy it, do not invent) plus the fonts to load
    and the type scale. Keeps the LLM off raw hex; every bundle clears the CSS
    :root token floor by construction."""
    import json as _json
    tokens = _bundle_global_tokens(theme)
    fonts = ", ".join(f.split(":")[0] for f in theme.get("google_fonts", []))
    scale = ", ".join(str(n) for n in theme.get("type_scale_px", []))
    return (
        f'CHOSEN THEME: "{theme.get("label", "")}" -- {theme.get("mood", "")}\n'
        f"Google Fonts to load: {fonts}\n"
        "Emit globalTokens EXACTLY as this object. Copy it: do not rename a key,\n"
        "change a value, drop a group, or invent a colour outside it.\n"
        + _json.dumps(tokens, ensure_ascii=False, indent=2) + "\n"
        f"Type scale in px (small to large), use these for font sizes: {scale}\n"
        "Every colour in any component decoration must be one of the colour tokens\n"
        "above (reference the token, never a raw hex that is not listed)."
    )


def _theme_choice_catalog():
    """The theme menu handed to Context Engineering: one 'name: mood' line per
    predefined theme, built from the library so the prompt and the library never
    drift. CE puts the chosen name into design_schema.theme.name, or leaves it
    null (then _build_token_bundle uses the default)."""
    return "\n".join(
        f'- {name}: {bundle.get("mood", "")}'
        for name, bundle in _THEME_LIBRARY.items()
    )


print(f"Theme library ready: {list(_THEME_LIBRARY)} (default {_THEME_DEFAULT}, "
      f"{len(_THEME_LIBRARY[_THEME_DEFAULT]['tokens'])} tokens)")


# ==========================================================================
# extract_intent_signals
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# Design schema — what the Context Engineering Agent produces
#
# FIXED_TECH_STACK is a constant, not a preference. The generated app is always
# plain HTML, CSS and JavaScript with no build step, so the validator below
# overwrites whatever the model puts in that field rather than trusting it.
# ═══════════════════════════════════════════════════════════════════════════
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# What KIND of shop this is. It decides what the page must contain: a marketplace
# needs a seller name on every card, a subscription shop needs a plan picker, a
# flash-sale shop needs a countdown. Until 2026-08-15 there was no field for any
# of this, so "build me a marketplace" and "build me a brand store" produced the
# same page. The values follow the standard retail classification.
CommerceType = Literal[
    "single_brand",           # one company sells only its own products
    "multi_brand_retailer",   # one retailer sells many brands
    "marketplace",            # many independent sellers, one platform
    "direct_to_consumer",     # maker sells straight to the public, no retailer
    "subscription",           # recurring delivery on a plan
    "digital_products",       # software, courses, ebooks, game items
    "on_demand",              # purchase tied to immediate delivery or service
    "flash_sale",             # limited quantity, countdowns, deep discounts
    "customisable_products",  # the buyer configures the product before paying
    "social_discovery",       # feeds, trends and user content drive browsing
]

# HOW that content is presented. Separate from CommerceType on purpose: the same
# shop can be laid out as a dense catalogue or as a sparse premium showcase.
# It was a free-text field until 2026-08-15, so the CSS agent had no fixed set of
# words to respond to and mostly ignored it.
DesignStyle = Literal[
    "catalog_heavy",           # many products, filters, sorting, comparison
    "minimal_premium",         # large imagery, generous whitespace, few controls
    "visual_first",            # photography and collections lead
    "information_heavy",       # specifications, comparison tables, reviews
    "promotion_heavy",         # banners, vouchers, countdowns, bundles
    "single_product_landing",  # one product, long scroll toward one purchase
    "personalised",            # recommendation strips and recently-viewed rows
]
# One-page commerce is NOT in that list. It is this system's fixed structure, not
# a style the user chooses -- every run produces exactly one document.


class UI(BaseModel):
    type: Optional[str] = Field(
        default=None,
        description=(
            "The ONE page type this run builds. A run produces a single document, "
            "so several requested areas become regions of it rather than separate "
            "values here. "
            "(e.g., landing_page, product_listing, product_detail, cart, checkout, account, search)"
        ),
    )
    commerce_type: Optional[CommerceType] = Field(
        default=None,
        description=(
            "What kind of shop this is. It decides what the page must CONTAIN. "
            "Leave null if the request gives no signal, and the planner applies "
            "the single_brand defaults."
        ),
    )
    style: Optional[DesignStyle] = Field(
        default=None,
        description=(
            "How the content is PRESENTED. Pick the closest value. Map loose "
            "words onto it: 'luxury' or 'premium' or 'clean' -> minimal_premium, "
            "'lots of products' -> catalog_heavy, 'specs and reviews' -> "
            "information_heavy, 'deals' or 'sale' -> promotion_heavy. Leave null "
            "if the request says nothing about looks."
        ),
    )
    density: Optional[str] = Field(
        default=None,
        description="Information density / spacing (e.g., comfortable, compact).",
    )
    navigation: Optional[str] = Field(
        default=None,
        description="Navigation pattern (e.g., top_nav, side_nav, hamburger, none).",
    )


class Theme(BaseModel):
    name: Optional[str] = Field(default=None, description="Chosen predefined theme name (e.g. 'warm-artisanal'); the visual token bundle is looked up from this. The system does not invent free-form colours.")
    mode: Optional[str] = Field(default=None, description="Light or dark mode preference.")


FIXED_TECH_STACK: List[Literal["html", "css", "javascript"]] = ["html", "css", "javascript"]


class Constraints(BaseModel):
    tech_stack: List[Literal["html", "css", "javascript"]] = Field(
        default_factory=lambda: FIXED_TECH_STACK.copy(),
        description="Fixed constant. Always ['html','css','javascript']; do not change.",
    )

    @field_validator("tech_stack", mode="before")
    @classmethod
    def force_fixed_tech_stack(cls, _v):
        return FIXED_TECH_STACK.copy()


class DesignSchema(BaseModel):
    ui: UI = Field(default_factory=UI)
    theme: Theme = Field(default_factory=Theme)
    constraints: Constraints = Field(default_factory=Constraints)
    extra_requirements: List[str] = Field(
        default_factory=list,
        description=(
            "Catch-all requirements that don't fit other fields. "
            "Use short, specific strings (<= 12 words each)."
        ),
    )


# ==========================================================================
# extract_intent_signals
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# Model handles for the Context Engineering Agent's tools
#
# Each handle has its own name on purpose. Both were once called `model`, with
# the name simply rebound partway down. That is safe in a file that runs once
# from top to bottom. It is not safe in a notebook, where re-running one cell
# rebinds the name and the next chain built captures the wrong model, silently.
#
# Both handles run the same model. They ran different ones once, with nothing
# recorded to say why, so they were brought into line on 2026-08-14.
# ═══════════════════════════════════════════════════════════════════════════
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

_intent_model = ChatOpenAI(model_name="gpt-5.4", temperature=0.0, timeout=120, max_retries=2)
_extra_requirements_model = ChatOpenAI(model_name="gpt-5.4", temperature=0.0, timeout=120, max_retries=2)

_str_parser = StrOutputParser()


# ==========================================================================
# extract_intent_signals
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# extract_intent_signals — turn the user's sentence into a design schema
#
# The prompt has its own name because a second, unrelated prompt further down
# used to share it. Two chains built from one name is a bug waiting for the
# wrong cell to be re-run.
# ═══════════════════════════════════════════════════════════════════════════
from langchain_core.prompts import PromptTemplate
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

# ── The worked example is BUILT BY the schema, never written beside it ───────
# It used to be a hand-typed JSON block, and it set `style` to "modern". On
# 2026-08-15 `style` became a Literal of seven values, "modern" stopped being one
# of them, and the one example the model had left showed an illegal answer with
# nothing to report it.
#
# Constructing it through DesignSchema fixes that permanently. An illegal value
# raises here, at build time, in a cell the offline runner executes. A field added
# to the schema appears in the example on its own.
def _schema_example_json() -> str:
    """One filled DesignSchema, rendered as the JSON the model must return."""
    return DesignSchema(
        ui=UI(type="product_listing",
              commerce_type="multi_brand_retailer", style="catalog_heavy",
              density="compact", navigation="top_nav"),
        theme=Theme(mode="dark"),
        constraints=Constraints(),
        extra_requirements=["Sticky promo banner on scroll"],
    ).model_dump_json(indent=2)


def _schema_vocabularies() -> str:
    """The four fixed word lists, read out of the schema itself."""
    import typing as _t
    rows = []
    for name, literal in (("commerce_type", CommerceType),
                          ("style", DesignStyle)):
        rows.append(f"- ui.{name}: " + " | ".join(_t.get_args(literal)))
    return "\n".join(rows)


def _build_intent_extraction_template() -> str:
    """The extraction prompt, with the example and the vocabularies filled in.

    PromptTemplate treats a brace as a placeholder, so the JSON braces are
    doubled before they go in. Only {query} survives as a real placeholder.
    """
    example = _schema_example_json().replace("{", "{{").replace("}", "}}")
    return """Extract the user's request into a DesignSchema.

WHAT TO FILL, AND WHAT TO LEAVE NULL
- Never invent a brand, a colour, or a feature the user did not ask for.
- ALWAYS map the words the user DID use onto the fixed lists below. Those lists
  exist so that a loose phrase becomes a value the rest of the system can act on.
  A null where the request gave a signal is a dropped requirement, not caution.
- A vague compliment is not a signal. "modern", "nice" and "clean" on their own
  fill nothing. A concrete phrase is a signal: "compact grid" and "filters" give
  catalog_heavy, "sale" and "countdown" give promotion_heavy.
- Anything with no home in a field goes in extra_requirements, 12 words or fewer.

FIXED LISTS (use one of these words exactly, or null)
""" + _schema_vocabularies() + """

THEME (visual mood -- choose ONE theme by NAME from this list, or null)
Pick the theme whose mood best fits the request. A mood word ("minimal",
"luxury", "boutique", "handmade", "cosy", "playful") is a signal; map it onto
the closest theme. If nothing signals a mood, leave theme.name null and the
system uses its default. Never invent a name that is not listed, and never
invent colours.
{theme_catalog}

OUTPUT
- Valid JSON matching DesignSchema. No markdown, no explanation, no extra keys.
- Use null or [] for anything the request does not signal.

WORKED EXAMPLE
Query: 'Build a modern dark-mode product listing page for a sneaker store that
stocks Nike, Adidas and New Balance. It needs filters, sorting, search, a cart
and a wishlist, a top nav and a compact grid, and a sticky promo banner. It has
to work well on phones and on desktops.'

Output:
""" + example + """

Why that example filled what it filled:
- multi_brand_retailer because three brands are named, not because it sells shoes.
- catalog_heavy because of "compact grid" and "filters", not because of "modern".
- "modern" filled nothing at all. It is a compliment, not a specification.
- theme.name was left null: "modern" is a compliment, not a mood, so no theme
  was signalled and the system default applies.

Now extract from the real query.
Query: {query}
"""


_intent_extraction_prompt = PromptTemplate.from_template(
    _build_intent_extraction_template())


extract_intent_signals_chain = _intent_extraction_prompt | _intent_model.with_structured_output(DesignSchema, method="function_calling")

extract_intent_signals_tool = extract_intent_signals_chain.as_tool(
    name="extract_intent_signals",
    description="Extract renderable UI/UX intent signals from a query and persist a DesignSchema payload",
    arg_types={"query": str, "theme_catalog": str},
)


@tool
def extract_intent_signals(runtime: ToolRuntime[ContextState]) -> Command:
    """Run intent signal extraction tool and persist the result into state.design_schema."""
    s = runtime.state
    query = s["input_query"]

    result_obj = extract_intent_signals_tool.invoke({"query": query, "theme_catalog": _theme_choice_catalog()})
    result = result_obj.model_dump() if hasattr(result_obj, "model_dump") else result_obj

    return Command(
        update={
            "design_schema": result,
            "messages": [
                ToolMessage(content="Stored design_schema from extract_intent_signals", tool_call_id=runtime.tool_call_id)
            ],
        }
    )


# ==========================================================================
# tavily_search
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# tavily_search_tool — look up time-sensitive design context on the web
#
# The search is deliberately failure-tolerant. An outage, a missing key or a
# rate limit all return an empty string rather than raising, because a run must
# not die over background reading that only enriches the schema.
#
# There used to be two copies of this helper and two identical clients behind
# them. One of each survives.
# ═══════════════════════════════════════════════════════════════════════════
import json
import os

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from tavily import TavilyClient
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

tavily_search_query_prompt = PromptTemplate.from_template(
    "Given user query: {query}\n"
    "Rewrite it into a short web search query (<= 12 words).\n"
    "Return only the rewritten search query."
)

tavily_search_query_chain = tavily_search_query_prompt | _intent_model | _str_parser


def safe_tavily_search(search_query: str) -> str:
    if not search_query.strip():
        return ""
    try:
        res = tavily_client.search(search_query, max_results=5)
        return json.dumps(res, ensure_ascii=False)
    except Exception:
        return ""


_tavily_summary_prompt = PromptTemplate.from_template(
    "Given user query: {query}\n"
    "Raw Tavily results (JSON): {search_result}\n\n"
    "Task: Summarize ONLY time-sensitive UI/UX relevant context into <= 6 bullet points.\n"
    "Rules:\n"
    "- Output plain text only (no markdown fencing).\n"
    "- If results are empty/irrelevant, return empty string.\n"
)

tavily_chain = (
    {
        "query": lambda x: x["query"],
        "search_query": tavily_search_query_chain,
    }
    | RunnableLambda(
        lambda x: {
            "query": x["query"],
            "search_result": safe_tavily_search(x["search_query"]),
        }
    )
    | _tavily_summary_prompt
    | _intent_model
    | _str_parser
)

tavily_tool = tavily_chain.as_tool(
    name="tavily_search_tool",
    description="Web search the time-based needs (e.g., 'latest design trends') and return a concise summary.",
    arg_types={"query": str},
)


@tool
def tavily_search_tool(runtime: ToolRuntime[ContextState]) -> Command:
    """Run Tavily search tool and persist the result into agent state."""
    s = runtime.state
    query = s["input_query"]

    result_obj = tavily_tool.invoke({"query": query})
    result = result_obj.model_dump() if hasattr(result_obj, "model_dump") else result_obj

    return Command(
        update={
            "tavily_search_result": result,
            "messages": [ToolMessage(content="Stored tavily_search_result", tool_call_id=runtime.tool_call_id)],
        }
    )


# ==========================================================================
# update_extra_requirements
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# update_extra_requirements — fold web findings into the design schema
#
# This tool touches ONE field and nothing else. It appends short items to the
# schema's catch-all requirements list. Everything the user actually asked for
# stays exactly as the extraction step left it, so a web search can never
# overwrite a stated requirement.
#
# Duplicates are dropped case-insensitively, and each item is cut to twelve
# words, because these strings are read by the planning chain and a paragraph
# pasted in from a search result would drown the real requirements.
# ═══════════════════════════════════════════════════════════════════════════
import json
from typing import Any, Dict, List

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

class ExtraRequirementsUpdate(BaseModel):
    items: List[str] = Field(
        default_factory=list,
        description="New time-related UI/UX items to append into DesignSchema.extra_requirements (<= 12 words each).",
    )


def _normalize_schema_payload(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


def _clean_item(text: Any, *, max_words: int = 12) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    words = [word for word in s.split() if word]
    if len(words) > max_words:
        s = " ".join(words[:max_words]).strip()
    return s


def _merge_extra_requirements(schema_payload: Any, new_items: List[str]) -> Dict[str, Any]:
    base = _normalize_schema_payload(schema_payload)
    if not base:
        base = DesignSchema().model_dump()
    validated = DesignSchema.model_validate(base).model_dump()
    existing: List[str] = list(validated.get("extra_requirements") or [])
    existing_lc = {e.strip().lower() for e in existing if isinstance(e, str) and e.strip()}

    for item in new_items or []:
        cleaned = _clean_item(item)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in existing_lc:
            continue
        existing.append(cleaned)
        existing_lc.add(key)

    validated["extra_requirements"] = existing
    return validated


update_extra_requirements_prompt = PromptTemplate.from_template(
    "Given user query: {query}\n"
    "Tavily search result (time-related context, may be empty): {tavily_search_result}\n"
    "Existing extra_requirements (JSON array): {existing_extra_requirements}\n\n"
    "Task: Extract up to 5 short time-related UI/UX requirements or trends from Tavily context that are useful to remember.\n"
    "Rules (strict):\n"
    "- Output must match ExtraRequirementsUpdate(items=[...]).\n"
    "- Each item must be <= 12 words.\n"
    "- Do NOT copy Tavily text verbatim; summarize instead.\n"
    "- Avoid duplicates with existing_extra_requirements.\n"
    "- If Tavily context is empty/irrelevant, return items=[].\n"
    "Return ONLY the structured object."
)

update_extra_requirements_chain = (
    update_extra_requirements_prompt
    | _extra_requirements_model.with_structured_output(ExtraRequirementsUpdate, method="function_calling")
)

update_extra_requirements_tool = update_extra_requirements_chain.as_tool(
    name="update_extra_requirements",
    description="Append time-related Tavily findings into design_schema.extra_requirements (only).",
    arg_types={
        "query": str,
        "tavily_search_result": str,
        "existing_extra_requirements": str,
    },
)


@tool
def update_extra_requirements(runtime: ToolRuntime[ContextState]) -> Command:
    """Update ONLY design_schema.extra_requirements using the Tavily search result."""
    s = runtime.state
    query = str(s.get("input_query", "") or "")
    tavily_search_result = str(s.get("tavily_search_result", "") or "")
    current_schema = _normalize_schema_payload(s.get("design_schema"))
    if not current_schema:
        current_schema = DesignSchema().model_dump()

    validated = DesignSchema.model_validate(current_schema).model_dump()
    existing_extra = validated.get("extra_requirements") or []
    existing_extra_json = json.dumps(existing_extra, ensure_ascii=False)

    result_obj = update_extra_requirements_tool.invoke(
        {
            "query": query,
            "tavily_search_result": tavily_search_result,
            "existing_extra_requirements": existing_extra_json,
        }
    )

    items: List[str] = []
    if hasattr(result_obj, "items"):
        items = list(getattr(result_obj, "items") or [])
    elif isinstance(result_obj, dict):
        items = list(result_obj.get("items") or [])

    merged_schema = _merge_extra_requirements(validated, items)
    return Command(
        update={
            "design_schema": merged_schema,
            "messages": [
                ToolMessage(
                    content="Updated design_schema.extra_requirements from Tavily search result",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


# ==========================================================================
# Streaming Progress Middleware
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# Progress messages from the Context Engineering Agent
#
# These write a line to the stream as the agent works, so the Streamlit chat
# shows what is happening instead of a spinner. They change nothing about the
# run.
# ═══════════════════════════════════════════════════════════════════════════
from langchain.agents.middleware import before_agent, wrap_tool_call
from langgraph.config import get_stream_writer
from langchain.agents import create_agent
from langchain.agents.middleware import before_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

@before_agent
def context_agent_progress(state, runtime):
    get_stream_writer()("   [Context Agent] Processing request...")
    return None


@wrap_tool_call
def context_tool_progress(request, handler):
    writer = get_stream_writer()
    tool_name = ""
    try:
        tool_name = (request.tool_call or {}).get("name") or ""
    except Exception:
        tool_name = ""

    if tool_name == "extract_intent_signals":
        writer("   [Context Agent] Extracting intent signals...")
    elif tool_name == "tavily_search_tool":
        writer("   [Context Agent] Searching the web for time-related information...")
    elif tool_name == "update_extra_requirements":
        writer("   [Context Agent] Updating design requirements...")
    return handler(request)


@before_agent
def context_reset_before(state, runtime):
    input_query = ""
    if isinstance(state, dict) and isinstance(state.get("input_query"), str):
        input_query = state.get("input_query", "") or ""

    if not input_query and isinstance(state, dict):
        msgs = state.get("messages") or []
        try:
            for m in reversed(list(msgs)):
                if hasattr(m, "type") and getattr(m, "type") == "human" and hasattr(m, "content"):
                    input_query = str(getattr(m, "content") or "")
                    break
                if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
                    input_query = m.get("content") or ""
                    break
        except Exception:
            pass

    return {
        "input_query": input_query,
        "design_schema": {},
        "tavily_search_result": "",
    }


# ==========================================================================
# System prompt
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# The Context Engineering Agent
#
# It reads the user's sentence and fills in the design schema. Nothing else.
# It refuses anything that is not a request for an e-commerce interface.
#
# The middleware runs in order before each invocation. The reset hook clears
# the schema and the search result, and keeps the query. Without it, a second
# message in the same conversation would extend the first message's schema
# rather than replace it.
#
# The reset hook has its own name because the orchestrator further down has a
# reset hook of its own, and the two used to share the name `reset_before`.
# ═══════════════════════════════════════════════════════════════════════════

_context_system_prompt = """
ROLE
You are the Context Engineering Agent. Read one request and fill the design schema. Nothing downstream sees the user's raw sentence, so any requirement dropped here is lost.

OUTCOME
The turn is finished only when exactly one is true:
1. `design_schema` contains a filled object and every applicable tool has run.
2. The request does not ask for an e-commerce interface, so you declined in one sentence without calling a tool.

CONSTRAINTS
- E-commerce storefront interfaces only. Decline anything else in one sentence.
- Only UI-renderable requirements. `constraints.tech_stack` is always ["html","css","javascript"].
- Do not add schema fields or invent values for a fixed list.
- Never invent a brand, a colour or a feature the user did not ask for.
- ALWAYS map the words they did use onto the fixed lists. Loose phrases must become values the rest of the system can act on. A null where the request gave a signal is a dropped requirement.
- Keep output minimal, explicit and deterministic.

TOOLS AND ORDER
- `extract_intent_signals` runs FIRST, on every request, without exception. It is the only tool that writes `design_schema`; the other tools only edit what it wrote. A turn where it never ran is incomplete regardless of what else happened.
- `tavily_search_tool` runs only when ROUTING below is satisfied. Skipping it is normal for most requests.
- `update_extra_requirements` runs only when `tavily_search_result` is non-empty.
- These are the only three tools. Do not invent another.

ROUTING (Tavily)
Call `tavily_search_tool` only when the request explicitly contains a specific year, one of "latest", "current", "trending", "this year", or a comparison between two times. Never call it for "modern", "clean" or "nice UI".

VERIFICATION
- After each tool returns, inspect the field it was supposed to write.
- A tool message that merely sounds successful is not evidence. The state field is the only evidence.
- Verify that the request's concrete words reached fields. If the request names brands, a look, or devices and those fields remain null, extraction is incomplete and the turn is not finished.

ITERATION POLICY
- If `design_schema` is still empty after `extract_intent_signals`, call the same tool again.
- At most 2 further calls, so 3 for the turn in total.
- If it is still empty after the third, stop and report what the last tool message said. Do not continue as though it worked.
- Never call a tool twice for any other reason.

ERROR HANDLING
- If the request is empty or not intelligible as a request for anything, stop and ask the user what they want built. Call no tool, and never invent a page to fill the silence.
- A tool message describing a validation failure is feedback. Call the same tool again and expect it to correct the named problem.
- You never write `design_schema` yourself. The tools write it. Describing one in prose does not produce it.
- Never paste search output into the schema. Only `update_extra_requirements` may touch `extra_requirements`.
"""


# ==========================================================================
# Agent
# ==========================================================================
_context_reasoning = _reasoning_for("context")

_context_model = ChatOpenAI(model="gpt-5.4", reasoning=_context_reasoning, timeout=120, max_retries=2)


context_engineering_agent = create_agent(
    model=_context_model,
    system_prompt=_context_system_prompt,
    tools=[extract_intent_signals, tavily_search_tool, update_extra_requirements],
    middleware=[context_agent_progress, context_reset_before, context_tool_progress],
    state_schema=ContextState,
    checkpointer=InMemorySaver(),
)


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
