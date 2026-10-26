"""The ONE gateway for model calls (CLAUDE.md): gpt-6-luna only, through Portkey, server side only.

Feature code never builds a model or client itself; it calls `run_agent()`. This module enforces: model
allowlist, input-size cap, output cap, step/token caps, daily spend cap, per-request cost estimate, and
the AI_ENABLED kill switch. When a limit is hit it raises `AIUnavailable` with a user-facing message. It
never falls back to another model or to a guess.

Limits live in LIMITS below (config), not in feature code. Usage is recorded per call with the feature
name only (no calendar data, no prompts, no answers).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI
from pydantic_ai import Agent, UsageLimitExceeded, UsageLimits
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

import store

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
_here = Path(__file__).resolve()
for folder in _here.parents[2:]:  # project folder first, then every parent (the class-wide .env holds the key)
    if (folder / ".env").exists():
        load_dotenv(folder / ".env", override=False)

log = logging.getLogger("llm")

MODEL_NAME = "gpt-6-luna"
ALLOWED_MODELS = frozenset({"gpt-6-luna"})
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")


@dataclass(frozen=True)
class Limits:
    max_input_chars: int = 16_000  # user text sent per call (the planner prompt carries the evidence list)
    max_output_tokens: int = 4_000  # per model response
    request_limit: int = 12  # model round trips (steps) per run
    input_tokens_limit: int = 250_000  # per run
    output_tokens_limit: int = 20_000  # per run
    daily_cap_usd: float = 1.00
    per_run_cap_usd: float = 0.25  # estimated; a warning is logged if exceeded
    reasoning_effort: str = "low"  # raise per feature if quality needs it


LIMITS = Limits()

# Per-feature speed settings. A stalled connection used to wait up to 10 minutes; now each call gives up after its timeout
# and retries once. "none" turns reasoning off for simple tasks (the model also accepts low, medium, high, xhigh, max).
DEFAULT_TIMEOUT = 90.0
FEATURE_SETTINGS: dict[str, dict] = {
    "interview": {"effort": "none", "timeout": 30.0},
    "planner": {"timeout": 150.0},
    "planner_repair": {"timeout": 120.0},
    "class_finder": {"timeout": 90.0},
    "restaurant_finder": {"timeout": 90.0},
    "movie_finder": {"timeout": 90.0},
}

# USD per 1M tokens, plus per web-search call. Starting numbers from third-party price pages:
# VERIFY against OpenAI's pricing page. Estimates only.
PRICE_IN, PRICE_CACHED_IN, PRICE_OUT = 0.10, 0.01, 0.50
PRICE_WEB_SEARCH_CALL = 0.01


class AIUnavailable(Exception):
    """AI features are paused or a limit was hit. The message is safe to show to the user."""


def ai_enabled() -> bool:
    return os.getenv("AI_ENABLED", "true").strip().lower() not in ("false", "0", "no", "off")


def assert_model(name: str) -> None:
    if name not in ALLOWED_MODELS:
        raise ValueError(f"Model {name!r} is not allowed. Only {sorted(ALLOWED_MODELS)} may be used.")


def estimate_cost(usage: Any) -> float:
    cached = getattr(usage, "cache_read_tokens", 0) or 0
    fresh_in = max((usage.input_tokens or 0) - cached, 0)
    searches = getattr(usage, "web_searches", 0) or 0
    return (fresh_in * PRICE_IN + cached * PRICE_CACHED_IN + (usage.output_tokens or 0) * PRICE_OUT) / 1_000_000 + searches * PRICE_WEB_SEARCH_CALL


@lru_cache(maxsize=1)
def _model() -> OpenAIResponsesModel:
    assert_model(MODEL_NAME)
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise AIUnavailable("The AI service isn't configured (missing PORTKEY_API_KEY).")
    client = AsyncOpenAI(api_key=key, base_url=PORTKEY_BASE_URL, default_headers={"x-portkey-provider": "openai"}, max_retries=1)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


async def run_agent(agent: Agent, prompt: "str | Sequence[Any]", *, feature: str, deps: Any = None):
    """Run `agent` on `prompt` under all the limits. Returns the agent result."""
    if not ai_enabled():
        raise AIUnavailable("AI features are turned off right now (AI_ENABLED=false).")
    parts = [prompt] if isinstance(prompt, str) else list(prompt)
    if sum(len(p) for p in parts if isinstance(p, str)) > LIMITS.max_input_chars:
        raise AIUnavailable("That request is too long. Shorten it and try again.")
    if store.spend_today() >= LIMITS.daily_cap_usd:
        raise AIUnavailable("AI features are paused: today's spending limit has been reached. Try again tomorrow.")

    fs = FEATURE_SETTINGS.get(feature, {})
    settings: Any = {
        "max_tokens": LIMITS.max_output_tokens,
        "openai_reasoning_effort": fs.get("effort", LIMITS.reasoning_effort),
        "timeout": fs.get("timeout", DEFAULT_TIMEOUT),
        "extra_headers": {"x-portkey-metadata": json.dumps({"feature": feature})},  # feature only, never user data
    }
    limits = UsageLimits(
        request_limit=LIMITS.request_limit,
        input_tokens_limit=LIMITS.input_tokens_limit,
        output_tokens_limit=LIMITS.output_tokens_limit,
    )
    started = time.monotonic()
    try:
        result = await agent.run(prompt, deps=deps, model=_model(), model_settings=settings, usage_limits=limits)
    except UsageLimitExceeded:
        raise AIUnavailable("This request hit its safety limit before finishing, so it was stopped. Try again with less.")
    except (APITimeoutError, APIConnectionError):
        log.warning("feature=%s timed out or lost the connection after %.0fs", feature, time.monotonic() - started)
        raise AIUnavailable("The AI took too long to answer. Please try again.")
    usage = result.usage
    log.info("feature=%s took %.1fs (%s in, %s out tokens)", feature, time.monotonic() - started, usage.input_tokens or 0, usage.output_tokens or 0)  # timing only: never prompts or answers
    cost = estimate_cost(usage)
    store.record_usage(feature, usage.input_tokens or 0, usage.output_tokens or 0, getattr(usage, "web_searches", 0) or 0, cost)
    if cost > LIMITS.per_run_cap_usd:
        log.warning("feature=%s estimated cost %.3f exceeded the per-run cap", feature, cost)
    return result
