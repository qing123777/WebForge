"""Dump the CSS and JS modify-loop tools' replies on the baseline fixture pages.

    python tools/dev_loop_probe.py <out.json>           extract only (fast)
    python tools/dev_loop_probe.py <out.json> --lint    also apply_and_lint, real linters

Run it before a change to the loop core and again after, then compare the
two files byte for byte (cmp): the change is behaviour-preserving when they
match. Save the "before" file first, or run it in a separate `git worktree`
of the old commit; do not stash in a working tree other sessions share.
Ticket 09: 1,344 cases, identical. The baseline does not capture these replies; they are what the
model reads back after each extract or apply call.

Offline: no model call (dead keys); --lint runs the real ESLint and
Stylelint through npx.
"""
import contextlib, io, json, os, pathlib, re, sys
from types import SimpleNamespace
for k in ("OPENAI_API_KEY", "TAVILY_API_KEY", "LANGSMITH_API_KEY", "GOOGLE_API_KEY"):
    os.environ[k] = "sk-dead"
os.environ["LANGSMITH_TRACING"] = "false"
ROOT = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
with contextlib.redirect_stdout(io.StringIO()):
    import webforge.primary_orchestrator as W
FIX = ROOT / "baseline" / "fixtures"
LINT = "--lint" in sys.argv

def rt(**st):
    return SimpleNamespace(state=st, tool_call_id="t1")

def dump(cmd):
    u = dict(cmd.update)
    msgs = [m.content for m in u.pop("messages", [])]
    return {"msgs": msgs, "upd": {k: v for k, v in sorted(u.items())}}

out = {}
for html in sorted(FIX.glob("preview_*.html")):
    sid = html.stem[len("preview_"):]
    names = sorted(set(re.findall(r'class="([A-Za-z0-9_-]+)', html.read_text(encoding="utf-8"))))[:6]
    names = [f".{n}" for n in names] + ["no-such-component", names[0] if names else "x"]
    for ext, tool_ext, apply_t in (("css", W.extract_css_component, W.apply_and_lint_css),
                                   ("js", W.extract_js_component, W.apply_and_lint_js)):
        f = FIX / f"preview_{sid}.{ext}"
        if not f.exists():
            continue
        code = f.read_text(encoding="utf-8")
        st = {f"{ext}_code": code, "session_id": sid, "intent": "modify",
              "lint_attempts": 1, "patch_attempts": 1}
        for n in names:
            out[f"{sid}.{ext}.x1.{n}"] = dump(tool_ext.func(rt(**st), component=n))
        out[f"{sid}.{ext}.xN"] = dump(tool_ext.func(rt(**st), components=names))
        out[f"{sid}.{ext}.xT"] = dump(tool_ext.func(rt(**st, target_components=names[:3])))
        out[f"{sid}.{ext}.xE"] = dump(tool_ext.func(rt(**{**st, f"{ext}_code": ""}), component=names[0]))
        if LINT:
            # apply: a bad diff, an empty call, a no-block name, and a good one-line diff
            n0 = names[0]
            out[f"{sid}.{ext}.a_empty"] = dump(apply_t.func(runtime=rt(**st), diff_output=""))
            out[f"{sid}.{ext}.a_bad"] = dump(apply_t.func(runtime=rt(**st), diff_output="@@ -1,1 +1,1 @@\n-zzz\n+yyy\n", component=n0))
            out[f"{sid}.{ext}.a_noblk"] = dump(apply_t.func(runtime=rt(**st), diff_output="@@ -1 +1 @@\n-a\n+b\n", component="no-such-component"))
            blk = tool_ext.func(rt(**st), component=n0).update["messages"][0].content
            first = blk.splitlines()[0] if blk else ""
            good = f"@@ -1,1 +1,1 @@\n-{first}\n+{first} \n"
            out[f"{sid}.{ext}.a_good"] = dump(apply_t.func(runtime=rt(**st), diff_output=good, component=n0))
            st0 = {**st, "lint_attempts": 0, "patch_attempts": 0}
            out[f"{sid}.{ext}.a_good0"] = dump(apply_t.func(runtime=rt(**st0), diff_output=good, component=n0))
            out[f"{sid}.{ext}.a_bad0"] = dump(apply_t.func(runtime=rt(**st0), diff_output="@@ -1,1 +1,1 @@\n-zzz\n+yyy\n", component=n0))
            out[f"{sid}.{ext}.a_batch0"] = dump(apply_t.func(runtime=rt(**st0), diffs=[
                {"component": n0, "diff_output": good},
                {"component": names[1] if len(names) > 1 else n0, "diff_output": "@@ -1 +1 @@\n-q\n+r\n"}]))
            out[f"{sid}.{ext}.a_batch"] = dump(apply_t.func(runtime=rt(**st), diffs=[
                {"component": n0, "diff_output": good},
                {"component": "no-such-component", "diff_output": good},
                {"component": names[1] if len(names) > 1 else n0, "diff_output": "@@ -1 +1 @@\n-q\n+r\n"}]))
json.dump(out, open(sys.argv[1], "w"), indent=0, sort_keys=True, default=str)
print(len(out), "cases")
