"""Conversational voice agent using OpenAI or hosted Qwen."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from langchain_openai.middleware import OpenAIModerationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

ROOT = Path(__file__).resolve().parent
INSTRUCTIONS_FILE = ROOT / "config" / "voice_agent_instructions.md"
_agents = {}
_agents_lock = threading.Lock()


def get_voice_agent(provider=None):
    """Load each provider once, on first use; keep their histories separate."""
    provider = resolve_provider(provider)
    with _agents_lock:
        if provider not in _agents:
            _agents[provider] = create_voice_agent(provider)
        return _agents[provider]


def resolve_provider(provider=None):
    if provider is None:
        provider = os.getenv("TEXT_MODEL_PROVIDER", "openai")
    if not isinstance(provider, str) or provider.strip().lower() not in {"openai", "qwen"}:
        raise ValueError("provider must be 'openai' or 'qwen'")
    return provider.strip().lower()

def create_voice_agent(provider=None):
    """Create the in-memory conversational agent for the browser app."""
    provider = resolve_provider(provider)
    if provider == "qwen":
        settings = {name: os.getenv(name, "").strip() for name in
                    ("QWEN_BASE_URL", "QWEN_API_KEY", "QWEN_MODEL")}
        missing = [name for name, value in settings.items() if not value]
        if missing:
            raise ValueError(f"Hosted Qwen requires: {', '.join(missing)}")
        model = ChatOpenAI(
            base_url=settings["QWEN_BASE_URL"].rstrip("/"),
            api_key=settings["QWEN_API_KEY"],
            model=settings["QWEN_MODEL"],
            max_tokens=int(os.getenv("QWEN_MAX_NEW_TOKENS", "256")),
            timeout=float(os.getenv("QWEN_TIMEOUT_SECONDS", "300")),
            max_retries=0,
            use_responses_api=False,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    elif provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is missing; add it to the project .env file")
        model = init_chat_model(os.getenv("AGENT_MODEL", "openai:gpt-4.1-mini"))
    else:
        raise ValueError("TEXT_MODEL_PROVIDER must be 'openai' or 'qwen'")
    system_prompt = INSTRUCTIONS_FILE.read_text(encoding="utf-8")
    middleware = [
        OpenAIModerationMiddleware(
            model="omni-moderation-latest",
            check_input=True,
            check_output=True,
            exit_behavior="end",
        )
    ] if provider == "openai" else []
    return create_agent(
        model=model,
        name="andrew_voice_agent",
        tools=[],
        system_prompt=system_prompt,
        checkpointer=InMemorySaver(),
        middleware=middleware,
    )
