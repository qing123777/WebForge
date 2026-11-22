"""specs: the four specification schemas, their repair and validation, and the four planning generators.

Lines 1518-4486 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

from webforge.context_agent import *  # noqa: F401,F403

# ==========================================================================
# Pydantic models of 4 specifications
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# The four specification schemas
#
# These 34 types are the contract the whole system is built on:
#
#   Layout       which pages exist, and which regions each page has
#   Component    the tree of elements, their tags, states and events
#   Interaction  what happens when the user clicks something
#   Decoration   how each component looks, in each of its states
#
# UISpecificationBundle checks that the four agree with each other. A component
# that styling refers to must exist in the tree. A page that interactions refer
# to must exist in the layout. Without that check, the four could each be valid
# and still describe four different pages.
#
# WHY THE STRICTNESS BELOW MATTERS
# --------------------------------
# A second, looser copy of these classes used to exist further down. It typed
# the HTML tag as a plain string and defaulted the owning agent. Either would
# fail quietly: an invented tag renders as nothing and no linter flags it, and
# a defaulted owner hands the element to the wrong developer agent. The unit
# tests below assert the strict behaviour so a paste-back cannot go unnoticed.
# ═══════════════════════════════════════════════════════════════════════════

from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field, model_validator


AgentType = Literal["HTML", "CSS", "JavaScript"]

# "home" is first because it is the commonest single-page request ("build me a
# phone shop"). It was MISSING until 2026-08-15, while the planning prompt
# carried a full "Storefront / Homepage (home)" Baymard checklist -- so the
# checklist the system most needed could never be selected, and a storefront was
# forced to masquerade as a product listing page.
PageType = Literal["home", "plp", "pdp", "cart", "checkout", "account", "search"]

LayoutType = Literal[
    "grid",
    "flex-row",
    "flex-column",
    "single-column",
    "multi-column",
    "absolute",
    "stack",
]

ResponsiveBreakpoint = Literal["mobile", "tablet", "desktop", "wide"]

HTMLTag = Literal[
    "div", "span", "section", "header", "footer", "nav", "main",
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "img", "video", "picture",
    "a",
    "ul", "ol", "li",
    "form", "input", "button", "label", "select", "option", "textarea",
    "article", "aside", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "td", "th",
]

ActionType = Literal[
    "updateState", "navigate",
    "toggleVisibility", "updateData", "showFeedback", "emit",
    "addToCart", "updateQuantity",
    "applyFilter", "clearFilter", "toggleWishlist",
    # A checkout moves through stages and ends in a completed order. Without
    # names for those two, a five-stage flow had to be described as a pile of
    # updateState actions and nothing downstream could tell it apart from a
    # hover effect.
    "advanceStep", "submitOrder",
]

ComponentCategory = Literal[
    # Navigation & structure
    "navbar", "footer", "breadcrumb",
    # Product display
    "product-card", "product-grid", "product-image-gallery",
    "product-price", "product-rating",
    # Filtering & sorting
    "filter-panel", "sort-bar",
    # Cart & checkout
    "mini-cart", "cart-item", "add-to-cart-button",
    "order-summary", "checkout-form", "payment-form",
    # The step indicator and the confirmation panel had no category until
    # 2026-08-15, so every role-based rule -- the image rule, the preview's
    # select mode, any future guard -- was blind to them. A checkout that never
    # advanced looked identical to one that did.
    "checkout-steps", "order-confirmation",
    # Product interaction
    "size-picker", "quantity-selector", "wishlist-button",
    # Search
    "search-bar", "search-results",
    # Pagination & promotions
    "pagination", "promo-banner",
    # Account
    "account-profile", "order-history",
    # General
    "hero-section",
]

RECOMMENDED_STATES = {
    "idle", "hover", "active", "focus", "focus-within",
    "disabled", "loading", "success", "error",
    "selected", "expanded", "collapsed", "empty",
    "checked", "unchecked", "indeterminate",
    "open", "closed",
}


class Region(BaseModel):
    name: str = Field(
        description="Region name. Unique within a page. Used as the dict key in ComponentSpec.regionComponents."
    )
    ownedBy: AgentType = Field(
        description="Default agent ownership for this region. Components inside MAY override this at the ComponentNode level."
    )
    layoutType: LayoutType = Field(
        description="How child components are arranged within this region (grid, flex-row, etc.)."
    )


class Page(BaseModel):
    pageName: str = Field(description="Unique page identifier. Primary linking key across ALL specs.")
    pageType: PageType = Field(
        description="B2C page type. Drives which components and interactions are expected."
    )
    pageLayoutType: LayoutType = Field(
        description="Top-level layout strategy for arranging regions on the page."
    )
    responsive: bool = Field(default=True)
    regions: List[Region] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_region_names(self):
        names = [r.name for r in self.regions]
        if len(names) != len(set(names)):
            raise ValueError(f"Page '{self.pageName}': region names must be unique.")
        return self


class LayoutSpecification(BaseModel):
    pages: List[Page] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_page_names(self):
        names = [p.pageName for p in self.pages]
        if len(names) != len(set(names)):
            raise ValueError("LayoutSpecification: pageName must be unique.")
        return self


class ComponentState(BaseModel):
    name: str = Field(
        description="State identifier (e.g., 'hover', 'loading'). Should typically come from RECOMMENDED_STATES."
    )
    description: Optional[str] = None


class ComponentEvent(BaseModel):
    event: str = Field(description="DOM-style event name (e.g., 'onClick', 'onSubmit').")
    flowName: Optional[str] = Field(
        default=None,
        description="Name of the InteractionFlow that implements this event. MUST match an InteractionFlow.name.",
    )


class DataBindingSpec(BaseModel):
    source: str = Field(
        description="Data path this component reads from (e.g. 'product.price', 'cart.items', 'filters.category')."
    )
    format: Optional[str] = Field(
        default=None,
        description="Display format hint (e.g. 'currency', 'list', 'count', 'date', 'percentage').",
    )


class ComponentNode(BaseModel):
    id: str = Field(description="Unique component identifier. Stable across all specs.")
    tag: HTMLTag
    ownedBy: AgentType = Field(description="Execution agent. May override the parent Region.ownedBy.")
    componentCategory: Optional[ComponentCategory] = Field(
        default=None,
        description=(
            "B2C component category — written as the HTML data-component attribute value. "
            "Pick the closest value from ComponentCategory. Omit for purely structural wrappers "
            "that are not individually addressable (use <div> for those instead)."
        ),
    )
    props: Dict[str, Any] = Field(default_factory=dict)
    dataBinding: Optional[DataBindingSpec] = None
    states: List[ComponentState] = Field(default_factory=list)
    events: List[ComponentEvent] = Field(default_factory=list)
    className: Optional[str] = Field(
        default=None,
        description="CSS class name. Primary linking key to DecorationSpec.ComponentDecoration.",
    )
    children: List["ComponentNode"] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self):
        if self.ownedBy == "CSS" and not self.className:
            raise ValueError(f"{self.id}: CSS-owned component must define className.")
        if len({s.name for s in self.states}) != len(self.states):
            raise ValueError(f"{self.id}: duplicate state names.")
        if len({e.event for e in self.events}) != len(self.events):
            raise ValueError(f"{self.id}: duplicate event names.")
        return self


ComponentNode.model_rebuild()


class PageComponentTree(BaseModel):
    pageName: str
    regionComponents: Dict[str, List[ComponentNode]] = Field(
        description="Top-level components keyed by region name. Each key MUST match a Region.name in LayoutSpec."
    )


# The one description of dataSets, read by BOTH the schema the model fills and
# the schema the guard enforces.
#
# The generator binds the model to ComponentSpecificationDraft, and a field
# description is what reaches the model as part of the function schema. The draft
# used to describe dataSets not at all, so the model was hard-refused for
# omitting a field it had never been told about at that layer. Naming the text
# once means the two schemas cannot drift apart again.
_DATASETS_DESCRIPTION = (
    "REQUIRED whenever the page shows merchandise. Named lists of the run's real "
    "records, which every agent renders from, e.g. {'products': [{'id': 'p1', "
    "'name': 'Aurora Headphones', 'price': '89.00'}, ...]}. A storefront needs "
    "6-12 entries under "
    "'products'; a cart needs 'cartItems'. Every record needs a unique 'id' and "
    "a non-empty 'name', plus whatever the cards display. Emit real, plausible "
    "content -- never 'Product 1' or a blank price. Leaving this empty leaves "
    "the HTML and JavaScript agents to invent two different product lists."
)

_PAGES_DESCRIPTION = (
    "One entry per page in the layout specification, with the same pageName."
)


class ComponentSpecification(BaseModel):
    pages: List[PageComponentTree] = Field(
        default_factory=list, description=_PAGES_DESCRIPTION)
    # The one place the run's actual content lives. Without it the component tree
    # says "a product card goes here" and nothing says WHICH products, so the
    # HTML agent invented eight and the JS agent invented eight different ones.
    # Nothing could then rewrite a detail section from a clicked card, because
    # there was no shared record to rewrite it from. DataBindingSpec.source
    # points into these lists.
    dataSets: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description=_DATASETS_DESCRIPTION,
    )

    @model_validator(mode="after")
    def _unique_page_names(self):
        names = [p.pageName for p in self.pages]
        if len(names) != len(set(names)):
            raise ValueError("ComponentSpecification: pageName must be unique.")
        return self

    @model_validator(mode="after")
    def _valid_data_sets(self):
        for key, records in self.dataSets.items():
            seen = set()
            for n, rec in enumerate(records):
                if not isinstance(rec, dict):
                    raise ValueError(
                        f"dataSets['{key}'][{n}] must be an object, got "
                        f"{type(rec).__name__}.")
                rid = str(rec.get("id") or "").strip()
                name = str(rec.get("name") or "").strip()
                if not rid or not name:
                    raise ValueError(
                        f"dataSets['{key}'][{n}] needs a non-empty 'id' and "
                        f"'name'. Every guard downstream matches on them.")
                if rid in seen:
                    raise ValueError(
                        f"dataSets['{key}']: duplicate id '{rid}'. Ids identify "
                        f"which record a card was clicked for.")
                seen.add(rid)
        return self


class PageComponentTreeDraft(BaseModel):
    pageName: str
    regionComponents: Dict[str, List[ComponentNode]] = Field(
        default_factory=dict,
        description="Draft top-level components keyed by region name. The final validator still requires full region coverage.",
    )


class ComponentSpecificationDraft(BaseModel):
    """What the MODEL fills in. Every description here reaches the model.

    This is the schema bound by with_structured_output, so a field the final
    specification describes carefully and this one leaves bare is a field the
    model is judged on without being briefed. dataSets was exactly that until
    2026-08-16.
    """

    pages: List[PageComponentTreeDraft] = Field(
        default_factory=list, description=_PAGES_DESCRIPTION)
    # Carried on the draft too, or the two-stage generator would drop the
    # records between the draft and the final specification.
    dataSets: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict, description=_DATASETS_DESCRIPTION)

    @model_validator(mode="before")
    @classmethod
    def _rescue_misfiled_records(cls, data):
        """Move the records to the top level, wherever the model put them.

        `dataSets` sits beside `pages`, and `regionComponents` is a different
        dictionary two levels down that also maps a name to a list. The model
        confuses the two, and until 2026-08-16 that confusion was fatal: it
        failed inside the parser, so the repair step never saw it and all three
        attempts were spent on a misfiled record rather than a wrong plan.

        Two shapes are rescued, both observed live. The records arriving as a
        key of regionComponents or of the page, and a torn answer leaving loose
        strings where component objects belong.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        rescued: Dict[str, Any] = {}
        pages = []

        for page in (data.get("pages") or []):
            if not isinstance(page, dict):
                continue
            page = dict(page)

            # the records, filed on the page instead of beside pages
            if isinstance(page.get("dataSets"), dict):
                rescued.update(page.pop("dataSets"))

            regions = page.get("regionComponents")
            if isinstance(regions, dict):
                cleaned = {}
                for name, nodes in regions.items():
                    # the records, filed as though they were a region
                    if name == "dataSets" and isinstance(nodes, dict):
                        rescued.update(nodes)
                        continue
                    if isinstance(nodes, list):
                        # a torn answer leaves strings where objects belong
                        cleaned[name] = [n for n in nodes if isinstance(n, dict)]
                page["regionComponents"] = cleaned

            pages.append(page)

        data["pages"] = pages
        if rescued and not data.get("dataSets"):
            data["dataSets"] = rescued
        return data


class InteractionEvent(BaseModel):
    event: str
    targetId: str = Field(description="Component where the event originates. MUST match a ComponentNode.id.")


class ActionResultState(BaseModel):
    description: str = Field(
        description="Human-readable outcome of this action (e.g. 'Cart item count increments; button shows Added')."
    )


class InteractionAction(BaseModel):
    type: ActionType
    targetId: Optional[str] = Field(default=None, description="If specified, MUST match a ComponentNode.id.")
    payload: Optional[Dict[str, Any]] = None
    result_state: Optional[ActionResultState] = None


class InteractionStateTransition(BaseModel):
    componentId: str = Field(description="MUST match a ComponentNode.id.")
    fromState: Optional[str] = Field(default=None)
    toState: str = Field(description="MUST match a name in the target component's states[].")


class InteractionFlow(BaseModel):
    name: str = Field(description="Unique flow identifier. Referenced by ComponentEvent.flowName.")
    description: Optional[str] = None
    trigger: InteractionEvent
    actions: List[InteractionAction]
    stateTransitions: List[InteractionStateTransition] = Field(default_factory=list)


class PageInteraction(BaseModel):
    pageName: str
    flows: List[InteractionFlow]

    @model_validator(mode="after")
    def _unique_flow_names(self):
        names = [f.name for f in self.flows]
        if len(names) != len(set(names)):
            raise ValueError(f"Page '{self.pageName}': flow names must be unique.")
        return self


class InteractionSpecification(BaseModel):
    pages: List[PageInteraction] = Field(default_factory=list)


class DesignTokens(BaseModel):
    colors: Dict[str, str] = Field(default_factory=dict)
    typography: Dict[str, Any] = Field(default_factory=dict)
    spacing: Dict[str, str] = Field(default_factory=dict)
    borders: Dict[str, str] = Field(default_factory=dict)
    shadows: Dict[str, str] = Field(default_factory=dict)
    radii: Dict[str, str] = Field(default_factory=dict)


class TransitionSpec(BaseModel):
    property: str = Field(default="all")
    duration: str = Field(default="200ms")
    easing: str = Field(default="ease-in-out")
    delay: Optional[str] = None


class StateVariant(BaseModel):
    stateName: str = Field(description="MUST match a ComponentState.name on the linked ComponentNode.")
    styles: Dict[str, Any]


