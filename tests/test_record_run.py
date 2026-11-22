"""record_run.summarise: the numbers it writes come from leaf model calls only."""
import datetime as dt
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import record_run as rr  # noqa: E402

T0 = dt.datetime(2026, 11, 10, 12, 0, 0, tzinfo=dt.timezone.utc)


def _run(id_, name, rtype, start, end, parent=None, usage=None, error=None, cost=None):
    return types.SimpleNamespace(
        id=id_, name=name, run_type=rtype, parent_run_id=parent,
        start_time=T0 + dt.timedelta(seconds=start),
        end_time=T0 + dt.timedelta(seconds=end), error=error, status="success",
        usage_metadata=usage, outputs={}, inputs={"messages": ["x" * 10]},
        extra={"metadata": {"ls_model_name": "gpt-5.4"}}, total_cost=cost,
        prompt_tokens=None, completion_tokens=None)


def _trace():
    use = {"input_tokens": 1000, "output_tokens": 200,
           "input_token_details": {"cache_read": 400},
           "output_token_details": {"reasoning": 50}}
    root = _run("r", "Primary Orchestrator - PO-08", "chain", 0, 100)
    step = _run("s", "call_html_agent", "tool", 10, 40, parent="r")
    agent = _run("a", "HTML Agent", "chain", 11, 39, parent="s")
    # the parent chain carries the child's usage too; it must not be counted twice
    agent.usage_metadata = use
    llm = _run("l", "ChatOpenAI", "llm", 12, 30, parent="a", usage=use, cost=0.004)
    lint = _run("t", "run_html_validate", "tool", 31, 32, parent="a", error="boom")
    return root, [root, step, agent, llm, lint]


def test_counts_only_leaf_model_calls():
    root, runs = _trace()
    summary, calls, steps, tools = rr.summarise(runs, root)
    assert summary["model_calls"] == 1
    assert summary["tokens"] == {"input": 600, "cache_read": 400, "output": 200,
                                 "reasoning": 50}
    expect = 600 / 1e6 * 2.50 + 400 / 1e6 * 0.25 + 200 / 1e6 * 15.00
    assert abs(summary["cost_usd"] - round(expect, 4)) < 1e-9
    assert calls[0]["agent"] == "HTML Agent" and calls[0]["model"] == "gpt-5.4"
    assert calls[0]["start_offset_s"] == 12.0 and calls[0]["duration_s"] == 18.0
    assert summary["langsmith_cost_usd"] == 0.004


def test_steps_tools_and_wall_clock():
    root, runs = _trace()
    summary, calls, steps, tools = rr.summarise(runs, root)
    assert summary["wall_s"] == 100.0
    assert steps == [{"step": "call_html_agent", "start_offset_s": 10.0,
                      "duration_s": 30.0, "error": False}]
    assert {"tool": "run_html_validate", "calls": 1, "errors": 1} in tools
    assert summary["tool_errors"] == {"run_html_validate": 1}


def test_a_run_without_usage_is_not_priced_as_free():
    root, runs = _trace()
    runs[3].usage_metadata = None
    summary, calls, _, _ = rr.summarise(runs, root)
    assert summary["model_calls"] == 0 and calls == []
