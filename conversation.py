"""OpenAI-backed conversational voice agent, following the marathon assistant pattern."""

from __future__ import annotations

import os
from pathlib import Path

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_openai.middleware import OpenAIModerationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

ROOT = Path(__file__).resolve().parent
INSTRUCTIONS_FILE = ROOT / "config" / "voice_agent_instructions.md"

def create_voice_agent():
    """Create the in-memory conversational agent for the browser app."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing; add it to the project .env file")

    model = init_chat_model(os.getenv("AGENT_MODEL", "openai:gpt-4.1-mini"))
    system_prompt = INSTRUCTIONS_FILE.read_text(encoding="utf-8")
    middleware = [
        OpenAIModerationMiddleware(
            model="omni-moderation-latest",
            check_input=True,
            check_output=True,
            exit_behavior="end",
        )
    ]
    return create_agent(
        model=model,
        name="andrew_voice_agent",
        tools=[],
        system_prompt=system_prompt,
        checkpointer=InMemorySaver(),
        middleware=middleware,
    )