class ResponsiveVariant(BaseModel):
    breakpoint: ResponsiveBreakpoint
    minWidth: Optional[str] = None
    maxWidth: Optional[str] = None
    styles: Dict[str, Any]


class ComponentDecoration(BaseModel):
    componentId: str = Field(description="MUST match a ComponentNode.id.")
    className: str = Field(description="MUST match the target ComponentNode.className.")
    baseStyles: Dict[str, Any] = Field(default_factory=dict)
    stateVariants: List[StateVariant] = Field(default_factory=list)
    responsiveStyles: List[ResponsiveVariant] = Field(default_factory=list)
    transitions: List[TransitionSpec] = Field(default_factory=list)
    pseudoElements: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _no_dupes(self):
        names = [v.stateName for v in self.stateVariants]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.componentId}: duplicate stateVariant names.")
        breakpoints = [v.breakpoint for v in self.responsiveStyles]
        if len(breakpoints) != len(set(breakpoints)):
            raise ValueError(f"{self.componentId}: duplicate breakpoint in responsiveStyles.")
        return self


class PageDecoration(BaseModel):
    pageName: str
    pageTokens: Optional[DesignTokens] = Field(default=None)
    componentDecorations: List[ComponentDecoration] = Field(default_factory=list)


class DecorationSpecification(BaseModel):
    globalTokens: DesignTokens = Field(default_factory=DesignTokens)
    pages: List[PageDecoration] = Field(default_factory=list)


class UISpecificationBundle(BaseModel):
    layout: LayoutSpecification
    component: ComponentSpecification
    interaction: InteractionSpecification
    decoration: DecorationSpecification

    @model_validator(mode="after")
    def _cross_spec_consistency(self):
        def walk_ids(node: ComponentNode) -> Set[str]:
            ids = {node.id}
            for child in node.children:
                ids |= walk_ids(child)
            return ids

        def walk_state_index(node: ComponentNode, idx: Dict[str, Set[str]]):
            idx[node.id] = {s.name for s in node.states}
            for child in node.children:
                walk_state_index(child, idx)

        def walk_class_index(node: ComponentNode, idx: Dict[str, Optional[str]]):
            idx[node.id] = node.className
            for child in node.children:
                walk_class_index(child, idx)

        def walk_event_flows(node: ComponentNode, declared: Set[str]):
            for event in node.events:
                if event.flowName:
                    declared.add(event.flowName)
            for child in node.children:
                walk_event_flows(child, declared)

        layout_pages = {p.pageName for p in self.layout.pages}
        comp_pages = {p.pageName for p in self.component.pages}
        intr_pages = {p.pageName for p in self.interaction.pages}
        deco_pages = {p.pageName for p in self.decoration.pages}

        if not comp_pages.issubset(layout_pages):
            raise ValueError(f"ComponentSpec references unknown pages: {comp_pages - layout_pages}")
        if not intr_pages.issubset(layout_pages):
            raise ValueError(f"InteractionSpec references unknown pages: {intr_pages - layout_pages}")
        if not deco_pages.issubset(layout_pages):
            raise ValueError(f"DecorationSpec references unknown pages: {deco_pages - layout_pages}")

        for layout_page in self.layout.pages:
            page_name = layout_page.pageName
            comp_page = next((p for p in self.component.pages if p.pageName == page_name), None)
            intr_page = next((p for p in self.interaction.pages if p.pageName == page_name), None)
            deco_page = next((p for p in self.decoration.pages if p.pageName == page_name), None)

            if comp_page is None:
                continue

            layout_region_names = {r.name for r in layout_page.regions}
            comp_region_names = set(comp_page.regionComponents.keys())
            if not comp_region_names.issubset(layout_region_names):
                raise ValueError(
                    f"Page '{page_name}': ComponentSpec.regionComponents has unknown regions: {comp_region_names - layout_region_names}"
                )

            all_ids: Set[str] = set()
            state_index: Dict[str, Set[str]] = {}
            class_index: Dict[str, Optional[str]] = {}
            declared_flows: Set[str] = set()

            for nodes in comp_page.regionComponents.values():
                for node in nodes:
                    all_ids |= walk_ids(node)
                    walk_state_index(node, state_index)
                    walk_class_index(node, class_index)
                    walk_event_flows(node, declared_flows)

            if intr_page:
                actual_flow_names = {f.name for f in intr_page.flows}
                missing_flows = declared_flows - actual_flow_names
                if missing_flows:
                    raise ValueError(
                        f"Page '{page_name}': ComponentEvent.flowName refers to unknown flows: {missing_flows}"
                    )

                for flow in intr_page.flows:
                    if flow.trigger.targetId not in all_ids:
                        raise ValueError(
                            f"Page '{page_name}', flow '{flow.name}': trigger.targetId '{flow.trigger.targetId}' is not a known component."
                        )
                    for action in flow.actions:
                        if action.targetId and action.targetId not in all_ids:
                            raise ValueError(
                                f"Page '{page_name}', flow '{flow.name}': action.targetId '{action.targetId}' unknown."
                            )
                    for transition in flow.stateTransitions:
                        if transition.componentId not in all_ids:
                            raise ValueError(
                                f"Page '{page_name}', flow '{flow.name}': transition.componentId '{transition.componentId}' unknown."
                            )
                        comp_states = state_index.get(transition.componentId, set())
                        if transition.toState not in comp_states:
                            raise ValueError(
                                f"Page '{page_name}', flow '{flow.name}': toState '{transition.toState}' not declared on '{transition.componentId}' (declared: {comp_states})."
                            )
                        if transition.fromState is not None and transition.fromState not in comp_states:
                            raise ValueError(
                                f"Page '{page_name}', flow '{flow.name}': fromState '{transition.fromState}' not declared on '{transition.componentId}'."
                            )

            if deco_page:
                for deco in deco_page.componentDecorations:
                    if deco.componentId not in all_ids:
                        raise ValueError(
                            f"Page '{page_name}': Decoration componentId '{deco.componentId}' is not a known component."
                        )
                    target_class = class_index.get(deco.componentId)
                    if target_class != deco.className:
                        raise ValueError(
                            f"Page '{page_name}': Decoration className '{deco.className}' does not match component '{deco.componentId}'.className='{target_class}'."
                        )
                    comp_states = state_index.get(deco.componentId, set())
                    for variant in deco.stateVariants:
                        if variant.stateName not in comp_states:
                            raise ValueError(
                                f"Page '{page_name}': Decoration for '{deco.componentId}' has stateVariant '{variant.stateName}' not in declared states {comp_states}."
                            )

        return self

def literal_values(annotation) -> str:
    """The values of a Literal, comma separated, for pasting into a prompt.

    A prompt that hand-lists a schema's values falls behind the schema and
    nothing reports it. advanceStep and submitOrder were added to ActionType on
    2026-08-15 and the interactions prompt still named eleven of thirteen a day
    later, so the checkout stages they were added for could not be described.
    """
    import typing as _lv_typing
    return ", ".join(str(v) for v in _lv_typing.get_args(annotation))


# ==========================================================================
# Pydantic models of 4 specifications
# ==========================================================================
import typing

# ── What the user is allowed to choose ────────────────────────────────────────
# One list, derived from the schema itself with typing.get_args, so it can never
# drift from what the system actually accepts. Three consumers need the same
# answer and used to guess it separately: the Primary Orchestrator, which asks
# the user what they want; the preview panel, which shows the choices; and this
# documentation. A hand-written copy of the values would be wrong the first time
# anyone added a value to a Literal.


def _opt(value, help_text):
    """One selectable value: the exact word the schema takes, plus plain words."""
    return {"value": value,
            "label": value.replace("_", " ").capitalize(),
            "help": help_text}


USER_CHOICE_HELP = {
    "commerce_type": {
        "single_brand": "One company selling only its own products.",
        "multi_brand_retailer": "One shop selling many brands.",
        "marketplace": "Many independent sellers on one platform.",
        "direct_to_consumer": "The maker sells straight to the public.",
        "subscription": "Customers subscribe and receive deliveries.",
        "digital_products": "Downloads: software, courses, ebooks.",
        "on_demand": "Buying is tied to immediate delivery or service.",
        "flash_sale": "Countdowns, limited stock, deep discounts.",
        "customisable_products": "The buyer configures the product first.",
        "social_discovery": "Feeds, trends and customer photos lead.",
    },
    "style": {
        "catalog_heavy": "Many products, dense, filters always visible.",
        "minimal_premium": "Lots of whitespace, big images, few controls.",
        "visual_first": "Photography leads; the picture fills the card.",
        "information_heavy": "Specifications, comparisons and reviews.",
        "promotion_heavy": "Banners, badges, vouchers and bundles.",
        "single_product_landing": "One product, one long persuasive scroll.",
        "personalised": "Recommended and recently-viewed strips.",
    },
    "type": {
        "home": "A storefront: hero, categories, featured products.",
        "plp": "A product listing with filters and sorting.",
        "pdp": "One product in detail, with a gallery.",
        "cart": "The basket and its order summary.",
        "checkout": "The five-stage checkout accordion.",
        "account": "Profile, orders and saved addresses.",
        "search": "Search results for a query.",
    },
}


def user_choice_options() -> dict:
    """Every choice the user may make, ready for the preview panel to render.

    Values come from the schema, not from a hand-written list. Adding a value to
    a Literal makes it appear here automatically, and the test below fails if any
    value is missing its plain-English line.
    """
    fields = [
        ("commerce_type", "What kind of shop", CommerceType,
         "Decides what the page must contain."),
        ("style", "How it should look", DesignStyle,
         "Decides how that content is presented."),
        ("type", "Which page", PageType,
         "A run builds exactly one page. Other areas become sections of it."),
    ]
    out = {}
    for key, label, literal, note in fields:
        out[key] = {
            "label": label,
            "note": note,
            "required": False,
            "default_when_unset": {"commerce_type": "single_brand",
                                   "style": "catalog_heavy",
                                   "type": "inferred from the request"}[key],
            "values": [_opt(v, USER_CHOICE_HELP[key][v])
                       for v in typing.get_args(literal)],
        }
    return out


# Choices the user does NOT get, and the reason each one is fixed. The panel
# shows these too: a user who knows why cannot ask for it and be refused later.
FIXED_BY_DESIGN = [
    {"what": "Number of pages",
     "value": "always one",
     "why": "Every generated file is named after the session alone, so a second "
            "page has nowhere to go. Several areas become sections of one page, "
            "reached by in-page links."},
    {"what": "Technology",
     "value": "plain HTML, CSS and JavaScript",
     "why": "No framework and no build step, so the result opens in a browser "
            "with nothing installed."},
    {"what": "Server",
     "value": "none",
     "why": "Front end only. Sign-in and payment are simulated in the browser "
            "and the page says so."},
    {"what": "Structural changes after generation",
     "value": "not available",
     "why": "The specifications and the tests are built once, during generation. "
            "Adding or removing a component would leave both stale, so a "
            "structural request starts a new generation instead."},
    {"what": "Responsive design",
     "value": "always on (phone and desktop)",
     "why": "A store has to work on the phone people actually shop on, so every "
            "page is built to fit both phone and desktop, and this baseline of a "
            "modern site is not something to switch off."},
]


def choices_for_prompt() -> str:
    """The choice list as prompt text, generated from the same source as the panel.

    The Primary Orchestrator is the only agent that speaks to the user, so it is
    the one that must know what may be asked for. Writing that list into its
    prompt by hand would put a second copy of the vocabulary in the system, and
    the copy would be wrong the first time anyone added a value.
    """
    lines = []
    for key, spec in user_choice_options().items():
        values = " | ".join(v["value"] for v in spec["values"])
        lines.append(f"- {spec['label']} ({key}). {spec['note']}")
        lines.append(f"  {values}")
        lines.append(f"  If the user says nothing: {spec['default_when_unset']}.")
    return "\n".join(lines)


def fixed_for_prompt() -> str:
    """The four limits as prompt text, each with the reason to give the user."""
    return "\n".join(f"- {f['what']}: {f['value']}. {f['why']}"
                     for f in FIXED_BY_DESIGN)


# ==========================================================================
# UISpecificationBundle validation tool suite
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# Repairing a specification before the developer agents see it
#
# The planning chain returns four specifications. They are usually close to
# correct and occasionally not. These helpers sit between the planner and the
# developer agents and do three jobs:
#
#   accept        take a specification whether it arrives as an object, a plain
#                 dict, or nothing at all, and turn it into a checked object
#   repair        fill in what can be filled in without inventing anything, such
#                 as a region the planner declared in the layout and then left
#                 out of the component tree
#   refuse        describe, in one message, everything that is still wrong
#
# The order matters. Repairing before checking means the planner is only asked
# to fix what a machine genuinely cannot work out on its own.
#
# _invoke_structured_with_retries is the loop around all of it. It calls the
# planner, checks the result, and feeds any complaint back into the next
# attempt as extra context. It stops after three tries. That bound is the point:
# a loop with no cap would keep paying for attempts until one happened to pass,
# and would then report a success rate of 100% that means nothing.
# ═══════════════════════════════════════════════════════════════════════════
from typing import Any, Callable, Dict, List, Optional
import contextvars as _spec_ctxvars

# The LangSmith run-name prefix for the current planning run, e.g.
# "E2E-SD-01". run_planning_pipeline sets it; each generator's structured
# .invoke reads it and names that call "<prefix> - <stage>", e.g.
# "E2E-SD-01 - decoration". Left unset on the graph path, where the .invoke
# keeps its default run name.
_RUN_NAME_PREFIX = _spec_ctxvars.ContextVar("_planning_run_name_prefix", default=None)


def _coerce_layout_spec(payload: Any) -> LayoutSpecification:
    if isinstance(payload, LayoutSpecification):
        return payload
    if payload is None:
        payload = {}
    return LayoutSpecification.model_validate(payload)


def _coerce_component_spec(payload: Any) -> ComponentSpecification:
    if isinstance(payload, ComponentSpecification):
        return payload
    if payload is None:
        payload = {}
    return ComponentSpecification.model_validate(payload)


def _coerce_interaction_spec(payload: Any) -> InteractionSpecification:
    if isinstance(payload, InteractionSpecification):
        return payload
    if payload is None:
        payload = {}
    if isinstance(payload, dict) and "pages" not in payload:
        payload = {"pages": []}
    return InteractionSpecification.model_validate(payload)


def _coerce_decoration_spec(payload: Any) -> DecorationSpecification:
    if isinstance(payload, DecorationSpecification):
        return payload
    if payload is None:
        payload = {}
    return DecorationSpecification.model_validate(payload)


def _walk_component_nodes(node: ComponentNode):
    yield node
    for child in node.children:
        yield from _walk_component_nodes(child)


# A component in one of these categories renders merchandise, so there has to be
# merchandise for it to render. Every other category can be static.
_MERCHANDISE_CATEGORIES = frozenset({
    "product-card", "product-grid", "product-image-gallery", "cart-item",
    "search-results", "order-history",
})

