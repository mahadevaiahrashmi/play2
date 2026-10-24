"""Shared, dependency-free types for the LLM-call stack.

Contract: an *LLM function* is any callable ``(messages) -> LLMResponse`` where
``messages`` is a chat-style list of ``{"role": ..., "content": ...}`` dicts.
Every wrapper in this package (``resilient_llm``, ``budget``,
``structured_action``) takes and returns this shape, so they compose freely.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Message = dict[str, str]


@dataclass(frozen=True)
class LLMResponse:
    """Raw model reply plus token usage (as reported by the provider/mock)."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


LLMFn = Callable[[list[Message]], LLMResponse]


def estimate_tokens(text: str) -> int:
    """Crude, deterministic token estimate (~4 chars/token, min 1).

    Used for pre-call budget reservations and by the mock LLM. It is an
    estimate, not a tokenizer.
    """
    return max(1, (len(text) + 3) // 4)


def estimate_message_tokens(messages: list[Message]) -> int:
    return sum(estimate_tokens(m.get("content", "")) for m in messages)
