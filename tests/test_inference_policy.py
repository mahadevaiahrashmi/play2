# agent-notes: { ctx: "OpenAIPolicy history injection (issue #26)", deps: [inference.py], state: active, last: "sato@2026-04-15" }
"""Verify OpenAIPolicy injects rolling action/reward history into the prompt."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inference import HISTORY_WINDOW, OpenAIPolicy  # noqa: E402
from warehouse_routing.models import Cell, Observation  # noqa: E402


class FakeClient:
    def __init__(self, reply: str = "E") -> None:
        self.reply = reply
        self.calls: list[dict] = []

        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=outer.reply))]
                )

        self.chat = SimpleNamespace(completions=_Completions())


def _obs(steps: int) -> Observation:
    return Observation(
        grid_rows=4,
        grid_cols=4,
        warehouse=Cell(row=0, col=0),
        sku_locations=[Cell(row=2, col=2)],
        obstacles=[],
        robot_pos=Cell(row=0, col=0),
        visited=[False],
        steps_taken=steps,
        step_budget=20,
        tier="easy",
        attempt=1,
        variation_seed=0,
    )


def _user_msg(call: dict) -> str:
    return next(m["content"] for m in call["messages"] if m["role"] == "user")


def test_history_starts_empty_then_grows() -> None:
    client = FakeClient(reply="E")
    policy = OpenAIPolicy(client=client, model="m")

    policy.choose(_obs(0))
    assert "recent_moves: none" in _user_msg(client.calls[0])

    policy.record("E", -0.01)
    policy.choose(_obs(1))
    assert "E->r=-0.01" in _user_msg(client.calls[1])

    policy.record("N", 0.10)
    policy.choose(_obs(2))
    msg = _user_msg(client.calls[2])
    assert "E->r=-0.01" in msg and "N->r=0.10" in msg


def test_history_window_caps_at_eight() -> None:
    client = FakeClient(reply="N")
    policy = OpenAIPolicy(client=client, model="m")
    for i in range(HISTORY_WINDOW + 4):
        policy.record("E", -0.01 * (i + 1))
    policy.choose(_obs(20))
    msg = _user_msg(client.calls[0])
    assert msg.count("E->r=") == HISTORY_WINDOW


def test_new_episode_resets_history() -> None:
    client = FakeClient(reply="N")
    policy = OpenAIPolicy(client=client, model="m")

    policy.choose(_obs(5))
    policy.record("E", -0.01)
    policy.choose(_obs(6))
    assert "E->r=" in _user_msg(client.calls[1])

    # New episode: steps_taken resets to 0
    policy.choose(_obs(0))
    assert "recent_moves: none" in _user_msg(client.calls[2])