import re as _re_contract

# A mini-cart is an overlay drawer: it opens over the page and the shopper
# must be able to dismiss it. PO-10 po07cdf97e opened its mini-cart and
# nothing -- no button, no flow -- ever closed it. A close control announces
# itself in its id, its flowName or its ariaLabel. Keyed on the mini-cart
# CATEGORY, not on open/closed state names, so an expandable navbar or
# accordion (which toggles itself and needs no separate close) is never
# flagged. Add other overlay categories here if the enum grows one.
_CLOSE_CONTROL_RE = _re_contract.compile(r"close|dismiss|hide", _re_contract.IGNORECASE)

# A mini-cart CLOSE control belongs on the drawer container, never on the
# button that OPENS it. The model routinely tags both the trigger and the
# panel componentCategory='mini-cart' -- po2r12253d9 shipped
# header-mini-cart-toggle (a <button>) beside mini-cart-drawer (an <aside>
# that already carried mini-cart-close). The close-control check fired on the
# button, which cannot hold a close control, and bounced a correct spec into
# a 3/3 thrash. A control tag is a trigger, not a drawer, so it is exempt.
_NON_DRAWER_TAGS = ("button", "a", "input", "select", "textarea", "label")

# Page types that exist to sell. A run on one of these owes real records in
# dataSets even when the model forgot to label its product cards with a
# merchandise category. E2E-SD-03 shipped an empty tea shop on 2026-08-23
# because every card's componentCategory came back null, so the category
# test below stayed silent. The page type is a signal the model cannot leave
# off, so it is the backstop when the labels are missing.
_MERCHANDISE_PAGE_TYPES = frozenset({"home", "plp", "pdp"})


def _validate_component_contract_for_downstream(
    layout: LayoutSpecification,
    component: ComponentSpecification,
) -> Optional[str]:
    layout_pages = {p.pageName: p for p in layout.pages}
    violations: List[str] = []

    for comp_page in component.pages:
        layout_page = layout_pages.get(comp_page.pageName)
        if layout_page is None:
            continue

        layout_region_names = {region.name for region in layout_page.regions}
        component_region_names = set(comp_page.regionComponents.keys())

        missing_regions = layout_region_names - component_region_names
        if missing_regions:
            violations.append(
                f"Page '{comp_page.pageName}' is missing regionComponents entries for: "
                + ", ".join(sorted(missing_regions))
            )

        extra_regions = component_region_names - layout_region_names
        if extra_regions:
            violations.append(
                f"Page '{comp_page.pageName}' has unknown regionComponents keys: "
                + ", ".join(sorted(extra_regions))
            )

        # A region whose KEY is present but whose list is EMPTY is not planned,
        # it is skipped. The name comparison above cannot see the difference,
        # and _repair_component_spec_from_layout actively hides it: it fills
        # every layout region with `existing_nodes ... or []`, so a region the
        # model never wrote arrives here as a present-but-empty key and passes.
        # On PO-08 po01c3d233 that let 4 of 7 HTML regions ship unplanned --
        # including the product grid -- so the decoration stage had nothing to
        # decorate there, the CSS agent had nothing to style, and half the page
        # rendered with no rules at all.
        #
        # A JavaScript-owned region is exempt: mini-cart and its kind are built
        # at runtime and have no authored components by design.
        for region in layout_page.regions:
            if str(getattr(region, "ownedBy", "") or "").strip().lower() == "javascript":
                continue
            if not (comp_page.regionComponents.get(region.name) or []):
                violations.append(
                    f"Page '{comp_page.pageName}', region '{region.name}' is "
                    f"declared in the layout and owned by "
                    f"{getattr(region, 'ownedBy', 'HTML')}, but its "
                    f"regionComponents list is EMPTY. Every region the layout "
                    f"declares has to be planned: give it at least one component "
                    f"tree. Only a JavaScript-owned region may be left empty."
                )

        for region_name, nodes in comp_page.regionComponents.items():
            for root in nodes:
                for node in _walk_component_nodes(root):
                    if not str(node.ownedBy).strip():
                        violations.append(
                            f"Page '{comp_page.pageName}', region '{region_name}', component '{node.id}' is missing ownedBy."
                        )

                    for event in node.events:
                        if not str(event.event).strip():
                            violations.append(
                                f"Page '{comp_page.pageName}', region '{region_name}', component '{node.id}' has an event with an empty event name."
                            )
                        if not (event.flowName and str(event.flowName).strip()):
                            event_name = event.event if str(event.event).strip() else "<empty-event-name>"
                            violations.append(
                                f"Page '{comp_page.pageName}', region '{region_name}', component '{node.id}' has event '{event_name}' without a non-empty flowName."
                            )

                    if node.ownedBy == "CSS":
                        if not (node.className and str(node.className).strip()):
                            violations.append(
                                f"Page '{comp_page.pageName}', region '{region_name}', component '{node.id}' must define className because it is CSS-owned."
                            )

                    # A search box the user types into needs a real, addressable
                    # <input>. If the search-bar is one opaque node, a type test
                    # can only aim at the form, and Playwright fill refuses a
                    # <form> -- PO-06 shipped exactly that. Require the field as a
                    # child component so it has its own id/selector.
                    if node.componentCategory == "search-bar" and not any(
                            n.tag in ("input", "textarea")
                            for n in _walk_component_nodes(node)):
                        violations.append(
                            f"Page '{comp_page.pageName}', region '{region_name}', "
                            f"search-bar '{node.id}' has no <input> or <textarea> "
                            f"child. Model the actual text field as a child component "
                            f"with its own id, so a test can type into it -- a search "
                            f"whose only addressable node is the form cannot be filled.")

                    # A quantity-selector that nothing can drive is a static
                    # number. PO-10 po07cdf97e shipped the mini-cart quantity as
                    # a bare <span> with events:[], so nothing downstream could
                    # wire a stepper and Test Generation had no event to cover.
                    # Like the search-bar/input rule above, the control lives as
                    # a CHILD: require at least one event-bearing node in the
                    # quantity-selector subtree. The prompt asks for a proper
                    # minus / value / plus trio; this guarantees the floor. A
                    # sibling remove button is not inside it, so it does not count.
                    if node.componentCategory == "quantity-selector" and not any(
                            n.events for n in _walk_component_nodes(node)):
                        violations.append(
                            f"Page '{comp_page.pageName}', region '{region_name}', "
                            f"quantity-selector '{node.id}' has no control that can "
                            f"change the amount: it and its children declare no "
                            f"events. Add a decrement and an increment control as "
                            f"button CHILDREN of it, each with its own id and an "
                            f"onClick event (flowName like 'decreaseCartItem' / "
                            f"'increaseCartItem'), so a shopper can adjust the "
                            f"quantity in the cart.")

                    # A mini-cart drawer opens over the page, so it needs a
                    # control to close it. Require a close control in its
                    # subtree: a descendant carrying an event whose id,
                    # flowName or ariaLabel reads close/dismiss/hide. Like the
                    # quantity-selector rule, the control lives as a CHILD and
                    # the prompt asks for it; this guarantees the floor. A
                    # remove or checkout button is not a close control (PO-10
                    # mini-cart-panel had both of those and no way back to
                    # closed). Keyed on the category, so a toggle-only navbar
                    # or accordion is never touched.
                    if (node.componentCategory == "mini-cart"
                            and str(node.tag) not in _NON_DRAWER_TAGS
                            and not any(
                            _CLOSE_CONTROL_RE.search(str(n.id or ""))
                            or any(_CLOSE_CONTROL_RE.search(str(ev.flowName or "")) for ev in n.events)
                            for n in _walk_component_nodes(node) if n.events)):
                        violations.append(
                            f"Page '{comp_page.pageName}', region '{region_name}', "
                            f"mini-cart '{node.id}' has no control to close it. "
                            f"Add a close button as a CHILD with its own id and "
                            f"an onClick event that closes the drawer (id like "
                            f"'mini-cart-close', flowName like 'closeMiniCart'), "
                            f"so the shopper can dismiss it. A remove or checkout "
                            f"button does not close the drawer.")

    # A page that declares product cards and carries no records is valid against
    # every check above, builds cleanly, lints cleanly and passes its generated
    # tests. It just leaves the HTML agent and the JS agent to invent their own
    # separate product lists, which is the defect dataSets exists to remove.
    # E2E-SD-03 caught exactly this on 2026-08-16.
    if not component.dataSets:
        _merch = sorted({
            str(node.componentCategory)
            for comp_page in component.pages
            for nodes in comp_page.regionComponents.values()
            for root in nodes
            for node in _walk_component_nodes(root)
            if node.componentCategory in _MERCHANDISE_CATEGORIES
        })
        _selling = sorted({
            str(page.pageType) for page in layout.pages
            if str(page.pageType) in _MERCHANDISE_PAGE_TYPES
        })
        if _merch:
            violations.append(
                f"dataSets is empty, but this page declares {', '.join(_merch)}. "
                f"Emit the run's real records there (a unique 'id' and a "
                f"non-empty 'name' each, plus whatever the cards show), so the "
                f"HTML and JavaScript agents render the SAME items instead of "
                f"inventing two different lists."
            )
        elif _selling:
            # The model left every card's category null, so the branch above
            # saw no merchandise. The page type still says this run sells, so
            # empty dataSets is refused and the reason tells it how to fix it.
            violations.append(
                f"dataSets is empty on a selling page (pageType "
                f"{', '.join(_selling)}). Build the product region from "
                f"product-card (or product-grid) components that EACH carry "
                f"that componentCategory, and list the run's real items once "
                f"in dataSets (a unique 'id' and a non-empty 'name' each, plus "
                f"price or image as the cards show). One shared list, so the "
                f"HTML and JavaScript agents render the SAME items rather than "
                f"inventing two."
            )

    if not violations:
        return None

    max_violations = 25
    rendered = [f"- {issue}" for issue in violations[:max_violations]]
    if len(violations) > max_violations:
        rendered.append(f"- ... and {len(violations) - max_violations} more issue(s).")
    return "[components] ComponentSpecification is incomplete for downstream:\n" + "\n".join(rendered)


def _build_component_scaffold_from_layout(layout: Any) -> Dict[str, Any]:
    layout_obj = _coerce_layout_spec(layout)
    return {
        "pages": [
            {
                "pageName": page.pageName,
                "regionComponents": {region.name: [] for region in page.regions},
            }
            for page in layout_obj.pages
        ],
        # An empty slot reads as an instruction to fill it, which is why every
        # region arrives as an empty list. The prompt tells the model to start
        # from this scaffold exactly, so a key absent here is a key the model
        # never writes.
        "dataSets": {},
    }


def _build_component_contract_from_layout(layout: Any) -> str:
    layout_obj = _coerce_layout_spec(layout)
    lines: List[str] = []

    for page in layout_obj.pages:
        lines.append(f"Page {page.pageName} ({page.pageType}):")
        for region in page.regions:
            lines.append(f"- {region.name} [{region.layoutType}] owned by {region.ownedBy}")

    return "\n".join(lines)


def _guess_component_tag(component_id: str, region_name: str) -> HTMLTag:
    token = f"{component_id} {region_name}".lower()
    if any(word in token for word in {"bottomnav", "bottom_nav", "nav", "navbar"}):
        return "nav"
    if any(word in token for word in {"header", "topbar", "top_bar"}):
        return "header"
    if any(word in token for word in {"search", "filter", "form", "checkout", "payment"}):
        return "form"
    if any(word in token for word in {"button", "cta", "action", "add_to_cart", "place_order"}):
        return "button"
    if any(word in token for word in {"list", "grid", "gallery", "carousel", "items", "products"}):
        return "section"
    return "section"


def _default_component_node_for_ref(component_id: str, region_name: str) -> Dict[str, Any]:
    return {
        "id": component_id,
        "tag": _guess_component_tag(component_id, region_name),
        "ownedBy": "HTML",
        "props": {},
        "children": [],
    }


def _repair_component_spec_from_layout(layout: Any, candidate: Any) -> Dict[str, Any]:
    layout_obj = _coerce_layout_spec(layout)

    if hasattr(candidate, "model_dump"):
        payload = candidate.model_dump()
    elif isinstance(candidate, dict):
        payload = dict(candidate)
    else:
        payload = {}

    raw_pages = payload.get("pages") if isinstance(payload.get("pages"), list) else []
    pages_by_name: Dict[str, Dict[str, Any]] = {}
    for page in raw_pages:
        if not isinstance(page, dict):
            continue
        page_name = str(page.get("pageName") or "").strip()
        if not page_name:
            continue
        region_components = page.get("regionComponents")
        if not isinstance(region_components, dict):
            region_components = {}
        pages_by_name[page_name] = {
            "pageName": page_name,
            "regionComponents": {key: list(value or []) for key, value in region_components.items() if isinstance(key, str)},
        }

    repaired_pages: List[Dict[str, Any]] = []
    for layout_page in layout_obj.pages:
        page_payload = pages_by_name.get(
            layout_page.pageName,
            {"pageName": layout_page.pageName, "regionComponents": {}},
        )
        repaired_regions: Dict[str, List[Any]] = {}

        for region in layout_page.regions:
            existing_nodes = list(page_payload["regionComponents"].get(region.name) or [])
            repaired_regions[region.name] = existing_nodes

        repaired_pages.append(
            {
                "pageName": layout_page.pageName,
                "regionComponents": repaired_regions,
            }
        )

    # Replace ONLY `pages`, and carry every other top-level field through.
    # This used to return a fresh {"pages": ...}, which discarded everything
    # else the model produced. `dataSets` was added on 2026-08-15 and never
    # survived this line, so the run's real product records were thrown away
    # between the model and validation with nothing reporting it. Rebuilding
    # from the payload means a field added later cannot be lost the same way.
    repaired = dict(payload)
    repaired["pages"] = repaired_pages
    return repaired


import re as _re_fill

# Region names that read like "the product listing". Used only to choose what a
# LAST-RESORT fill puts in an HTML region the model left empty; it never runs on
# a region the model actually planned, so a match on an already-filled region is
# impossible.
_PRODUCT_REGION_RE = _re_fill.compile(
    r"product|listing|catalog|catalogue|grid|deal|shop|browse|plp|results|storefront|collection",
    _re_fill.IGNORECASE,
)


def _flatten_node_dicts(nodes):
    for n in (nodes or []):
        if not isinstance(n, dict):
            continue
        yield n
        yield from _flatten_node_dicts(n.get("children") or [])


def _fallback_container_node(region_name: str) -> Dict[str, Any]:
    """One CSS-owned container carrying the region className -- the exact shape
    the prompt asks a prose region to use. No events, so no event rule applies;
    className is set, so the CSS-owned rule is satisfied."""
    return {
        "id": f"{region_name}-content", "tag": "div", "ownedBy": "CSS",
        "props": {}, "states": [], "events": [],
        "className": f"{region_name}-content", "children": [],
    }


