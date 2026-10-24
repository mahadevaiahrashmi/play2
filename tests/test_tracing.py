"""tracing: spans (finish order, parents, exceptions), episode accounting, loop alerts."""

import json
import threading

import pytest

from warehouse_routing.tracing import LoopDetector, Tracer


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_spans_recorded_in_finish_order_with_parent_names_and_durations() -> None:
    clock = FakeClock()
    tracer = Tracer(clock=clock)
    with tracer.span("outer"):
        clock.t = 1.0
        with tracer.span("inner", step=3):
            clock.t = 4.0
        clock.t = 6.0
    spans = tracer.spans
    assert [s.name for s in spans] == ["inner", "outer"]  # child finishes first
    inner, outer = spans
    assert inner.parent == "outer" and outer.parent is None
    assert inner.duration == 3.0 and outer.duration == 6.0
    assert inner.attrs == {"step": 3}
    assert inner.status == "ok"


def test_span_recorded_on_exception_and_exception_propagates() -> None:
    tracer = Tracer(clock=FakeClock())
    with pytest.raises(ValueError), tracer.span("outer"), tracer.span("boom"):
        raise ValueError("bad")
    assert [s.name for s in tracer.spans] == ["boom", "outer"]
    assert all(s.status == "error" for s in tracer.spans)
    assert tracer.spans[0].error == "ValueError: bad"


def test_parent_stack_unwinds_after_exception() -> None:
    tracer = Tracer(clock=FakeClock())
    with pytest.raises(RuntimeError), tracer.span("a"):
        raise RuntimeError
    with tracer.span("b"):
        pass
    assert tracer.spans[-1].parent is None


def test_episode_accounting_latency_cost_errors() -> None:
    clock = FakeClock()
    tracer = Tracer(clock=clock)
    with tracer.episode("ep1") as ep:
        tracer.add_cost(0.25)
        tracer.add_cost(0.5)
        tracer.add_error("timeout")
        clock.t = 7.5
    assert ep.latency == 7.5
    assert ep.cost == 0.75
    assert ep.errors == ["timeout"]
    # spans created inside an episode see the episode span as parent
    with tracer.episode("ep2"), tracer.span("llm.call"):
        pass
    call = next(s for s in tracer.spans if s.name == "llm.call")
    assert call.parent == "episode" and call.episode_id == "ep2"


def test_exception_in_episode_is_counted_as_error() -> None:
    tracer = Tracer(clock=FakeClock())
    with pytest.raises(KeyError), tracer.episode("e") as ep:
        raise KeyError("x")
    assert ep.errors and "KeyError" in ep.errors[0]
    assert ep.status == "error"


def test_loop_detector_alerts_at_every_multiple_of_threshold() -> None:
    det = LoopDetector("state", threshold=3)
    fired = [det.observe("A") is not None for _ in range(9)]
    assert fired == [False, False, True, False, False, True, False, False, True]
    alert = det.observe("A")
    assert alert is None
    assert det.observe("B") is None  # other keys counted independently


def test_loop_detector_alert_contents() -> None:
    det = LoopDetector("prompt", threshold=2)
    det.observe("k")
    alert = det.observe("k")
    assert alert is not None
    assert (alert.kind, alert.key, alert.count) == ("prompt", "k", 2)


def test_threshold_must_be_positive() -> None:
    with pytest.raises(ValueError):
        LoopDetector("state", threshold=0)


def test_oscillating_agent_triggers_state_alerts_in_episode() -> None:
    seen = []
    tracer = Tracer(clock=FakeClock(), loop_threshold=3, on_alert=seen.append)
    with tracer.episode("osc") as ep:
        for i in range(12):  # E/W oscillation between cell (0,1) and (0,2)
            tracer.observe_state(("pos", 1 + i % 2))
    # each of the 2 states visited 6 times -> alerts at counts 3 and 6 for each
    assert ep.alerts == 4
    assert len(seen) == 4
    assert {a.key for a in seen} == {("pos", 1), ("pos", 2)}
    assert sorted(a.count for a in seen) == [3, 3, 6, 6]
    rep = tracer.report()
    assert rep["alerts_total"] == 4
    assert rep["alerts"][0]["episode_id"] == "osc"


def test_observe_outside_episode_is_an_error() -> None:
    with pytest.raises(RuntimeError):
        Tracer(clock=FakeClock()).observe_state("x")


def test_report_is_json_serialisable_and_summarises() -> None:
    clock = FakeClock()
    tracer = Tracer(clock=clock)
    with tracer.episode("e1"):
        with tracer.span("policy.choose"):
            clock.t += 2
        tracer.add_cost(0.1)
    rep = tracer.report(include_spans=True)
    text = json.dumps(rep)
    assert json.loads(text)["episodes"][0]["episode_id"] == "e1"
    assert rep["span_summary"]["policy.choose"] == {"count": 1, "total_s": 2.0, "errors": 0}
    assert len(rep["spans"]) == 2
    assert "spans" not in tracer.report()


def test_span_cap_counts_dropped_spans() -> None:
    tracer = Tracer(clock=FakeClock(), max_spans=2)
    for _ in range(5):
        with tracer.span("s"):
            pass
    rep = tracer.report()
    assert len(tracer.spans) == 2 and rep["dropped_spans"] == 3
    assert rep["span_summary"]["s"]["count"] == 5  # summary still counts every span


def test_threads_have_independent_span_stacks_and_episodes() -> None:
    tracer = Tracer(clock=FakeClock())
    barrier = threading.Barrier(4)

    def work(i: int) -> None:
        with tracer.episode(f"e{i}"):
            barrier.wait()
            with tracer.span("step"):
                tracer.add_cost(1.0)

    ts = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    steps = [s for s in tracer.spans if s.name == "step"]
    assert {s.episode_id for s in steps} == {"e0", "e1", "e2", "e3"}
    assert all(s.parent == "episode" for s in steps)
    assert [e["cost"] for e in tracer.report()["episodes"]] == [1.0] * 4
