"""Spec Base Styles: Python writes the CSS the decoration specification pins.

    python tests/test_spec_base.py        (or pytest, once it is installed)

Offline, no model calls. Uses the real stylelint through _lint_css_source.
"""
import contextlib
import io
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "baseline"))
for _k in ("OPENAI_API_KEY", "TAVILY_API_KEY", "LANGSMITH_API_KEY"):
    os.environ[_k] = "sk-test-dead-key"
os.environ["LANGSMITH_TRACING"] = "false"

# The package's flat namespace (ticket 15: it was the fyp.py shim). A write
# goes through webforge.set_everywhere, which reaches every module holding it.
with contextlib.redirect_stdout(io.StringIO()):
    import webforge  # noqa: E402
    import webforge.primary_orchestrator as po  # noqa: E402
from capture import FakeRuntime, command_to_json  # noqa: E402

DECO = {
    "globalTokens": {"colors": {"--color-accent": "#b5642a", "--color-bg": "#faf5ee"},
                     "spacing": {"--page-max-width": "1200px"}},
    "pages": [{"pageName": "plp", "componentDecorations": [
        {"componentId": "price", "className": "featured-bean-price",
         "baseStyles": {"fontSize": "18px", "font-weight": 700, "color": "var(--color-accent)"},
         "stateVariants": [{"stateName": "hover", "styles": {"color": "#8f4c1e"}}],
         "responsiveStyles": [{"breakpoint": "mobile", "maxWidth": "640px",
                               "styles": {"font-size": "16px"}}]},
        {"componentId": "grid", "className": "product-grid",
         "baseStyles": {"display": "grid", "gap": "24px"}},
        {"componentId": "cart", "className": "mini-cart",
         "baseStyles": {"display": "grid", "visibility": "visible",
                        "background-color": "#ffffff"}},
        {"componentId": "evil", "className": "bad class",
         "baseStyles": {"color": "red"}},
        {"componentId": "inject", "className": "safe",
         "baseStyles": {"color": "red; } body { display: none", "margin": None}},
    ]}],
}
COMPONENTS = {"pages": [{"components": [
    {"id": "cart", "className": "mini-cart",
     "states": [{"name": "default"}, {"name": "open"}]},
    {"id": "grid", "className": "product-grid", "states": [{"name": "default"}]},
]}]}


def block():
    return po._spec_base_css(DECO, COMPONENTS)


def test_tokens_rules_states_media():
    b = block()
    assert ":root { --color-accent: #b5642a; --color-bg: #faf5ee; --page-max-width: 1200px; }" in b
    assert ".featured-bean-price { font-size: 18px; font-weight: 700; color: var(--color-accent); }" in b
    assert ".featured-bean-price:hover { color: #8f4c1e; }" in b
    assert "@media (max-width: 640px) { .featured-bean-price { font-size: 16px; } }" in b


def test_state_props_only_dropped_on_toggling_components():
    b = block()
    assert ".product-grid { display: grid; gap: 24px; }" in b, "a plain grid keeps display pinned"
    assert ".mini-cart { background-color: #ffffff; }" in b, "a drawer keeps its colour"
    assert "visibility" not in b and ".mini-cart { display" not in b, \
        "a drawer's display/visibility must stay the model's (PO-10 always-open drawer)"


def test_unsafe_input_is_skipped():
    b = block()
    assert "bad class" not in b and ".safe" not in b and "body {" not in b
    assert "None" not in b


def test_block_goes_last_and_is_idempotent():
    model_css = ".featured-bean-price { color: #000; padding: 4px; }\n"
    once = po._with_spec_base(model_css, DECO, COMPONENTS)
    twice = po._with_spec_base(once, DECO, COMPONENTS)
    assert once == twice
    assert once.index("padding: 4px") < once.index(po._SPEC_BASE_START), "block must come last"
    assert once.count(po._SPEC_BASE_START) == 1


def test_lint_keeps_the_models_rule_and_the_block_clean():
    css = (":root { --x: 1px; }\n"
           ".featured-bean-price { padding: 4px; }\n"
           ".featured-bean-price { margin: 0; }\n")
    full = po._with_spec_base(css, DECO, COMPONENTS)
    res = command_to_json(po._lint_css_source(full, FakeRuntime({"session_id": "t"})))
    out = res.get("css_code", full)
    body = out[:out.index(po._SPEC_BASE_START)]
    assert body.count(".featured-bean-price") == 1, "the model's own duplicates are collapsed"
    assert "padding: 4px" in body and "margin: 0" in body, "the model's declarations stay outside the block"
    assert out.count(po._SPEC_BASE_START) == 1
    assert res.get("lint_passed") is True, res["messages"]


def test_store_css_code_appends_the_block_on_generate():
    sid = "741c7b34-f21e-4f7c-8cc8-9d2635e24bde"
    fixtures = ROOT / "baseline" / "fixtures"
    old_root = po._PREVIEW_ROOT
    webforge.set_everywhere("_PREVIEW_ROOT", fixtures)
    try:
        css = (fixtures / f"preview_{sid}.css").read_text(encoding="utf-8")
        deco = {"globalTokens": {}, "pages": [{"pageName": "p", "componentDecorations": [
            {"componentId": "price", "className": "featured-bean-price",
             "baseStyles": {"font-size": "18px"}}]}]}
        state = {"intent": "generate", "session_id": sid,
                 "decoration_specification": deco, "components_specification": {}}
        res = command_to_json(po.store_css_code.func(css, FakeRuntime(state)))
    finally:
        webforge.set_everywhere("_PREVIEW_ROOT", old_root)
    out = res.get("css_code")
    assert out, f"store refused: {res['messages']}"
    assert out.rstrip().endswith(po._SPEC_BASE_END)
    assert ".featured-bean-price { font-size: 18px; }" in out


def test_truncated_model_css_is_closed_before_the_block():
    cut = ".a { color: red; }\n.b,\n.c"
    assert po._close_truncated_css(cut) == ".a { color: red; }"
    assert po._close_truncated_css(".a { color: red; }\n.b { margin: 0;").endswith("margin: 0;\n}")
    assert po._close_truncated_css(".a { color: red; }\n/* note */") == ".a { color: red; }\n/* note */"


def test_empty_spec_changes_nothing():
    assert po._spec_base_css({}) == ""
    assert po._with_spec_base(".a { color: red; }", {}).strip() == ".a { color: red; }"


def test_prompt_shows_the_block():
    p = po._spec_base_prompt_block({"decoration_specification": DECO,
                                     "components_specification": COMPONENTS})
    assert "Spec styles written for you" in p and po._SPEC_BASE_START in p
    assert po._spec_base_prompt_block({}) == ""


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"FAIL  {name}: {e}")
    print(f"\n{'all passed' if not failed else f'{failed} failed'}")
    sys.exit(1 if failed else 0)