def _fallback_product_grid_node(region_name: str) -> Dict[str, Any]:
    """A product-grid whose single product-card is bound to `products` -- the
    same one-node-per-record shape a passing spec uses, so the page still shows
    the real catalogue the model already put in dataSets. HTML-owned with
    classNames so the CSS agent can still target it."""
    return {
        "id": f"{region_name}-grid", "tag": "section", "ownedBy": "HTML",
        "componentCategory": "product-grid", "props": {}, "states": [], "events": [],
        "className": f"{region_name}-grid",
        "children": [{
            "id": f"{region_name}-card", "tag": "article", "ownedBy": "HTML",
            "componentCategory": "product-card", "props": {}, "states": [], "events": [],
            "className": f"{region_name}-card",
            "dataBinding": {"source": "products"}, "children": [],
        }],
    }


def _fill_empty_html_regions(layout: Any, repaired: Dict[str, Any]):
    """LAST RESORT: give every empty HTML-owned region a valid fallback node.

    The empty-region guard is correct -- an HTML region with no components ships
    unstyled and unplanned (PO-08 po01c3d233). But on a many-region brief the
    model keeps dropping the product-listing and the footer, and identical
    retries cannot recover it: PO-10 po2r1707798 failed the components stage 3/3
    and aborted a paid run. This runs ONLY after the model has spent every
    attempt, and fills what it left empty rather than lose the run:

      product-listing kind -> a product-grid whose card is bound to the products
                              the model already produced (the real catalogue).
      any other region     -> one CSS-owned container with the region className.

    The model plans; Python only guarantees the floor when the model would not.
    Returns (repaired, count). A JavaScript-owned region is never filled -- it is
    built at runtime by design."""
    layout_obj = _coerce_layout_spec(layout)
    has_products = bool((repaired.get("dataSets") or {}).get("products"))
    pages_by_name = {p.get("pageName"): p for p in repaired.get("pages", [])
                     if isinstance(p, dict)}
    filled = 0
    for layout_page in layout_obj.pages:
        page = pages_by_name.get(layout_page.pageName)
        if not page:
            continue
        rc = page.setdefault("regionComponents", {})
        page_has_product = any(
            (n or {}).get("componentCategory") in ("product-card", "product-grid")
            for nodes in rc.values() for n in _flatten_node_dicts(nodes))
        for region in layout_page.regions:
            if str(getattr(region, "ownedBy", "") or "").strip().lower() == "javascript":
                continue
            if rc.get(region.name):
                continue  # the model planned this region -- leave it untouched
            if (has_products and not page_has_product
                    and _PRODUCT_REGION_RE.search(region.name)):
                rc[region.name] = [_fallback_product_grid_node(region.name)]
                page_has_product = True
            else:
                rc[region.name] = [_fallback_container_node(region.name)]
            filled += 1
    return repaired, filled


def _bundle_validate_or_warn(
    *,
    stage: str,
    layout: Any,
    component: Optional[Any] = None,
    interaction: Optional[Any] = None,
    decoration: Optional[Any] = None,
) -> Optional[str]:
    try:
        layout_obj = _coerce_layout_spec(layout)
        component_obj = _coerce_component_spec(component or {"pages": []})
        interaction_obj = _coerce_interaction_spec(interaction or {"pages": []})
        decoration_obj = _coerce_decoration_spec(decoration or {})

        layout_page_names = {p.pageName for p in layout_obj.pages}
        component_page_names = {p.pageName for p in component_obj.pages}
        missing_component_pages = layout_page_names - component_page_names
        if missing_component_pages:
            raise ValueError(
                "ComponentSpecification missing pages for layout: " + ", ".join(sorted(missing_component_pages))
            )

        component_contract_warning = _validate_component_contract_for_downstream(layout_obj, component_obj)
        if component_contract_warning:
            raise ValueError(component_contract_warning)

        UISpecificationBundle(
            layout=layout_obj,
            component=component_obj,
            interaction=interaction_obj,
            decoration=decoration_obj,
        )
        return None
    except Exception as e:
        return f"[{stage}] UISpecificationBundle validation warning: {e}"


import json as _spec_json
import time as _spec_time

# Every attempt every specification generator has made in this kernel.
#
# A stage that ends up correct still costs whatever its retries cost, and until
# now a successful stage recorded nothing. Reading this list after a run answers
# the only question that matters when a stage is slow: was it one slow call, or
# several ordinary ones?
_SPEC_TIMINGS: List[Dict[str, Any]] = []


def _spec_progress(text: str) -> None:
    """Write one diagnostic line to the console, never to the chat.

    This deliberately does NOT use get_stream_writer(). That writer feeds the
    graph's custom stream, and bridge.py forwards every string on it into the
    Streamlit chat, so a timing line would be shown to the person waiting as
    though the system were talking to them. It is not for them. The chat
    already gets a progress line from the planning chain itself
    saying which specification is being written.

    print puts it under the cell during a manual run, and in the Streamlit
    server's terminal during a graph run. Both are where someone debugging a
    slow stage would look. spec_timing_report() reads the same attempts back
    afterwards from _SPEC_TIMINGS.
    """
    print(text)


def spec_timing_report(stage: Optional[str] = None) -> None:
    """Print what every attempt cost. Call it after a slow run."""
    rows = [r for r in _SPEC_TIMINGS if stage is None or r["stage"] == stage]
    if not rows:
        print("No specification attempts recorded yet.")
        return
    print(f"{'stage':<14}{'attempt':<9}{'seconds':>9}  outcome")
    print("-" * 78)
    for r in rows:
        print(f"{r['stage']:<14}{r['attempt']:<9}{r['seconds']:>9.1f}  {r['outcome'][:44]}")
    print("-" * 78)
    for st in sorted({r["stage"] for r in rows}):
        srows = [r for r in rows if r["stage"] == st]
        print(f"{st}: {len(srows)} attempt(s), {sum(r['seconds'] for r in srows):.1f}s total")


# A previous answer larger than this is sent truncated. The component
# specification with a full product catalogue is the only one that gets close.
_RETRY_ANSWER_LIMIT = 60000


def _render_previous_answer(previous: Any) -> tuple[str, str]:
    """The previous answer, small enough to send back, with no field silently lost.

    Returns (rendered, note). The note is empty when nothing was shortened.

    Two decisions here, both bought with a failed run: PO-08 po015c7e79 on
    2026-08-31, where the components stage spent all three attempts and the
    build never started.

    INDENT. This used to render at indent=2. Measured on real component
    specifications from this project's own checkpoints, 90,457 characters
    indented against 42,177 compact. The indentation is pure cost, and the model
    reads either form the same way.

    WHAT GETS CUT. This used to keep the first _RETRY_ANSWER_LIMIT characters
    and drop the rest. Every generator has one field holding almost all of the
    bulk (pages) and small fields serialised after it, so a tail cut always
    destroyed the small ones first. On po015c7e79 the component specification's
    dataSets began at character 86,780 of 90,457: attempt 1 produced a correct
    catalogue, the echo cut it away, and attempts 2 and 3 came back with dataSets
    empty. The retry loop broke a field that was already right, and the guard
    then reported it as the model's mistake, which is the worst kind of failure,
    because the evidence points at the wrong place.

    So an over-long answer now keeps every top-level field, shortens only the
    largest one, and names the field it shortened.
    """
    try:
        rendered = _spec_json.dumps(previous, ensure_ascii=False, default=str)
    except Exception:
        rendered = str(previous)
    if len(rendered) <= _RETRY_ANSWER_LIMIT:
        return rendered, ""

    # Not a mapping, or a mapping with nothing to protect: the old behaviour is
    # the only one available.
    if not isinstance(previous, dict) or len(previous) < 2:
        return (rendered[:_RETRY_ANSWER_LIMIT] + "\n... (cut short here)",
                "\nYour answer was too large to show in full, so it stops part "
                "way. Rebuild the missing tail from the request.\n")

    parts: Dict[str, str] = {}
    for key, value in previous.items():
        try:
            parts[key] = _spec_json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            parts[key] = _spec_json.dumps(str(value), ensure_ascii=False)

    biggest = max(parts, key=lambda k: len(parts[k]))
    # Room left for the big field once every other one is shown in full. The
    # floor stops it collapsing to nothing when the small fields are themselves
    # large: a partial echo is still better than none.
    others = sum(len(parts[k]) + len(k) + 6 for k in parts if k != biggest)
    room = max(2000, _RETRY_ANSWER_LIMIT - others)

    note = ""
    if len(parts[biggest]) > room:
        parts[biggest] = parts[biggest][:room] + ' "... cut short here"'
        note = (f"\nYour answer was too large to show in full, so {biggest!r} "
                f"stops part way and is not valid JSON on its own. Every OTHER "
                f"field is shown COMPLETE: keep those exactly as they are, and "
                f"never empty one because you cannot see it here. Rebuild only "
                f"the missing tail of {biggest!r} from the request.\n")

    body = "{" + ", ".join(f"{_spec_json.dumps(k)}: {parts[k]}"
                           for k in previous) + "}"
    return body, note


def _retry_feedback(previous: Any, complaint: str, attempt: int) -> str:
    """What the next attempt is told: what it produced, and what was wrong.

    A complaint on its own is an instruction to start again and avoid a mistake
    the model cannot see, which is how one stage produced three unrelated
    failures in a row on 2026-08-16. Showing the answer back turns the next
    attempt into an edit.

    A previous answer that never parsed is not shown, because there is no object
    to edit. The complaint carries the parser's own reason in that case.
    """
    if previous is None:
        return complaint

    rendered, truncated = _render_previous_answer(previous)

    return (
        f"YOUR PREVIOUS ANSWER (attempt {attempt})\n"
        f"{rendered}\n"
        f"{truncated}"
        f"\nWHAT WAS WRONG WITH IT\n"
        f"{complaint}\n"
        f"\nEdit the answer above so every point is fixed. Keep everything that "
        f"was not criticised exactly as it is, including ids and names. Return "
        f"the whole corrected object, not a patch."
    )


def _invoke_structured_with_retries(
    *,
    stage: str,
    structured_tool: Any,
    base_payload: Dict[str, Any],
    validate_result: Callable[[Any], Optional[str]],
    max_attempts: int = 3,
    on_give_up: Optional[Callable[[Any, Optional[str]], Optional[Any]]] = None,
    normalize: Optional[Callable[[Any], Any]] = None,
) -> tuple[Optional[Any], Optional[str]]:
    validation_feedback = ""
    last_error: Optional[str] = None
    # The answer the previous attempt gave, so the next one edits rather than
    # starts again. Only the last one is kept, so the payload stops growing
    # after the first retry instead of compounding.
    previous_answer: Optional[Any] = None
    # Every attempt's reason, not just the final one. Whether the model is
    # converging or repeating itself is the single most useful thing to know
    # when a stage gives up, and it is invisible from the last error alone.
    attempt_errors: List[str] = []

    # LangSmith run name for this stage, e.g. "E2E-SD-01 - decoration".
    # The prefix is set by run_planning_pipeline; unset in the graph path,
    # so the invoke keeps its default name there.
    _rn_prefix = _RUN_NAME_PREFIX.get()
    _invoke_config = {"run_name": f"{_rn_prefix} - {stage}"} if _rn_prefix else None

    for attempt in range(1, max_attempts + 1):
        payload = dict(base_payload)
        payload["validation_feedback"] = validation_feedback
        _t0 = _spec_time.perf_counter()

        def _record(outcome: str) -> float:
            secs = _spec_time.perf_counter() - _t0
            _SPEC_TIMINGS.append({"stage": stage, "attempt": attempt,
                                  "seconds": secs, "outcome": outcome})
            _spec_progress(f"   [{stage}] attempt {attempt}/{max_attempts} "
                           f"took {secs:.1f}s: {outcome}")
            return secs

        try:
            if _invoke_config is not None:
                candidate = structured_tool.invoke(payload, config=_invoke_config)
            else:
                candidate = structured_tool.invoke(payload)
            if hasattr(candidate, "model_dump"):
                candidate = candidate.model_dump()
        except Exception as e:
            last_error = (
                f"[{stage}] structured output parse/invoke failed "
                f"(attempt {attempt}/{max_attempts}): {type(e).__name__}: {e}"
            )
            # Nothing parsed, so there is no object to show back. The
            # parser's own reason is already in last_error.
            previous_answer = None
            validation_feedback = last_error
            _secs = _record("the answer could not be parsed")
            attempt_errors.append(f"attempt {attempt}: [{_secs:.1f}s] {last_error}")
            continue

        warn = validate_result(candidate)
        if warn is None:
            _record("accepted")
            return candidate, None

        last_error = warn
        previous_answer = candidate
        # Show the model a NORMALISED copy of its own answer, not the raw
        # one, when the stage supplies a normaliser. The components stage
        # repairs `pages` back to the full set of layout regions, so a
        # region the model dropped comes back as an empty key it can see and
        # fill. Feeding back the raw answer instead showed the model an
        # answer with the key already gone, and it could not re-add what it
        # could not see -- PO-10 po2r1707798 failed 3/3 identically.
        _feedback_answer = normalize(candidate) if normalize is not None else candidate
        validation_feedback = _retry_feedback(_feedback_answer, warn, attempt)
        _secs = _record("rejected, retrying with the answer and the reason")
        attempt_errors.append(f"attempt {attempt}: [{_secs:.1f}s] {warn}")

    # Every attempt was rejected. Let a caller-supplied last resort try to
    # rescue the answer deterministically (e.g. fill what the model kept
    # leaving out) before the stage reports failure. Only stages that pass
    # on_give_up use it; the rest fail exactly as before.
    if on_give_up is not None and previous_answer is not None:
        _rescued = on_give_up(previous_answer, last_error)
        if _rescued is not None:
            return _rescued, None

    if not attempt_errors:
        return None, last_error or f"[{stage}] structured tool failed without details"
    history = "\n".join(attempt_errors)
    return None, (
        f"[{stage}] gave up after {max_attempts} attempts. Each attempt and why "
        f"it was rejected:\n{history}"
    )


# ==========================================================================
# UISpecificationBundle validation tool suite
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# Shared spec rules - the guidance the four generators write against
#
# These used to live only in the planning agent's system prompt, which could
# not pass them to the four generators (each generator makes its own LLM call
# with its own prompt). So the checklists that were authored to shape the specs
# never reached the model that writes them. The audit on 2026-08-23 confirmed
# it: only the layout stage received any run-specific intent, and only there.
#
# The fix is to hold the rules as DATA here, and inject the slice that applies
# into every generator. Two pieces:
#
#   _SPEC_HOUSE_RULES   the rules that are the same every run (one page, one
#                       token set, real copy, label components, accessibility,
#                       no unused declarations). A plain constant.
#   _build_run_brief    the rules that depend on THIS run: the one commerce
#                       line, the one style line, and the Baymard checklist for
#                       the chosen page type. A tiny builder that looks up and
#                       assembles; it never validates -- the values are already
#                       from the fixed lists the schema enforces.
#
# Keyed by the exact CommerceType / DesignStyle / PageType literals, so a unit
# test can assert every value has a rule and a new value cannot slip in without
# one.
# ═══════════════════════════════════════════════════════════════════════════

