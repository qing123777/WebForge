"""Ticket 14: the UI's JS and CSS live in ui_assets/ as plain files.

    python -m pytest tests/test_ui_assets.py        (or python tests/test_ui_assets.py)

Offline, no model calls.

  UA-1  each asset exists, reads as UTF-8, and is bare CSS or JS (the tag
        is added by stream_lit.py).
  UA-2  preview_frame_js fills both of its fields, each exactly once.
  UA-3  stream_lit.py holds no long string block again (the three that moved
        were 947, 1,746 and 1,032 lines; the longest left is under 60), no
        f-string in it doubles a brace (the hazard of JS/CSS in an
        f-string), and every asset it reads exists.
  UA-4  importing ui_assets loads no agent code.
  UA-5  tools/ui_render_probe.py pairs calls by their text: same bytes when a
        block moves to ui_assets, a changed or removed call is counted,
        and a removed call does not shift the ones after it.
"""
import ast
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI = ROOT / "stream_lit.py"
ASSETS = ["app.css", "chrome.js", "preview_frame.css", "preview_frame.js"]
LONGEST_BLOCK = 60


# UA-1 ------------------------------------------------------------------------

@pytest.mark.parametrize("name", ASSETS)
def test_asset_is_plain_css_or_js(name):
    import ui_assets
    text = ui_assets.read(name)
    assert text.strip(), name
    ends = (text.lstrip()[:8], text.rstrip()[-9:])
    assert not ends[0].startswith(("<style>", "<script>")), \
        f"{name} opens with its own tag; stream_lit.py adds it"
    assert not ends[1].endswith(("</style>", "</script>")), \
        f"{name} closes with its own tag; stream_lit.py adds it"


# UA-2 ------------------------------------------------------------------------

def test_preview_frame_js_fills_both_fields():
    import ui_assets
    raw = ui_assets.read("preview_frame.js")
    assert raw.count(ui_assets.SELECT_ENABLED_FIELD) == 1
    assert raw.count(ui_assets.MODIFY_MARKER_FIELD) == 1
    js = ui_assets.preview_frame_js("true", "MARKER_EXPR")
    assert "__WF_" not in js
    assert "var selectEnabled = true;" in js
    assert "marker: MARKER_EXPR" in js


# UA-3 ------------------------------------------------------------------------

def test_stream_lit_keeps_no_long_string_block():
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    long = sorted(((n.end_lineno - n.lineno, n.lineno) for n in ast.walk(tree)
                   if isinstance(n, (ast.Constant, ast.JoinedStr))
                   and n.end_lineno - n.lineno >= LONGEST_BLOCK), reverse=True)
    assert not long, f"(lines, at line) of string blocks in stream_lit.py: {long}"


def test_no_f_string_in_stream_lit_doubles_a_brace():
    """The brace hazard: JS or CSS inside an f-string must write {{ and }},
    while the block next to it must not. Since ticket 14 no f-string in
    stream_lit.py holds a literal brace at all."""
    src = UI.read_text(encoding="utf-8")
    doubled = sorted(n.lineno for n in ast.walk(ast.parse(src))
                     if isinstance(n, ast.JoinedStr)
                     and re.search(r"\{\{|\}\}", ast.get_source_segment(src, n) or ""))
    assert not doubled, f"f-strings with doubled braces at lines {doubled}"


def test_every_asset_stream_lit_reads_exists():
    names = set(re.findall(r'ui_assets\.read\("([^"]+)"\)', UI.read_text(encoding="utf-8")))
    names.add("preview_frame.js")       # read through preview_frame_js
    assert names == set(ASSETS)
    for name in names:
        assert (ROOT / "ui_assets" / name).is_file(), name


# UA-4 ------------------------------------------------------------------------

def test_importing_ui_assets_loads_no_agent_code():
    probe = ("import sys, ui_assets; "
             "print(sorted(m for m in sys.modules if m.startswith('langchain')"
             " or (m.startswith('webforge.') and m != 'webforge.config')))")
    out = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True,
                         text=True, timeout=120)
    assert out.stdout.strip() == "[]", out.stdout + out.stderr


# UA-5 ------------------------------------------------------------------------

_PAGE = '''
components.html("<script>a()</script>", height=0)
def panel(sid):
    st.markdown(f"<div id='{sid}'>x</div>", unsafe_allow_html=True)
st.markdown("\\n    <style>" + ui_assets.read("app.css") + "</style>\\n    ")
'''


def test_render_probe_pairs_calls_by_their_text():
    sys.path.insert(0, str(ROOT / "tools"))
    import ui_render_probe as probe
    import ui_assets
    lines, bad = probe.compare(_PAGE, _PAGE)
    assert bad == 0 and sum(x.startswith("IDENTICAL") for x in lines) == 3
    css = ui_assets.read("app.css")
    inlined = _PAGE.replace('ui_assets.read("app.css")', repr(css))
    assert probe.compare(_PAGE, inlined)[1] == 0          # moved, same bytes
    assert probe.compare(_PAGE, _PAGE.replace("a()", "b()"))[1] == 1
    removed = _PAGE.replace('components.html("<script>a()</script>", height=0)\n', "")
    lines, bad = probe.compare(_PAGE, removed)
    assert bad == 1 and any(x.startswith("REMOVED") for x in lines)
    assert any(x.startswith("IDENTICAL  panel#1") for x in lines)   # not shifted


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