_SPEC_HOUSE_RULES = """HOUSE RULES (every stage obeys these)
- ONE page only. Named areas (storefront, listing, cart, checkout) are REGIONS of the same page, reached by in-page anchors (href="#regionId"), never separate pages.
- ONE design-token set: one primary, surface, and text colour; one spacing scale; one corner radius; one type scale. Every component uses it. Name tokens for CSS :root properties.
- REAL copy only: specific product names, realistic prices with currency, meaningful headings. Never "Product 1", "$0.00", or lorem ipsum.
- LABEL every recognisable component with a componentCategory from the list (product tile, product image, cart line, navbar, footer, search bar, price, rating, filter panel, sort control, add-to-cart button, promo banner). When in doubt, label it; a missing category silently switches off a downstream rule.
- SPARSITY: every region justifies its space (product grid at least 4 items, featured row at least 3) and uses the same spacing scale.
- MOBILE: state one breakpoint and the layout on each side. No region declares a fixed pixel width wider than the viewport.
- ACCESSIBILITY: images use meaningful alt text from the record; every interactive control is reachable and labelled; component states surface as aria-*/data-state DOM attributes.
- LIVE VALUES: any interaction-updated number or text (cart item count, cart subtotal, order total, result count) is its OWN component with a stable id, never embedded in heading prose. The changing flow names that component id as its rewrite target.
- SEARCH: every page includes a site search bar in the header region: a labelled search text input, tagged as the search bar component, for looking up or filtering products. Include it for every page type; a checkout region may hide it while active per its own rules.
- MAINTAINABILITY: declare nothing unused; any unreferenced token, class, or state is a defect."""


# One line per CommerceType value. Content, not looks: what the page must CONTAIN.
_COMMERCE_RULES = {
    "single_brand": "One brand voice, an about/story region, no seller names anywhere.",
    "multi_brand_retailer": "A brand name on every product card, and a brand filter.",
    "marketplace": "A seller name and seller rating on every card, a seller filter, and a shipped-by line in the cart.",
    "direct_to_consumer": "A materials or how-it-is-made region, and a comparison against the traditional retail price.",
    "subscription": "A plan picker with at least two frequencies, the recurring price stated per delivery, and a cancel-anytime line near the primary button.",
    "digital_products": "No shipping fields anywhere in checkout, a file format and size on the product, and an instant-delivery line.",
    "on_demand": "A delivery time estimate on every card, a store or area picker, and a live order status region.",
    "flash_sale": "A countdown, the original price struck through beside the sale price, and a stock-remaining indicator per card.",
    "customisable_products": "An option picker that changes the shown price, and a running configuration summary beside it.",
    "social_discovery": "A feed-style browsing region, a trending row, and customer photos on the product detail.",
}


# One line per DesignStyle value. How it is PRESENTED; never removes a required
# component, only changes density, imagery and how many controls are visible.
_STYLE_RULES = {
    "catalog_heavy": "Compact spacing, small cards, at least 8 per grid, filters open by default.",
    "minimal_premium": "Generous spacing, large imagery, at most 3 cards per row, the filter panel collapsed behind one control.",
    "visual_first": "Image-dominant cards where the photo fills most of the card, and a multi-image gallery on the product detail.",
    "information_heavy": "Specification tables, a comparison region, review summaries, and text-dense cards.",
    "promotion_heavy": "A promotional banner region, badges on discounted cards, and a bundle or voucher region.",
    "single_product_landing": "One product, a long scroll with several persuasion regions, and a repeated primary button.",
    "personalised": "A recommended-for-you strip and a recently-viewed strip, both populated from dataSets.",
}


# One checklist per PageType value. Baymard's mandatory components for a B2C
# storefront. Apply the checklist for the page type the layout chose.
_BAYMARD_CHECKLISTS = {
    "home": [
        "Hero section with a value proposition and a primary CTA",
        "Product category navigation (tiles or a nav bar)",
        "Featured products section (at least 4 products)",
        "Trust signals (reviews, guarantees, secure-checkout badges)",
    ],
    "plp": [
        "Filter panel with at least: category, price range, brand",
        "Sort bar with at least: relevance, price ascending/descending, newest",
        "Product grid (at least 2 columns on mobile, 3 to 4 on desktop)",
        "Each product card: image, name, price, primary CTA (add to cart or view)",
        "Pagination or infinite scroll, visible and not hidden behind a button",
    ],
    "pdp": [
        "Image gallery with a thumbnail strip (at least 3 images)",
        "Product name, price, and a SKU or variant selector (size/colour)",
        "Add-to-cart button, prominent, above the fold on mobile",
        "Shipping cost estimate shown before the cart step",
        "Product description plus a specifications tabs/accordion",
        "Reviews section with a rating summary",
    ],
    "cart": [
        "Cart item list: image, name, quantity selector, line total, remove button",
        "Order summary sidebar: subtotal, shipping, tax, total",
        "Proceed-to-checkout CTA, single and prominent",
        "Continue-shopping link",
    ],
    "checkout": [
        "Five stages in one document, each its own component with expanded/collapsed/success states: (1) review cart, (2) customer details, (3) review order, (4) payment, (5) order confirmation",
        "Exactly one stage expanded at a time; a finished stage collapses to a SUMMARY of the values entered, not just its heading",
        "A checkout-steps progress indicator naming all five, the current one carrying aria-current=step",
        "Enclosed checkout: while the checkout region is active, hide the global nav and the search bar (an interaction flow of type toggleVisibility targeting the navbar and the search bar)",
        "A guest-checkout option, offered before account creation is pushed",
        "Inline form validation on blur, not only on submit",
        "Order summary visible in every stage",
        "A clear CTA per stage (e.g. Continue to Payment, not a generic Submit)",
        "Final stage is an order-confirmation component with an order number, the items and a delivery estimate; payment action type submitOrder saves the order to browser storage; the copy says it is a demo, not a real payment",
    ],
    "search": [
        "Result count stated in words next to the query (24 results for 'headphones')",
        "The query stays visible in the search field after submitting",
        "A sort control and the same filter panel the listing page uses",
        "An empty-results state with a suggestion, never a blank region",
    ],
    "account": [
        "Order history list with status badges and a re-order CTA",
        "Wishlist with add-to-cart from the wishlist",
        "Saved-addresses section",
        "Profile settings (name, email, password)",
    ],
}

# Defaults match the planning prompt: a null commerce_type is single_brand, a
# null style is catalog_heavy.
_COMMERCE_DEFAULT = "single_brand"
_STYLE_DEFAULT = "catalog_heavy"


def _run_page_type(layout_payload):
    """The single page's pageType from a layout payload, or None if not chosen yet."""
    try:
        pages = (layout_payload or {}).get("pages") or []
        if pages:
            return pages[0].get("pageType")
    except AttributeError:
        pass
    return None


def _build_run_brief(design_schema, page_type=None):
    """Assemble the run-specific brief: the commerce line, the style line, and
    the Baymard checklist for the chosen page type.

    Looks up and stitches together; it does not validate. When page_type is
    None (the layout stage has not chosen one yet) it lists the page types and
    their headline components instead, so layout can pick and shape regions."""
    ui = (design_schema or {}).get("ui") or {}
    commerce = ui.get("commerce_type") or _COMMERCE_DEFAULT
    style = ui.get("style") or _STYLE_DEFAULT

    lines = [
        f"Commerce type -- {commerce}: "
        f"{_COMMERCE_RULES.get(commerce, _COMMERCE_RULES[_COMMERCE_DEFAULT])}",
        f"Design style -- {style}: "
        f"{_STYLE_RULES.get(style, _STYLE_RULES[_STYLE_DEFAULT])}",
    ]

    if page_type:
        checklist = _BAYMARD_CHECKLISTS.get(page_type, [])
        if checklist:
            lines.append(f"Baymard checklist for the {page_type} page "
                         f"(include every item):")
            lines += [f"  - {item}" for item in checklist]
    else:
        lines.append("Page types you may choose, and a couple of their must-haves:")
        for page, items in _BAYMARD_CHECKLISTS.items():
            head = "; ".join(items[:2])
            lines.append(f"  - {page}: {head} ...")

    return "\n".join(lines)


print("Shared spec rules ready: house rules + commerce/style/Baymard tables + _build_run_brief")


# ==========================================================================
# UISpecificationBundle validation tool suite
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# The planning model, shared by the four specification generators
#
# It has its own name because six different models in this project were all
# called `model`, so building a chain meant hoping the right one was bound.
#
# The four generators run in order and each reads what the one before produced.
# None of them trusts the model's first answer: each hands its result to the
# repair helpers, and any complaint goes back into the next attempt as extra
# context. Three attempts, then the generator gives up and stores nothing.
# ═══════════════════════════════════════════════════════════════════════════
import json
from typing import Any, Dict, Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command


_spec_model = ChatOpenAI(model_name="gpt-5.4", temperature=0.0, timeout=120, max_retries=2)


# ==========================================================================
# layout_specification_generator
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# layout_specification_generator
#
# Which pages exist, and which regions each page has. One page per run.
# ═══════════════════════════════════════════════════════════════════════════
import json
from typing import Any, Dict, Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command


layout_prompt = PromptTemplate.from_template(
    """You are the layout stage of a planning pipeline. Decide the single page and the regions it contains.
{house_rules}
CONTEXT
RUN BRIEF
{run_brief}
INPUTS
- input_query: {input_query}
- design_schema (JSON): {design_schema}
- validation_feedback (may be empty): {validation_feedback}

Produce one LayoutSpecification holding EXACTLY ONE page. The page has pageName, pageType, pageLayoutType, responsive, and regions. Each region has only a name, ownedBy, and layoutType. Name regions only; the next stage decides their contents.
CONSTRAINTS
- Return exactly one page, never zero or two.
- Storefront, listing, cart, checkout, or similar requested areas are REGIONS of that one page, never separate pages.
- Navigation uses in-page anchor scrolling, never page loads. Every region name must be unique within the page and reachable by an anchor.
- Choose the single pageType the request emphasises. For example, browsing plus a cart is a listing page with a cart region, not two pages.
- pageType must be one of:
""" + literal_values(PageType) + """
- pageLayoutType and every region layoutType must be one of:
""" + literal_values(LayoutType) + """
- ownedBy must be one of:
""" + literal_values(AgentType) + """
- design_schema is constraints, not content. Never add a feature it switches off.
- The page is always built responsive for phone and desktop. Page.responsive stays true; responsiveness is fixed, never a per-run choice.
- A thin request is still buildable: choose the regions that kind of shop needs rather than returning fewer.
- Never return an empty page list. If the request does not say what is sold, use a home page with a hero region, product grid region, and footer.

VERIFICATION
Before the result is accepted, Python verifies that:
- it parses as a LayoutSpecification;
- pages contains exactly one page;
- the page contains at least one region;
- region names are unique within the page.

ITERATION POLICY
- Empty validation_feedback means this is the first attempt.
- Filled validation_feedback contains YOUR OWN previous answer and its failures. Edit that answer rather than rebuilding from the request, and do not change anything not criticised.
- Fix every reported issue in one pass.
- Return the complete corrected object, never a patch or patch description.
- Keep pageName and all region names exactly unchanged.

OUTPUT
Return only the LayoutSpecification object. No markdown or explanation.
"""
)

layout_specification_generator_chain = (
    layout_prompt | _spec_model.with_structured_output(LayoutSpecification, method="function_calling")
)

layout_specification_generator_tool = layout_specification_generator_chain.as_tool(
    name="layout_specification_generator",
    description="Generate LayoutSpecification from input_query + design_schema.",
    arg_types={"input_query": str, "design_schema": str, "house_rules": str, "run_brief": str, "validation_feedback": str},
)


def _spec_tool_command(field: str, spec: Optional[Dict[str, Any]], message: str,
                       tool_call_id: str) -> Command:
    """The Command a generator's @tool adapter returns.

    Each stage is a plain function returning (spec, message): spec is the
    stored field, or None when the stage gave up, and message is the text the
    tool reports. run_planning_pipeline calls the plain functions directly; the
    @tool adapters exist so the tool schemas stay what they were."""
    update: Dict[str, Any] = {}
    if spec is not None:
        update[field] = spec
    update["messages"] = [ToolMessage(content=message, tool_call_id=tool_call_id)]
    return Command(update=update)


def generate_layout_specification(s: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str]:
    """Layout stage as a plain function: (layout_specification | None, message)."""
    input_query = str(s.get("input_query", "") or "")
    design_schema_payload: Any = s.get("design_schema") or {}

    def _validate(candidate: Any) -> Optional[str]:
        try:
            obj = _coerce_layout_spec(candidate)
        except Exception as e:
            return f"[layout] LayoutSpecification validation warning: {e}"
        if not obj.pages:
            return "[layout] LayoutSpecification.pages must be non-empty"
        # The ceiling, not just the floor. This message is handed back to the
        # model as validation_feedback and the chain retries, so a request for
        # several pages is corrected here instead of failing three stages later
        # at the Secondary Orchestrator's refusal.
        if len(obj.pages) > 1:
            names = [p.pageName for p in obj.pages]
            return (f"[layout] LayoutSpecification.pages must contain EXACTLY ONE "
                    f"page, got {len(obj.pages)}: {names}. This system builds ONE "
                    f"document per run. Re-plan the extra pages as regions of the "
                    f"single page, and pick the pageType the request emphasises.")
        for page in obj.pages:
            if not page.regions:
                return f"[layout] Page '{page.pageName}' must contain at least 1 region"
        return None

    base_payload = {
        "input_query": input_query,
        "design_schema": json.dumps(design_schema_payload, ensure_ascii=False),
        "house_rules": _SPEC_HOUSE_RULES,
        "run_brief": _build_run_brief(design_schema_payload, page_type=None),
    }
    candidate, error = _invoke_structured_with_retries(
        stage="layout",
        structured_tool=layout_specification_generator_tool,
        base_payload=base_payload,
        validate_result=_validate,
        max_attempts=3,
    )

    if error or candidate is None:
        return None, f"FAILED to generate layout_specification.\n{error}"

    result_obj = _coerce_layout_spec(candidate)
    result = result_obj.model_dump()
    return result, "Stored layout_specification."


@tool
def layout_specification_generator(runtime: ToolRuntime[ContextState]) -> Command:
    """Generate and store layout_specification."""
    spec, message = generate_layout_specification(runtime.state)
    return _spec_tool_command("layout_specification", spec, message, runtime.tool_call_id)


# ==========================================================================
# Unit Test
# ==========================================================================

from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Union
import json

ToolLike = Union[str, Any]  # name in globals() OR the tool object itself

def _pretty(title: str, obj: Any) -> None:
    print(f"\n--- {title} ---")
    try:
        print(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True))
    except TypeError:
        # Fallback for non-JSON-serializable objects
        print(repr(obj))


def _tool_failure_reason(update: Dict[str, Any]) -> str:
    """The text the tool wrote to explain itself, ready to print.

    A generator that gives up returns only {"messages": [ToolMessage(...)]}, and
    that message names the reason for every attempt. The assertion above used to
    report the missing key and drop the message, so the one useful sentence in
    the object was never seen.
    """
    messages = update.get("messages") or []
    parts = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
    if not parts:
        return ("The tool returned no message either, so it failed without "
                "saying why. Read the tool's give-up branch.")
    return "The tool said why:\n" + "\n".join(parts)


def run_tool_unit_test_state_snapshots(
    *,
    tool_name: ToolLike,
    input_query: str,
    # Which keys to show in BEFORE/AFTER snapshots (defaults to a focused set)
    fields_to_show: Optional[List[str]] = None,
    # Which keys MUST be present in Command.update (e.g., ["layout_specification"])
    expected_update_fields: Optional[List[str]] = None,
    initial_state: Optional[Dict[str, Any]] = None,
    tool_call_id: str = "unit-test",
    verbose: bool = True,
    assert_after: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None,
    forbidden_update_fields: Optional[List[str]] = None,
 ) -> Dict[str, Any]:
    """
    General unit-test harness for LangGraph @tool wrappers.

    - Builds a dummy runtime with `.state` and `.tool_call_id`
    - Calls the tool function (StructuredTool.func)
    - Captures BEFORE/AFTER snapshots for selected state fields
    - Validates expected/forbidden keys in Command.update
    """
    if fields_to_show is None:
        fields_to_show = ["input_query", "design_schema", "tavily_search_result", "extra_requirements", "layout_specification"]

    # Resolve tool object
    if isinstance(tool_name, str):
        if tool_name not in _flat_namespace():
            raise KeyError(f"Tool '{tool_name}' not found in globals().")
        tool_obj = _flat_namespace()[tool_name]
    else:
        tool_obj = tool_name

    dummy_state: Dict[str, Any] = dict(initial_state or {})
    dummy_state.setdefault("input_query", input_query)
    dummy_runtime = SimpleNamespace(state=dummy_state, tool_call_id=tool_call_id)

    before_state = dict(dummy_state)
    before_snapshot = {k: before_state.get(k) for k in fields_to_show}
    if verbose:
        _pretty("BEFORE (selected state fields)", before_snapshot)

    tool_fn = getattr(tool_obj, "func", None)
    if tool_fn is None:
        if not callable(tool_obj):
            raise TypeError("Provided tool is neither a StructuredTool with .func nor a callable")
        tool_fn = tool_obj

    cmd = tool_fn(dummy_runtime)
    update = getattr(cmd, "update", None)
    if not isinstance(update, dict):
        raise AssertionError("Expected Command.update to be a dict")

    if expected_update_fields:
        missing = [k for k in expected_update_fields if k not in update]
        if missing:
            raise AssertionError(
                f"Expected {missing} in Command.update, got keys: "
                f"{sorted(update.keys())}\n"
                f"{_tool_failure_reason(update)}")

    if forbidden_update_fields:
        for k in forbidden_update_fields:
            if k in update:
                raise AssertionError(f"Did not expect '{k}' to be updated by this tool")

    after_state = dict(before_state)
    after_state.update(update)
    after_snapshot = {k: after_state.get(k) for k in fields_to_show}
    if verbose:
        _pretty("AFTER (selected state fields)", after_snapshot)
        _pretty("Command.update keys", sorted(update.keys()))

    if assert_after is not None:
        assert_after(before_state, after_state)

    return {
        "before_state": before_state,
        "after_state": after_state,
        "before_snapshot": before_snapshot,
        "after_snapshot": after_snapshot,
        "cmd": cmd,
        "update": update,
    }


# ==========================================================================
# Unit Test
# ==========================================================================
# # LIVE-LLM: costs credits, run manually only
# # Test layout_specification_generator: show input_query, design_schema, layout_specification BEFORE/AFTER
# # Deliberately asks for several areas in ONE sentence without asking for
# # several pages. That is the shape a real request takes, and the right answer
# # is one page whose regions are those areas.
# test_query = (
#     "Build a modern dark-mode product listing page for a sneaker store. "
#     "Use a top nav and a compact grid. Include search, filters, sorting, cart, and wishlist. "
#     "Also add a sticky promo banner. Infer the remaining details based on best practices for e-commerce UI design."
#  )

# seed_schema = DesignSchema(
#     ui=UI(
#         type="product_listing",
#         # "modern" until 2026-08-15, when style became a fixed list of seven
#         # words and stopped accepting free text. The brief says "compact grid"
#         # and asks for filters and sorting, which is what catalog_heavy means.
#         style="catalog_heavy",
#         commerce_type="multi_brand_retailer",
#         density="compact",
#         navigation="top_nav",
#     ),
#     theme=Theme(mode="dark"),
#     extra_requirements=["Sticky promo banner on scroll"],
# ).model_dump()

# result = run_tool_unit_test_state_snapshots(
#     tool_name="layout_specification_generator",
#     input_query=test_query,
#     initial_state={
#         "design_schema": seed_schema,
#         "layout_specification": None,
#     },
#     fields_to_show=["input_query", "design_schema", "layout_specification"],
#     expected_update_fields=["layout_specification"],
#     forbidden_update_fields=["design_schema"],
#     verbose=True,
#  )

# print("\nPASS: layout_specification_generator produced layout_specification")

# # The page cap lives in this generator's own validator, so this is the live
# # proof of it. A second page here means the cap did not hold against a real
# # model, which no offline test can tell you.
# _lay_pages = (result["after_state"].get("layout_specification") or {}).get("pages") or []
# assert len(_lay_pages) == 1, (
#     f"FAIL: {len(_lay_pages)} pages came back: "
#     f"{[p.get('pageName') for p in _lay_pages if isinstance(p, dict)]}. "
#     f"This system builds ONE document per run and the generator's validator is "
#     f"supposed to reject anything else.")
# print("PASS: exactly one page, as the single-document rule requires")

# # Print layout_specification as a clear parent → child architecture tree
# layout_spec = (result.get("after_state") or {}).get("layout_specification") or {}

# def _print_layout_architecture(layout: dict) -> None:
#     def _safe_dict(x):
#         return x if isinstance(x, dict) else {}
#     def _safe_list(x):
#         return x if isinstance(x, list) else []

#     pages = _safe_list(layout.get("pages"))
#     print("\n=== Layout Specification Architecture (parent → child) ===")
#     if not pages:
#         print("(no pages)")
#         return

#     for page in pages:
#         page = _safe_dict(page)
#         page_name = page.get("pageName") or page.get("name") or "<unnamed page>"
#         page_layout_type = (
#             page.get("pageLayoutType")
#             or _safe_dict(page.get("layout")).get("type")
#             or "<missing pageLayoutType>"
#         )
#         responsive = page.get("responsive")
#         if responsive is None:
#             responsive = _safe_dict(page.get("layout")).get("responsive")

#         print(f"\nPage")
#         print(f"  pageName: {page_name}")
#         print(f"  pageLayoutType: {page_layout_type}")
#         if responsive is not None:
#             print(f"  responsive: {responsive}")

#         regions = _safe_list(page.get("regions"))
#         if not regions:
#             print("  regions: []")
#             continue

#         print("  regions:")
#         for region in regions:
#             region = _safe_dict(region)
#             region_name = region.get("name") or "<unnamed region>"
#             owned_by = region.get("ownedBy")
#             layout_type = region.get("layoutType") or _safe_dict(region.get("layout")).get("type")

#             print("    - Region")
#             print(f"      name: {region_name}")
#             if owned_by is not None:
#                 print(f"      ownedBy: {owned_by}")
#             if layout_type is not None:
#                 print(f"      layoutType: {layout_type}")

#             # A Region carries name, ownedBy and layoutType, and nothing
#             # else. Its components live in the component specification under
#             # regionComponents[name], which the layout stage has not written
#             # yet. Two lines here used to read region["componentRefs"] and
#             # region["components"]. Region has never had either, so the lookup
#             # returned None and every region of every correct answer printed
#             # "components: []" as though the layout had come back empty.
#             print(f"      components: named later, in the component "
#                   f"specification under regionComponents[{region_name!r}]")

# _print_layout_architecture(layout_spec)

# # What every attempt of this stage cost. One slow stage ruins a run even when
# # the other three are quick, so the total is the number to watch.
# print()
# spec_timing_report("layout")


# ==========================================================================
# components_specification_generator
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# components_specification_generator
#
# The tree of elements inside those regions.
#
# This one is handed an empty scaffold built from the layout, with every
# page and region already present as an empty list. Filling in blanks is a
# far easier task than inventing a structure that has to match one, and the
# guard downstream refuses any region left out.
# ═══════════════════════════════════════════════════════════════════════════
import json
import re
from typing import Any, Dict, Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command


# ── No-image contract at the DATA layer (2026-08-30) ──────────────────
# The system embeds no images. The HTML agent's guard already refuses every
# <img>, but the model kept putting image URLs into the shared dataSets records
# (image/imageAlt/...) and even whole image-only datasets (galleryImages,
# brewingStoryImages). The JavaScript agent renders from those records and had no
# such guard, so the URLs reached the page as broken <img> tags (PO-08
# po0113ce72). The prompt now asks the model not to; this strips them out so no
# downstream agent can render one even if it tries. Prompt persuades, Python
# guarantees.
_IMAGE_RECORD_KEYS  = ("image", "imageAlt", "imageUrl", "imageURL",
                       "img", "photo", "thumbnail", "alt")
_IMAGE_DATASET_NAME = re.compile(r"image|gallery|photo|thumbnail", re.IGNORECASE)


def _strip_image_content(spec: dict) -> dict:
    """Remove images from a components_specification's dataSets.

    Two moves: drop the image keys from every record, and drop a dataset that
    exists only to hold images (its name says so). A record keeps its id, name
    and every non-image field, so products/cart/categories survive intact -- only
    the image URLs and the image-only lists go. Returns a shallow copy; the input
    is not mutated."""
    if not isinstance(spec, dict):
        return spec
    data_sets = spec.get("dataSets")
    if not isinstance(data_sets, dict):
        return spec
    kept = {}
    for name, records in data_sets.items():
        if _IMAGE_DATASET_NAME.search(str(name)):
            continue  # an image-only dataset -- galleryImages, productPhotos, ...
        if isinstance(records, list):
            records = [
                {k: v for k, v in rec.items() if k not in _IMAGE_RECORD_KEYS}
                if isinstance(rec, dict) else rec
                for rec in records
            ]
        kept[name] = records
    new_spec = dict(spec)
    new_spec["dataSets"] = kept
    return new_spec


# html-validate's aria-label-misuse ALLOWS aria-label on a short list of
# elements (interactive, labelable, landmark) and refuses it everywhere else.
# The components stage still writes props.ariaLabel on other nodes ('Coffee
# price' on a <span>), the HTML agent copies props onto the element as it is
# told to, and the linter then refuses the page: on PO-08 4fb17fbe 16 of the
# first save's 19 lint errors were this one, on two span nodes rendered eight
# times, and fixing them cost a 75 s rewrite (speed-cost ticket 04). The HTML
# prompt already forbids it; this removes the prop so the spec stops asking
# for what the linter refuses. The list is the linter's own, probed through
# run_html_validate on 2026-11-10 (span, p, div, headings, ul, li, strong,
# small, an <a> without href ... are all refused). A role or a tabindex makes
# the label valid on any element, so those nodes keep it.
_ARIA_LABEL_VALID_TAGS = {
    "article", "aside", "footer", "form", "header", "main", "nav", "search",
    "section", "area", "dialog", "fieldset", "figure", "iframe", "img",
    "summary", "details", "table", "td", "th", "button", "input", "select",
    "textarea", "output", "label", "meter", "progress", "audio", "video",
}


def _map_component_nodes(spec, fix_node):
    """A copy of spec with fix_node applied to every dict under 'pages',
    children first. fix_node gets a shallow copy it may change and return.
    The input is not mutated."""
    if not isinstance(spec, dict) or not isinstance(spec.get("pages"), list):
        return spec

    def walk(node):
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        return fix_node({k: walk(v) if isinstance(v, (dict, list)) else v
                         for k, v in node.items()})

    new_spec = dict(spec)
    new_spec["pages"] = walk(spec["pages"])
    return new_spec


def _strip_invalid_aria_labels(spec: dict) -> dict:
    """Drop props.ariaLabel from every component node html-validate would
    refuse it on. Returns a copy; the input is not mutated."""
    def fix(node):
        props = node.get("props")
        if not (isinstance(node.get("tag"), str) and isinstance(props, dict)
                and "ariaLabel" in props):
            return node
        tag = node["tag"].strip().lower()
        valid = (tag in _ARIA_LABEL_VALID_TAGS
                 or (tag == "a" and props.get("href"))
                 or props.get("role")
                 or any(k.lower() == "tabindex" for k in props))
        if not valid:
            node["props"] = {k: v for k, v in props.items() if k != "ariaLabel"}
        return node
    return _map_component_nodes(spec, fix)


# html-validate's wcag/h32 wants a submit button inside every <form>. The
# components stage also uses `form` for a group of controls nothing submits (a
# roast filter made of type="button" toggles, a sort bar around a <select>).
# The HTML agent then had to add a submit button no flow handles: on PO-08
# 4fb17fbe the page shipped an "Apply roast filter" button whose click reloads
# the page and drops the script's state. Such a node is a form in name only,
# so it becomes a div; a form with a submit event, or one that holds a submit
# button, is a real form and stays.
def _retag_unsubmitted_forms(spec: dict) -> dict:
    """Turn every `form` node that nothing submits into a `div`. Returns a
    copy; the input is not mutated."""
    def _event_name(ev):
        name = (ev.get("event") or ev.get("name")) if isinstance(ev, dict) else ev
        return str(name or "").strip().lower()

    def _holds_submit(node):
        if isinstance(node, list):
            return any(_holds_submit(n) for n in node)
        if not isinstance(node, dict):
            return False
        props = node.get("props") if isinstance(node.get("props"), dict) else {}
        if str(props.get("type") or "").strip().lower() == "submit":
            return True
        return _holds_submit(node.get("children"))

    def fix(node):
        if not (isinstance(node.get("tag"), str)
                and node["tag"].strip().lower() == "form"):
            return node
        submitted = any(_event_name(ev) in ("onsubmit", "submit")
                        for ev in node.get("events") or [])
        if not submitted and not _holds_submit(node.get("children")):
            node["tag"] = "div"
        return node
    return _map_component_nodes(spec, fix)


components_prompt = PromptTemplate.from_template(
    """You are the components stage of a planning pipeline. Decide what sits inside each region and what content the page shows.
CONTEXT
{house_rules}
RUN BRIEF
{run_brief}
INPUTS
- input_query: {input_query}
- layout_specification (JSON): {layout_specification}
- required_component_contract:
{required_component_contract}
- component_scaffold (JSON): {component_scaffold}
- validation_feedback (may be empty): {validation_feedback}

Produce one ComponentSpecification with exactly two top-level keys:
- pages: one entry per layout page, each with pageName and regionComponents.
- dataSets: the run's real records.

dataSets sits beside pages at the top level, never inside regionComponents or on a page.
Start from component_scaffold exactly. Keep every pageName and regionComponents key unchanged. Replace each empty region list with its component trees and the empty dataSets object with real records. Three downstream stages read only this specification, so every field they need must be here.
COMPONENT vs CONTENT
Keep the tree small. Create a ComponentNode only for something with its own structure, styling, behaviour or state, or something a test must target directly. Everything else is content in dataSets or prose written into the region.
- Repeated items are ONE node rendered once per dataSets record: eight products are one product-card node plus eight records, never eight cards; three cart lines are one cart-item plus three records.
- Headings, tag lines, body copy, values, prices and product names are content, not nodes. Prices and names belong in dataSets; headings and copy are prose.
- A specified value such as "Morning Tide" or $18 remains content. Only its own behaviour or state, such as a changing sale price or a linked name, promotes it to a node.
- An element the user types into or clicks stays a node with its own id so tests can reach it. Static display text does not.
- Where they collide, the region rule wins over the content rule: every region needs at least one node. A prose-only region gets exactly ONE node: a CSS-owned container carrying that region's className, with all copy as its content. One node for the whole region, never one per paragraph. 
Only a region the layout marks ownedBy JavaScript may remain empty.

HARD CONSTRAINTS
- dataSets contains the run's real content as named record lists. A storefront needs 6 to 12 products; a cart needs cartItems. Every record has a unique id, non-empty name, and every displayed field such as price, category or rating. Use plausible names and prices, 
never Product 1 or blank values. HTML renders these records and JavaScript reuses the same records when interactions rewrite content.
- This system embeds no images. Records never contain image, photo, thumbnail or url fields, and there are no image-only datasets such as galleryImages or product-photo lists. A picture is a labelled placeholder drawn from the record's name.
- Each dataBinding.source points to its list path, for example products.price. Never encode dataBinding as a plain string.
- ComponentNode.id is unique across the whole run and remains unchanged in later specifications.
- ownedBy is one of:
""" + literal_values(AgentType) + """
Never null or blank. A component not requiring CSS ownership is owned by HTML; do not leave className blank to avoid deciding ownership.
- componentCategory is one of:
""" + literal_values(ComponentCategory) + """
It is written verbatim as the HTML data-component attribute. Omit it for a purely structural wrapper that nothing addresses directly.
- Omit unused optional fields instead of sending empty strings.
- Every layout region must be planned with at least one component tree. Only a region marked ownedBy JavaScript may have an empty list. A prose-only region uses exactly ONE CSS-owned container with that region's className, as COMPONENT vs CONTENT describes.
- Every purchasable item is a product-card; a collection of them is a product-grid. It CARRIES its componentCategory so record and image rules can detect it.
- Any component the user TYPES into, such as a search-bar or text filter, includes its actual <input> or <textarea> as a CHILD component with its own id; never model the field as one opaque node.
- A quantity-selector is interactive, not a label: give it a decrement button and an increment button as CHILD components, each with its own id and an onClick event, so the shopper can change the amount in the cart. A bare number with no buttons is not a quantity-selector.
- A mini-cart drawer opens over the page, so it needs a close control: a button CHILD with its own id and an onClick event that closes the drawer (id like 'mini-cart-close', flowName like 'closeMiniCart'). A remove or checkout button does not close it.
- Every event has a non-empty name and non-empty flowName.
- Every CSS-owned component has a className.

VERIFICATION
Python validates the whole answer and returns all problems at once:
- it parses as a ComponentSpecification
- page names exactly match the layout
- each page's regionComponents keys exactly match that layout page's region names
- every component carries ownedBy
- every event has non-empty name and flowName
- every CSS-owned component has className
- merchandise pages contain records in dataSets
- purchasable items satisfy the product-card/product-grid and componentCategory rules
- typed-into controls expose their actual input child with its own id

ITERATION POLICY
- Empty validation_feedback means first attempt.
- Filled validation_feedback contains YOUR OWN previous answer and its problems. Edit that answer rather than rebuilding from the request, and do not change uncriticised parts.
- Fix every reported point in one pass.
- Return the whole corrected object, never a patch or patch description.
- Keep ids, classNames and flowNames exactly as they were.

ERROR HANDLING
A layout region not mentioned by the request still gets a sensible component. Never drop its key or leave it empty unless the layout marks it ownedBy JavaScript.
If what the shop sells is unclear, invent a plausible catalogue of the right kind and populate dataSets. Never leave dataSets empty, because downstream agents would otherwise invent inconsistent content.
OUTPUT
Return only the ComponentSpecification object. No markdown, no explanation.
"""
)

components_specification_generator_chain = (
    components_prompt | _spec_model.with_structured_output(ComponentSpecificationDraft, method="function_calling")
)

components_specification_generator_tool = components_specification_generator_chain.as_tool(
    name="components_specification_generator",
    description="Generate ComponentSpecification from input_query + layout_specification.",
    arg_types={
        "input_query": str,
        "layout_specification": str,
        "required_component_contract": str,
        "component_scaffold": str,
        "house_rules": str,
        "run_brief": str,
        "validation_feedback": str,
    },
)


def generate_components_specification(s: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str]:
    """Components stage as a plain function: (components_specification | None, message)."""
    input_query = str(s.get("input_query", "") or "")
    layout_payload = s.get("layout_specification") or {}
    design_schema_payload = s.get("design_schema") or {}
    _page_type = _run_page_type(layout_payload)
    validated_candidate: Dict[str, Any] | None = None

    def _validate(candidate: Any) -> Optional[str]:
        nonlocal validated_candidate
        validated_candidate = None
        try:
            repaired_candidate = _repair_component_spec_from_layout(layout_payload, candidate)
            obj = _coerce_component_spec(repaired_candidate)
        except Exception as e:
            return f"[components] ComponentSpecification validation warning: {e}"

        # Did the repair keep everything the model produced?
        #
        # The repair rebuilds `pages` from the layout, which is its job. Every
        # other top-level field must survive untouched. When one does not, the
        # guard below reports it as though the model had omitted it, and the
        # next hour is spent reading prompts instead of Python. That happened on
        # 2026-08-15 with dataSets, and the repair only stops doing it once its
        # cell has been re-executed, so a stale kernel looks exactly like a
        # model failure.
        _dropped = sorted(
            k for k, v in (candidate if isinstance(candidate, dict) else {}).items()
            if k != "pages"
            and v not in (None, "", [], {})
            and not (repaired_candidate or {}).get(k)
        )
        if _dropped:
            return (
                "[components] INTERNAL, not a model failure: the repair step "
                f"dropped {', '.join(_dropped)} after the model produced it. "
                "Retrying cannot help, because the loss happens after the model "
                "answers. Re-run the specification repair helpers cell "
                "(_repair_component_spec_from_layout), then this one. If it "
                "persists, the repair is discarding a field it does not "
                "recognise instead of carrying it through."
            )
        if not obj.pages:
            return "[components] ComponentSpecification.pages must be non-empty"
        try:
            layout_obj = _coerce_layout_spec(layout_payload)
        except Exception as e:
            return f"[components] Cannot validate against layout_specification: {e}"
        component_contract_warning = _validate_component_contract_for_downstream(layout_obj, obj)
        if component_contract_warning:
            return component_contract_warning
        validated_candidate = obj.model_dump()
        return _bundle_validate_or_warn(
            stage="components",
            layout=layout_payload,
            component=obj,
            interaction={"pages": []},
            decoration={},
        )

    base_payload = {
        "input_query": input_query,
        "layout_specification": json.dumps(layout_payload, ensure_ascii=False),
        "required_component_contract": _build_component_contract_from_layout(layout_payload),
        "component_scaffold": json.dumps(_build_component_scaffold_from_layout(layout_payload), ensure_ascii=False),
        "house_rules": _SPEC_HOUSE_RULES,
        "run_brief": _build_run_brief(design_schema_payload, _page_type),
    }
    def _last_resort(last_candidate: Any, last_error: Optional[str]) -> Optional[Any]:
        # The model spent all its attempts. If the only thing still wrong is
        # empty HTML regions, fill them so a paid run is not thrown away; any
        # other failure class still aborts (_validate must come back clean).
        try:
            repaired = _repair_component_spec_from_layout(layout_payload, last_candidate)
            filled, _n = _fill_empty_html_regions(layout_payload, repaired)
        except Exception:
            return None
        if not _n:
            return None
        if _validate(filled) is None:
            _spec_progress(
                f"   [components] last-resort fill: the model left {_n} HTML "
                f"region(s) empty after 3 attempts; Python filled them "
                f"(product-listing to a product-grid bound to products, other to "
                f"a CSS container) so the run completes instead of aborting.")
            return validated_candidate
        return None

    candidate, error = _invoke_structured_with_retries(
        stage="components",
        structured_tool=components_specification_generator_tool,
        base_payload=base_payload,
        validate_result=_validate,
        max_attempts=3,
        on_give_up=_last_resort,
        normalize=lambda c: _repair_component_spec_from_layout(layout_payload, c),
    )

    if error or candidate is None:
        return None, f"FAILED to generate components_specification.\n{error}"

    result_obj = _coerce_component_spec(validated_candidate or candidate)
    result = _strip_image_content(result_obj.model_dump())
    # Order matters: a form nothing submits becomes a div, and a div cannot
    # carry an aria-label.
    result = _strip_invalid_aria_labels(_retag_unsubmitted_forms(result))
    return result, "Stored components_specification."


@tool
def components_specification_generator(runtime: ToolRuntime[ContextState]) -> Command:
    """Generate and store components_specification, then bundle-validate layout-component."""
    spec, message = generate_components_specification(runtime.state)
    return _spec_tool_command("components_specification", spec, message, runtime.tool_call_id)


# ==========================================================================
# interactions_specification_Generator
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# interactions_specification_generator
#
# What happens when the user clicks something.
# ═══════════════════════════════════════════════════════════════════════════
import json
from typing import Any, Dict, Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command


interactions_prompt = PromptTemplate.from_template(
    """You are the interactions stage of a deterministic planning pipeline. Define what happens when users click, type, or hover.
{house_rules}
RUN BRIEF
{run_brief}
INPUTS
- input_query: {input_query}
- layout_specification (JSON): {layout_specification}
- components_specification (JSON): {components_specification}
- validation_feedback (may be empty): {validation_feedback}

CONSTRAINTS
- Produce one InteractionSpecification with one flow for every event declared by the components. Each flow names itself, its trigger, and the actions that trigger performs.
- Cover every page declared by the layout. A page with no interactions still appears with an empty flow list.
- action.type must be one of:
""" + literal_values(ActionType) + """
- The system builds ONE document. Prefer updateState, toggleVisibility, or updateData. Use navigate only for an in-page anchor; navigation almost always means scrolling within the same page.
- result_state, when present, is an object containing only a non-empty description.
- Keep every flow name exactly as declared by the components.
- Every trigger and action must target an existing component id, and every state transitioned to must be declared on that component.
- Never invent a component id. If a flow has nowhere valid to point, drop it.
- If a component declares an event you do not understand, still create its flow using the simplest honest behaviour.

VERIFICATION
Python validates that:
- the answer parses as an InteractionSpecification
- every layout page is covered
- every flowName declared by the components has a same-named flow
- every trigger and action targets an existing component id
- every transitioned-to state is declared on that component

ITERATION POLICY
- Empty validation_feedback means this is the first attempt.
- Filled validation_feedback contains YOUR OWN previous answer and its failures. Edit that answer rather than rebuilding from the request, and do not change anything that was not criticised.
- Fix every reported problem in one pass.
- Return the complete corrected object, never a patch or patch description.
- Keep flow names exactly unchanged.

OUTPUT
Return only the InteractionSpecification object. No markdown, no explanation.
"""
)

interactions_specification_generator_chain = (
    interactions_prompt | _spec_model.with_structured_output(InteractionSpecification, method="function_calling")
)

interactions_specification_generator_tool = interactions_specification_generator_chain.as_tool(
    name="interactions_specification_generator",
    description="Generate InteractionSpecification from input_query + layout_specification + components_specification.",
    arg_types={
        "input_query": str,
        "layout_specification": str,
        "components_specification": str,
        "house_rules": str,
        "run_brief": str,
        "validation_feedback": str,
    },
)


def generate_interactions_specification(s: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str]:
    """Interactions stage as a plain function: (interactions_specification | None, message)."""
    input_query = str(s.get("input_query", "") or "")
    layout_payload: Any = s.get("layout_specification") or {}
    components_payload: Any = s.get("components_specification") or {}
    design_schema_payload: Any = s.get("design_schema") or {}
    _page_type = _run_page_type(layout_payload)

    def _validate(candidate: Any) -> Optional[str]:
        try:
            obj = _coerce_interaction_spec(candidate)
        except Exception as e:
            return f"[interactions] InteractionSpecification validation warning: {e}"
        if not obj.pages:
            return "[interactions] InteractionSpecification.pages must be non-empty"
        try:
            layout_obj = _coerce_layout_spec(layout_payload)
        except Exception as e:
            return f"[interactions] Cannot validate against layout_specification: {e}"
        layout_page_names = {p.pageName for p in layout_obj.pages}
        interaction_page_names = {p.pageName for p in obj.pages}
        missing_pages = layout_page_names - interaction_page_names
        if missing_pages:
            return "[interactions] InteractionSpecification missing pages for layout: " + ", ".join(sorted(missing_pages))
        return _bundle_validate_or_warn(
            stage="interactions",
            layout=layout_payload,
            component=components_payload,
            interaction=obj,
            decoration={},
        )

    base_payload = {
        "input_query": input_query,
        "layout_specification": json.dumps(layout_payload, ensure_ascii=False),
        "components_specification": json.dumps(components_payload, ensure_ascii=False),
        "house_rules": _SPEC_HOUSE_RULES,
        "run_brief": _build_run_brief(design_schema_payload, _page_type),
    }
    candidate, error = _invoke_structured_with_retries(
        stage="interactions",
        structured_tool=interactions_specification_generator_tool,
        base_payload=base_payload,
        validate_result=_validate,
        max_attempts=3,
    )

    if error or candidate is None:
        return None, f"FAILED to generate interactions_specification.\n{error}"

    result_obj = _coerce_interaction_spec(candidate)
    result = result_obj.model_dump()
    return result, "Stored interactions_specification."


@tool
def interactions_specification_generator(runtime: ToolRuntime[ContextState]) -> Command:
    """Generate and store interactions_specification, then bundle-validate layout-component-interaction."""
    spec, message = generate_interactions_specification(runtime.state)
    return _spec_tool_command("interactions_specification", spec, message, runtime.tool_call_id)


# ==========================================================================
# Unit Test
# ==========================================================================
# # LIVE-LLM: costs credits, run manually only
# # Unit test: interactions_specification_generator (reuses run_tool_unit_test_state_snapshots from Cell 65)
# # Both flows stay in one document, which is the only shape this system builds.
# # View Details scrolls to a section of the same page. Quick View opens a modal.
# interaction_test_query = (
#     "Ecommerce UI: clicking a product card or View Details scrolls to the product "
#     "details section of the same page; "
#     "clicking Quick View opens a popup/modal with product details."
#  )

# # Dummy layout_specification. ONE page, because that is what a real run
# # produces. This fixture used to carry two, which taught by worked example that
# # a spec bundle spans pages and that a click hops between them. The old second
# # page is the productDetail region below.
# #
# # A Region names itself, its owning agent and how it arranges its children. It
# # does NOT list component ids -- those live in the component specification,
# # keyed by region name, and that key is the only join between the two.
# dummy_layout_specification = {
#     "pages": [
#         {
#             "pageName": "ProductListingPage",
#             "pageType": "plp",
#             "pageLayoutType": "single-column",
#             "responsive": True,
#             "regions": [
#                 {"name": "header", "ownedBy": "HTML", "layoutType": "flex-row"},
#                 {"name": "mainContent", "ownedBy": "HTML", "layoutType": "grid"},
#                 {"name": "productDetail", "ownedBy": "HTML",
#                  "layoutType": "flex-column"},
#             ],
#         },
#     ]
# }

# # Dummy components_specification, in the shape a real planning run emits.
# #
# # regionComponents keys MUST equal the layout region names exactly. Every event
# # carries a flowName, because that name is what the interactions generator has
# # to produce a matching InteractionFlow for -- which is the thing this test is
# # really checking. dataSets holds the run's real records, so the page describes
# # WHICH products rather than leaving each developer agent to invent its own.
# dummy_components_specification = {
#     "pages": [
#         {
#             "pageName": "ProductListingPage",
#             "regionComponents": {
#                 "header": [
#                     {
#                         "id": "header",
#                         "tag": "header",
#                         "ownedBy": "HTML",
#                         "className": "site-header",
#                         "children": [
#                             {
#                                 "id": "header_search_bar",
#                                 "tag": "input",
#                                 "ownedBy": "HTML",
#                                 "componentCategory": "search-bar",
#                                 "className": "search-bar",
#                                 "props": {"type": "search"},
#                                 "children": [],
#                             }
#                         ],
#                     },
#                 ],
#                 "mainContent": [
#                     {
#                         "id": "product_grid",
#                         "tag": "section",
#                         "ownedBy": "HTML",
#                         "componentCategory": "product-grid",
#                         "className": "product-grid",
#                         "children": [
#                             {
#                                 "id": "product_card",
#                                 "tag": "article",
#                                 "ownedBy": "HTML",
#                                 "componentCategory": "product-card",
#                                 "className": "product-card",
#                                 "dataBinding": {"source": "products"},
#                                 "events": [{"event": "onClick",
#                                             "flowName": "openProductDetails"}],
#                                 "children": [
#                                     {
#                                         "id": "view_details_button",
#                                         "tag": "button",
#                                         "ownedBy": "HTML",
#                                         "className": "view-details-btn",
#                                         "props": {"type": "button"},
#                                         "events": [{"event": "onClick",
#                                                     "flowName": "openProductDetails"}],
#                                         "children": [],
#                                     },
#                                     {
#                                         "id": "quick_view_button",
#                                         "tag": "button",
#                                         "ownedBy": "HTML",
#                                         "className": "quick-view-btn",
#                                         "props": {"type": "button"},
#                                         "events": [{"event": "onClick",
#                                                     "flowName": "openQuickView"}],
#                                         "children": [],
#                                     },
#                                 ],
#                             },
#                         ],
#                     },
#                     {
#                         "id": "product_details_modal",
#                         "tag": "section",
#                         "ownedBy": "HTML",
#                         "className": "product-modal",
#                         "props": {"aria-modal": "true"},
#                         "states": [{"name": "open"}, {"name": "hidden"}],
#                         "children": [
#                             {
#                                 "id": "modal_close_button",
#                                 "tag": "button",
#                                 "ownedBy": "HTML",
#                                 "className": "modal-close-btn",
#                                 "props": {"type": "button"},
#                                 "events": [{"event": "onClick",
#                                             "flowName": "closeQuickView"}],
#                                 "children": [],
#                             }
#                         ],
#                     },
#                 ],
#                 "productDetail": [
#                     {
#                         "id": "pdp_root",
#                         "tag": "section",
#                         "ownedBy": "HTML",
#                         "className": "product-detail",
#                         "children": [
#                             {
#                                 "id": "add_to_cart_button",
#                                 "tag": "button",
#                                 "ownedBy": "HTML",
#                                 "componentCategory": "add-to-cart-button",
#                                 "className": "add-to-cart-btn",
#                                 "props": {"type": "button"},
#                                 "events": [{"event": "onClick",
#                                             "flowName": "addToCart"}],
#                                 "children": [],
#                             }
#                         ],
#                     },
#                 ],
#             },
#         },
#     ],
#     "dataSets": {
#         "products": [
#             {"id": "p1", "name": "Aurora Pour-Over Kettle", "price": "58.00"},
#             {"id": "p2", "name": "Meridian Burr Grinder", "price": "129.00"},
#             {"id": "p3", "name": "Harbour Ceramic Dripper", "price": "34.00"},
#         ]
#     },
# }

# # The fixture is checked here, before the model is called. A fixture the schema
# # refuses fails every attempt on the INPUT, so the retries only prove the same
# # thing three times and the error names the model, not the fixture. That is
# # exactly what happened on 2026-08-16.
# _iv_layout = _coerce_layout_spec(dummy_layout_specification)
# _iv_components = _coerce_component_spec(dummy_components_specification)
# _iv_problem = _validate_component_contract_for_downstream(_iv_layout, _iv_components)
# assert not _iv_problem, f"FIXTURE INVALID before any model call: {_iv_problem}"
# print("Fixtures validate against today's schema. Calling the model.\n")

# # Every flowName the components declare. The generator must return an
# # InteractionFlow for each one, or the components reference flows that do not
# # exist and nothing downstream can wire the click.
# _expected_flows = sorted({
#     e.flowName
#     for page in _iv_components.pages
#     for nodes in page.regionComponents.values()
#     for root in nodes
#     for node in _walk_component_nodes(root)
#     for e in node.events
#     if e.flowName
# })
# print("flowNames the components declare:", _expected_flows, "\n")

# # Run tool under unit test harness
# interaction_res = run_tool_unit_test_state_snapshots(
#     tool_name="interactions_specification_generator",
#     input_query=interaction_test_query,
#     initial_state={
#         "layout_specification": dummy_layout_specification,
#         "components_specification": dummy_components_specification,
#         "interactions_specification": None,
#     },
#     fields_to_show=[
#         "input_query",
#         "layout_specification",
#         "components_specification",
#         "interactions_specification",
#     ],
#     expected_update_fields=["interactions_specification"],
#     forbidden_update_fields=["layout_specification", "components_specification"],
#     verbose=False,
#  )

# after_interactions_spec = (interaction_res.get("after_state") or {}).get("interactions_specification") or {}
# print("PASS: interactions_specification_generator produced interactions_specification")

# # One page in, so one page out. A second page here would mean the generator
# # invented one, which nothing downstream could build.
# assert len((after_interactions_spec or {}).get("pages") or []) == 1, \
#     "FAIL: the interactions generator returned more than the one page it was given"

# # The real check: every declared flowName came back as an InteractionFlow.
# _returned_flows = sorted({
#     (f or {}).get("name")
#     for p in ((after_interactions_spec or {}).get("pages") or [])
#     for f in (p.get("flows") or [])
#     if isinstance(f, dict) and f.get("name")
# })
# _unanswered = [f for f in _expected_flows if f not in _returned_flows]
# assert not _unanswered, (
#     f"FAIL: components declare flowNames with no matching InteractionFlow: "
#     f"{_unanswered}\n     returned: {_returned_flows}")
# print("PASS: every declared flowName has a matching InteractionFlow:",
#       _expected_flows)

# # Small summary to confirm key flows exist (scroll-to-section vs modal)
# if isinstance(after_interactions_spec, dict):
#     pages = after_interactions_spec.get("pages") or []
#     print("Pages in interactions_specification:", len(pages) if isinstance(pages, list) else "<unexpected>")
#     if isinstance(pages, list):
#         for p in pages:
#             if not isinstance(p, dict):
#                 continue
#             flows = p.get("flows") or []
#             print("-", p.get("pageName"), "flows:", len(flows) if isinstance(flows, list) else "<unexpected>")

# # What every attempt of this stage cost. One slow stage ruins a run even when
# # the other three are quick, so the total is the number to watch.
# print()
# spec_timing_report("interactions")


# ==========================================================================
# decoration_specification_Generator
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# decoration_specification_generator
#
# How each element looks, in each of its states.
# ═══════════════════════════════════════════════════════════════════════════
import json
from typing import Any, Dict, Optional

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command


decoration_prompt = PromptTemplate.from_template(
    """You are the decoration stage of a deterministic planning pipeline. Decide how the page looks and return one DecorationSpecification.
{house_rules}
RUN BRIEF
{run_brief}
DESIGN TOKENS (authoritative visual theme)
{design_tokens}
INPUTS
- input_query: {input_query}
- layout_specification (JSON): {layout_specification}
- components_specification (JSON): {components_specification}
- interactions_specification (JSON): {interactions_specification}
- validation_feedback (may be empty): {validation_feedback}

CONSTRAINTS
- Put the DESIGN TOKENS into globalTokens verbatim. Build every component colour from those tokens; never leave globalTokens empty or invent a hex colour outside the provided set.
- Cover every layout page, grouped by page, with one decoration per styled component. If a page has nothing to style, include it with an empty decoration list.
- Decorate ONLY components whose className is a real non-empty string. Components with missing or blank className get no decoration.
- Every decoration className must be a concrete non-empty string copied verbatim from its component. Never invent or tidy a className or componentId.
- Style a state variant only when the interaction specification shows something can put the component into that state. Every state variant must name a state that component declares.

VERIFICATION
Python checks the answer and returns the failure reason:
- it parses as a DecorationSpecification
- it covers every page the layout declares
- every componentId names a component that exists
- every className matches that component's own className exactly
- every state variant names a state that component declares

ITERATION POLICY
- Empty feedback means this is the first attempt.
- Filled feedback contains YOUR OWN previous answer and its errors. Edit that answer; do not rebuild from the request or change anything not criticised.
- Fix every reported issue in one go.
- Return the entire corrected object, never a patch or patch description.
- Keep className tokens exactly as they were.

OUTPUT
Return only the DecorationSpecification object. No markdown, no explanation.
"""
)

decoration_specification_generator_chain = (
    decoration_prompt | _spec_model.with_structured_output(DecorationSpecification, method="function_calling")
)

decoration_specification_generator_tool = decoration_specification_generator_chain.as_tool(
    name="decoration_specification_generator_llm",
    description="Generate DecorationSpecification from input_query + design_schema + layout_specification + components_specification + interactions_specification.",
    arg_types={
        "input_query": str,
        "layout_specification": str,
        "components_specification": str,
        "interactions_specification": str,
        "house_rules": str,
        "run_brief": str,
        "design_tokens": str,
        "validation_feedback": str,
    },
)


def generate_decoration_specification(s: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str]:
    """Decoration stage as a plain function: (decoration_specification | None, message)."""
    input_query = str(s.get("input_query", "") or "")
    design_schema_payload: Any = s.get("design_schema") or {}
    components_specification: Any = s.get("components_specification") or {}
    layout_specification: Any = s.get("layout_specification") or {}
    interactions_specification: Any = s.get("interactions_specification") or {"pages": []}
    _page_type = _run_page_type(layout_specification)

    def _validate(candidate: Any) -> Optional[str]:
        try:
            obj = _coerce_decoration_spec(candidate)
        except Exception as e:
            return f"[decoration] DecorationSpecification validation warning: {e}"
        try:
            layout_obj = _coerce_layout_spec(layout_specification)
        except Exception as e:
            return f"[decoration] Cannot validate against layout_specification: {e}"
        layout_page_names = {p.pageName for p in layout_obj.pages}
        decoration_page_names = {p.pageName for p in obj.pages}
        missing_pages = layout_page_names - decoration_page_names
        if missing_pages:
            return "[decoration] DecorationSpecification missing pages for layout: " + ", ".join(sorted(missing_pages))
        return _bundle_validate_or_warn(
            stage="decoration",
            layout=layout_specification,
            component=components_specification,
            interaction=interactions_specification,
            decoration=obj,
        )

    base_payload = {
        "input_query": input_query,
        "components_specification": json.dumps(components_specification, ensure_ascii=False),
        "layout_specification": json.dumps(layout_specification, ensure_ascii=False),
        "interactions_specification": json.dumps(interactions_specification, ensure_ascii=False),
        "house_rules": _SPEC_HOUSE_RULES,
        "run_brief": _build_run_brief(design_schema_payload, _page_type),
        "design_tokens": _theme_tokens_block(_build_token_bundle(design_schema_payload)),
    }
    candidate, error = _invoke_structured_with_retries(
        stage="decoration",
        structured_tool=decoration_specification_generator_tool,
        base_payload=base_payload,
        validate_result=_validate,
        max_attempts=3,
    )

    if error or candidate is None:
        return None, f"FAILED to generate decoration_specification.\n{error}"

    result_obj = _coerce_decoration_spec(candidate)
    result = result_obj.model_dump()
    return result, "Stored decoration_specification."


@tool
def decoration_specification_generator(runtime: ToolRuntime[ContextState]) -> Command:
    """Generate and store decoration_specification, then full bundle-validate."""
    spec, message = generate_decoration_specification(runtime.state)
    return _spec_tool_command("decoration_specification", spec, message, runtime.tool_call_id)


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
